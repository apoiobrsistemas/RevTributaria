"""Testes do Motor Fiscal Bidirecional (Saída vs Entrada Inversa, 27 UFs, CST/CSOSN, ST, RBC e DIFAL)."""

from __future__ import annotations

from decimal import Decimal

from src.app.service import RevTributariaService
from src.engine.fiscal_engine import (
    ALIQUOTAS_INTERNAS_UF,
    ContextoOperacaoFiscal,
    avaliar_operacao_bidirecional,
)
from src.legislation.official_catalog import CATALOGO_FONTES_OFICIAIS
from src.legislation.url_guard import validar_url_oficial


def test_catalogo_cobre_todas_27_ufs_e_urls_oficiais() -> None:
    ufs_catalogo = {f["uf"] for f in CATALOGO_FONTES_OFICIAIS if f["uf"] != "BR"}
    assert len(ufs_catalogo) == 27
    assert ufs_catalogo == set(ALIQUOTAS_INTERNAS_UF.keys())
    for fonte in CATALOGO_FONTES_OFICIAIS:
        validar_url_oficial(str(fonte["url_oficial"]))


def test_entrada_inversa_st_mva_ajustada_e_trava_simples_nacional() -> None:
    # Fornecedor Lucro Real (SC 12%) -> Nossa Empresa (SP 18%) sem protocolo -> Antecipação + MVA Ajustada
    ctx_normal = ContextoOperacaoFiscal(
        direcao="ENTRADA",
        finalidade="COMERCIALIZACAO",
        uf_origem="SC",
        uf_destino="SP",
        ncm="85071090",
        valor_produto=Decimal("1000.00"),
        cst_ou_csosn="00",
        tem_st=True,
        tem_protocolo_st=False,
        mva_original_pct=Decimal("40.00"),
        fornecedor_simples_nacional=False,
    )
    res_norm = avaliar_operacao_bidirecional(ctx_normal)
    assert res_norm["uf_legislacao_aplicavel"] == "SP"
    assert res_norm["cfop_esperado"] == "2403"
    assert Decimal(res_norm["mva_aplicada_pct"]) > Decimal("40.00")
    assert Decimal(res_norm["antecipacao_st_entrada"]) > Decimal("0")
    assert Decimal(res_norm["credito_admitido"]) == Decimal("0")
    assert res_norm["semaforo_risco"] == "AMARELO"

    # Fornecedor Simples Nacional -> Trava Convênio 142/2018 mantém MVA Original (40.00%)
    ctx_sn = ContextoOperacaoFiscal(
        direcao="ENTRADA",
        finalidade="COMERCIALIZACAO",
        uf_origem="SC",
        uf_destino="SP",
        ncm="85071090",
        valor_produto=Decimal("1000.00"),
        cst_ou_csosn="202",
        tem_st=True,
        tem_protocolo_st=True,
        st_retida_na_origem=False,
        mva_original_pct=Decimal("40.00"),
        fornecedor_simples_nacional=True,
    )
    res_sn = avaliar_operacao_bidirecional(ctx_sn)
    assert Decimal(res_sn["mva_aplicada_pct"]) == Decimal("40.00")
    assert res_sn["semaforo_risco"] == "VERMELHO"


def test_entrada_uso_consumo_difal_e_credito_vedado() -> None:
    ctx = ContextoOperacaoFiscal(
        direcao="ENTRADA",
        finalidade="USO_CONSUMO",
        uf_origem="SP",
        uf_destino="MG",
        ncm="84713012",
        valor_produto=Decimal("1000.00"),
        cst_ou_csosn="00",
    )
    res = avaliar_operacao_bidirecional(ctx)
    assert res["cfop_esperado"] == "2556"
    assert Decimal(res["difal_valor"]) > Decimal("0")
    assert Decimal(res["credito_admitido"]) == Decimal("0")
    assert "VEDADO" in res["regra_credito_detalhe"]


def test_cst_020_070_051_060_101_e_pmpf_com_trava_cbenef() -> None:
    # CST 070 (RBC + ST) sem cBenef -> bloqueio VERMELHO
    res_70_sem = avaliar_operacao_bidirecional(
        ContextoOperacaoFiscal(
            direcao="SAIDA",
            finalidade="COMERCIALIZACAO",
            uf_origem="SP",
            uf_destino="SP",
            ncm="04051000",
            valor_produto=Decimal("1000.00"),
            cst_ou_csosn="70",
            reducao_bc_pct=Decimal("61.11"),
            tem_st=True,
            mva_original_pct=Decimal("30.00"),
            cbenef="",
        )
    )
    assert res_70_sem["cbenef_obrigatorio"] is True
    assert res_70_sem["semaforo_risco"] == "VERMELHO"
    assert Decimal(res_70_sem["bc_icms_proprio"]) == Decimal("388.90")

    # CST 051 (Diferimento 100%) com cBenef
    res_51 = avaliar_operacao_bidirecional(
        ContextoOperacaoFiscal(
            direcao="SAIDA",
            finalidade="COMERCIALIZACAO",
            uf_origem="SP",
            uf_destino="SP",
            ncm="84321000",
            valor_produto=Decimal("1000.00"),
            cst_ou_csosn="51",
            percentual_diferimento_pct=Decimal("100.00"),
            cbenef="SP050001",
        )
    )
    assert Decimal(res_51["valor_icms_diferido"]) == Decimal("180.00")
    assert Decimal(res_51["valor_icms_proprio"]) == Decimal("0.00")
    assert res_51["semaforo_risco"] == "VERDE"

    # CSOSN 101 na entrada com permissão de crédito (Art. 23 LC 123/2006)
    res_101 = avaliar_operacao_bidirecional(
        ContextoOperacaoFiscal(
            direcao="ENTRADA",
            finalidade="COMERCIALIZACAO",
            uf_origem="SP",
            uf_destino="SP",
            ncm="61091000",
            valor_produto=Decimal("1000.00"),
            cst_ou_csosn="101",
            fornecedor_simples_nacional=True,
            aliquota_credito_sn_pct=Decimal("2.50"),
        )
    )
    assert Decimal(res_101["credito_admitido"]) == Decimal("25.00")


def test_service_simular_operacao_bidirecional(tmp_path) -> None:
    srv = RevTributariaService(tmp_path / "bidir.db")
    try:
        srv.executar_seed_sp(usar_rede=False)
        res = srv.simular_operacao_bidirecional(
            direcao="ENTRADA",
            finalidade="COMERCIALIZACAO",
            uf_origem="PR",
            uf_destino="SP",
            ncm="85071090",
            valor_produto="1000.00",
        )
        assert res["direcao"] == "ENTRADA"
        assert res["uf_legislacao_aplicavel"] == "SP"
        assert len(res["memoria_calculo"]) == 10
        assert len(res["bases_legais"]) >= 2
    finally:
        srv.close()
