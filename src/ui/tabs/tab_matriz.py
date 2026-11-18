"""Aba 1: Painel de NCMs & Regras (Matriz Legal)."""

from __future__ import annotations

from typing import Callable

import streamlit as st

from src.app.service import RevTributariaService
from src.database import OptimisticLockError


def _origem_regra_label(regra: dict) -> str:
    disp = str(regra.get("dispositivo_legal") or "")
    if "TIPI" in disp or "CONFAZ" in disp or "Siscomex" in disp or "Portal NF-e" in disp:
        return "Automático: TIPI/CONFAZ"
    if regra.get("fonte_legal_id") or regra.get("confianca_ia"):
        return "Automático: Linx + IA Oficial"
    return "Manual"


def render_aba_matriz(
    *,
    db_path: str,
    usuario: str,
    carregar_regras: Callable[[str, str, str, str, str, str], list[dict]],
    limpar_cache: Callable[[], None],
) -> None:
    """Renderiza a aba de curadoria, edição com optimistic locking e histórico."""
    st.subheader("Painel de NCMs & Regras (Matriz Legal)")

    with st.expander("📤 Importar Planilha de NCMs (.xlsx / .csv) & Baixar Template Padrão"):
        col_tpl, col_up = st.columns([1, 2])
        with col_tpl:
            srv_tpl = RevTributariaService(db_path)
            try:
                tpl_bytes = srv_tpl.gerar_template_carga_ncms_bytes()
            finally:
                srv_tpl.close()
            st.download_button(
                "⬇️ Baixar Template Padrão (.xlsx)",
                data=tpl_bytes,
                file_name="modelo_carga_ncms.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        with col_up:
            arq_ncms = st.file_uploader(
                "Subir planilha de NCMs (.xlsx ou .csv)",
                type=["xlsx", "csv"],
                key="upload_lote_ncms",
            )
            if arq_ncms and st.button("📥 Importar Planilha para Matriz", key="btn_import_lote"):
                ext = f".{arq_ncms.name.rsplit('.', 1)[-1].lower()}" if "." in arq_ncms.name else ".xlsx"
                srv_imp = RevTributariaService(db_path)
                try:
                    res_imp = srv_imp.importar_regras_lote(
                        arq_ncms.read(),
                        extensao=ext,
                        usuario=usuario,
                    )
                    limpar_cache()
                    st.success(
                        f"Importação concluída: {res_imp['inseridas']} regra(s) inserida(s) em A_CONFERIR "
                        f"({res_imp['ignoradas']} ignorada(s))."
                    )
                finally:
                    srv_imp.close()

    c1, c2, c3, c4, c5 = st.columns(5)
    uf_orig = c1.text_input("UF Origem", value="", max_chars=2, placeholder="Todas", key="f_uf_orig")
    uf_dest = c2.text_input("UF Destino", value="", max_chars=2, placeholder="Todas", key="f_uf_dest")
    ncm_filtro = c3.text_input("NCM", value="", key="f_ncm")
    cest_filtro = c4.text_input("CEST", value="", key="f_cest")
    status_filtro = c5.selectbox("Status", ["", "A_CONFERIR", "ACEITO", "REJEITADO"], key="f_status")

    regras = carregar_regras(db_path, uf_orig, uf_dest, ncm_filtro, cest_filtro, status_filtro)

    if regras:
        st.caption(f"{len(regras)} regra(s) encontrada(s).")

        tabela_visao = [
            {
                "ID": r["id"],
                "Orig": r["uf_origem"],
                "Dest": r["uf_destino"],
                "NCM": r["ncm"] or "*",
                "CEST": r["cest"],
                "CFOP": r["cfop"],
                "CST": r["cst_icms"],
                "ICMS %": r["aliquota_icms"],
                "Red. Base %": r["reducao_base_icms"],
                "ST": "Sim" if r["tem_st"] else "Não",
                "MVA %": r["margem_st"],
                "cBenef": r.get("codigo_beneficio_fiscal") or "",
                "Versão": f"v{r['versao']}",
                "Status": r["status_validacao"],
                "Origem Regra": _origem_regra_label(r),
            }
            for r in regras
        ]
        st.dataframe(tabela_visao, use_container_width=True, hide_index=True)

        pendentes = [(r["id"], r["versao"]) for r in regras if r["status_validacao"] == "A_CONFERIR"]
        if pendentes and st.button(f"✅ Aceitar {len(pendentes)} regra(s) A_CONFERIR em lote"):
            srv = RevTributariaService(db_path)
            try:
                qtd = srv.aprovar_em_lote(pendentes, usuario)
                limpar_cache()
                st.success(f"{qtd} regra(s) aprovada(s) em lote.")
            finally:
                srv.close()

        st.divider()
        opcoes = {
            f"#{r['id']} | {r['uf_origem']}→{r['uf_destino']} | NCM {r['ncm'] or '*'} | {r['status_validacao']} (v{r['versao']})": r
            for r in regras
        }
        selecao_label = st.selectbox("Selecionar regra para detalhar / editar / aceitar", list(opcoes.keys()))
        r = opcoes[selecao_label]

        col_a, col_b = st.columns([2, 1])
        with col_a:
            if r.get("fonte_url_oficial"):
                st.markdown(f"**Fonte Oficial:** [{r['fonte_url_oficial']}]({r['fonte_url_oficial']})")
            if r.get("trecho_citado"):
                st.info(f"Trecho literal da lei: \"{r['trecho_citado']}\"")
            st.write(
                f"Alíquota ICMS: **{r['aliquota_icms']}%** | Red. Base: **{r['reducao_base_icms']}%** | "
                f"ST: **{'Sim' if r['tem_st'] else 'Não'}** (MVA {r['margem_st']}%, Alíq ST {r['aliquota_icms_st']}%)"
            )
        with col_b:
            nova_aliq = st.number_input(
                "Alíquota ICMS (%)",
                value=float(r["aliquota_icms"] or 0.0),
                step=0.5,
                key=f"edit_aliq_{r['id']}",
            )
            motivo = st.text_input(
                "Motivo / Dispositivo",
                value=str(r.get("dispositivo_legal") or ""),
                key=f"edit_mot_{r['id']}",
            )
            b1, b2 = st.columns(2)
            if b1.button("💾 Salvar Edição", key="btn_save_regra"):
                srv = RevTributariaService(db_path)
                try:
                    srv.aprovar_ou_editar_regra(
                        tabela="regras_estaduais_icms",
                        registro_id=r["id"],
                        versao_atual=r["versao"],
                        alteracoes={"aliquota_icms": nova_aliq, "dispositivo_legal": motivo},
                        usuario=usuario,
                        motivo=motivo,
                    )
                    limpar_cache()
                    st.success(f"Regra #{r['id']} atualizada para v{r['versao'] + 1}.")
                except OptimisticLockError as exc:
                    st.error(str(exc))
                finally:
                    srv.close()
            if b2.button("✅ Aceitar Regra", key="btn_accept_regra"):
                srv = RevTributariaService(db_path)
                try:
                    srv.aprovar_ou_editar_regra(
                        tabela="regras_estaduais_icms",
                        registro_id=r["id"],
                        versao_atual=r["versao"],
                        alteracoes={"aliquota_icms": nova_aliq},
                        usuario=usuario,
                        motivo=motivo or "Aceite fiscal na UI",
                        aprovar=True,
                    )
                    limpar_cache()
                    st.success(f"Regra #{r['id']} aceita!")
                except OptimisticLockError as exc:
                    st.error(str(exc))
                finally:
                    srv.close()

        srv_h = RevTributariaService(db_path)
        try:
            hist = srv_h.listar_historico_regra("regras_estaduais_icms", r["id"])
        finally:
            srv_h.close()
        if hist:
            st.caption("Histórico de alterações (append-only):")
            st.dataframe(hist, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma regra encontrada com os filtros atuais.")

    with st.expander("➕ Cadastrar Nova Regra Manual"):
        with st.form("form_nova_regra"):
            mc1, mc2, mc3, mc4 = st.columns(4)
            m_orig = mc1.text_input("UF Origem", "SP")
            m_dest = mc2.text_input("UF Destino", "SP")
            m_ncm = mc3.text_input("NCM (8 dígitos)", "85171300")
            m_cest = mc4.text_input("CEST (opcional)", "")
            mc5, mc6, mc7, mc8 = st.columns(4)
            m_cfop = mc5.text_input("CFOP", "5102")
            m_cst = mc6.text_input("CST ICMS", "00")
            m_aliq = mc7.number_input("Alíquota ICMS (%)", value=18.0)
            m_st = mc8.checkbox("Tem ICMS-ST?")
            m_mva = st.number_input("MVA Original (%)", value=0.0)
            m_aliq_st = st.number_input("Alíquota ST (%)", value=18.0)
            m_disp = st.text_input("Dispositivo Legal", "RICMS/SP Art. 52")
            if st.form_submit_button("Cadastrar Regra"):
                srv = RevTributariaService(db_path)
                try:
                    novo_id = srv.criar_regra_estadual_manual(
                        uf_origem=m_orig,
                        uf_destino=m_dest,
                        ncm=m_ncm,
                        cest=m_cest,
                        cfop=m_cfop,
                        cst_icms=m_cst,
                        aliquota_icms=m_aliq,
                        tem_st=m_st,
                        margem_st=m_mva,
                        aliquota_icms_st=m_aliq_st,
                        dispositivo_legal=m_disp,
                        usuario=usuario,
                    )
                    limpar_cache()
                    st.success(f"Regra #{novo_id} criada em A_CONFERIR.")
                finally:
                    srv.close()
