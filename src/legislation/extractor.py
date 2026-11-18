"""Extrator de trechos vigentes por marcadores com falha segura."""

from __future__ import annotations

import hashlib
import re


class RecorteMarcadorNaoEncontradoError(RuntimeError):
    """Lançada quando o marcador de início ou fim do recorte vigente não é encontrado."""


def recortar_texto_vigente(
    texto: str,
    marcador_inicio: str,
    marcador_fim: str | None = None,
) -> str:
    """Recorta o trecho vigente entre marcador_inicio e marcador_fim.

    Falha segura: aborta com RecorteMarcadorNaoEncontradoError se o marcador
    inicial (ou o marcador final, quando informado) não for encontrado,
    evitando leitura de dispositivos revogados ou da página inteira.
    """
    if not texto or not marcador_inicio:
        raise RecorteMarcadorNaoEncontradoError(
            "Texto vazio ou marcador de início não informado; recorte abortado."
        )

    idx_inicio = texto.find(marcador_inicio)
    if idx_inicio == -1:
        raise RecorteMarcadorNaoEncontradoError(
            f"Marcador de início não encontrado no texto oficial: {marcador_inicio!r}"
        )

    if marcador_fim:
        idx_busca_fim = idx_inicio + len(marcador_inicio)
        idx_fim = texto.find(marcador_fim, idx_busca_fim)
        if idx_fim == -1:
            raise RecorteMarcadorNaoEncontradoError(
                f"Marcador de fim não encontrado após o início: {marcador_fim!r}"
            )
        return texto[idx_inicio:idx_fim].strip()

    return texto[idx_inicio:].strip()


def hash_conteudo_limpo(texto: str) -> str:
    """Calcula SHA-256 do corpo limpo normalizando múltiplos espaços."""
    normalizado = re.sub(r"\s+", " ", texto).strip()
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()
