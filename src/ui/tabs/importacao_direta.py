"""Aba: Importação Direta do Exterior (DI / DUIMP / NF-e Entrada CFOP 3.xxx)."""

from __future__ import annotations

from decimal import Decimal
import streamlit as st

from src.app.service import RevTributariaService
from src.engine.import_engine import (
    ContextoImportacaoDireta,
    calcular_importacao_direta,
    gerar_matriz_importacao_lote,
    parsear_planilha_lote_importacao,
)
from src.integrations.import_docs_parser import exportar_espelho_importacao_xlsx
from src.integrations.linx_terceiro_exporter import exportar_tabela_crua_xlsx

UFS_BR = [
    "SP", "RJ", "MG", "PR", "RS", "SC", "ES", "BA", "PE", "CE",
    "GO", "DF", "MT", "MS", "PA", "AM", "MA", "PB", "RN", "AL",
    "SE", "PI", "TO", "RO", "AC", "AP", "RR",
]


def _d_str(v: float) -> Decimal:
    return Decimal(str(v))


def render_aba_importacao_direta(*, db_path: str, usuario: str = "auditor_fiscal") -> None:
    """Renderiza a aba completa de Importação Direta (DI / DUIMP / Entrada 3.xxx)."""
    st.markdown(
        '<div class="rev-section-card notranslate" translate="no">'
        '<div class="rev-section-header">'
        '<div class="rev-section-badge">🚢</div>'
        '<div>'
        '<div style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:1.25rem;font-weight:700;color:#0F172A;">'
        'Importação Direta do Exterior (DI / DUIMP / NF-e Entrada CFOP 3.xxx)'
        '</div>'
        '<div style="font-size:0.9rem;color:#475569;margin-top:4px;">'
        'Validação TEC/CAMEX (Origem 1 vs 6), cálculo por dentro do ICMS-Importação (LC 87/96), auditoria de DUIMP/DI/NF-e e reflexo na saída.'
        '</div>'
        '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    sub1, sub2, sub3 = st.tabs(
        [
            "🔎 Consulta & Validador por NCM (Individual e Lote)",
            "📄 Importador & Auditor (DUIMP / DI / PDF / XML NF-e 3.xxx)",
            "📚 Regras de Importação & TEC/CAMEX",
        ]
    )

    # ------------------------------------------------------------------
    # SUB-ABA 1: Consulta & Validador por NCM (Individual e Lote)
    # ------------------------------------------------------------------
    with sub1:
        modo_imp = st.radio(
            "Modo de Validação",
            ["Consulta Individual (1 NCM)", "Lote de Pré-Embarque (.xlsx / .csv)"],
            horizontal=True,
            key="imp_modo_sub1",
        )
        c1, c2, c3, c4 = st.columns([1.0, 1.0, 1.2, 1.2])
        uf_des = c1.selectbox("UF Desembaraço", UFS_BR, index=0, key="imp_uf_des")
        uf_dest = c2.selectbox("UF Destino (Importador)", UFS_BR, index=0, key="imp_uf_dest")
        uf_sai = c3.selectbox("UF Saída Subsequente (Simulação)", UFS_BR, index=1, key="imp_uf_sai")
        fin_pad = c4.selectbox(
            "Finalidade Padrão",
            ["COMERCIALIZACAO", "INDUSTRIALIZACAO", "ATIVO_IMOBILIZADO", "USO_CONSUMO", "OUTRAS"],
            key="imp_fin_pad",
        )

        srv_imp = RevTributariaService(db_path)
        try:
            regras_imp = {r["ncm"]: r for r in srv_imp.listar_regras_importacao_ncm()}
        finally:
            srv_imp.close()

        linhas_imp: list[dict] = []
        if modo_imp.startswith("Consulta Individual"):
            i1, i2, i3, i4 = st.columns([1.1, 1.1, 1.0, 1.0])
            ncm_in = i1.text_input("NCM (8 dígitos)", value="85171300", key="imp_ncm_in").strip()
            reg_db = regras_imp.get(ncm_in, {})
            cif_in = i2.number_input("Valor Aduaneiro / CIF (R$)", min_value=0.0, value=10000.0, step=500.0, key="imp_cif_in")
            sis_in = i3.number_input("Taxa Siscomex (R$)", min_value=0.0, value=154.23, step=10.0, key="imp_sis_in")
            afrmm_in = i4.number_input("AFRMM (R$)", min_value=0.0, value=0.0, step=50.0, key="imp_afrmm_in")

            a1, a2, a3, a4, a5 = st.columns(5)
            ii_in = a1.number_input("II (%)", min_value=0.0, value=float(reg_db.get("aliquota_ii", 16.0)), step=0.5, key="imp_ii_in")
            ipi_in = a2.number_input("IPI (%)", min_value=0.0, value=float(reg_db.get("aliquota_ipi", 15.0)), step=0.5, key="imp_ipi_in")
            pis_in = a3.number_input("PIS-Imp (%)", min_value=0.0, value=float(reg_db.get("aliquota_pis_imp", 2.10)), step=0.1, key="imp_pis_in")
            cof_in = a4.number_input("COFINS-Imp (%)", min_value=0.0, value=float(reg_db.get("aliquota_cofins_imp", 9.65)), step=0.1, key="imp_cof_in")
            adic_in = a5.number_input("Adic. COFINS 1%", min_value=0.0, value=float(reg_db.get("adicional_cofins_imp", 1.00)), step=0.5, key="imp_adic_in")

            f1, f2, f3 = st.columns([1.2, 1.0, 1.0])
            sem_sim = f1.checkbox(
                "Sem Similar Nacional (Lista CAMEX — Origem 6)",
                value=bool(reg_db.get("sem_similar_nacional_camex", 0)),
                key="imp_camex_chk",
            )
            tem_st_imp = f2.checkbox("Tem ICMS-ST na Entrada", value=bool(reg_db.get("tem_st", 0)), key="imp_st_chk")
            mva_imp = f3.number_input("MVA Original ST (%)", min_value=0.0, value=float(reg_db.get("mva_original_st", 0.0)), step=5.0, key="imp_mva_in")

            res_u = calcular_importacao_direta(
                ContextoImportacaoDireta(
                    ncm=ncm_in,
                    cest=str(reg_db.get("cest") or ""),
                    uf_desembaraco=uf_des,
                    uf_destino=uf_dest,
                    finalidade=fin_pad,
                    sem_similar_nacional_camex=sem_sim,
                    valor_aduaneiro_cif=_d_str(cif_in),
                    taxa_siscomex=_d_str(sis_in),
                    afrmm=_d_str(afrmm_in),
                    aliquota_ii=_d_str(ii_in),
                    aliquota_ipi=_d_str(ipi_in),
                    aliquota_pis_imp=_d_str(pis_in),
                    aliquota_cofins_imp=_d_str(cof_in),
                    adicional_cofins_imp=_d_str(adic_in),
                    tem_st=tem_st_imp,
                    mva_original_st=_d_str(mva_imp),
                    uf_saida_subsequente=uf_sai,
                )
            )
            linhas_imp = [res_u]
        else:
            up_lote = st.file_uploader(
                "Suba planilha .xlsx ou .csv (colunas: NCM, Valor Aduaneiro/CIF, Frete, Seguro, Siscomex, AFRMM, Finalidade)",
                type=["xlsx", "csv"],
                key="imp_up_lote",
            )
            if up_lote is not None:
                itens_raw = parsear_planilha_lote_importacao(up_lote.name, up_lote.getvalue())
                ctxs: list[ContextoImportacaoDireta] = []
                for it in itens_raw:
                    reg_db = regras_imp.get(it["ncm"], {})
                    ctxs.append(
                        ContextoImportacaoDireta(
                            ncm=it["ncm"],
                            cest=it["cest"] or str(reg_db.get("cest") or ""),
                            uf_desembaraco=uf_des,
                            uf_destino=uf_dest,
                            finalidade=it["finalidade"] or fin_pad,
                            sem_similar_nacional_camex=bool(it["sem_similar_nacional_camex"] or reg_db.get("sem_similar_nacional_camex", 0)),
                            valor_aduaneiro_cif=it["valor_aduaneiro_cif"],
                            frete_internacional=it["frete_internacional"],
                            seguro_internacional=it["seguro_internacional"],
                            taxa_siscomex=it["taxa_siscomex"],
                            afrmm=it["afrmm"],
                            outras_despesas_aduaneiras=it["outras_despesas_aduaneiras"],
                            aliquota_ii=it["aliquota_ii"] if it["aliquota_ii"] > 0 else _d_str(float(reg_db.get("aliquota_ii", 0.0))),
                            aliquota_ipi=it["aliquota_ipi"] if it["aliquota_ipi"] > 0 else _d_str(float(reg_db.get("aliquota_ipi", 0.0))),
                            aliquota_pis_imp=_d_str(float(reg_db.get("aliquota_pis_imp", 2.10))),
                            aliquota_cofins_imp=_d_str(float(reg_db.get("aliquota_cofins_imp", 9.65))),
                            adicional_cofins_imp=_d_str(float(reg_db.get("adicional_cofins_imp", 1.00))),
                            tem_st=bool(reg_db.get("tem_st", 0)),
                            mva_original_st=_d_str(float(reg_db.get("mva_original_st", 0.0))),
                            uf_saida_subsequente=uf_sai,
                        )
                    )
                linhas_imp = gerar_matriz_importacao_lote(ctxs)

        if linhas_imp:
            r0 = linhas_imp[0]
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Origem / CFOP Entrada", f"Orig {r0['origem_entrada']} | {r0['cfop_entrada']}")
            k2.metric("Base ICMS Por Dentro", f"R$ {r0['base_icms_por_dentro']}")
            k3.metric("ICMS-Imp + FCP", f"R$ {r0['valor_icms_importacao']} (+{r0['valor_fcp_importacao']})")
            k4.metric("Custo Desembaraçado", f"R$ {r0['custo_total_desembaracado']}")
            k5.metric("Saída Subseq. (Inter)", f"Orig {r0['origem_saida_subsequente']} | {r0['aliquota_saida_interestadual']}%")

            st.dataframe(linhas_imp, use_container_width=True, hide_index=True)
            st.download_button(
                "📥 Exportar Matriz de Importação (.xlsx)",
                data=exportar_tabela_crua_xlsx(linhas_imp, sheet_name="Matriz_Importacao_3xxx"),
                file_name="matriz_importacao_direta.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="imp_dl_matriz_xlsx",
                type="primary",
            )

    # ------------------------------------------------------------------
    # SUB-ABA 2: Importador & Auditor (DUIMP / DI / PDF / XML NF-e 3.xxx)
    # ------------------------------------------------------------------
    with sub2:
        arqs_doc = st.file_uploader(
            "Suba DUIMP (.json / .xml), DI (.xml / .pdf) ou XML NF-e de Entrada (CFOP 3.xxx)",
            type=["json", "xml", "pdf"],
            accept_multiple_files=True,
            key="imp_docs_up",
        )
        if arqs_doc and st.button("🚀 Auditar Documentos de Importação", type="primary", key="imp_docs_run"):
            resultados_docs: list[dict] = []
            srv_doc = RevTributariaService(db_path)
            try:
                for arq in arqs_doc:
                    aud = srv_doc.registrar_e_auditar_documento_importacao(
                        arq.name,
                        arq.getvalue(),
                        uf_destino=uf_dest,
                    )
                    resultados_docs.append(aud)
            finally:
                srv_doc.close()
            st.session_state["imp_docs_aud_res"] = resultados_docs

        for aud in st.session_state.get("imp_docs_aud_res") or []:
            st.subheader(f"{aud['tipo_documento']} — {aud['numero_documento']} ({aud['status_conciliacao']})")
            st.dataframe(aud["itens_auditados"], use_container_width=True, hide_index=True)
            st.download_button(
                f"📥 Baixar Espelho Conferido ({aud['numero_documento']}.xlsx)",
                data=exportar_espelho_importacao_xlsx(aud["itens_auditados"]),
                file_name=f"espelho_importacao_{aud['numero_documento']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"imp_dl_esp_{aud['numero_documento']}",
            )

    # ------------------------------------------------------------------
    # SUB-ABA 3: Regras de Importação & TEC/CAMEX
    # ------------------------------------------------------------------
    with sub3:
        b1, b2 = st.columns([1.4, 2.0])
        if b1.button("🔄 Sincronizar Catálogo Base TEC/CAMEX/TIPI", type="primary", key="imp_sync_tec"):
            srv_s = RevTributariaService(db_path)
            try:
                res_s = srv_s.sincronizar_tec_camex_padrao()
            finally:
                srv_s.close()
            st.success(f"✅ {res_s['regras_sincronizadas']} regra(s) TEC/CAMEX sincronizada(s)!")

        filtro_ncm_r = b2.text_input("Filtrar NCM nas Regras TEC/CAMEX", value="", key="imp_filtro_regra")
        srv_l = RevTributariaService(db_path)
        try:
            regras_lista = srv_l.listar_regras_importacao_ncm(ncm=filtro_ncm_r)
        finally:
            srv_l.close()

        st.dataframe(regras_lista, use_container_width=True, hide_index=True)

        if regras_lista:
            opcoes_aprov = [f"#{r['id']} | NCM {r['ncm']} | {r['uf_desembaraco']}->{r['uf_destino']} | {r['status']}" for r in regras_lista]
            sel_aprov = st.selectbox("Selecionar regra para aprovar (ACEITO)", opcoes_aprov, key="imp_sel_aprov")
            id_aprov = int(sel_aprov.split("|")[0].replace("#", "").strip())
            if st.button("✅ Aprovar Regra TEC/CAMEX (ACEITO)", key="imp_btn_aprov"):
                srv_a = RevTributariaService(db_path)
                try:
                    srv_a.aprovar_regra_importacao_ncm(id_aprov, usuario=usuario)
                finally:
                    srv_a.close()
                st.success(f"Regra #{id_aprov} aprovada com sucesso!")
                st.rerun()
