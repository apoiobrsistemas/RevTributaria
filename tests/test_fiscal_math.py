"""Vetores de teste obrigatórios do motor matemático puro (Decimal)."""

from __future__ import annotations

from decimal import Decimal

from src.engine import (
    FUNDO_NA_MVA,
    ItemCalculo,
    calcular_item,
    calcular_mva_ajustado,
    calcular_reducao_por_carga,
    origem_por_fci,
)


def test_fundo_na_mva_estados_permitidos():
    assert FUNDO_NA_MVA == frozenset({"RJ", "PR", "BA", "SE", "AL"})


def test_mva_ajustado_rj_e_nao_fundo_sp():
    # Vetor obrigatório RJ: aliquota=20, fcp=2, mva_original=49, inter=12 -> 68.10
    assert (
        calcular_mva_ajustado("49", "12", "20", uf_destino="RJ", fcp_pct="2")
        == Decimal("68.10")
    )
    # SP não inclui FCP na fórmula do MVA ajustado
    assert (
        calcular_mva_ajustado("49", "12", "18", uf_destino="SP", fcp_pct="2")
        == Decimal("59.90")
    )


def test_reducao_por_carga_sp_e_rj_fecp():
    # SP: carga=8.80, aliquota=18.00 -> 51.11
    assert calcular_reducao_por_carga("8.80", "18.00", uf_destino="SP") == Decimal("51.11")
    # RJ (com FECP no denominador): carga=14.00, aliquota=20.00, fcp=2.00 -> 36.36
    assert (
        calcular_reducao_por_carga("14.00", "20.00", uf_destino="RJ", fcp_pct="2.00")
        == Decimal("36.36")
    )
    # RJ (com FECP): carga=8.80 -> 60.00
    assert (
        calcular_reducao_por_carga("8.80", "20.00", uf_destino="RJ", fcp_pct="2.00")
        == Decimal("60.00")
    )


def test_st_completa_vetor_referencia():
    # valor=1000, ipi=150, mva=68.10, aliquota_st=20, fcp_st=2, carga=12
    # -> icms=120.00, base_st=1933.15, st=266.63, fcp_st=38.66
    item = ItemCalculo(
        valor_produto=Decimal("1000.00"),
        valor_ipi=Decimal("150.00"),
        uf_origem="SP",
        uf_destino="RJ",
        ncm="85171300",
    )
    regra = {
        "aliquota_icms": Decimal("12.00"),
        "tem_st": 1,
        "margem_st": Decimal("49.00"),
        "aliquota_icms_st": Decimal("20.00"),
        "aliquota_fcp": Decimal("2.00"),
    }

    res = calcular_item(item, regra)
    assert res.valor_icms_proprio == Decimal("120.00")
    assert res.mva_aplicada == Decimal("68.10")
    assert res.bc_st == Decimal("1933.15")
    assert res.valor_icms_st == Decimal("266.63")
    assert res.valor_fcp_st == Decimal("38.66")


def test_estimativa_simplificada_st():
    item = ItemCalculo(
        valor_produto=Decimal("1000.00"),
        uf_origem="SP",
        uf_destino="MT",
        ncm="85171300",
    )
    regra = {
        "aliquota_icms": Decimal("7.00"),
        "tem_st": 1,
        "regime_estimativa_simplificado_st": 1,
        "percentual_carga_tributaria_media": Decimal("12.50"),
    }
    res = calcular_item(item, regra)
    assert res.bc_st == Decimal("1000.00")
    assert res.valor_icms_st == Decimal("125.00")


def test_difal_base_unica_e_dupla_com_ipi_e_reducao_fcp():
    item = ItemCalculo(
        valor_produto=Decimal("1000.00"),
        valor_ipi=Decimal("100.00"),
        uf_origem="SP",
        uf_destino="MG",
        ncm="85171300",
        operacao_com_contribuinte=True,
    )
    regra_dupla = {
        "aliquota_icms": Decimal("12.00"),
        "aliquota_interna_uf_destino_difal": Decimal("18.00"),
        "aliquota_fcp": Decimal("2.00"),
        "utiliza_bc_dupla_difal": 1,
        "somar_ipi_base_difal_fcp": 1,
    }
    res_dupla = calcular_item(item, regra_dupla)
    # base_ini = 1100, icms = 120 -> bc_1 = 980 -> bc_dupla = 980 / 0.80 = 1225.00
    # difal = 1225 * 0.18 - 120 = 220.50 - 120 = 100.50; fcp = 1225 * 0.02 = 24.50
    assert res_dupla.bc_difal == Decimal("1225.00")
    assert res_dupla.valor_difal == Decimal("100.50")
    assert res_dupla.valor_fcp_difal == Decimal("24.50")

    regra_unica = {
        "aliquota_icms": Decimal("12.00"),
        "aliquota_interna_uf_destino_difal": Decimal("18.00"),
        "aliquota_interestadual_difal": Decimal("12.00"),
        "aliquota_fcp": Decimal("2.00"),
        "utiliza_bc_dupla_difal": 0,
        "somar_ipi_base_difal_fcp": 0,
    }
    res_unica = calcular_item(item, regra_unica)
    assert res_unica.bc_difal == Decimal("1000.00")
    assert res_unica.valor_difal == Decimal("60.00")
    assert res_unica.valor_fcp_difal == Decimal("20.00")


def test_icms_efetivo_e_fci_origem_e_ibs_cbs():
    assert origem_por_fci("35.00") == "5"
    assert origem_por_fci("55.00") == "3"
    assert origem_por_fci("80.00") == "8"

    item = ItemCalculo(
        valor_produto=Decimal("1000.00"),
        uf_origem="SP",
        uf_destino="MG",
        ncm="85171300",
        conteudo_importacao_pct=Decimal("75.00"),
    )
    regra_icms = {
        "aliquota_icms": Decimal("12.00"),
        "cst_icms": "60",
        "aliquota_icms_efetivo": Decimal("18.00"),
        "reducao_base_icms_efetivo": Decimal("20.00"),
    }
    regra_fed = {
        "aliquota_pis": Decimal("1.65"),
        "aliquota_cofins": Decimal("7.60"),
        "cclass_trib": "200001",
        "aliquota_cbs": Decimal("8.80"),
        "aliquota_ibs_uf": Decimal("15.00"),
        "aliquota_ibs_mun": Decimal("2.70"),
        "reducao_ibs_cbs": Decimal("60.00"),
    }

    res = calcular_item(item, regra_icms, regra_fed)
    assert res.origem_efetiva == "8"
    assert res.aliquota_icms == Decimal("4.00")
    assert res.bc_icms_efetivo == Decimal("800.00")
    assert res.valor_icms_efetivo == Decimal("144.00")
    assert res.cclass_trib == "200001"
    assert res.valor_cbs == Decimal("35.20")
    assert res.valor_ibs_total == Decimal("70.80")
