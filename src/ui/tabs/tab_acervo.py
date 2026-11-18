"""Aba Acervo Técnico & NTs: Documentação Oficial Indexada com Lastro Normativo."""

from __future__ import annotations

from urllib.parse import urlparse

import streamlit as st

from src.app.service import RevTributariaService


def render_tab_acervo(service: RevTributariaService) -> None:
    """Renderiza o repositório pesquisável de normas, NTs, Portarias SRE e RC SEFAZ-SP."""
    st.subheader("📚 Acervo Técnico & NTs Oficiais")
    st.caption(
        "Auditoria blindada por normas oficiais. Zero achismo, 100% lastro legal. "
        "Busque por código de erro SEFAZ (ex.: 930), número de NT/Portaria ou NCM."
    )

    col_busca, col_esfera, col_tipo, col_status = st.columns([2.2, 1.1, 1.2, 1.0])
    with col_busca:
        termo = st.text_input(
            "Busca instantânea (Erro SEFAZ, NT, Portaria, NCM)",
            placeholder="Ex: 930, 2024.001, SRE 70/2025, 85171300...",
            key="acervo_busca_termo",
        )
    with col_esfera:
        esfera = st.selectbox(
            "Esfera",
            ["", "FEDERAL", "ESTADUAL_SP", "CONFAZ", "ENCAT"],
            format_func=lambda x: "Todas as esferas" if x == "" else x,
            key="acervo_filtro_esfera",
        )
    with col_tipo:
        tipo_doc = st.selectbox(
            "Tipo de Documento",
            [
                "",
                "NOTA_TECNICA",
                "PORTARIA_SRE",
                "PORTARIA_CAT",
                "DECRETO",
                "CONVENIO_ICMS",
                "RESPOSTA_CONSULTA",
                "LEI_COMPLEMENTAR",
            ],
            format_func=lambda x: "Todos os tipos" if x == "" else x.replace("_", " "),
            key="acervo_filtro_tipo",
        )
    with col_status:
        status_norma = st.selectbox(
            "Status",
            ["", "VIGENTE", "ALTERADA", "REVOGADA"],
            format_func=lambda x: "Todos" if x == "" else x,
            key="acervo_filtro_status",
        )

    docs = service.buscar_acervo_documental(
        esfera=esfera,
        tipo_documento=tipo_doc,
        status_norma=status_norma,
        termo=termo,
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Documentos Encontrados", len(docs))
    m2.metric(
        "Normas Vigentes",
        sum(1 for d in docs if str(d.get("status_norma")).upper() == "VIGENTE"),
    )
    m3.metric(
        "NTs NF-e / ENCAT",
        sum(1 for d in docs if str(d.get("tipo_documento")).upper() == "NOTA_TECNICA"),
    )

    if not docs:
        st.info("Nenhum documento encontrado para os filtros informados.")
        return

    for doc in docs:
        status = str(doc.get("status_norma") or "VIGENTE").upper()
        badge = "🟢 VIGENTE" if status == "VIGENTE" else ("🟡 ALTERADA" if status == "ALTERADA" else "🔴 REVOGADA")
        header = f"{badge} | {doc['codigo_ato']} — {doc['titulo']} ({doc['esfera']})"
        with st.expander(header, expanded=bool(termo.strip())):
            portal_origem = urlparse(str(doc.get("url_oficial") or "")).netloc or doc.get("esfera") or "-"
            c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
            c1.markdown(f"**Vigência:** `{doc.get('vigencia_inicio') or '-'}` até `{doc.get('vigencia_fim') or 'Atual'}`")
            c2.markdown(f"**Portal:** {portal_origem}")
            c3.markdown(f"**Hash SHA-256:** `{str(doc.get('hash_sha256') or '')[:18]}...`")

            if doc.get("artigos_chave"):
                st.markdown(f"**Artigos / Cláusulas-Chave:** `{doc['artigos_chave']}`")
            if doc.get("ncms_impactados"):
                st.markdown(f"**NCMs Impactados:** `{doc['ncms_impactados']}`")
            if doc.get("codigos_erro_sefaz"):
                st.markdown(f"**Rejeições SEFAZ:** `{doc['codigos_erro_sefaz']}`")
            if doc.get("regras_xml"):
                st.markdown(f"**Regras de Validação XML / Schema:** {doc['regras_xml']}")

            st.markdown("**Trecho Literal da Norma:**")
            st.code(str(doc.get("texto_literal") or ""), language="text")

            col_link, col_btn = st.columns([2, 1])
            with col_link:
                st.markdown(f"[🔗 Abrir Fonte Oficial ({portal_origem})]({doc.get('url_oficial')})")
            with col_btn:
                ncms_raw = [x.strip() for x in str(doc.get("ncms_impactados") or "").split(",") if x.strip()]
                ncm_alvo = ncms_raw[0] if ncms_raw and ncms_raw[0][0].isdigit() else "85171300"
                if st.button("🔎 Validar NCM com esta Norma", key=f"btn_val_acervo_{doc['id']}"):
                    st.session_state["skill_ncm_alvo"] = "".join(c for c in ncm_alvo if c.isdigit())[:8] or "85171300"
                    st.success(f"NCM {st.session_state['skill_ncm_alvo']} carregado no Validador Inteligente (aba ✅ Validador NCMs & Skills).")
