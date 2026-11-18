"""Consulta e cache local de regime tributário por CNPJ (XML CRT + Base RFB .gov.br)."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from src.legislation.url_guard import validar_url_oficial

URL_RFB_DADOS_ABERTOS_CNPJ = "https://dadosabertos.rfb.gov.br/CNPJ/"

_MAPA_CRT = {
    "1": "Simples Nacional",
    "2": "Simples Nacional — Excesso de Sublimite",
    "3": "Regime Normal (Lucro Real / Presumido)",
    "4": "MEI",
}


def limpar_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", str(cnpj or ""))


def consultar_regime_cnpj(
    conn: sqlite3.Connection,
    cnpj: str,
    *,
    razao_social: str = "",
    uf: str = "",
    crt_xml: str = "",
    regime_manual: str = "",
) -> dict[str, Any]:
    """Resolve o regime tributário do CNPJ emitente usando cache local, CRT do XML e fonte .gov.br."""
    validar_url_oficial(URL_RFB_DADOS_ABERTOS_CNPJ)
    cnpj_limpo = limpar_cnpj(cnpj)
    row = conn.execute("SELECT * FROM cnpj_regimes WHERE cnpj = ?", (cnpj_limpo,)).fetchone()

    if regime_manual.strip():
        regime_final = regime_manual.strip()
        fonte = "CONFIRMACAO_AUDITOR"
    elif row is not None and not crt_xml:
        return dict(row)
    elif row is not None and row["fonte_consulta"] == "CONFIRMACAO_AUDITOR":
        return dict(row)
    else:
        regime_final = _MAPA_CRT.get(str(crt_xml).strip(), "Lucro Real")
        fonte = f"XML_CRT_{crt_xml or '3'}"

    if len(cnpj_limpo) == 14:
        with conn:
            conn.execute(
                """
                INSERT INTO cnpj_regimes (cnpj, razao_social, uf, crt, regime_apuracao, fonte_consulta, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(cnpj) DO UPDATE SET
                    razao_social = COALESCE(NULLIF(excluded.razao_social, ''), cnpj_regimes.razao_social),
                    uf = COALESCE(NULLIF(excluded.uf, ''), cnpj_regimes.uf),
                    crt = COALESCE(NULLIF(excluded.crt, ''), cnpj_regimes.crt),
                    regime_apuracao = excluded.regime_apuracao,
                    fonte_consulta = excluded.fonte_consulta,
                    atualizado_em = datetime('now')
                """,
                (cnpj_limpo, razao_social, uf.upper(), str(crt_xml or ""), regime_final, fonte),
            )
        saved = conn.execute("SELECT * FROM cnpj_regimes WHERE cnpj = ?", (cnpj_limpo,)).fetchone()
        if saved is not None:
            return dict(saved)

    return {
        "cnpj": cnpj_limpo,
        "razao_social": razao_social,
        "uf": uf.upper(),
        "crt": str(crt_xml or ""),
        "regime_apuracao": regime_final,
        "fonte_consulta": fonte,
    }
