"""Cliente de leitura normativa por IA sem web search e com validação literal."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

from src.legislation.url_guard import validar_url_oficial

SCHEMA_SAIDA_REGRA_FISCAL: dict[str, Any] = {
    "type": "object",
    "required": ["ncm_formatado", "regras"],
    "properties": {
        "ncm_formatado": {"type": "string"},
        "cest_formatado": {"type": "string"},
        "regras": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["dispositivo_legal", "trecho_citado"],
                "properties": {
                    "dispositivo_legal": {"type": "string"},
                    "trecho_citado": {"type": "string"},
                    "aliquota_icms": {"type": ["number", "null"]},
                    "reducao_base_icms": {"type": ["number", "null"]},
                    "margem_st": {"type": ["number", "null"]},
                    "codigo_beneficio_fiscal": {"type": ["string", "null"]},
                    "confianca_ia": {"type": "string", "enum": ["ALTA", "MEDIA", "BAIXA"]},
                },
            },
        },
    },
}


def formatar_ncm(ncm: str) -> str:
    """Formata NCM de 8 dígitos para o padrão com pontos (ex: '85171300' -> '8517.13.00')."""
    digitos = re.sub(r"\D", "", ncm or "")
    if len(digitos) != 8:
        raise ValueError(f"NCM inválido (esperados 8 dígitos): {ncm!r}")
    return f"{digitos[:4]}.{digitos[4:6]}.{digitos[6:8]}"


def formatar_cest(cest: str) -> str:
    """Formata CEST de 7 dígitos para o padrão com pontos (ex: '2105301' -> '21.053.01')."""
    if not cest:
        return ""
    digitos = re.sub(r"\D", "", cest)
    if len(digitos) != 7:
        raise ValueError(f"CEST inválido (esperados 7 dígitos): {cest!r}")
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:7]}"


def normalizar_texto_literal(texto: str) -> str:
    """Normaliza texto para conferência literal: NFKD, sem acentos, sem pontuação, lowercase."""
    if not texto:
        return ""
    sem_acentos = "".join(
        ch for ch in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(ch)
    )
    sem_pontuacao = re.sub(r"[^\w\s]", " ", sem_acentos.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", sem_pontuacao).strip()


def citacao_existe_literalmente(trecho_citado: str, texto_oficial: str) -> bool:
    """Retorna True somente se o trecho citado existir literalmente no texto oficial normalizado."""
    trecho_norm = normalizar_texto_literal(trecho_citado)
    oficial_norm = normalizar_texto_literal(texto_oficial)
    if not trecho_norm or not oficial_norm:
        return False
    return trecho_norm in oficial_norm


@dataclass(frozen=True)
class ConfiguracaoLLM:
    """Configuração de leitura por IA que proíbe web_search por construção."""

    modelo: str = "gemini-2.5-flash"
    web_search: bool = False
    temperatura: float = 0.0

    def __post_init__(self) -> None:
        if self.web_search:
            raise ValueError("web_search é estritamente proibido na leitura de legislação oficial.")


TransportLLM = Callable[[str, dict[str, Any], bool], str | dict[str, Any]]


class ClienteLeituraIA:
    """Cliente de extração normativa estruturada sobre texto oficial já recortado."""

    def __init__(
        self,
        transport: TransportLLM,
        config: ConfiguracaoLLM | None = None,
    ) -> None:
        self.config = config or ConfiguracaoLLM(web_search=False)
        if self.config.web_search:
            raise ValueError("web_search deve estar desabilitado.")
        self._transport = transport

    def analisar_norma(
        self,
        *,
        texto_recortado: str,
        ncm: str,
        cest: str = "",
        url_oficial: str = "",
    ) -> dict[str, Any]:
        """Envia texto oficial recortado + NCM/CEST formatados e filtra citações alucinadas."""
        if url_oficial:
            validar_url_oficial(url_oficial)
        if not texto_recortado.strip():
            raise ValueError("texto_recortado não pode ser vazio.")

        ncm_fmt = formatar_ncm(ncm)
        cest_fmt = formatar_cest(cest) if cest else ""

        prompt = (
            f"Analise exclusivamente o texto legal oficial abaixo para o NCM {ncm_fmt}"
            + (f" e CEST {cest_fmt}" if cest_fmt else "")
            + ".\nExtraia as regras aplicáveis em JSON e copie literalmente `trecho_citado`.\n\n"
            f"TEXTO OFICIAL:\n{texto_recortado}"
        )

        bruto = self._transport(prompt, SCHEMA_SAIDA_REGRA_FISCAL, False)
        dados = json.loads(bruto) if isinstance(bruto, str) else dict(bruto)

        regras_validas: list[dict[str, Any]] = []
        regras_descartadas: list[dict[str, Any]] = []

        for regra in dados.get("regras", []):
            trecho = str(regra.get("trecho_citado") or "")
            if citacao_existe_literalmente(trecho, texto_recortado):
                regras_validas.append(regra)
            else:
                regras_descartadas.append(regra)

        return {
            "ncm_formatado": dados.get("ncm_formatado", ncm_fmt),
            "cest_formatado": dados.get("cest_formatado", cest_fmt),
            "regras_validas": regras_validas,
            "citacoes_descartadas": len(regras_descartadas),
            "regras_descartadas": regras_descartadas,
        }
