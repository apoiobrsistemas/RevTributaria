"""Aba Principal: Consulta Matriz por NCM (Individual ou Lote .xlsx / .csv / .txt)."""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal

import streamlit as st

from src.app.service import RevTributariaService
from src.database.connection import init_db
from src.database.naturezas import (
    aplicar_ids_natureza_nas_linhas,
    listar_ids_naturezas_operacao_db,
    salvar_ids_naturezas_operacao_db,
)
from src.engine.fiscal_engine import (
    ContextoOperacaoFiscal,
    avaliar_operacao_bidirecional,
    resolver_parametros_estaduais,
)
from src.ui.design_system import formatar_ncm_mascara

UFS_BR = [
    "SP", "RJ", "MG", "PR", "RS", "SC", "ES", "BA", "PE", "CE",
    "GO", "DF", "MT", "MS", "PA", "AM", "MA", "PB", "RN", "AL",
    "SE", "PI", "TO", "RO", "AC", "AP", "RR",
]


def render_consulta_matriz_ncm(*, db_path: str) -> None:
    """Renderiza a consulta completa linha a linha (1 NCM ou lote de NCMs via arquivo)."""
    st.markdown(
        '<div class="rev-section-card notranslate" translate="no">'
        '<div class="rev-section-header">'
        '<div class="rev-section-badge">🔎</div>'
        '<div>'
        '<div style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:1.25rem;font-weight:700;color:#0F172A;">'
        'Consulta Matriz por NCM (CFOPs &amp; Impostos)'
        '</div>'
        '<div style="font-size:0.9rem;color:#475569;margin-top:4px;">'
        'Selecione o perfil tributário e informe o NCM para validar alíquotas, benefícios fiscais, ST e travas de rejeição.'
        '</div>'
        '</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    modo = st.radio(
        "Modo de Consulta",
        ["Consulta Individual (1 NCM)", "Importar Lista de NCMs em Lote (.xlsx / .csv / .txt)"],
        horizontal=True,
        key="cm_modo",
    )

    srv_ncm = RevTributariaService(db_path)
    try:
        ncms_disponiveis = srv_ncm.listar_ncms_disponiveis()
    finally:
        srv_ncm.close()

    regimes_emp = [
        "Lucro Real",
        "Lucro Presumido",
        "Simples Nacional",
        "Simples Nacional — Excesso de Sublimite",
        "MEI",
    ]
    atividades_emp = [
        "Varejo (Padrão)",
        "Indústria / Atacado Têxtil & Calçados (SP)",
    ]
    opcoes_dest = ["Todas (27 UFs)"] + sorted(UFS_BR)

    c1, c2, c3, c4, c5 = st.columns([1.3, 1.5, 0.8, 1.1, 1.0])
    regime_emp = c1.selectbox("Regime Tributário (Origem)", regimes_emp, index=0, key="cm_regime_emp")
    atividade_emp = c2.selectbox("Atividade / Benefício SP", atividades_emp, index=0, key="cm_atividade_emp")
    uf_orig = c3.selectbox("UF Origem", UFS_BR, index=0, key="cm_uf_orig")
    uf_dest_sel = c4.selectbox("UF Destino", opcoes_dest, index=0, key="cm_uf_dest")
    data_ref = c5.date_input("Data de Vigência", value=date.today(), key="cm_data")
    destinos_param = None if uf_dest_sel == "Todas (27 UFs)" else [uf_dest_sel]

    linhas: list[dict] = []
    ncms_sem_regra: list[str] = []
    nome_export = "planilha_padrao"

    if modo.startswith("Consulta Individual"):
        if ncms_disponiveis:
            default_idx = ncms_disponiveis.index("85071090") if "85071090" in ncms_disponiveis else 0
            ncm_sel = st.selectbox(
                "NCM cadastrado (ou digite abaixo)",
                ncms_disponiveis,
                index=default_idx,
                key="cm_ncm_sel",
            )
            ncm_manual = st.text_input("Ou digite outro NCM (8 dígitos)", value="", key="cm_ncm_manual")
            ncm = ncm_manual.strip() or ncm_sel
        else:
            ncm = st.text_input("NCM (8 dígitos)", value="85171300", key="cm_ncm_txt")

        st.caption(
            f"📌 NCM em análise: `{formatar_ncm_mascara(ncm)}` — "
            "Dica: digite os 8 dígitos sem pontos ou selecione um NCM já homologado na lista."
        )

        srv = RevTributariaService(db_path)
        try:
            pre_val = srv.validar_pre_consulta_ncms(
                [ncm],
                uf_origem=uf_orig,
                data_referencia=data_ref.isoformat(),
            )
            linhas = srv.consultar_matriz_operacional_todas_ufs(
                ncm=ncm,
                uf_origem=uf_orig,
                ufs_destino=destinos_param,
                data_referencia=data_ref.isoformat(),
                regime_tributario=regime_emp,
                atividade_empresa=atividade_emp,
            )
        finally:
            srv.close()

        sufixo = "TODAS_UFS" if uf_dest_sel == "Todas (27 UFs)" else uf_dest_sel
        nome_export = f"planilha_padrao_{ncm}_{uf_orig}_{sufixo}.xlsx"
        if not linhas:
            st.warning(
                f"Nenhuma regra encontrada para o NCM `{ncm}` ({uf_orig} → {uf_dest_sel}). "
                "Verifique na aba Matriz Legal ou importe a regra."
            )
            return
    else:
        arquivo = st.file_uploader(
            "Suba arquivo .xlsx, .csv ou .txt contendo a lista de NCMs (1 por linha ou coluna 'NCM')",
            type=["xlsx", "csv", "txt"],
            key="cm_upload_lote",
        )
        if arquivo is None:
            st.info("Envie um arquivo `.xlsx`, `.csv` ou `.txt` com os NCMs desejados para gerar a composição consolidada.")
            return

        srv = RevTributariaService(db_path)
        try:
            ncms_lote = srv.extrair_ncms_de_arquivo(arquivo.name, arquivo.getvalue())
            if not ncms_lote:
                st.error("Nenhum NCM válido de 8 dígitos foi encontrado no arquivo enviado.")
                return
            pre_val = srv.validar_pre_consulta_ncms(
                ncms_lote,
                uf_origem=uf_orig,
                data_referencia=data_ref.isoformat(),
            )
            res_lote = srv.consultar_matriz_operacional_lote(
                ncms_lote,
                uf_origem=uf_orig,
                ufs_destino=destinos_param,
                data_referencia=data_ref.isoformat(),
                regime_tributario=regime_emp,
                atividade_empresa=atividade_emp,
            )
            linhas = res_lote["linhas"]
            ncms_sem_regra = res_lote["ncms_sem_regra"]
        finally:
            srv.close()

        status_box = st.container()
        with status_box:
            st.info(
                f"Arquivo {arquivo.name} processado: {res_lote['ncms_encontrados']}/{res_lote['ncms_solicitados']} "
                f"NCM(s) encontrados ({len(linhas)} linhas geradas)."
            )
            if ncms_sem_regra:
                st.warning(f"NCMs sem regra cadastrada no banco ({len(ncms_sem_regra)}): {', '.join(ncms_sem_regra)}")

        sufixo = "TODAS_UFS" if uf_dest_sel == "Todas (27 UFs)" else uf_dest_sel
        nome_export = f"planilha_padrao_lote_{len(ncms_lote)}_ncms_{uf_orig}_{sufixo}.xlsx"
        if not linhas:
            return

    st.info(
        f"Validação Pré-Consulta: {pre_val['fontes_ativas']} fontes oficiais (.gov.br/.leg.br) ativas | "
        f"Alertas Vigia abertos: {pre_val['alertas_vigia_abertos']} | "
        f"NCMs validados (5 camadas + SRE 70/74): {pre_val['ncms_ok']} OK, "
        f"{pre_val['ncms_alerta']} Alerta(s), {pre_val['ncms_bloqueio']} Bloqueio(s)."
    )

    # Mapeamento configurável de IDs por Natureza de Operação (persistido no banco)
    _conn_nat = init_db(db_path)
    try:
        ids_salvos = listar_ids_naturezas_operacao_db(_conn_nat)
    finally:
        _conn_nat.close()

    # Garante que todas as naturezas presentes na consulta apareçam na lista (1x cada)
    naturezas_ordem = list(ids_salvos.keys())
    for l in linhas:
        nat_linha = str(l.get("Natureza de Operação") or "").strip()
        if nat_linha and nat_linha not in ids_salvos:
            ids_salvos[nat_linha] = 0
            naturezas_ordem.append(nat_linha)

    with st.expander("🔢 Configurar IDs das Naturezas de Operação (Sistema de Terceiros)", expanded=False):
        st.caption(
            "Informe o código/ID numérico de cada Natureza de Operação no seu sistema de destino. "
            "Os números ficam salvos automaticamente e aparecem na coluna 'ID Natureza' ao lado da Natureza (na tela e nos arquivos exportados)."
        )
        h_nat, h_id = st.columns([3, 1.2])
        h_nat.markdown("**Natureza de Operação**")
        h_id.markdown("**ID da Natureza**")
        novos_ids: dict[str, int] = {}
        for idx_nat, nat_nome in enumerate(naturezas_ordem):
            col_n, col_v = st.columns([3, 1.2])
            col_n.text_input(
                "Natureza",
                value=nat_nome,
                disabled=True,
                label_visibility="collapsed",
                key=f"cm_nat_nome_{idx_nat}",
            )
            novos_ids[nat_nome] = int(
                col_v.number_input(
                    f"ID {nat_nome}",
                    min_value=0,
                    step=1,
                    value=int(ids_salvos.get(nat_nome, 0)),
                    label_visibility="collapsed",
                    key=f"cm_nat_id_{idx_nat}",
                )
            )

        if novos_ids != ids_salvos:
            _conn_save = init_db(db_path)
            try:
                ids_salvos = salvar_ids_naturezas_operacao_db(_conn_save, novos_ids)
            finally:
                _conn_save.close()
            st.toast("IDs das Naturezas salvos automaticamente.", icon="✅")

    linhas = aplicar_ids_natureza_nas_linhas(linhas, ids_salvos)

    with st.expander("⚖️ Auditoria Direcional (Saída vs Entrada Inversa), Memória de Cálculo & Semáforo de Risco", expanded=False):
        d1, d2, d3, d4 = st.columns([1.4, 1.4, 1.0, 1.0])
        dir_sel = d1.selectbox(
            "Direção da Operação",
            ["SAIDA", "ENTRADA"],
            format_func=lambda x: "SAÍDA — Nossa Empresa = Emissor" if x == "SAIDA" else "ENTRADA — Nossa Empresa = Recebedor / Compra",
            key="cm_dir_op",
        )
        fin_sel = d2.selectbox(
            "Finalidade da Operação",
            ["COMERCIALIZACAO", "INDUSTRIALIZACAO", "USO_CONSUMO", "ATIVO_IMOBILIZADO", "DEVOLUCAO"],
            key="cm_fin_op",
        )
        uf_dest_dir = d3.selectbox("UF Destino (Recebedor)", UFS_BR, index=UFS_BR.index("SP"), key="cm_dir_uf_d")
        cst_dir = d4.selectbox(
            "CST / CSOSN",
            ["00", "10", "20", "30", "40", "41", "50", "51", "60", "70", "90", "101", "102", "201", "202", "500"],
            key="cm_dir_cst",
        )

        p1, p2, p3, p4 = st.columns([1.1, 1.0, 1.0, 1.2])
        vlr_dir = p1.number_input("Valor Produto (R$)", min_value=0.0, value=1000.0, step=100.0, key="cm_dir_vlr")
        mva_dir = p2.number_input("MVA Original (%)", min_value=0.0, value=0.0, step=1.0, key="cm_dir_mva")
        red_dir = p3.number_input("Redução BC (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0, key="cm_dir_red")
        cbenef_dir = p4.text_input("cBenef (se aplicável)", value="", key="cm_dir_cbenef")

        t1, t2, t3, t4 = st.columns(4)
        sn_forn = t1.checkbox("Fornecedor Simples Nacional", value=False, key="cm_dir_sn")
        tem_st_dir = t2.checkbox("Item sujeito à ST", value=cst_dir in {"10", "30", "70", "201", "202"}, key="cm_dir_st")
        proto_dir = t3.checkbox("Possui Protocolo/Convênio ST", value=False, key="cm_dir_proto")
        retido_dir = t4.checkbox("ST já retida na origem", value=False, key="cm_dir_ret")

        ncm_ctx = str(linhas[0].get("NCM") if linhas else "85071090")
        auto_fase2 = st.checkbox(
            "🤖 Preenchimento Automático via Matriz Bilateral & cBenef UF",
            value=True,
            key="cm_dir_auto_fase2",
        )
        _conn_f2 = init_db(db_path)
        try:
            params_f2 = resolver_parametros_estaduais(
                _conn_f2,
                uf_origem=uf_orig,
                uf_destino=uf_dest_dir,
                ncm=ncm_ctx,
                cst=cst_dir,
                direcao=dir_sel,
                data_operacao=data_ref.isoformat(),
            )
        finally:
            _conn_f2.close()

        cbenef_validos_lista = params_f2.get("cbenef_validos_uf") or []
        mva_efetiva = float(params_f2["mva_original"]) if (auto_fase2 and params_f2["protocolo_encontrado"]) else float(mva_dir)
        tem_st_efetivo = bool(params_f2["tem_st"]) if (auto_fase2 and params_f2["protocolo_encontrado"]) else tem_st_dir
        proto_efetivo = bool(params_f2["tem_protocolo_st"]) if (auto_fase2 and params_f2["protocolo_encontrado"]) else proto_dir
        cbenef_efetivo = cbenef_dir.strip() or (params_f2["cbenef_sugerido"] if (auto_fase2 and cst_dir in {"20", "30", "40", "41", "50", "51", "70"}) else "")

        with st.container(border=True):
            st.markdown("**📜 Acordo Interestadual & Validação cBenef**")
            ac1, ac2 = st.columns([1.3, 1.2])
            ac1.markdown(
                f"**Protocolo / Convênio:** `{params_f2['ato_legal_st']}`  \n"
                f"**Acordo Bilateral:** `{'SIM' if params_f2['tem_protocolo_st'] else 'NÃO'}` | "
                f"**MVA Original:** `{float(params_f2['mva_original']):.2f}%`"
            )
            if cbenef_validos_lista:
                opcoes_cb = [f"{c['codigo_cbenef']} — {c['descricao'][:55]}" for c in cbenef_validos_lista]
                ac2.markdown(f"**cBenef válidos em {params_f2['uf_cbenef']} (CST {cst_dir}):**")
                ac2.caption(" | ".join(opcoes_cb[:4]))
            else:
                ac2.markdown(f"**Trava CST x cBenef ({params_f2['uf_cbenef']}):** Sem cBenef obrigatório cadastrado para CST `{cst_dir}`.")

        res_dir = avaliar_operacao_bidirecional(
            ContextoOperacaoFiscal(
                direcao=dir_sel,
                finalidade=fin_sel,
                uf_origem=uf_orig,
                uf_destino=uf_dest_dir,
                ncm=ncm_ctx,
                valor_produto=Decimal(str(vlr_dir)),
                cst_ou_csosn=cst_dir,
                cbenef=cbenef_efetivo,
                aliquota_interna_destino=params_f2["aliquota_interna_destino"] if (auto_fase2 and params_f2["protocolo_encontrado"]) else None,
                aliquota_fcp=params_f2["fcp_destino"] if (auto_fase2 and params_f2["protocolo_encontrado"]) else None,
                reducao_bc_pct=Decimal(str(red_dir)),
                tem_st=tem_st_efetivo,
                tem_protocolo_st=proto_efetivo,
                st_retida_na_origem=retido_dir,
                mva_original_pct=Decimal(str(mva_efetiva)),
                fornecedor_simples_nacional=sn_forn,
            ),
            cbenef_validos=cbenef_validos_lista,
            ato_legal_st=params_f2["ato_legal_st"],
        )

        risco = res_dir["semaforo_risco"]
        if risco == "VERDE":
            st.success(f"🟢 Semáforo de Risco: VERDE — {res_dir['papel_nossa_empresa']} | CFOP {res_dir['cfop_esperado']}")
        elif risco == "AMARELO":
            st.warning(f"🟡 Semáforo de Risco: AMARELO (Atenção / Recolhimento) — {res_dir['papel_nossa_empresa']} | CFOP {res_dir['cfop_esperado']}")
        else:
            st.error(f"🔴 Semáforo de Risco: VERMELHO (Risco de Autuação/Rejeição) — {res_dir['papel_nossa_empresa']} | CFOP {res_dir['cfop_esperado']}")

        for al in res_dir["alertas_preventivos"]:
            st.warning(f"⚠️ {al}")

        col_mem, col_leg = st.columns([1.4, 1.0])
        with col_mem:
            st.markdown("**Memória de Cálculo Auditável (Passo a Passo)**")
            st.dataframe(res_dir["memoria_calculo"], use_container_width=True, hide_index=True)
        with col_leg:
            st.markdown("**Base Legal Específica**")
            for b in res_dir["bases_legais"]:
                st.markdown(f"- {b}")

    # Filtros rápidos
    f1, f2, f3, f4, f5 = st.columns(5)
    ops = [
        "Todas",
        "Compra para Comercialização",
        "Venda de Mercadorias",
        "Devolução de Compra",
        "Devolução de Venda",
        "Entrada de Transferência entre Filiais",
        "Saída de Transferência entre Filiais",
        "Outras Entradas",
        "Outras Saídas",
    ]
    op_sel = f1.selectbox("Operação", ops, key="cm_f_op")
    orig_sel = f2.selectbox("Origem", ["Todas", "Nacional", "Importado"], key="cm_f_orig")
    regimes = ["Todos"] + sorted({l["Regime ICMS"] for l in linhas})
    reg_sel = f3.selectbox("Regime ICMS", regimes, key="cm_f_reg")
    dest_sel = f4.selectbox("Perfil (NC / CO)", ["Todos", "NC (Não Contribuinte)", "CO (Contribuinte)"], key="cm_f_dest")
    ncms_no_res = ["Todos"] + sorted({str(l["NCM"]) for l in linhas})
    ncm_filtro = f5.selectbox("Filtrar NCM", ncms_no_res, key="cm_f_ncm")

    filtradas = [
        l
        for l in linhas
        if (op_sel == "Todas" or l["Natureza de Operação"] == op_sel)
        and (orig_sel == "Todas" or l["Origem"] == orig_sel)
        and (reg_sel == "Todos" or l["Regime ICMS"] == reg_sel)
        and (
            dest_sel == "Todos"
            or (dest_sel.startswith("NC") and l["Perfil (NC/CO)"] == "NC")
            or (dest_sel.startswith("CO") and l["Perfil (NC/CO)"] == "CO")
        )
        and (ncm_filtro == "Todos" or str(l["NCM"]) == ncm_filtro)
    ]

    st.caption(f"Exibindo {len(filtradas)} linha(s) ({uf_orig} -> {uf_dest_sel}).")
    st.dataframe(filtradas, use_container_width=True, hide_index=True)

    if filtradas:
        nome_base = nome_export.rsplit(".", 1)[0]
        colunas_export = list(filtradas[0].keys())

        buf_csv = io.StringIO()
        writer = csv.DictWriter(buf_csv, fieldnames=colunas_export, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(filtradas)
        csv_bytes = ("\ufeff" + buf_csv.getvalue()).encode("utf-8")

        linhas_txt = ["|".join(colunas_export)]
        for row in filtradas:
            linhas_txt.append("|".join(str(row.get(c, "")).replace("\n", " ") for c in colunas_export))
        txt_bytes = "\n".join(linhas_txt).encode("utf-8")

        st.markdown("#### 📤 Exportar Resultado")
        ex1, ex2, ex3 = st.columns(3)
        ex1.download_button(
            "📥 Baixar CSV (.csv)",
            data=csv_bytes,
            file_name=f"{nome_base}.csv",
            mime="text/csv",
            key="cm_dl_csv",
            use_container_width=True,
        )
        ex2.download_button(
            "📥 Baixar TXT (.txt)",
            data=txt_bytes,
            file_name=f"{nome_base}.txt",
            mime="text/plain",
            key="cm_dl_txt",
            use_container_width=True,
        )
        if ex3.button("⚙️ Preparar Excel (.xlsx)", key="cm_prep_xlsx", use_container_width=True):
            with st.spinner("Gerando planilhas Excel (.xlsx)..."):
                srv_exp = RevTributariaService(db_path)
                try:
                    st.session_state["cm_xlsx_bytes"] = srv_exp.exportar_matriz_padrao_xlsx(filtradas)
                    st.session_state["cm_xlsx_unica_bytes"] = srv_exp.exportar_matriz_erp_unica_xlsx(filtradas)
                    st.session_state["cm_xlsx_name"] = nome_export
                    st.session_state["cm_xlsx_qtd"] = len(filtradas)
                finally:
                    srv_exp.close()

        if st.session_state.get("cm_xlsx_bytes") and st.session_state.get("cm_xlsx_name") == nome_export:
            st.success(f"Planilhas Excel prontas ({st.session_state.get('cm_xlsx_qtd', len(filtradas))} linhas). Clique abaixo para baixar:")
            dl1, dl2 = st.columns(2)
            dl1.download_button(
                "📥 Baixar Multi-Abas (.xlsx)",
                data=st.session_state["cm_xlsx_bytes"],
                file_name=st.session_state.get("cm_xlsx_name", nome_export),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="cm_dl_xlsx_multi",
                use_container_width=True,
            )
            dl2.download_button(
                "📥 Baixar Aba Única — Layout ERP (.xlsx)",
                data=st.session_state["cm_xlsx_unica_bytes"],
                file_name="erp_" + st.session_state.get("cm_xlsx_name", nome_export),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="cm_dl_xlsx_erp",
                use_container_width=True,
            )
