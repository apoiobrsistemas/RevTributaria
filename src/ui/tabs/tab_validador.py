"""Aba de Validação de Regras & Exceções NCM (SP): Árvore 5 Camadas + Auditoria em Lote."""

from __future__ import annotations

from typing import Callable

import streamlit as st

from src.app.service import RevTributariaService


def render_aba_validador(
    *,
    db_path: str,
    limpar_cache: Callable[[], None],
) -> None:
    """Renderiza o Pipeline de 5 Skills, a árvore de decisão de 5 camadas e a auditoria em lote."""
    st.subheader("Validador Inteligente (Skills) & Exceções NCM (SP)")
    st.caption("Auditoria blindada por normas oficiais. Zero achismo, 100% lastro legal.")

    sub_skills, sub_arvore, sub_lote = st.tabs(
        [
            "🤖 Pipeline 5 Skills & Anti-Alucinação",
            "🌳 Árvore 5 Camadas (Individual & 10 Casos Críticos SP)",
            "📦 Auditoria em Lote (Matriz NCMs do Banco)",
        ]
    )

    with sub_skills:
        ncm_default = str(st.session_state.get("skill_ncm_alvo") or "85171300")
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            sk_ncm = st.text_input("NCM (8 dígitos)", value=ncm_default, key="sk_ncm")
            sk_cst = st.text_input("CST ICMS", value="00", key="sk_cst")
        with s2:
            sk_cbenef = st.text_input("cBenef (SRE 70/2025)", value="", key="sk_cbenef")
            sk_cest = st.text_input("CEST", value="2105300", key="sk_cest")
        with s3:
            sk_st = st.selectbox("Tem ST?", [0, 1], index=0, key="sk_st")
            sk_red = st.number_input("Redução BC (%)", min_value=0.0, max_value=100.0, value=0.0, key="sk_red")
        with s4:
            sk_ex = st.text_input("Ex-TIPI", value="", key="sk_ex")
            sk_emb = st.text_input("Embalagem", value="", key="sk_emb")
        sk_desc = st.text_input("Descrição do Item", value="Mercadoria padrão", key="sk_desc")

        if st.button("🚀 Executar Pipeline das 5 Skills Fiscais", type="primary", key="btn_exec_skills"):
            srv_sk = RevTributariaService(db_path)
            try:
                res_sk = srv_sk.executar_pipeline_skills_ncm(
                    ncm=sk_ncm,
                    cst_icms=sk_cst,
                    cbenef=sk_cbenef,
                    tem_st=int(sk_st),
                    cest=sk_cest,
                    reducao_bc=float(sk_red),
                    descricao_item=sk_desc,
                    ex_tipi=sk_ex,
                    embalagem=sk_emb,
                )
            finally:
                srv_sk.close()

            k1, k2, k3 = st.columns(3)
            k1.metric("Score de Lastro Normativo", f"{res_sk['score_lastro']}%")
            k2.metric("Selo de Confiabilidade", res_sk["selo_confiabilidade"])
            k3.metric("Veredito Final", res_sk["status_geral"])

            st.progress(min(100, max(0, int(res_sk["score_lastro"]))) / 100.0)

            if res_sk["lacuna_normativa"]:
                st.warning(f"⚠️ {res_sk['mensagem_bloqueio']}")

            st.markdown("#### Execução Sequencial das 5 Skills")
            for sk in res_sk["skills"]:
                icone = "✅" if sk["status"] == "OK" else ("⚠️" if sk["status"] == "ALERTA" else "🚫")
                with st.expander(f"{icone} {sk['nome']} — [{sk['codigo_ato']}]", expanded=sk["status"] != "OK"):
                    st.write(sk["detalhe"])
                    st.caption(f"ID Documento Acervo: {sk['doc_id'] or 'N/A'} | Lastro OK: {sk['lastro_ok']}")

            st.markdown("#### 📄 Evidência Documental (Lastro Oficial)")
            if not res_sk["evidencias_documentais"]:
                st.error("Nenhuma evidência documental vigente vinculada.")
            else:
                for ev in res_sk["evidencias_documentais"]:
                    with st.expander(f"📜 {ev['codigo_ato']} — {ev['titulo']} ({ev['esfera']})", expanded=False):
                        st.markdown(f"**Portal Oficial:** {ev['portal_origem']} | **Status:** `{ev['status_norma']}`")
                        st.markdown(f"**Vigência:** `{ev['vigencia_inicio']}` até `{ev['vigencia_fim']}`")
                        st.markdown(f"**Hash SHA-256:** `{ev['hash_sha256']}` | **Última Sincronização:** `{ev['ultima_sincronizacao']}`")
                        st.code(ev["trecho_literal"], language="text")
                        st.markdown(f"[🔗 Consultar Ato Oficial]({ev['url_oficial']})")

    with sub_arvore:
        srv = RevTributariaService(db_path)
        try:
            casos = srv.listar_casos_criticos_sp()
        finally:
            srv.close()

        opcoes_casos = ["(Entrada Manual)"] + [c["titulo"] for c in casos]
        escolha = st.selectbox("Navegar pelos 10 Casos Críticos Pré-Mapeados (SP)", opcoes_casos)
        caso_sel = next((c for c in casos if c["titulo"] == escolha), None)

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            ncm_in = st.text_input("NCM (8 dígitos)", value=caso_sel["ncm"] if caso_sel else "15091000")
            cst_in = st.text_input("CST ICMS", value=caso_sel["cst_icms"] if caso_sel else "00")
        with c2:
            cbenef_in = st.text_input("cBenef (SRE 70/2025)", value=caso_sel["cbenef"] if caso_sel else "")
            cest_in = st.text_input("CEST", value=caso_sel["cest"] if caso_sel else "")
        with c3:
            tem_st_in = st.selectbox("Tem ST?", [0, 1], index=int(caso_sel["tem_st"]) if caso_sel else 0)
            red_in = st.number_input("Redução BC (%)", min_value=0.0, max_value=100.0, value=float(caso_sel["reducao_bc"]) if caso_sel else 0.0)
        with c4:
            ex_in = st.text_input("Ex-TIPI", value=caso_sel["ex_tipi"] if caso_sel else "")
            emb_in = st.text_input("Embalagem", value=caso_sel["embalagem"] if caso_sel else "")

        desc_in = st.text_input(
            "Descrição do Item",
            value=caso_sel["descricao_item"] if caso_sel else "",
        )
        if caso_sel:
            st.info(f"**Norma-chave:** {caso_sel['norma_chave']}")

        if st.button("🌳 Executar Árvore de Decisão (5 Camadas)", type="primary"):
            srv = RevTributariaService(db_path)
            try:
                res = srv.avaliar_arvore_5_camadas_individual(
                    ncm=ncm_in,
                    cst_icms=cst_in,
                    cbenef=cbenef_in,
                    tem_st=int(tem_st_in),
                    cest=cest_in,
                    reducao_bc=float(red_in),
                    descricao_item=desc_in,
                    ex_tipi=ex_in,
                    embalagem=emb_in,
                )
            finally:
                srv.close()

            status_g = res["status_geral"]
            if status_g == "OK":
                st.success(f"Resultado Final NCM {res['ncm']}: **CONFORME (OK)**")
            elif status_g == "ALERTA":
                st.warning(f"Resultado Final NCM {res['ncm']}: **ALERTA**")
            else:
                st.error(f"Resultado Final NCM {res['ncm']}: **BLOQUEIO**")

            for cam in res["camadas"]:
                badge = "✅" if cam["status"] == "OK" else ("⚠️" if cam["status"] == "ALERTA" else "🛑")
                with st.expander(f"{badge} {cam['nome']} — [{cam['status']}]", expanded=True):
                    st.write(cam["detalhe"])
                    st.caption(f"Referência: {cam['norma_referencia']}")

    with sub_lote:
        srv = RevTributariaService(db_path)
        try:
            resumo = srv.obter_resumo_mapeamento_ncms()
        finally:
            srv.close()

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("NCMs Estaduais", resumo["ncms_estaduais_distintos"])
        m2.metric("NCMs Federais", resumo["ncms_federais_distintos"])
        m3.metric("Com cBenef", resumo["ncms_com_cbenef"])
        m4.metric("Com ST", resumo["ncms_com_st"])
        m5.metric("Erros", resumo["validacao_erros"])
        m6.metric("Alertas", resumo["validacao_alertas"])
        st.caption(
            f"Última validação: `{resumo['ultima_validacao']}` | "
            f"Redução BC: `{resumo['ncms_com_reducao']}` NCMs | "
            f"Isenção/Suspensão: `{resumo['ncms_com_isencao']}` NCMs"
        )

        col_btn, col_uf = st.columns([2, 1])
        with col_uf:
            uf_filtro = st.selectbox("UF Origem para validar", ["TODAS", "SP", "RJ", "MG", "PR", "SC", "RS"], index=1)
        with col_btn:
            if st.button("🔍 Validar Todos os NCMs & Exceções Agora", type="primary"):
                with st.status("Executando validador completo de NCMs e exceções...", expanded=True) as status:
                    srv = RevTributariaService(db_path)
                    try:
                        uf_param = None if uf_filtro == "TODAS" else uf_filtro
                        st.write("Cruzando NCMs × Regras Federais × Conv. 52/91 × Conv. 142/18 × cBenef × ST...")
                        resultado = srv.executar_validacao_ncms(uf_origem=uf_param, persistir=True)
                        limpar_cache()
                        status.update(
                            label=(
                                f"Concluído: {resultado['total_ncms_mapeados']} NCMs mapeados | "
                                f"{resultado['ncms_com_erro']} erros | {resultado['ncms_com_alerta']} alertas"
                            ),
                            state="complete",
                        )
                    finally:
                        srv.close()

        f1, f2, f3 = st.columns(3)
        with f1:
            sev = st.selectbox("Severidade", ["", "ERRO", "ALERTA", "INFO"], format_func=lambda x: x or "Todas")
        with f2:
            cat = st.selectbox(
                "Categoria",
                [
                    "",
                    "CBENEF",
                    "ST_CONCESSAO",
                    "ISENCAO",
                    "REDUCAO_BC",
                    "DIFERIMENTO",
                    "ICMS_EFETIVO",
                    "MONOFASICO",
                    "VIGENCIA",
                    "FONTE_LEGAL",
                    "NCM_FEDERAL",
                ],
                format_func=lambda x: x or "Todas",
            )
        with f3:
            ncm_busca = st.text_input("Filtrar NCM", placeholder="Ex: 8517")

        srv = RevTributariaService(db_path)
        try:
            achados = srv.listar_validacoes_ncm(severidade=sev, categoria=cat, ncm=ncm_busca, limite=500)
        finally:
            srv.close()

        if achados:
            st.dataframe(achados, use_container_width=True)
        else:
            st.info("Nenhum achado para os filtros selecionados (ou execute a validação acima).")
