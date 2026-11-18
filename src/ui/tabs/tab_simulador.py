"""Aba 2: Simulador de Cálculo (11 Blocos) + Espelho de XML NF-e + Matriz Operacional."""

from __future__ import annotations

from datetime import date

import streamlit as st

from src.app.service import RevTributariaService


def render_aba_simulador(*, db_path: str) -> None:
    """Renderiza o simulador de cálculo dos 11 blocos e o espelho de XML para conferência."""
    st.subheader("Simulador de Cálculo (11 Blocos) & Espelho XML NF-e")
    with st.form("form_simulador"):
        c1, c2, c3, c4 = st.columns(4)
        s_orig = c1.text_input("UF Origem", "SP")
        s_dest = c2.text_input("UF Destino", "RJ")
        s_ncm = c3.text_input("NCM", "85171300")
        s_cest = c4.text_input("CEST", "")

        f1, f2, f3, f4 = st.columns(4)
        s_operacao = f1.selectbox(
            "Operação",
            [
                "Todas",
                "Venda de Mercadorias",
                "Compra para Comercialização",
                "Devolução de Compra",
                "Devolução de Venda",
                "Entrada de Transferência entre Filiais",
                "Saída de Transferência entre Filiais",
                "Outras Entradas",
                "Outras Saídas",
            ],
            index=1,
        )
        s_regime = f2.selectbox(
            "Regime Tributário (Origem)",
            [
                "Lucro Real",
                "Lucro Presumido",
                "Simples Nacional",
                "Simples Nacional — Excesso de Sublimite",
                "MEI",
            ],
            index=0,
        )
        s_atividade = f3.selectbox(
            "Atividade / Benefício SP",
            [
                "Varejo (Padrão)",
                "Indústria / Atacado Têxtil & Calçados (SP)",
            ],
            index=0,
        )
        s_origem_merc = f4.selectbox("Origem da Mercadoria", ["Todas", "Nacional", "Importado"], index=0)

        c5, c6, c7, c8 = st.columns(4)
        s_val = c5.number_input("Valor Produto (R$)", value=1000.0, min_value=0.01)
        s_ipi = c6.number_input("IPI (R$)", value=0.0, min_value=0.0)
        s_fci = c7.number_input("Conteúdo Importação FCI (%)", value=0.0, min_value=0.0, max_value=100.0)
        s_contrib = c8.checkbox("Destinatário Contribuinte?", value=True)
        s_data = st.date_input("Data da Operação", value=date.today())

        if st.form_submit_button("🧮 Calcular 11 Blocos & Gerar Espelho XML", type="primary"):
            srv = RevTributariaService(db_path)
            try:
                orig_cod_calc = "2" if s_origem_merc == "Importado" else "0"
                res = srv.simular_calculo_item(
                    uf_origem=s_orig,
                    uf_destino=s_dest,
                    ncm=s_ncm,
                    cest=s_cest,
                    valor=s_val,
                    ipi=s_ipi if s_ipi > 0 else None,
                    fci=s_fci if s_fci > 0 else None,
                    contribuinte=s_contrib,
                    origem_mercadoria=orig_cod_calc,
                    data_referencia=s_data.isoformat(),
                    regime_tributario=s_regime,
                    atividade_empresa=s_atividade,
                )
                st.session_state["sim_resultado"] = res
                st.session_state["sim_params"] = {
                    "ncm": s_ncm,
                    "uf_orig": s_orig,
                    "uf_dest": s_dest,
                    "cest": s_cest,
                    "data": s_data.isoformat(),
                    "regime": s_regime,
                    "atividade": s_atividade,
                    "operacao": s_operacao,
                    "origem_merc": s_origem_merc,
                    "contrib": s_contrib,
                }
            except LookupError as exc:
                st.session_state.pop("sim_resultado", None)
                st.warning(str(exc))
            finally:
                srv.close()

    res = st.session_state.get("sim_resultado")
    params = st.session_state.get("sim_params")
    if res and params:
        b1, b2, b3 = st.columns(3)
        b1.metric("ICMS Próprio", f"R$ {res['valor_icms_proprio']}", f"Alíq {res['aliquota_icms']}% | CST {res['cst_esperado']} | CFOP {res['cfop_esperado']}")
        b2.metric("ICMS-ST", f"R$ {res['valor_icms_st']}", f"MVA {res['mva_aplicada']}% | BC R$ {res['bc_st']}")
        b3.metric("DIFAL / FCP", f"R$ {res['valor_difal']}", f"FCP-ST R$ {res['valor_fcp_st']}")
        b4, b5, b6 = st.columns(3)
        b4.metric("PIS / COFINS", f"R$ {res['valor_pis']} / R$ {res['valor_cofins']}")
        b5.metric("ICMS Efetivo", f"R$ {res['valor_icms_efetivo']}", f"BC Efet R$ {res['bc_icms_efetivo']}")
        b6.metric(
            "IBS / CBS (Transição)",
            f"R$ {res['valor_ibs_total']} / R$ {res['valor_cbs']}",
            f"cClassTrib {res['cclass_trib'] or '-'}",
        )

        st.markdown("**📄 Espelho de XML NF-e (Conferência de Emissão Real)**")
        espelho = res.get("espelho_xml", [])
        st.dataframe(espelho, use_container_width=True, hide_index=True)

        srv_op = RevTributariaService(db_path)
        try:
            xlsx_esp = srv_op.exportar_matriz_erp_unica_xlsx(espelho) if espelho else b""
            linhas_op = srv_op.consultar_matriz_operacional(
                ncm=params["ncm"],
                uf_origem=params["uf_orig"],
                uf_destino=params["uf_dest"],
                cest=params["cest"],
                data_referencia=params["data"],
                regime_tributario=params["regime"],
                atividade_empresa=params["atividade"],
            )
        finally:
            srv_op.close()

        if xlsx_esp:
            st.download_button(
                "📥 Exportar Espelho XML (.xlsx)",
                data=xlsx_esp,
                file_name=f"espelho_xml_{params['ncm']}_{params['uf_orig']}_{params['uf_dest']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        contrib_alvo = "S" if params["contrib"] else "N"
        linhas_filtradas = [
            l
            for l in linhas_op
            if (params["operacao"] == "Todas" or l["Natureza de Operação"] == params["operacao"])
            and (params["origem_merc"] == "Todas" or l["Origem"] == params["origem_merc"])
            and (
                l["Natureza de Operação"] not in {"Venda de Mercadorias", "Outras Saídas"}
                or l["Operação com Contribuinte (S/N)"] == contrib_alvo
            )
        ]
        if linhas_filtradas:
            st.markdown("**Composição Tributária da Operação (CFOP, CST, Alíquotas, IPI, PIS/COFINS, CBS/IBS)**")
            st.dataframe(linhas_filtradas, use_container_width=True, hide_index=True)

        with st.expander("Detalhamento Completo dos 11 Blocos (JSON)"):
            st.json(res)
