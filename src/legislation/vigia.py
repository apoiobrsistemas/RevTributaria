"""Rotina CLI do Vigia Noturno (Zero IA) para monitoramento de normas oficiais."""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from src.database import get_connection
from src.legislation.ai_reader import citacao_existe_literalmente
from src.legislation.extractor import (
    RecorteMarcadorNaoEncontradoError,
    hash_conteudo_limpo,
    recortar_texto_vigente,
)
from src.legislation.parsers import baixar_url_oficial, extrair_texto_por_tipo
from src.legislation.url_guard import DominioNaoOficialError, validar_url_oficial


@dataclass(frozen=True)
class AlertaVigia:
    """Alerta emitido pelo Vigia Noturno sem uso de IA."""

    codigo: str
    fonte_id: int
    uf: str
    grupo: str
    tipo: str  # MUDANCA_CONTEUDO | CITACAO_QUEBRADA | URL_INDISPONIVEL | MARCADOR_AUSENTE | URL_INVALIDA
    mensagem: str


def gerar_codigo_alerta(uf: str, grupo: str, data_ref: date | None = None) -> str:
    """Gera código padronizado VIGIA-AAAAMMDD-UF-GRUPO."""
    ref = data_ref or date.today()
    uf_clean = (uf or "BR").upper()
    grupo_clean = (grupo or "GERAL").upper()
    return f"VIGIA-{ref.strftime('%Y%m%d')}-{uf_clean}-{grupo_clean}"


def _dias_desde(iso_timestamp: str | None, data_ref: date) -> int:
    if not iso_timestamp:
        return 0
    try:
        dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00")).date()
        return max(0, (data_ref - dt).days)
    except ValueError:
        return 0


FetcherFn = Callable[[str, bool], tuple[bytes, str]]


def verificar_fontes(
    conn: sqlite3.Connection,
    *,
    fetcher: FetcherFn | None = None,
    data_ref: date | None = None,
    marcadores: dict[int, tuple[str, str | None]] | None = None,
) -> list[AlertaVigia]:
    """Executa a verificação noturna (Zero IA) sobre todas as fontes ativas."""
    ref = data_ref or date.today()
    agora_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    alertas: list[AlertaVigia] = []
    marcadores = marcadores or {}

    fontes = conn.execute(
        "SELECT * FROM fontes_legais WHERE status_fonte IN ('ATIVA', 'FALHA')"
    ).fetchall()

    for fonte in fontes:
        fonte_id = int(fonte["id"])
        uf = str(fonte["uf"])
        grupo = str(fonte["tipo_norma"]).upper().replace(" ", "_")
        url = str(fonte["url_oficial"])
        usar_playwright = "rj.gov.br" in url.lower()

        try:
            validar_url_oficial(url)
        except DominioNaoOficialError as exc:
            alertas.append(
                AlertaVigia(
                    codigo=gerar_codigo_alerta(uf, grupo, ref),
                    fonte_id=fonte_id,
                    uf=uf,
                    grupo=grupo,
                    tipo="URL_INVALIDA",
                    mensagem=str(exc),
                )
            )
            continue

        try:
            if fetcher is not None:
                raw_bytes, content_type = fetcher(url, usar_playwright)
            else:
                raw_bytes, content_type = baixar_url_oficial(url, usar_playwright=usar_playwright)

            texto = extrair_texto_por_tipo(raw_bytes, content_type, url=url)
            if fonte_id in marcadores:
                m_ini, m_fim = marcadores[fonte_id]
                texto = recortar_texto_vigente(texto, m_ini, m_fim)
        except RecorteMarcadorNaoEncontradoError as exc:
            alertas.append(
                AlertaVigia(
                    codigo=gerar_codigo_alerta(uf, grupo, ref),
                    fonte_id=fonte_id,
                    uf=uf,
                    grupo=grupo,
                    tipo="MARCADOR_AUSENTE",
                    mensagem=str(exc),
                )
            )
            continue
        except Exception as exc:
            dias_sem_acesso = _dias_desde(fonte["ultima_verificacao"], ref)
            if dias_sem_acesso >= 2:
                conn.execute(
                    "UPDATE fontes_legais SET status_fonte = 'FALHA' WHERE id = ?",
                    (fonte_id,),
                )
                alertas.append(
                    AlertaVigia(
                        codigo=gerar_codigo_alerta(uf, grupo, ref),
                        fonte_id=fonte_id,
                        uf=uf,
                        grupo=grupo,
                        tipo="URL_INDISPONIVEL",
                        mensagem=f"Fonte indisponível há {dias_sem_acesso} dias: {exc}",
                    )
                )
            continue

        novo_hash = hash_conteudo_limpo(texto)
        hash_anterior = fonte["hash_conteudo"]
        if hash_anterior and hash_anterior != novo_hash:
            alertas.append(
                AlertaVigia(
                    codigo=gerar_codigo_alerta(uf, grupo, ref),
                    fonte_id=fonte_id,
                    uf=uf,
                    grupo=grupo,
                    tipo="MUDANCA_CONTEUDO",
                    mensagem=f"Alteração detectada no corpo da norma {fonte['numero_norma']}.",
                )
            )

        # Verifica se citações aceitas continuam presentes literalmente no texto oficial
        for tabela in ("regras_estaduais_icms", "regras_federais"):
            regras = conn.execute(
                f"""
                SELECT id, trecho_citado, dispositivo_legal
                FROM {tabela}
                WHERE fonte_legal_id = ?
                  AND status_registro = 'ATIVA'
                  AND status_validacao = 'ACEITO'
                  AND trecho_citado IS NOT NULL
                  AND trecho_citado != ''
                """,
                (fonte_id,),
            ).fetchall()
            for r in regras:
                if not citacao_existe_literalmente(str(r["trecho_citado"]), texto):
                    alertas.append(
                        AlertaVigia(
                            codigo=gerar_codigo_alerta(uf, grupo, ref),
                            fonte_id=fonte_id,
                            uf=uf,
                            grupo=grupo,
                            tipo="CITACAO_QUEBRADA",
                            mensagem=(
                                f"Citação de {tabela}#{r['id']} ({r['dispositivo_legal']}) "
                                "não encontrada literalmente na norma."
                            ),
                        )
                    )

        conn.execute(
            """
            UPDATE fontes_legais
            SET hash_conteudo = ?, ultima_verificacao = ?, status_fonte = 'ATIVA'
            WHERE id = ?
            """,
            (novo_hash, agora_iso, fonte_id),
        )

    for alerta in alertas:
        conn.execute(
            """
            INSERT OR IGNORE INTO vigia_alertas (
                codigo, fonte_id, uf, grupo, tipo, mensagem, status_alerta
            ) VALUES (?, ?, ?, ?, ?, ?, 'ABERTO')
            """,
            (
                alerta.codigo,
                alerta.fonte_id,
                alerta.uf,
                alerta.grupo,
                alerta.tipo,
                alerta.mensagem,
            ),
        )

    conn.commit()
    return alertas


def main(argv: list[str] | None = None) -> int:
    """Entrypoint CLI do Vigia Noturno (zero IA)."""
    parser = argparse.ArgumentParser(description="Vigia Noturno de Legislação Oficial (Zero IA)")
    parser.add_argument("--db", default="revtributaria.db", help="Caminho para o banco SQLite")
    args = parser.parse_args(argv)

    conn = get_connection(args.db)
    try:
        alertas = verificar_fontes(conn)
        for a in alertas:
            print(f"[{a.codigo}] ({a.tipo}) {a.mensagem}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
