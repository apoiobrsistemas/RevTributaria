"""Aba 4: Comparativo Matriz ERP (Frente B)."""

from __future__ import annotations

import os
from datetime import date
from typing import Callable

import streamlit as st

from src.app.service import RevTributariaService


def render_aba_comparativo_erp(
    *,
    db_path: str,
    limpar_cache: Callable[[], None],
) -> None:
    """Renderiza a aba de comparação da matriz ERP e flags internas."""
    st.subheader("Comparativo Matriz ERP (Frente B)")

    modo = st.radio(
        "Origem da Matriz para Auditoria",
        ["Upload Planilha ERP (.xlsx / .csv)", "Matriz Sincronizada Linx Microvix"],
        horizontal=True,
    )

    if modo == "Upload Planilha ERP (.xlsx / .csv)":
        arquivo = st.file_uploader(
            "Suba a planilha da matriz tributária do ERP (.xlsx ou .csv)",
            type=["xlsx", "csv"],
        )
        lote = st.text_input("Identificador do Lote", value=f"LOTE-{date.today().isoformat()}")
        if arquivo and st.button("🔍 Auditar Flags do ERP"):
            ext = os.path.splitext(arquivo.name)[1].lower() or ".xlsx"
            srv = RevTributariaService(db_path)
            try:
                res = srv.executar_auditoria_erp(arquivo.read(), lote_importacao=lote, extensao=ext)
                st.success(
                    f"Lote `{res['lote_importacao']}`: {res['linhas_importadas']} linhas importadas, "
                    f"{res['total_divergencias']} divergências."
                )
                limpar_cache()
            finally:
                srv.close()
    else:
        srv_l = RevTributariaService(db_path)
        try:
            linx_cfgs = srv_l.listar_linx_config_tributarias()
        finally:
            srv_l.close()
        if linx_cfgs:
            st.dataframe(linx_cfgs, use_container_width=True)
        else:
            st.info("Nenhuma configuração tributária sincronizada do Linx Microvix ainda.")

    srv_d = RevTributariaService(db_path)
    try:
        divs_erp = srv_d.listar_divergencias(tipo_auditoria="CONFIG_ERP")
    finally:
        srv_d.close()

    if divs_erp:
        st.markdown("**Divergências nas Flags Internas do ERP**")
        st.dataframe(divs_erp, use_container_width=True)
    else:
        st.info("Nenhuma divergência de configuração ERP registrada ainda.")
