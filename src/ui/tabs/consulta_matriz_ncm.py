"""Aba Principal: Consulta Matriz por NCM (Individual ou Lote .xlsx / .csv / .txt)."""

from __future__ import annotations

import csv
import importlib
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
from src.ui.design_system import formatar_ncm_mascara

UFS_BR = [
    "SP", "RJ", "MG", "PR", "RS", "SC", "ES", "BA", "PE", "CE",
    "GO", "DF", "MT", "MS", "PA", "AM", "MA", "PB", "RN", "AL",
    "SE", "PI", "TO", "RO", "AC", "AP", "RR",
]


def render_consulta_matriz_ncm(*, db_path: str) -> None:
    """Renderiza a consulta completa linha a linha (1 NCM ou lote de NCMs via arquivo)."""
    import src.engine.fiscal_engine as _fe_mod

    if not hasattr(_fe_mod, "resolver_parametros_estaduais"):
        importlib.reload(_fe_mod)
    ContextoOperacaoFiscal = _fe_mod.ContextoOperacaoFiscal
    avaliar_operacao_bidirecional = _fe_mod.avaliar_operacao_bidirecional
    resolver_parametros_estaduais = _fe_mod.resolver_parametros_estaduais

    from src.engine.lote_entrada_auditor import auditar_lote_xml_entrada
    from src.engine.reforma_tributaria_engine import ContextoReformaLC214, calcular_transicao_lc214
    from src.engine.xml_reforma_validator import validar_xml_reforma_lc214
    from src.integrations.linx_terceiro_exporter import (
        exportar_layout_linx_terceiro_csv,
        exportar_layout_linx_terceiro_xlsx,
    )
    from src.integrations.microvix_conciliador import (
        conciliar_lote_com_microvix,
        exportar_relatorio_auditoria_lote_xlsx,
    )
    import src.integrations.microvix_config_exporter as _mx_mod

    if not hasattr(_mx_mod, "exportar_matriz_ncm_69_xlsx"):
        importlib.reload(_mx_mod)
    COLUNAS_MATRIZ_NCM_69 = _mx_mod.COLUNAS_MATRIZ_NCM_69
    exportar_matriz_ncm_69_csv = _mx_mod.exportar_matriz_ncm_69_csv
    exportar_matriz_ncm_69_xlsx = _mx_mod.exportar_matriz_ncm_69_xlsx
    exportar_microvix_xlsx = _mx_mod.exportar_microvix_xlsx
    gerar_linhas_microvix = _mx_mod.gerar_linhas_microvix
    validar_matriz_ncm_69 = _mx_mod.validar_matriz_ncm_69
    validar_planilha_microvix = _mx_mod.validar_planilha_microvix
    from src.integrations.xml_entrada_parser import parsear_arquivos_entrada

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

    with st.expander("🏛️ Reforma Tributária (LC 214/2025 — IBS / CBS / IS & Validador XML gIBSCBS)", expanded=False):
        r1, r2, r3, r4 = st.columns([1.0, 1.2, 1.2, 1.0])
        ano_ref = r1.selectbox("Ano de Competência", list(range(2026, 2034)), index=0, key="cm_ref_ano")
        vlr_bruto_ref = r2.number_input("Valor Operação Bruto (R$)", min_value=0.0, value=1000.0, step=100.0, key="cm_ref_vlr")
        dir_ref = r3.selectbox("Direção (Reforma)", ["SAIDA", "ENTRADA"], key="cm_ref_dir")
        split_ok = r4.checkbox("Split Payment Liquidado?", value=True, key="cm_ref_split")

        rc1, rc2, rc3, rc4 = st.columns(4)
        icms_at = rc1.number_input("ICMS Atual (R$)", min_value=0.0, value=180.0, step=10.0, key="cm_ref_icms")
        pis_at = rc2.number_input("PIS Atual (R$)", min_value=0.0, value=16.5, step=1.0, key="cm_ref_pis")
        cof_at = rc3.number_input("COFINS Atual (R$)", min_value=0.0, value=76.0, step=1.0, key="cm_ref_cof")
        ipi_at = rc4.number_input("IPI Atual (R$)", min_value=0.0, value=0.0, step=5.0, key="cm_ref_ipi")

        ncm_ref = str(linhas[0].get("NCM") if linhas else "85071090")
        res_ref = calcular_transicao_lc214(
            ContextoReformaLC214(
                ano_calendario=int(ano_ref),
                ncm=ncm_ref,
                valor_operacao_bruto=Decimal(str(vlr_bruto_ref)),
                direcao=dir_ref,
                icms_atual=Decimal(str(icms_at)),
                pis_atual=Decimal(str(pis_at)),
                cofins_atual=Decimal(str(cof_at)),
                ipi_atual=Decimal(str(ipi_at)),
                split_payment_liquidado=split_ok,
            )
        )

        st.info(
            f"**{res_ref['fase_transicao']}** | CST IBS/CBS: `{res_ref['cst_ibs_cbs']}` | "
            f"cClassTrib: `{res_ref['cclass_trib']}` | Redução: `{res_ref['reducao_aliquota_pct']}%` "
            f"({res_ref['anexo_legal']} — {res_ref['artigo_legal']})"
        )
        for al_r in res_ref["alertas_reforma"]:
            st.warning(f"⚠️ {al_r}")

        comp_dual = [
            {
                "Sistema": "Sistema Atual (Integral)",
                "Base": f"R$ {vlr_bruto_ref:.2f}",
                "ICMS / ISS": f"R$ {icms_at:.2f}",
                "PIS / COFINS": f"R$ {pis_at + cof_at:.2f}",
                "IPI": f"R$ {ipi_at:.2f}",
                "CBS / IBS / IS": "R$ 0.00",
                "Compensação 2026": "R$ 0.00",
                "Carga Líquida Total": f"R$ {res_ref['carga_sistema_atual']}",
            },
            {
                "Sistema": f"Transição LC 214/2025 ({ano_ref})",
                "Base": f"R$ {res_ref['base_limpa_por_fora']} (por fora)",
                "ICMS / ISS": f"R$ {res_ref['icms_residual']}",
                "PIS / COFINS": f"R$ {Decimal(res_ref['pis_residual']) + Decimal(res_ref['cofins_residual'])}",
                "IPI": f"R$ {res_ref['ipi_residual']}",
                "CBS / IBS / IS": f"CBS {res_ref['valor_cbs']} | IBS {res_ref['valor_ibs_total']} | IS {res_ref['valor_is']}",
                "Compensação 2026": f"-R$ {res_ref['compensacao_2026']}",
                "Carga Líquida Total": f"R$ {res_ref['carga_liquida_transicao']}",
            },
        ]
        st.dataframe(comp_dual, use_container_width=True, hide_index=True)

        if dir_ref == "ENTRADA":
            st.caption(f"💳 **Crédito Financeiro Entrada:** {res_ref['regra_credito_reforma']}")

        xml_trecho = st.text_area(
            "Validador Rápido XML (gIBSCBS / gIS — Cole um trecho <det> ou <IBSCBS>)",
            value="",
            height=100,
            key="cm_ref_xml_txt",
        )
        if xml_trecho.strip():
            v_xml = validar_xml_reforma_lc214(xml_trecho)
            if v_xml["valido"]:
                st.success(f"✅ XML válido ({v_xml['itens_auditados']} item(ns) auditado(s)).")
            else:
                for err in v_xml["erros"]:
                    st.error(f"🚫 {err}")

    with st.expander("📥 Auditoria Lote XML de Entrada & Conciliação ERP (Linx Microvix)", expanded=False):
        l1, l2 = st.columns([2.0, 1.0])
        arqs_lote = l1.file_uploader(
            "Subir XMLs ou pacote ZIP de NF-es de Entrada (.xml / .zip)",
            type=["xml", "zip"],
            accept_multiple_files=True,
            key="cm_lote_xml_up",
        )
        fin_lote = l2.selectbox(
            "Finalidade Padrão do Lote",
            ["COMERCIALIZACAO", "INDUSTRIALIZACAO", "USO_CONSUMO", "ATIVO_IMOBILIZADO", "DEVOLUCAO"],
            key="cm_lote_fin",
        )
        if arqs_lote and st.button("🚀 Auditar Lote & Conciliar Microvix", type="primary", key="cm_lote_run"):
            payload_arqs = [(a.name, a.getvalue()) for a in arqs_lote]
            parsed_lote = parsear_arquivos_entrada(payload_arqs)
            _conn_lote = init_db(db_path)
            try:
                res_lote = auditar_lote_xml_entrada(
                    parsed_lote["notas"],
                    conn=_conn_lote,
                    finalidade_padrao=fin_lote,
                )
                divs_erp = conciliar_lote_com_microvix(_conn_lote, res_lote["itens_auditados"])
            finally:
                _conn_lote.close()
            st.session_state["cm_lote_res"] = res_lote
            st.session_state["cm_lote_erp"] = divs_erp
            st.session_state["cm_lote_erros_parse"] = parsed_lote["erros"]

        if st.session_state.get("cm_lote_res"):
            res_lote = st.session_state["cm_lote_res"]
            divs_erp = st.session_state.get("cm_lote_erp") or []
            for ep in st.session_state.get("cm_lote_erros_parse") or []:
                st.error(f"Erro XML ({ep['arquivo']}): {ep['erro']}")

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Notas Auditadas", res_lote["total_notas"])
            k2.metric("Antecipação ST (GNRE)", f"R$ {res_lote['antecipacao_st_total']:.2f}")
            k3.metric("DIFAL + FCP", f"R$ {res_lote['difal_fcp_total']:.2f}")
            k4.metric("Crédito Legítimo", f"R$ {res_lote['credito_legitimo_total']:.2f}")
            k5.metric("Crédito Glosado", f"R$ {res_lote['credito_glosado_total']:.2f}")

            risco_filtro = st.selectbox(
                "Filtrar por Semáforo de Risco",
                ["Todos", "VERMELHO", "AMARELO", "VERDE"],
                key="cm_lote_risco_f",
            )
            itens_exibir = [
                it for it in res_lote["itens_auditados"]
                if risco_filtro == "Todos" or it["Semáforo"] == risco_filtro
            ]
            st.dataframe(itens_exibir, use_container_width=True, hide_index=True)

            xlsx_exec = exportar_relatorio_auditoria_lote_xlsx(res_lote, divs_erp)
            st.download_button(
                "📥 Baixar Relatório Executivo (4 Abas .xlsx)",
                data=xlsx_exec,
                file_name="auditoria_lote_entradas_microvix.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="cm_lote_dl_xlsx",
            )

    with st.expander("📤 Exportar Configuração Tributária (69 Campos NCM & Padrão Linx Microvix)", expanded=False):
        modo_exp_cfg = st.radio(
            "Formato da Planilha",
            [
                "Matriz Completa NCM — Todos os 69 Campos (Resultado da Consulta)",
                "Template Oficial Linx Microvix — 71 Colunas (A–BS por ID Config)",
            ],
            horizontal=True,
            key="cm_mx_modo_exp",
        )
        if modo_exp_cfg.startswith("Matriz Completa"):
            val_69 = validar_matriz_ncm_69(linhas)
            if val_69["valido"]:
                st.success(f"✅ Validador APROVADO: {val_69['total_linhas']} linha(s) e {len(COLUNAS_MATRIZ_NCM_69)} colunas completas (Regime Tributário -> Observações) com preenchimento padrão Linx.")
            else:
                for er in val_69["erros"]:
                    st.error(f"🚫 {er}")
            if val_69["valido"]:
                c69_1, c69_2 = st.columns(2)
                c69_1.download_button(
                    "📥 Baixar Matriz Completa NCM (69 campos .xlsx)",
                    data=exportar_matriz_ncm_69_xlsx(linhas),
                    file_name=f"matriz_ncm_69_campos_{nome_export.rsplit('.', 1)[0]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="cm_69_dl_xlsx",
                    type="primary",
                    use_container_width=True,
                )
                c69_2.download_button(
                    "📥 Baixar Matriz Completa NCM (69 campos .csv)",
                    data=exportar_matriz_ncm_69_csv(linhas),
                    file_name=f"matriz_ncm_69_campos_{nome_export.rsplit('.', 1)[0]}.csv",
                    mime="text/csv",
                    key="cm_69_dl_csv",
                    use_container_width=True,
                )
        else:
            mx1, mx2, mx3, mx4, mx5 = st.columns([1.1, 0.9, 0.9, 1.1, 1.2])
            mx_ids = mx1.text_input("ID Config (ex: 1 ou 1,2,3,4,5)", value="1", key="cm_mx_ids")
            mx_nat = mx2.text_input("Natureza de Operação", value="43", key="cm_mx_nat")
            mx_obs = mx3.text_input("Observação Padrão (opc.)", value="", key="cm_mx_obs")
            mx_reg_pc = mx4.selectbox("Regime PIS/COFINS", ["Lucro Real", "Lucro Presumido", "Simples Nacional"], key="cm_mx_reg")
            mx_orig = mx5.selectbox(
                "Origem Mercadoria",
                ["0 - Nacional", "1 - Importação Direta", "2 - Importada Merc. Interno", "3 - Nacional >40% Imp.", "5 - Nacional <=40% Imp.", "8 - Nacional >70% Imp."],
                key="cm_mx_orig",
            )
            mx_escopo = st.radio(
                "Escopo de Exportação",
                [
                    "Modo 1 — Operação Consultada (1 linha exata por ID Config)",
                    "Modo 2 — Matriz Nacional Completa (27 UFs x Contribuinte S/N = 54 linhas por ID Config)",
                ],
                horizontal=True,
                key="cm_mx_escopo",
            )
            mx_dir_col, mx_fin_col, mx_cst_col = st.columns(3)
            mx_dir = mx_dir_col.selectbox("Direção (Regra UF Linx)", ["SAIDA", "ENTRADA"], key="cm_mx_dir")
            mx_fin = mx_fin_col.selectbox("Finalidade", ["COMERCIALIZACAO", "INDUSTRIALIZACAO", "USO_CONSUMO", "ATIVO_IMOBILIZADO", "DEVOLUCAO"], key="cm_mx_fin")
            mx_cst = mx_cst_col.selectbox("CST ICMS Base", ["00", "10", "20", "30", "40", "41", "50", "51", "60", "70", "90"], key="cm_mx_cst")

            ncm_mx = str(linhas[0].get("NCM") if linhas else "85071090")
            uf_parceiro_mx = "SP" if uf_dest_sel == "Todas (27 UFs)" else uf_dest_sel
            obs_int = int(mx_obs.strip()) if mx_obs.strip().isdigit() else None
            _conn_mx = init_db(db_path)
            try:
                linhas_mx = gerar_linhas_microvix(
                    conn=_conn_mx,
                    id_configs=mx_ids,
                    natureza_operacao=mx_nat,
                    direcao=mx_dir,
                    finalidade=mx_fin,
                    uf_empresa=uf_orig,
                    uf_parceiro=uf_parceiro_mx,
                    ncm=ncm_mx,
                    origem_mercadoria=mx_orig[0],
                    cst_icms=mx_cst,
                    regime_pis_cofins=mx_reg_pc,
                    observacao_padrao=obs_int,
                    modo_nacional_27_ufs=mx_escopo.startswith("Modo 2"),
                    data_operacao=data_ref.isoformat(),
                )
            finally:
                _conn_mx.close()

            val_mx = validar_planilha_microvix(linhas_mx)
            if val_mx["valido"]:
                st.success(f"✅ Validador Pré-Exportação APROVADO: {val_mx['total_linhas']} linha(s) e 71 colunas (A–BS) prontas para importação no Linx Microvix.")
            else:
                for er in val_mx["erros"]:
                    st.error(f"🚫 {er}")

            preview_cols = [
                "ID Config", "Natureza de Operação", "UF da Operação", "Operação com Contribuinte (S/N)",
                "CFOP", "CST ICMS", "CSOSN", "Alíquota ICMS", "Margem ST", "CST PIS", "CST COFINS", "Número da FCI",
            ]
            st.dataframe([{c: r[c] for c in preview_cols} for r in linhas_mx[:10]], use_container_width=True, hide_index=True)

            if val_mx["valido"]:
                bytes_mx = exportar_microvix_xlsx(linhas_mx)
                st.download_button(
                    "📥 Baixar Importacao_ConfigTributaria_Microvix.xlsx",
                    data=bytes_mx,
                    file_name="Importacao_ConfigTributaria_Microvix.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="cm_mx_dl_btn",
                    type="primary",
                    use_container_width=True,
                )

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
        r69_1, r69_2 = st.columns(2)
        r69_1.download_button(
            "📥 Baixar Matriz Completa — Todos os 69 Campos (.xlsx)",
            data=exportar_matriz_ncm_69_xlsx(filtradas),
            file_name=f"matriz_completa_69_campos_{nome_base}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="cm_dl_69_filtradas_xlsx",
            type="primary",
            use_container_width=True,
        )
        r69_2.download_button(
            "📥 Baixar Matriz Completa — Todos os 69 Campos (.csv)",
            data=exportar_matriz_ncm_69_csv(filtradas),
            file_name=f"matriz_completa_69_campos_{nome_base}.csv",
            mime="text/csv",
            key="cm_dl_69_filtradas_csv",
            use_container_width=True,
        )
        lx1, lx2, lx3 = st.columns([1.0, 1.4, 1.4])
        id_cfg_ini = int(
            lx1.number_input(
                "ID Config Inicial (Linx)",
                min_value=1,
                step=1,
                value=1,
                key="cm_linx_id_cfg",
            )
        )
        linx_csv_bytes = exportar_layout_linx_terceiro_csv(
            filtradas,
            id_config_inicial=id_cfg_ini,
            ids_natureza=ids_salvos,
        )
        lx2.download_button(
            "📥 Exportar Padrão Linx Terceiros (.csv)",
            data=linx_csv_bytes,
            file_name=f"linx_terceiros_{nome_base}.csv",
            mime="text/csv",
            key="cm_dl_linx_csv",
            use_container_width=True,
        )
        if lx3.button("⚙️ Gerar Padrão Linx Terceiros (.xlsx)", key="cm_prep_linx_xlsx", use_container_width=True):
            with st.spinner("Gerando planilha no layout oficial Linx (71 colunas)..."):
                st.session_state["cm_linx_xlsx_bytes"] = exportar_layout_linx_terceiro_xlsx(
                    filtradas,
                    id_config_inicial=id_cfg_ini,
                    ids_natureza=ids_salvos,
                )
                st.session_state["cm_linx_xlsx_name"] = f"linx_terceiros_{nome_base}.xlsx"

        if st.session_state.get("cm_linx_xlsx_bytes") and st.session_state.get("cm_linx_xlsx_name") == f"linx_terceiros_{nome_base}.xlsx":
            st.download_button(
                "📥 Baixar Padrão Linx Terceiros (.xlsx)",
                data=st.session_state["cm_linx_xlsx_bytes"],
                file_name=st.session_state["cm_linx_xlsx_name"],
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="cm_dl_linx_xlsx",
                use_container_width=True,
            )

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
