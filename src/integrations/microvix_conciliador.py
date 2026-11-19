"""Conciliador de NF-e de Entrada com ERP Linx Microvix e Exportador Executivo Seguro (.xlsx)."""

from __future__ import annotations

import io
import re
from typing import Any

import openpyxl

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitizar_celula_planilha(valor: Any) -> Any:
    """Previne CSV/Excel Formula Injection neutralizando células iniciadas por =, +, -, @, TAB ou CR."""
    if isinstance(valor, str) and valor and valor[0] in _FORMULA_PREFIXES:
        return "'" + valor
    return valor


def _so_digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _sugerir_cst_entrada(cst_xml: str, tem_st: bool) -> str:
    c = str(cst_xml or "00").strip()
    if tem_st or c in {"10", "30", "60", "70", "201", "202", "203", "500"}:
        return "60"
    if c in {"20"}:
        return "20"
    if c in {"40", "41", "50", "103", "300", "400"}:
        return c if len(c) == 2 else "40"
    return "00"


def conciliar_lote_com_microvix(
    conn: Any,
    itens_auditados: list[dict[str, Any]],
    *,
    erp_registros: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Cruza itens auditados do XML contra cadastro Linx Microvix (SQLite ou CSV/JSON)."""
    mapa_erp: dict[str, dict[str, Any]] = {}

    if erp_registros:
        for r in erp_registros:
            cod = str(r.get("cod_produto") or r.get("cProd") or "").strip()
            if cod:
                mapa_erp[cod] = dict(r)
    elif conn is not None:
        rows = conn.execute(
            "SELECT cod_produto, nome_produto, ncm, cest, origem_mercadoria FROM linx_produtos"
        ).fetchall()
        for r in rows:
            mapa_erp[str(r["cod_produto"])] = dict(r)

    divergencias: list[dict[str, Any]] = []
    for it in itens_auditados:
        c_prod = str(it.get("cProd") or "").strip()
        ncm_xml = _so_digitos(it.get("NCM"))
        cest_xml = _so_digitos(it.get("CEST"))
        cfop_sugerido = str(it.get("CFOP Entrada Sugerido") or "")
        cst_xml = str(it.get("CST XML") or "00")
        tem_st = float(it.get("Antecipação/Compl. ST (R$)") or 0) > 0 or cst_xml in {"10", "30", "60", "70", "201", "202", "203", "500"}
        cst_entrada_sugerido = _sugerir_cst_entrada(cst_xml, tem_st)

        reg_erp = mapa_erp.get(c_prod)
        if reg_erp is None:
            divergencias.append(
                {
                    "NF-e": it.get("NF-e", ""),
                    "Item": it.get("Item", ""),
                    "cProd": c_prod,
                    "Descrição XML": it.get("Descrição", ""),
                    "Status Cadastro ERP": "NAO_LOCALIZADO",
                    "NCM XML": ncm_xml,
                    "NCM ERP": "-",
                    "CEST XML": cest_xml,
                    "CEST ERP": "-",
                    "CFOP Entrada Sugerido": cfop_sugerido,
                    "CST Entrada Sugerido": cst_entrada_sugerido,
                    "Divergências": "Produto não localizado no cadastro Linx Microvix — cadastrar antes da escrituração SPED.",
                }
            )
            continue

        ncm_erp = _so_digitos(reg_erp.get("ncm"))
        cest_erp = _so_digitos(reg_erp.get("cest"))
        cfop_erp = _so_digitos(reg_erp.get("cfop_entrada") or reg_erp.get("cfop"))
        cst_erp = str(reg_erp.get("cst_entrada") or reg_erp.get("cst_icms") or "").strip()

        problemas: list[str] = []
        if ncm_erp and ncm_xml and ncm_erp != ncm_xml:
            problemas.append(f"NCM divergente (XML={ncm_xml} vs ERP={ncm_erp})")
        if cest_xml and cest_erp != cest_xml:
            problemas.append(f"CEST divergente (XML={cest_xml} vs ERP={cest_erp or 'vazio'})")
        if cfop_erp and cfop_sugerido and cfop_erp != cfop_sugerido:
            problemas.append(f"CFOP Entrada divergente (ERP={cfop_erp} vs Sugerido={cfop_sugerido})")
        if cst_erp and cst_erp != cst_entrada_sugerido:
            problemas.append(f"CST Entrada divergente (ERP={cst_erp} vs Sugerido={cst_entrada_sugerido})")

        divergencias.append(
            {
                "NF-e": it.get("NF-e", ""),
                "Item": it.get("Item", ""),
                "cProd": c_prod,
                "Descrição XML": it.get("Descrição", ""),
                "Status Cadastro ERP": "DIVERGENTE" if problemas else "CONCILIADO",
                "NCM XML": ncm_xml,
                "NCM ERP": ncm_erp,
                "CEST XML": cest_xml,
                "CEST ERP": cest_erp,
                "CFOP Entrada Sugerido": cfop_sugerido,
                "CST Entrada Sugerido": cst_entrada_sugerido,
                "Divergências": " | ".join(problemas) if problemas else "Cadastro conciliado",
            }
        )

    return divergencias


def _escrever_aba(ws: Any, rows: list[dict[str, Any]]) -> None:
    if not rows:
        ws.append(["Sem registros para esta visão."])
        return
    headers = list(rows[0].keys())
    ws.append([sanitizar_celula_planilha(h) for h in headers])
    for r in rows:
        ws.append([sanitizar_celula_planilha(r.get(h, "")) for h in headers])


def exportar_relatorio_auditoria_lote_xlsx(
    resultado_lote: dict[str, Any],
    divergencias_erp: list[dict[str, Any]],
) -> bytes:
    """Gera Excel executivo (4 abas) com sanitização contra Formula Injection."""
    wb = openpyxl.Workbook()
    ws_guias = wb.active
    ws_guias.title = "Resumo Guias"
    _escrever_aba(ws_guias, list(resultado_lote.get("guias_por_nota") or []))

    ws_itens = wb.create_sheet("Itens Auditados")
    _escrever_aba(ws_itens, list(resultado_lote.get("itens_auditados") or []))

    ws_glosas = wb.create_sheet("Glosa de Créditos")
    _escrever_aba(ws_glosas, list(resultado_lote.get("glosas_credito") or []))

    ws_erp = wb.create_sheet("Divergências Cadastro ERP")
    _escrever_aba(ws_erp, divergencias_erp)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
