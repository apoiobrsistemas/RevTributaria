"""Aba 5: Mapa de Fontes Oficiais SP (Checklist 100%), Simulador SHA-256 & Vigia."""

from __future__ import annotations

from typing import Callable

import streamlit as st

from src.app.service import RevTributariaService


def render_aba_vigia(
    *,
    db_path: str,
    carregar_fontes: Callable[[str], list[dict]],
    limpar_cache: Callable[[], None],
) -> None:
    """Renderiza checklist dos 8 portais SP, simulador diário SHA-256 e alertas do Vigia."""
    st.subheader("Mapa de Fontes Oficiais SP (Checklist 100%) & Robô Monitor Diário")

    srv = RevTributariaService(db_path)
    try:
        mapa_8 = srv.obter_mapa_8_portais_sp()
    finally:
        srv.close()

    with st.expander("📋 Checklist 100% — Os 8 Portais Indispensáveis de SP (Formatos, Ciclos e Riscos)", expanded=True):
        st.dataframe(mapa_8, use_container_width=True)

    with st.expander("🤖 Simulador de Execução Diária (Detecção de Alterações via SHA-256)"):
        alvo_sim = st.selectbox(
            "Simular mudança normativa em qual portal?",
            [p["portal"] for p in mapa_8],
            index=1,
        )
        if st.button("▶️ Simular Varredura Diária SHA-256"):
            srv = RevTributariaService(db_path)
            try:
                sim = srv.simular_monitor_diario_sha256(simular_alteracao_portal=alvo_sim)
            finally:
                srv.close()
            st.dataframe(sim, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📚 Atualizar Catálogo Completo de Portais Oficiais (.gov.br/.leg.br)"):
            with st.status("Registrando catálogo oficial completo...", expanded=True) as status:
                srv = RevTributariaService(db_path)
                try:
                    res = srv.garantir_catalogo_fontes_oficiais()
                    limpar_cache()
                    status.update(
                        label=f"Catálogo atualizado ({res['total_catalogo']} portais oficiais, +{res['inseridas']} novos)",
                        state="complete",
                    )
                finally:
                    srv.close()
    with col2:
        if st.button("🔄 Revalidar Fontes Oficiais Agora"):
            with st.status("Executando releitura oficial (Zero IA)...", expanded=True) as status:
                srv = RevTributariaService(db_path)
                try:
                    alertas = srv.executar_vigia()
                    limpar_cache()
                    status.update(label=f"Concluído ({len(alertas)} alertas novos)", state="complete")
                finally:
                    srv.close()

    fontes = carregar_fontes(db_path)
    if fontes:
        st.markdown(f"**Catálogo de Normas e Portais Oficiais (`fontes_legais` — {len(fontes)} fontes)**")
        st.dataframe(fontes, use_container_width=True)
    else:
        st.info("Nenhuma fonte legal cadastrada em `fontes_legais`.")

    srv = RevTributariaService(db_path)
    try:
        alertas_abertos = srv.listar_alertas_vigia(status_alerta="ABERTO")
    finally:
        srv.close()

    if alertas_abertos:
        st.markdown(f"**Alertas Abertos Persistidos (`VIGIA-AAAAMMDD-UF-GRUPO` — {len(alertas_abertos)})**")
        for alerta in alertas_abertos:
            with st.expander(f"[{alerta['codigo']}] {alerta['tipo']} — {alerta['uf']}"):
                st.write(alerta["mensagem"])
                motivo_enc = st.text_input("Justificativa de conferência", key=f"vigia_mot_{alerta['id']}")
                if st.button("Encerrar Alerta", key=f"vigia_close_{alerta['id']}") and motivo_enc.strip():
                    srv = RevTributariaService(db_path)
                    try:
                        srv.encerrar_alerta_vigia(
                            alerta_id=int(alerta["id"]),
                            justificativa=motivo_enc.strip(),
                        )
                    finally:
                        srv.close()
                    limpar_cache()
                    st.success("Alerta conferido e gravado no banco.")
    else:
        st.success("Nenhum alerta aberto do Vigia Noturno.")
