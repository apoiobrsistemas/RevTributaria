"""Aba de Consulta Completa por NCM e Operação (Compra, Venda, Devoluções)."""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.app.service import RevTributariaService


def render_aba_matriz_operacoes(*, db_path: str) -> None:
    """Renderiza a matriz linha a linha por NCM, UF Origem e UF Destino."""
    st.subheader("Consulta de Matriz por Operação (Linha a Linha)")
    st.caption(
        "Informe NCM, UF Origem e UF Destino para visualizar CFOPs e impostos de "
        "Compra, Venda, Devolução de Compra e Devolução de Venda (Nacional/Importado, "
        "Contribuinte/Não Contribuinte, ST/Tributado Integralmente)."
    )

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1.5])
    ncm = c1.text_input("NCM (8 dígitos)", value="85171300", key="op_ncm")
    uf_orig = c2.text_input("UF Origem", value="SP", max_chars=2, key="op_uf_orig")
    uf_dest = c3.text_input("UF Destino", value="RJ", max_chars=2, key="op_uf_dest")
    data_ref = c4.date_input("Data de Vigência", value=date.today(), key="op_data")

    incluir_trib = st.checkbox(
        "Incluir variação 'Tributado Integralmente' quando o NCM possuir ST",
        value=True,
        key="op_incluir_trib",
    )

    srv = RevTributariaService(db_path)
    try:
        linhas = srv.consultar_matriz_completa_ncm(
            ncm=ncm,
            uf_origem=uf_orig,
            uf_destino=uf_dest,
            data_referencia=data_ref.isoformat(),
            incluir_tributado_se_st=incluir_trib,
        )
        xlsx_bytes = srv.exportar_matriz_ncm_xlsx(linhas) if linhas else b""
    finally:
        srv.close()

    if not linhas:
        st.warning(
            f"Nenhuma regra encontrada para NCM `{ncm}` ({uf_orig.upper()} → {uf_dest.upper()}). "
            "Verifique os filtros ou cadastre/importe a regra na aba Matriz Legal."
        )
        return

    # Filtros de refino na exibição
    f1, f2, f3, f4 = st.columns(4)
    naturezas = ["Todas"] + sorted({l["Natureza de Operação"] for l in linhas})
    nat_sel = f1.selectbox("Natureza de Operação", naturezas, key="op_f_nat")
    orig_sel = f2.selectbox("Origem", ["Todas", "Nacional", "Importado"], key="op_f_orig")
    contrib_sel = f3.selectbox("Contribuinte", ["Todos", "Sim", "Não"], key="op_f_contrib")
    regimes = ["Todos"] + sorted({l["Regime ICMS"] for l in linhas})
    reg_sel = f4.selectbox("Regime ICMS", regimes, key="op_f_reg")

    filtradas = [
        l
        for l in linhas
        if (nat_sel == "Todas" or l["Natureza de Operação"] == nat_sel)
        and (orig_sel == "Todas" or l["Origem"] == orig_sel)
        and (contrib_sel == "Todos" or l["Contribuinte"] == contrib_sel)
        and (reg_sel == "Todos" or l["Regime ICMS"] == reg_sel)
    ]

    st.caption(f"Exibindo **{len(filtradas)}** linha(s) de variação para o NCM `{ncm}`.")
    st.dataframe(filtradas, use_container_width=True, hide_index=True)

    if xlsx_bytes:
        st.download_button(
            "⬇️ Exportar Matriz Gerada (.xlsx)",
            data=xlsx_bytes,
            file_name=f"matriz_{ncm}_{uf_orig.upper()}_{uf_dest.upper()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
