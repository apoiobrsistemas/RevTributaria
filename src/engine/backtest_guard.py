"""Governança Determinística: Trava de Vigência (Anterioridade/Noventena), Backtest XML e Selo de Confiabilidade."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Mapping


def classificar_confiabilidade_deterministica(regra: Mapping[str, Any] | None) -> str:
    """Classifica o selo de confiabilidade da regra impedindo confusão entre normas auditadas e pendentes."""
    if not regra:
        return "A Conferir"
    status = str(regra.get("status_validacao") or regra.get("status") or "").strip().upper()
    if status != "ACEITO":
        return "A Conferir"

    origem_ext = str(regra.get("origem_extracao") or "").strip().upper()
    disp = str(regra.get("dispositivo_legal") or "").upper()
    trecho = str(regra.get("trecho_literal_lei") or "").strip()

    if origem_ext in {"TABELA_OFICIAL", "XLSX_OFICIAL", "JSON_OFICIAL", "CONFAZ_CSV"} or any(
        k in disp for k in ("SISCOMEX", "TIPI", "SVRS", "CLASSIF", "CONVÊNIO", "CONVENIO", "CAMEX")
    ):
        return "Validado via Tabela Oficial .xlsx/.json"
    if trecho:
        return "Texto Legal Validado Literalmente + Aceite Fiscal"
    return "Validado via Tabela Oficial .xlsx/.json"


def verificar_vigencia_futura_agendada(
    conn: sqlite3.Connection,
    *,
    ncm: str,
    uf_origem: str,
    uf_destino: str,
    data_operacao: str | None = None,
) -> dict[str, Any]:
    """Detecta normas publicadas com vigência futura (Anterioridade / Noventena) após data_operacao."""
    ref = data_operacao or date.today().isoformat()
    rows = conn.execute(
        """
        SELECT id, ncm, uf_origem, uf_destino, vigencia_inicio, aliquota_icms,
               margem_st, aliquota_icms_st, dispositivo_legal, status_validacao
        FROM regras_estaduais_icms
        WHERE ncm = ? AND uf_origem = ? AND uf_destino = ? AND vigencia_inicio > ?
          AND status_registro = 'ATIVA'
        ORDER BY vigencia_inicio ASC
        LIMIT 5
        """,
        (ncm.strip(), uf_origem.upper()[:2], uf_destino.upper()[:2], ref),
    ).fetchall()
    futuras = [dict(r) for r in rows]
    alerta = None
    if futuras:
        prox = futuras[0]
        alerta = (
            f"Anterioridade/Noventena: existe norma publicada para NCM {ncm} ({uf_origem}->{uf_destino}) "
            f"com vigência futura agendada para {prox['vigencia_inicio']} "
            f"(ICMS {prox['aliquota_icms']}%, {prox['dispositivo_legal'] or 'RICMS'})."
        )
    return {
        "possui_vigencia_futura": bool(futuras),
        "normas_futuras": futuras,
        "alerta": alerta,
    }


def validar_regra_contra_historico_xml(
    conn: sqlite3.Connection,
    ncm: str,
    uf: str,
    *,
    regra_candidata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Confronta regra candidata (ex.: A_CONFERIR) contra XMLs reais autorizados em nfe_itens."""
    uf_u = uf.strip().upper()[:2]
    ncm_u = ncm.strip()
    rows = conn.execute(
        """
        SELECT i.chave_acesso, i.numero_item, i.cfop, i.cst_icms, i.aliq_icms, i.valor_st, d.uf_emitente, d.uf_destinatario
        FROM nfe_itens i
        JOIN vw_nfe_status d ON d.chave_acesso = i.chave_acesso
        WHERE i.ncm = ? AND d.status_sefaz = 'AUTORIZADA' AND (d.uf_emitente = ? OR d.uf_destinatario = ?)
        ORDER BY i.id DESC
        LIMIT 50
        """,
        (ncm_u, uf_u, uf_u),
    ).fetchall()

    if not rows:
        return {
            "ncm": ncm_u,
            "uf": uf_u,
            "status_backtest": "SEM_HISTORICO_XML",
            "total_xmls_analisados": 0,
            "divergencias": [],
            "mensagem": f"Sem XMLs autorizados no histórico para NCM {ncm_u} na UF {uf_u}.",
        }

    if regra_candidata is None:
        reg_row = conn.execute(
            """
            SELECT * FROM regras_estaduais_icms
            WHERE ncm = ? AND (uf_origem = ? OR uf_destino = ?) AND status_registro = 'ATIVA'
            ORDER BY id DESC LIMIT 1
            """,
            (ncm_u, uf_u, uf_u),
        ).fetchone()
        regra_candidata = dict(reg_row) if reg_row else {}

    aliq_reg = float(regra_candidata.get("aliquota_icms") or 0.0)
    tem_st_reg = bool(
        regra_candidata.get("tem_st")
        or float(regra_candidata.get("margem_st") or 0.0) > 0.0
        or float(regra_candidata.get("aliquota_icms_st") or 0.0) > 0.0
    )
    divergencias: list[dict[str, Any]] = []

    for r in rows:
        aliq_xml = float(r["aliq_icms"] or 0.0)
        teve_st_xml = float(r["valor_st"] or 0.0) > 0.0 or str(r["cst_icms"] or "").endswith(("10", "30", "60", "70"))
        if abs(aliq_xml - aliq_reg) > 0.5 and aliq_xml > 0:
            divergencias.append(
                {
                    "chave_acesso": r["chave_acesso"],
                    "item": r["numero_item"],
                    "campo": "aliq_icms",
                    "xml_historico": aliq_xml,
                    "regra_candidata": aliq_reg,
                }
            )
        if tem_st_reg != teve_st_xml:
            divergencias.append(
                {
                    "chave_acesso": r["chave_acesso"],
                    "item": r["numero_item"],
                    "campo": "tem_st",
                    "xml_historico": teve_st_xml,
                    "regra_candidata": tem_st_reg,
                }
            )

    status_bt = "DIVERGE_HISTORICO_SEFAZ" if divergencias else "CONFORME_HISTORICO"
    return {
        "ncm": ncm_u,
        "uf": uf_u,
        "status_backtest": status_bt,
        "total_xmls_analisados": len(rows),
        "divergencias": divergencias,
        "mensagem": (
            f"Backtest em {len(rows)} item(ns) autorizado(s): "
            + ("DIVERGE do padrão histórico SEFAZ." if divergencias else "100% conforme histórico SEFAZ.")
        ),
    }
