"""Aba 3: Auditor de XML NF-e (Frente A) — Comparativo Linha a Linha (Nota x Lei)."""

from __future__ import annotations

from typing import Callable

import pandas as pd
import streamlit as st

from src.app.service import RevTributariaService


def _estilizar_comparativo(df: pd.DataFrame, celulas_divergentes: dict[tuple[int, str], str]) -> "pd.io.formats.style.Styler":
    """Destaca Check (✅/❌) e as células divergentes (Nota em vermelho, Lei em verde)."""

    def _aplicar(data: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=data.index, columns=data.columns)
        for idx, row in data.iterrows():
            n_item = int(row["Item"])
            reg = str(row["Registro"])
            chk = str(row["Check"])

            if chk == "❌":
                styles.at[idx, "Check"] = "background-color: #991b1b; color: #ffffff; font-weight: 700;"
            elif chk == "✅":
                styles.at[idx, "Check"] = "background-color: #166534; color: #ffffff; font-weight: 700;"
            elif chk == "⚠️":
                styles.at[idx, "Check"] = "background-color: #92400e; color: #ffffff; font-weight: 700;"

            if reg == "Lei (Esperado)":
                styles.at[idx, "Registro"] = "background-color: #0f172a; color: #93c5fd; font-weight: 600;"
            else:
                styles.at[idx, "Registro"] = "font-weight: 600;"

            for col in data.columns:
                sev = celulas_divergentes.get((n_item, col))
                if not sev:
                    continue
                if reg == "NF-e (Nota)":
                    if sev == "DIVERGENTE":
                        styles.at[idx, col] = "background-color: #7f1d1d; color: #fecaca; font-weight: 700; border: 2px solid #ef4444;"
                    else:
                        styles.at[idx, col] = "background-color: #78350f; color: #fde68a; font-weight: 700;"
                else:
                    if sev == "DIVERGENTE":
                        styles.at[idx, col] = "background-color: #14532d; color: #bbf7d0; font-weight: 700; border: 2px solid #22c55e;"
                    else:
                        styles.at[idx, col] = "background-color: #1e3a8a; color: #bfdbfe; font-weight: 700;"
        return styles

    return df.style.apply(_aplicar, axis=None)


def render_aba_auditor_xml(
    *,
    db_path: str,
    carregar_nfes: Callable[[str], list[dict]],
    limpar_cache: Callable[[], None],
) -> None:
    """Renderiza upload múltiplo, painel do emitente (CNPJ/CRT) e grade 2-linhas-por-item."""
    st.subheader("Auditor de XML NF-e (Frente A) — Comparativo Produto a Produto")
    arquivos = st.file_uploader(
        "Suba um ou mais XMLs de NF-e",
        type=["xml"],
        accept_multiple_files=True,
        key="xml_uploader_multi",
    )
    msg_box = st.empty()
    if arquivos and st.button("🚀 Auditar XMLs Enviados", type="primary", key="btn_auditar_xmls"):
        srv = RevTributariaService(db_path)
        mensagens: list[str] = []
        try:
            for arq in arquivos:
                xml_str = arq.read().decode("utf-8", errors="replace")
                res = srv.executar_auditoria_nfe(xml_str)
                st.session_state["xml_chave_sel"] = res["chave_acesso"]
                novos_est = res.get("ncms_estaduais_adicionados", 0)
                novos_fed = res.get("ncms_federais_adicionados", 0)
                extra_msg = (
                    f" | +{novos_est} regra(s) estadual(is) e +{novos_fed} federal(is) adicionada(s) à base."
                    if (novos_est or novos_fed)
                    else ""
                )
                mensagens.append(
                    f"NF-e {res['chave_acesso']} auditada — {res['total_divergencias']} divergência(s) encontrada(s){extra_msg}"
                )
            st.session_state["xml_ultimo_resumo"] = " ; ".join(mensagens)
            limpar_cache()
        finally:
            srv.close()

    if st.session_state.get("xml_ultimo_resumo"):
        msg_box.info(st.session_state["xml_ultimo_resumo"])

    nfes = carregar_nfes(db_path)
    if not nfes:
        st.info("Nenhuma NF-e importada ainda. Suba um arquivo `.xml` acima para iniciar.")
        return

    with st.expander(f"📋 Notas Fiscais Importadas (`vw_nfe_status` — {len(nfes)} nota(s))", expanded=False):
        st.dataframe(nfes, use_container_width=True, hide_index=True)

    opcoes_chave = [f"{n['numero_nf']} | {n['uf_emitente']}->{n['uf_destinatario']} | {n['chave_acesso']}" for n in nfes]
    chave_default = st.session_state.get("xml_chave_sel", nfes[0]["chave_acesso"])
    idx_def = next((i for i, n in enumerate(nfes) if n["chave_acesso"] == chave_default), 0)
    sel_label = st.selectbox("Selecione a NF-e para análise item a item", opcoes_chave, index=idx_def)
    chave_sel = nfes[opcoes_chave.index(sel_label)]["chave_acesso"]

    srv_meta = RevTributariaService(db_path)
    try:
        emit_info = srv_meta.consultar_regime_emitente_nfe(chave_sel)
    finally:
        srv_meta.close()

    with st.expander("🏢 Dados do Emitente (CNPJ / CRT do XML / Operação)", expanded=True):
        e1, e2, e3, e4 = st.columns(4)
        e1.text_input("CNPJ Emitente", value=emit_info.get("cnpj_emitente", ""), disabled=True)
        e2.text_input("Razão Social", value=emit_info.get("razao_emitente", ""), disabled=True)
        e3.text_input("Natureza XML (natOp)", value=emit_info.get("nat_op", ""), disabled=True)
        e4.text_input(
            "CRT / Tipo",
            value=f"CRT {emit_info.get('crt_emitente', '3')} ({emit_info.get('tipo_operacao_xml', 'Saída')})",
            disabled=True,
        )

        opcoes_reg = [
            "Lucro Real",
            "Lucro Presumido",
            "Simples Nacional",
            "Simples Nacional — Excesso de Sublimite",
            "MEI",
        ]
        reg_atual = str(emit_info.get("regime_apuracao") or "Lucro Real")
        idx_reg = next((i for i, r in enumerate(opcoes_reg) if r in reg_atual), 0)
        c_reg, c_nat, c_btn = st.columns([2, 1.5, 1])
        regime_escolhido = c_reg.selectbox("Regime do Emitente (Confirmar/Ajustar)", opcoes_reg, index=idx_reg)
        nat_audit = c_nat.selectbox("Operação para Auditoria", ["VENDA", "COMPRA_REVENDA", "TRANSFERENCIA"], index=0)
        contrib_dest = emit_info.get("contribuinte_dest", "S") == "S"
        if c_btn.button("🔄 Reaplicar Regime & Auditar"):
            srv_re = RevTributariaService(db_path)
            try:
                srv_re.consultar_regime_emitente_nfe(chave_sel, regime_manual=regime_escolhido)
                limpar_cache()
                st.success(f"Regime '{regime_escolhido}' vinculado ao CNPJ {emit_info.get('cnpj_emitente', '')}.")
            finally:
                srv_re.close()

    srv_cmp = RevTributariaService(db_path)
    try:
        comp = srv_cmp.gerar_comparativo_nfe_item_a_item(
            chave_sel,
            natureza_operacao=nat_audit,
            operacao_com_contribuinte=contrib_dest,
            regime_emitente=regime_escolhido,
        )
    finally:
        srv_cmp.close()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total de Itens", comp["total_itens"])
    m2.metric("✅ Itens OK", comp["itens_ok"])
    m3.metric("❌ Itens Divergentes", comp["itens_divergentes"])
    m4.metric("⚠️ Sem Regra / Atenção", comp["itens_sem_regra"])

    f1, f2 = st.columns([2, 1])
    filtro_itens = f1.radio(
        "Exibir",
        ["Todos os itens", "Somente Divergentes (❌)", "Somente Sem Regra/Atenção (⚠️)"],
        horizontal=True,
        key="xml_filtro_itens",
    )

    linhas = comp["linhas"]
    if filtro_itens.startswith("Somente Divergentes"):
        itens_alvo = {l["Item"] for l in linhas if l["Check"] == "❌"}
        linhas = [l for l in linhas if l["Item"] in itens_alvo]
    elif filtro_itens.startswith("Somente Sem Regra"):
        itens_alvo = {l["Item"] for l in linhas if l["Check"] == "⚠️"}
        linhas = [l for l in linhas if l["Item"] in itens_alvo]

    # Paginação de 100 itens (200 linhas) para suportar notas de 1000+ itens com fluidez
    itens_por_pag = 100
    linhas_por_pag = itens_por_pag * 2
    total_pags = max(1, (len(linhas) + linhas_por_pag - 1) // linhas_por_pag)
    pag = int(f2.number_input("Página (100 itens/pág.)", min_value=1, max_value=total_pags, value=1, step=1))
    ini = (pag - 1) * linhas_por_pag
    fim = ini + linhas_por_pag
    linhas_pag = linhas[ini:fim]

    if linhas_pag:
        df = pd.DataFrame(linhas_pag)
        styler = _estilizar_comparativo(df, comp["celulas_divergentes"])
        st.caption(
            f"Exibindo linhas {ini + 1}–{min(fim, len(linhas))} de {len(linhas)} "
            "(Linha 1 = NF-e / Nota | Linha 2 = Lei / Esperado)."
        )
        st.dataframe(styler, use_container_width=True, hide_index=True)

        srv_exp = RevTributariaService(db_path)
        try:
            xlsx_bytes = srv_exp.exportar_matriz_erp_unica_xlsx(linhas)
        finally:
            srv_exp.close()
        st.download_button(
            "📥 Exportar Auditoria Item a Item (.xlsx)",
            data=xlsx_bytes,
            file_name=f"auditoria_nfe_{chave_sel}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.success("Nenhum item encontrado para o filtro selecionado.")
