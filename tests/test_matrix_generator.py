"""Testes do gerador completo de matriz operacional por NCM (matrix_generator.py)."""

from __future__ import annotations

import io

import openpyxl

from src.app.seed_sp import executar_seed_sp
from src.app.service import RevTributariaService
from src.engine import gerar_matriz_ncm

COLUNAS_ESPERADAS = [
    "Regime Tributário",
    "NCM",
    "Rota",
    "UF Origem",
    "Natureza de Operação",
    "UF da Operação",
    "Operação com Contribuinte (S/N)",
    "CFOP",
    "CST ICMS",
    "CSOSN",
    "Observação Padrão",
    "Alíquota ICMS",
    "Red. Base ICMS",
    "Gera Crédito/Débito (S/N)",
    "Escriturar Valores sem Tributação como",
    "Valor Tributável ICMS",
    "Deduz ICMS/FCP do custo médio (S/N)",
    "Base de cálculo ICMS Obtida pelo Lucro (S/N)",
    "Alíquota FCP",
    "Somar IPI Base DIFAL FCP (S/N)",
    "Considerar Redução de base do ICMS no cálculo do FCP (S/N)",
    "Alíquota interna da UF Destino (DIFAL)",
    "Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)",
    "Utiliza base de cálculo Dupla (DIFAL)",
    "Alíquota ICMS Desonerado",
    "Alíquota FCP Desonerado",
    "Motivo Desoneração",
    "Código Beneficio Fiscal",
    "Percentual Crédito Presumido",
    "Deduz ICMS Desonerado Total Nota (S/N)",
    "Alíquota Diferimento",
    "Percentual FCP Diferimento",
    "Observação Complementar Diferimento",
    "Alíquota ICMS ST",
    "Margem ST",
    "Redução ICMS ST",
    "Utiliza Base ICMS p/ Cálculo ST (S/N)",
    "ICMS ST pago pela empresa em guia (S/N)",
    "Não deduzir o ICMS do cálculo do ICMS ST (S/N)",
    "Utiliza cálculo ICMS ST através do regime de estimativa simplificado (S/N)",
    "Percentual de carga tributária média (%)",
    "Somar ICMS/ST FCP-ST no Custo Médio (S/N)",
    "Alíquota ICMS Efetivo",
    "Redução de Base ICMS Efetivo",
    "CST PIS",
    "Alíquota PIS",
    "CST COFINS",
    "Alíquota COFINS",
    "Operação de Receita (S/N)",
    "Código Tipo Base de Crédito PIS/COFINS",
    "Base de Cálculo PIS/COFINS Obtida p/ Lucro (S/N)",
    "CST IPI",
    "Código Enquadramento IPI",
    "IPI Gera Crédito/Débito (S/N)",
    "Escriturar Valores Sem Tributação Como (base 2 ou base 3)",
    "CEST",
    "Origem",
    "Regime ICMS",
    "CRT",
    "Perfil (NC/CO)",
    "ICMS Crédito/Débito",
    "PIS/COFINS Crédito/Débito",
    "% MVA ST Ajustada",
    "DIFAL / FCP",
    "IPI Alíq.",
    "cClass",
    "Alíquota CBS",
    "Alíquota IBS",
    "Observações",
]


def test_gerar_matriz_ncm_st_com_reducao_nacional_e_importado():
    regra_est = {
        "cest": "2105301",
        "tem_st": 1,
        "tem_acordo_st": 1,
        "aliquota_icms": 18.0,
        "reducao_base_icms": 33.33,
        "aliquota_icms_st": 20.0,
        "margem_st": 49.0,
        "aliquota_fcp": 2.0,
        "codigo_beneficio_fiscal": "SP020027",
        "dispositivo_legal": "Convênio ICMS 142/2018",
    }
    regra_fed = {
        "aliquota_ipi": 5.0,
        "cst_pis_saida": "01",
        "aliquota_pis": 1.65,
        "cst_cofins_saida": "01",
        "aliquota_cofins": 7.60,
        "cst_ibs_cbs": "000",
        "cclass_trib": "000001",
        "aliquota_cbs": 8.80,
        "aliquota_ibs_uf": 15.0,
        "aliquota_ibs_mun": 2.7,
    }

    linhas = gerar_matriz_ncm(
        "85171300",
        "SP",
        "RJ",
        regra_est,
        regra_federal=regra_fed,
    )
    assert len(linhas) > 0
    assert list(linhas[0].keys()) == COLUNAS_ESPERADAS

    ops = {l["Natureza de Operação"] for l in linhas}
    assert ops == {
        "Compra para Comercialização",
        "Venda de Mercadorias",
        "Devolução de Compra",
        "Devolução de Venda",
        "Entrada de Transferência entre Filiais",
        "Saída de Transferência entre Filiais",
        "Outras Entradas",
        "Outras Saídas",
    }

    # Compra ST com protocolo: Nacional (12%, MVA ajustada 68.10) vs Importado (4%, MVA ajustada > 68.10)
    compras_st = [
        l for l in linhas
        if l["Natureza de Operação"] == "Compra para Comercialização" and l["Regime ICMS"] == "ST"
    ]
    nac = next(l for l in compras_st if l["Origem"] == "Nacional")
    imp = next(l for l in compras_st if l["Origem"] == "Importado")

    assert nac["CFOP"] == "2.403"
    assert nac["CST ICMS"] == "0.70"  # redução BC presente
    assert nac["Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)"] == 12.0
    assert nac["% MVA ST Ajustada"] == 68.10

    assert imp["CST ICMS"] == "2.70"
    assert imp["Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)"] == 4.0
    assert imp["% MVA ST Ajustada"] > nac["% MVA ST Ajustada"]

    # Compra ST sem protocolo (Não Signatário)
    sem_prot = [
        l for l in linhas
        if l["Natureza de Operação"] == "Compra para Comercialização" and l["Regime ICMS"] == "ST (Sem Protocolo)"
    ]
    assert len(sem_prot) == 2
    assert "NÃO SIGNATÁRIO" in sem_prot[0]["Observações"]

    # Venda: Contribuinte (6.404 / 6.102) vs Não Contribuinte (6.108 + DIFAL)
    vendas_st_contrib = [
        l for l in linhas
        if l["Natureza de Operação"] == "Venda de Mercadorias"
        and l["Regime ICMS"] == "ST"
        and l["Operação com Contribuinte (S/N)"] == "S"
    ]
    vendas_st_nc = [
        l for l in linhas
        if l["Natureza de Operação"] == "Venda de Mercadorias"
        and l["Regime ICMS"] == "ST"
        and l["Operação com Contribuinte (S/N)"] == "N"
    ]
    assert all(l["CFOP"] == "6.404" for l in vendas_st_contrib)
    assert all(l["CFOP"] == "6.108" and "DIFAL" in l["DIFAL / FCP"] for l in vendas_st_nc)


def test_service_consulta_matriz_operacional_e_exportacao_multi_abas(tmp_path):
    db_file = tmp_path / "matrix_gen.db"
    executar_seed_sp(db_file, usar_rede=False, gerar_template=False)

    srv = RevTributariaService(db_file)
    try:
        linhas = srv.consultar_matriz_operacional("85071090", "SP", "RJ", data_referencia="2026-06-01")
        assert len(linhas) >= 16

        xlsx_bytes = srv.exportar_matriz_padrao_xlsx(linhas)
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True)
        try:
            assert wb.sheetnames == [
                "Compras Comercialização",
                "Venda de Mercadorias",
                "Devoluções & Outras",
                "Transferências Filiais",
            ]
            assert len(list(wb["Compras Comercialização"].iter_rows(values_only=True))) > 1
            assert len(list(wb["Venda de Mercadorias"].iter_rows(values_only=True))) > 1
            assert len(list(wb["Devoluções & Outras"].iter_rows(values_only=True))) > 1
        finally:
            wb.close()
    finally:
        srv.close()


def test_consultar_matriz_todas_ufs_ordenacao_nc_primeiro_depois_co(tmp_path):
    db_file = tmp_path / "matrix_27ufs.db"
    executar_seed_sp(db_file, usar_rede=False, gerar_template=False)

    srv = RevTributariaService(db_file)
    try:
        linhas = srv.consultar_matriz_operacional_todas_ufs(
            "85071090", "SP", data_referencia="2026-06-01"
        )
        assert len(linhas) >= 27 * 10
        assert {l["UF da Operação"] for l in linhas} == {
            "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
            "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
            "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
        }
        assert "SP > AC" in {l["Rota"] for l in linhas}

        # Dentro de Nacional, todas as linhas NC devem vir antes das linhas CO
        nacionais = [l for l in linhas if l["Origem"] == "Nacional"]
        perfis_nac = [l["Perfil (NC/CO)"] for l in nacionais]
        assert perfis_nac.index("CO") > 0
        assert "NC" not in perfis_nac[perfis_nac.index("CO"):]

        # Dentro de Nacional + CO + Compra para Comercialização, Tributado Integralmente vem antes de ST
        compras_co = [
            l for l in nacionais
            if l["Perfil (NC/CO)"] == "CO" and l["Natureza de Operação"] == "Compra para Comercialização"
        ]
        regimes_compra = [l["Regime ICMS"] for l in compras_co]
        assert regimes_compra.index("ST") > 0
        assert "Tributado Integralmente" not in regimes_compra[regimes_compra.index("ST"):]
    finally:
        srv.close()


def test_regimes_tributarios_credito_debito_e_difal(tmp_path):
    db_file = tmp_path / "regimes.db"
    executar_seed_sp(db_file, usar_rede=False, gerar_template=False)
    srv = RevTributariaService(db_file)
    try:
        # 1. Simples Nacional (CRT 1): sem destaque ICMS próprio, sem crédito PIS/COFINS, DIFAL dispensado
        linhas_sn = srv.consultar_matriz_operacional_todas_ufs(
            "85171300", "SP", ufs_destino=["RJ"], data_referencia="2026-10-15", regime_tributario="Simples Nacional"
        )
        assert list(linhas_sn[0].keys())[0] == "Regime Tributário"
        assert linhas_sn[0]["Regime Tributário"] == "Simples Nacional"
        assert linhas_sn[0]["CRT"] == "1"
        venda_nc_sn = next(l for l in linhas_sn if l["Natureza de Operação"] == "Venda de Mercadorias" and l["Perfil (NC/CO)"] == "NC")
        assert venda_nc_sn["CST ICMS"] == "-"
        assert "Dispensado" in venda_nc_sn["DIFAL / FCP"]
        assert venda_nc_sn["Alíquota PIS"] == 0.0

        # 2. Excesso de Sublimite (CRT 2): destaca ICMS e recolhe DIFAL, mas PIS/COFINS no DAS
        linhas_sub = srv.consultar_matriz_operacional_todas_ufs(
            "85171300", "SP", ufs_destino=["RJ"], data_referencia="2026-10-15", regime_tributario="Simples Nacional — Excesso de Sublimite"
        )
        assert linhas_sub[0]["CRT"] == "2"
        venda_nc_sub = next(l for l in linhas_sub if l["Natureza de Operação"] == "Venda de Mercadorias" and l["Perfil (NC/CO)"] == "NC")
        assert venda_nc_sub["CST ICMS"] != "-"
        assert "DIFAL" in venda_nc_sub["DIFAL / FCP"] and "Dispensado" not in venda_nc_sub["DIFAL / FCP"]
        assert venda_nc_sub["Alíquota PIS"] == 0.0

        # 3. Lucro Presumido (CRT 3): 0,65% / 3,00% na venda, sem crédito na compra
        linhas_lp = srv.consultar_matriz_operacional_todas_ufs(
            "85171300", "SP", ufs_destino=["RJ"], data_referencia="2026-10-15", regime_tributario="Lucro Presumido"
        )
        compra_lp = next(l for l in linhas_lp if l["Natureza de Operação"] == "Compra para Comercialização")
        venda_lp = next(l for l in linhas_lp if l["Natureza de Operação"] == "Venda de Mercadorias")
        assert compra_lp["Alíquota PIS"] == 0.0
        assert "Sem Crédito" in compra_lp["PIS/COFINS Crédito/Débito"]
        assert venda_lp["Alíquota PIS"] == 0.65
        assert venda_lp["Alíquota COFINS"] == 3.00
        assert venda_lp["Alíquota interna da UF Destino (DIFAL)"] == 20.0
        assert venda_lp["Alíquota FCP"] == 2.0
        assert venda_lp["Operação de Receita (S/N)"] == "S"
        assert compra_lp["Operação de Receita (S/N)"] == "N"
    finally:
        srv.close()


def test_importacao_lote_ncms_txt_csv_xlsx_e_consolidacao(tmp_path):
    db_file = tmp_path / "lote_ncm.db"
    executar_seed_sp(db_file, usar_rede=False, gerar_template=False)

    srv = RevTributariaService(db_file)
    try:
        # 1. TXT com pontos e sem pontos
        ncms_txt = srv.extrair_ncms_de_arquivo("lista.txt", b"8517.13.00\n85071090\n8517.13.00\n")
        assert ncms_txt == ["85171300", "85071090"]

        # 2. CSV com cabeçalho
        ncms_csv = srv.extrair_ncms_de_arquivo("lista.csv", "ncm;descricao\n85171300;Celular\n84716053;Mouse\n".encode("utf-8"))
        assert ncms_csv == ["85171300", "84716053"]

        # 3. XLSX
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["NCM", "Produto"])
        ws.append(["8517.13.00", "Celular"])
        ws.append(["8507.10.90", "Bateria"])
        buf = io.BytesIO()
        wb.save(buf)
        ncms_xlsx = srv.extrair_ncms_de_arquivo("lista.xlsx", buf.getvalue())
        assert ncms_xlsx == ["85171300", "85071090"]

        # 4. Consolidação em lote (2 válidos + 1 inexistente)
        res = srv.consultar_matriz_operacional_lote(
            ["85171300", "85071090", "99999999"],
            uf_origem="SP",
            ufs_destino=["RJ"],
            data_referencia="2026-10-15",
            regime_tributario="Lucro Real",
        )
        assert res["ncms_solicitados"] == 3
        assert res["ncms_encontrados"] == 2
        assert res["ncms_sem_regra"] == ["99999999"]
        assert {l["NCM"] for l in res["linhas"]} == {"85171300", "85071090"}

        # Exportação consolidada em único .xlsx
        xlsx_out = srv.exportar_matriz_padrao_xlsx(res["linhas"])
        assert len(xlsx_out) > 0
    finally:
        srv.close()


def test_atividade_industria_atacado_textil_calcados_sp():
    regra_est = {
        "cest": "",
        "tem_st": 0,
        "aliquota_icms": 18.0,
        "reducao_base_icms": 0.0,
        "dispositivo_legal": "RICMS/SP",
    }
    # Cap. 61 (Confecções): Venda SP -> SP Contribuinte ganha redução 33,33% (CST 20, SP020052)
    linhas_61 = gerar_matriz_ncm(
        "61091000",
        "SP",
        "SP",
        regra_est,
        atividade_empresa="Indústria / Atacado Têxtil & Calçados (SP)",
    )
    venda_co = next(
        l for l in linhas_61
        if l["Natureza de Operação"] == "Venda de Mercadorias"
        and l["Origem"] == "Nacional"
        and l["Operação com Contribuinte (S/N)"] == "S"
    )
    venda_nc = next(
        l for l in linhas_61
        if l["Natureza de Operação"] == "Venda de Mercadorias"
        and l["Origem"] == "Nacional"
        and l["Operação com Contribuinte (S/N)"] == "N"
    )
    assert venda_co["CST ICMS"] == "0.20"
    assert venda_co["Red. Base ICMS"] == 33.33
    assert venda_co["Código Beneficio Fiscal"] == "SP020052"
    assert venda_nc["CST ICMS"] == "0.00"
    assert venda_nc["Red. Base ICMS"] == 0.0

    # Transferência entre Filiais: CST 0.41 (Nacional) e 2.41 (Importado) por ADC 49 STF
    transf_nac = next(
        l for l in linhas_61
        if l["Natureza de Operação"] == "Saída de Transferência entre Filiais"
        and l["Origem"] == "Nacional"
    )
    transf_imp = next(
        l for l in linhas_61
        if l["Natureza de Operação"] == "Saída de Transferência entre Filiais"
        and l["Origem"] == "Importado"
    )
    assert transf_nac["CST ICMS"] == "0.41"
    assert transf_nac["Alíquota ICMS"] == 0.0
    assert transf_nac["Código Beneficio Fiscal"] == "SP030007"
    assert transf_imp["CST ICMS"] == "2.41"
    assert transf_imp["Alíquota ICMS"] == 0.0
    assert transf_imp["Código Beneficio Fiscal"] == "SP030007"

    # Interestadual Importado (SP -> RJ): Alíquota ICMS = 4.0% (Resolução Senado 13/2012)
    linhas_inter = gerar_matriz_ncm("61091000", "SP", "RJ", regra_est)
    venda_inter_imp = next(
        l for l in linhas_inter
        if l["Natureza de Operação"] == "Venda de Mercadorias"
        and l["Origem"] == "Importado"
        and l["Operação com Contribuinte (S/N)"] == "S"
    )
    assert venda_inter_imp["Alíquota ICMS"] == 4.0
    assert venda_inter_imp["Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)"] == 4.0


def test_isencao_cbenef_obrigatorio_e_validacao_pre_consulta(tmp_path):
    regra_isenta = {
        "cest": "",
        "tem_st": 0,
        "cst_icms": "40",
        "aliquota_icms": 0.0,
        "reducao_base_icms": 0.0,
        "dispositivo_legal": "RICMS/SP Anexo I",
    }
    linhas_is = gerar_matriz_ncm("84321000", "SP", "SP", regra_isenta)
    venda_is = next(
        l for l in linhas_is
        if l["Natureza de Operação"] == "Venda de Mercadorias" and l["Origem"] == "Nacional"
    )
    assert venda_is["CST ICMS"] == "0.40"
    assert venda_is["Regime ICMS"] == "Isento / Benefício"
    assert venda_is["Alíquota ICMS"] == 0.0
    assert venda_is["Código Beneficio Fiscal"] == "SP010000"

    db_file = tmp_path / "pre_val.db"
    executar_seed_sp(db_file, usar_rede=False, gerar_template=False)
    srv = RevTributariaService(db_file)
    try:
        pre = srv.validar_pre_consulta_ncms(["85171300", "85071090"], uf_origem="SP", data_referencia="2026-10-15")
        assert pre["fontes_ativas"] >= 24
        assert pre["ncms_validados"] == 2
        assert len(pre["detalhes"]) == 2
    finally:
        srv.close()


def test_simulador_fallback_uf_origem_e_espelho_xml(tmp_path):
    db_file = tmp_path / "sim_fb.db"
    srv = RevTributariaService(db_file)
    try:
        conn = srv._get_conn()
        with conn:
            conn.execute(
                "INSERT INTO regras_federais (ncm, descricao_ncm, vigencia_inicio, cst_pis_saida, aliquota_pis, cst_cofins_saida, aliquota_cofins) VALUES ('61091000', 'Camiseta', '2026-01-01', '01', 1.65, '01', 7.60)"
            )
            conn.execute(
                "INSERT INTO regras_estaduais_icms (uf_origem, uf_destino, ncm, natureza_operacao, operacao_com_contribuinte, origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms) VALUES ('SP', 'SP', '61091000', 'VENDA', 1, '*', '2026-01-01', '5102', '00', 18.0)"
            )

        res = srv.simular_calculo_item(
            uf_origem="SP",
            uf_destino="RJ",
            ncm="61091000",
            valor=1000.0,
            contribuinte=True,
        )
        assert float(res["aliquota_icms"]) == 12.0
        assert res["valor_icms_proprio"] == "120.00"
        assert len(res["espelho_xml"]) == 9
        assert res["espelho_xml"][0]["Grupo XML"] == "<prod>"
    finally:
        srv.close()

    # Cap. 64 (Calçados): Venda SP -> SP Contribuinte referencia Anexo III Art. 43
    linhas_64 = gerar_matriz_ncm(
        "64039990",
        "SP",
        "SP",
        {
            "cest": "",
            "tem_st": 0,
            "aliquota_icms": 18.0,
            "reducao_base_icms": 0.0,
            "dispositivo_legal": "RICMS/SP",
        },
        atividade_empresa="Indústria / Atacado Têxtil & Calçados (SP)",
    )
    venda_64_co = next(
        l for l in linhas_64
        if l["Natureza de Operação"] == "Venda de Mercadorias"
        and l["Origem"] == "Nacional"
        and l["Operação com Contribuinte (S/N)"] == "S"
    )
    assert "Anexo III Art. 43" in venda_64_co["Observação Padrão"]
