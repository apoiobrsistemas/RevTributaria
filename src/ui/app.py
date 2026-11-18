"""Interface visual local em Streamlit (conectada exclusivamente a RevTributariaService)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT_DIR = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import streamlit as st

from src.app.service import RevTributariaService, baixar_bytes_oficiais
from src.database import DEFAULT_DB_PATH
from src.ui.design_system import (
    apply_modern_design_system,
    formatar_data_ptbr,
    formatar_milhar_ptbr,
)
from src.ui.tabs import (
    render_aba_auditor_xml,
    render_aba_comparativo_erp,
    render_aba_matriz,
    render_aba_simulador,
    render_aba_validador,
    render_aba_vigia,
    render_consulta_matriz_ncm,
    render_tab_acervo,
)

st.set_page_config(
    page_title="RevTributaria — Auditoria Fiscal & Matriz 11 Blocos",
    page_icon="⚖️",
    layout="wide",
)
apply_modern_design_system()


@st.cache_data(ttl=60)
def _carregar_resumo(db_path: str) -> dict:
    srv = RevTributariaService(db_path)
    try:
        return srv.obter_resumo_sidebar()
    finally:
        srv.close()


@st.cache_data(ttl=60)
def _carregar_regras(
    db_path: str,
    uf_origem: str,
    uf_destino: str,
    ncm: str,
    cest: str,
    status_validacao: str,
) -> list[dict]:
    srv = RevTributariaService(db_path)
    try:
        return srv.listar_regras_estaduais(
            uf_origem=uf_origem,
            uf_destino=uf_destino,
            ncm=ncm,
            cest=cest,
            status_validacao=status_validacao,
        )
    finally:
        srv.close()


@st.cache_data(ttl=60)
def _carregar_fontes(db_path: str) -> list[dict]:
    srv = RevTributariaService(db_path)
    try:
        return srv.listar_fontes_legais()
    finally:
        srv.close()


@st.cache_data(ttl=60)
def _carregar_nfes(db_path: str) -> list[dict]:
    srv = RevTributariaService(db_path)
    try:
        return srv.listar_nfe_documentos()
    finally:
        srv.close()


def _limpar_cache() -> None:
    st.cache_data.clear()


def _render_sidebar(db_path: str) -> tuple[str, str]:
    st.sidebar.markdown(
        '<div class="rev-brand notranslate" translate="no">'
        '<div class="rev-brand-icon">⚖️</div>'
        '<div>'
        '<div class="rev-brand-title">RevTributária</div>'
        '<div class="rev-brand-sub">Inteligência &amp; Conformidade Fiscal</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    rotina_slot = st.sidebar.empty()
    if not st.session_state.get("rotina_diaria_verificada_sessao"):
        with rotina_slot.status("🔄 Verificando atualizações oficiais do dia...", expanded=False) as st_dia:
            srv_dia = RevTributariaService(db_path)
            try:
                res_dia = srv_dia.executar_rotina_diaria_ao_abrir(uf_origem="SP")
                st.session_state["rotina_diaria_verificada_sessao"] = True
                st.session_state["rotina_diaria_info"] = res_dia
                if res_dia.get("executado_agora"):
                    _limpar_cache()
                st_dia.update(
                    label=f"Base sincronizada ({res_dia['ultima_data']})",
                    state="complete",
                )
            finally:
                srv_dia.close()
        rotina_slot.empty()

    st.sidebar.markdown(
        '<div class="rev-sync-banner notranslate" translate="no">'
        '<span class="rev-pulse" style="background:#2563EB;"></span>'
        '<span>Base sincronizada com portais oficiais</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    resumo = _carregar_resumo(db_path)
    badge_conferir = (
        '<div class="rev-kpi-badge-ok">Tudo em dia</div>'
        if int(resumo["regras_a_conferir"]) == 0
        else ""
    )
    st.sidebar.markdown(
        '<div class="rev-kpi-grid notranslate" translate="no">'
        '<div class="rev-kpi-card">'
        '<div class="rev-kpi-label">A Conferir</div>'
        f'<div class="rev-kpi-val">{formatar_milhar_ptbr(resumo["regras_a_conferir"])}</div>'
        f'{badge_conferir}'
        '</div>'
        '<div class="rev-kpi-card">'
        '<div class="rev-kpi-label">Regras Ativas</div>'
        f'<div class="rev-kpi-val">{formatar_milhar_ptbr(resumo["regras_aceitas"])}</div>'
        '</div>'
        '<div class="rev-kpi-card">'
        '<div class="rev-kpi-label">Fontes .gov.br</div>'
        f'<div class="rev-kpi-val">{formatar_milhar_ptbr(resumo["fontes_cadastradas"])}</div>'
        '</div>'
        '<div class="rev-kpi-card">'
        '<div class="rev-kpi-label">NF-es</div>'
        f'<div class="rev-kpi-val">{formatar_milhar_ptbr(resumo["nfes_importadas"])}</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    vigia_fmt = formatar_data_ptbr(resumo["ultima_verificacao_vigia"])
    linx_fmt = formatar_data_ptbr(resumo["ultima_sincronizacao_linx"])
    usuario = st.session_state.get("usuario_auditor", "auditor_fiscal")
    iniciais = "".join(p[0].upper() for p in usuario.replace("_", " ").split()[:2]) or "AF"
    st.sidebar.markdown(
        f'<div class="rev-date-badge notranslate" translate="no">🛡️ <strong>Último Vigia:</strong> {vigia_fmt}<br>'
        f'🔌 <strong>Último Linx:</strong> {linx_fmt}</div>'
        f'<div class="rev-profile-card notranslate" translate="no">'
        f'<div class="rev-avatar">{iniciais}</div>'
        f'<div>'
        f'<div style="font-size:0.86rem;font-weight:600;color:#0F172A;">Auditor Fiscal</div>'
        f'<div style="font-size:0.74rem;color:#64748B;">Sessão Protegida • {usuario}</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    with st.sidebar.expander("⚙️ Sessão & CNPJ Linx", expanded=False):
        usuario = st.text_input("Usuário auditor", value=usuario, key="cfg_usuario_auditor")
        st.session_state["usuario_auditor"] = usuario
        cnpj_linx = st.text_input("CNPJ Loja Linx (para sync)", value="", key="cfg_cnpj_linx")

    if st.sidebar.button(
        "🔄 Sincronizar Bases Oficiais (TIPI + Siscomex + CONFAZ + NF-e)",
        use_container_width=True,
    ):
        with st.sidebar.status("Sincronizando bases oficiais...", expanded=True) as status:
            st.write("Descobrindo pares NCM+CEST ativos (Linx + NF-es)...")
            srv = RevTributariaService(db_path)
            try:
                st.write("Baixando Siscomex, TIPI Receita Federal e CONFAZ (.gov.br)...")
                res = srv.sincronizar_bases_oficiais(fetcher=baixar_bytes_oficiais)
                status.update(
                    label=f"Sincronização concluída ({res['pares_descobertos']} pares)",
                    state="complete",
                )
                _limpar_cache()
                st.sidebar.json(res)
            except Exception as exc:
                status.update(label="Falha na sincronização", state="error")
                st.sidebar.error(str(exc))
            finally:
                srv.close()

    if st.sidebar.button("🔌 Sincronizar Linx Microvix (Incremental)", use_container_width=True):
        if not cnpj_linx.strip():
            st.sidebar.warning("Informe o CNPJ da loja para sincronização incremental.")
        else:
            with st.sidebar.status("Conectando ao Web Service Linx Microvix...", expanded=True) as status:
                srv = RevTributariaService(db_path)
                try:
                    res = srv.sincronizar_linx(cnpj_linx.strip())
                    status.update(label="Linx sincronizado com sucesso!", state="complete")
                    _limpar_cache()
                    st.sidebar.json(res)
                except Exception as exc:
                    status.update(label="Erro na integração Linx", state="error")
                    st.sidebar.error(str(exc))
                finally:
                    srv.close()

    if st.sidebar.button("🛡️ Rodar Vigia da Legislação Agora", use_container_width=True):
        with st.sidebar.status("Executando Vigia Noturno (Zero IA)...", expanded=True) as status:
            srv = RevTributariaService(db_path)
            try:
                alertas = srv.executar_vigia()
                st.session_state["alertas_vigia"] = alertas
                status.update(label=f"Vigia finalizado ({len(alertas)} alertas)", state="complete")
                _limpar_cache()
            except Exception as exc:
                status.update(label="Falha no Vigia", state="error")
                st.sidebar.error(str(exc))
            finally:
                srv.close()

    if st.sidebar.button("📥 Carregar Seed Inicial SP (20 NCMs)", use_container_width=True):
        with st.sidebar.status("Carregando Seed SP (20 NCMs)...", expanded=True) as status:
            srv = RevTributariaService(db_path)
            try:
                res = srv.executar_seed_sp(usar_rede=False)
                _limpar_cache()
                status.update(label="Seed SP carregado com sucesso!", state="complete")
                st.sidebar.json(res)
            finally:
                srv.close()

    return db_path, usuario


def main() -> None:
    db_path = str(DEFAULT_DB_PATH)
    db_path, usuario = _render_sidebar(db_path)

    st.markdown(
        '<div class="rev-hero notranslate" translate="no">'
        '<div class="rev-hero-text">⚖️ <strong>RevTributária</strong> — '
        'Auditoria guiada por normas oficiais. Zero achismo, 100% lastro legal.</div>'
        '<div class="rev-status-pill"><span class="rev-pulse"></span>'
        'Monitoramento &amp; Guardrail Ativos</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    tab_op, tab1, tab2, tab3, tab4, tab5, tab6, tab_acervo = st.tabs(
        [
            "🔎 Consulta Matriz por NCM (CFOPs & Impostos)",
            "📋 Matriz Legal (NCMs)",
            "🧮 Simulador (11 Blocos)",
            "📄 Auditor XML NF-e",
            "⚙️ Comparativo ERP",
            "🛡️ Vigia & Fontes",
            "✅ Validador NCMs & Skills",
            "📚 Acervo Técnico & NTs",
        ]
    )
    with tab_op:
        render_consulta_matriz_ncm(db_path=db_path)
    with tab1:
        render_aba_matriz(
            db_path=db_path,
            usuario=usuario,
            carregar_regras=_carregar_regras,
            limpar_cache=_limpar_cache,
        )
    with tab2:
        render_aba_simulador(db_path=db_path)
    with tab3:
        render_aba_auditor_xml(
            db_path=db_path,
            carregar_nfes=_carregar_nfes,
            limpar_cache=_limpar_cache,
        )
    with tab4:
        render_aba_comparativo_erp(db_path=db_path, limpar_cache=_limpar_cache)
    with tab5:
        render_aba_vigia(
            db_path=db_path,
            carregar_fontes=_carregar_fontes,
            limpar_cache=_limpar_cache,
        )
    with tab6:
        render_aba_validador(db_path=db_path, limpar_cache=_limpar_cache)
    with tab_acervo:
        srv_ac = RevTributariaService(db_path)
        try:
            render_tab_acervo(srv_ac)
        finally:
            srv_ac.close()


if __name__ == "__main__":
    main()
