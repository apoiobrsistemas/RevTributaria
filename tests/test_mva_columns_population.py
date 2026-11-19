"""Testes unitários aditivos para preenchimento obrigatório das colunas de Margem MVA e Alíq. ST."""

from __future__ import annotations

from decimal import Decimal

from src.engine.fiscal_math import calcular_mva_ajustado
from src.engine.matrix_generator import (
    avaliar_arvore_booleana_ncm,
    gerar_matriz_consolidada_ncm,
    gerar_matriz_ncm,
)


def _regra_st_sp(mva: float = 59.67, aliq_st: float = 18.0, usa_alias_iva: bool = False) -> dict:
    regra = {
        "cest": "1705300",
        "tem_st": 1,
        "tem_acordo_st": 1,
        "aliquota_icms": 18.0,
        "aliquota_icms_st": aliq_st,
        "cst_icms": "60",
        "dispositivo_legal": "Portaria SRE 12/2026 / RICMS/SP Art. 313-W",
    }
    if usa_alias_iva:
        regra["iva_st"] = mva
    else:
        regra["margem_st"] = mva
    return regra


def test_mva_colunas_preenchidas_entrada_e_saida_cst_10_e_60() -> None:
    regra_inter = _regra_st_sp(mva=59.67, aliq_st=18.0, usa_alias_iva=True)

    # 1. gerar_matriz_ncm (principal)
    linhas_grid = gerar_matriz_ncm(
        ncm="19053100",
        uf_origem="MG",
        uf_destino="SP",
        regra_estadual=regra_inter,
    )
    st_grid = [ln for ln in linhas_grid if ln["Regime ICMS"] == "ST"]
    assert len(st_grid) > 0
    for ln in st_grid:
        assert ln["Margem ST"] == 59.67
        assert ln["% MVA ST Ajustada"] > 59.67
        assert ln["Alíquota ICMS ST"] == 18.0

    # Confirma presença tanto em CST x.60 (substituído) quanto em CST x.10 (retido)
    assert any(ln["CST ICMS"].endswith(".60") and ln["Margem ST"] == 59.67 and ln["% MVA ST Ajustada"] > 59.67 for ln in st_grid)
    assert any(ln["CST ICMS"].endswith(".10") and ln["Margem ST"] == 59.67 and ln["% MVA ST Ajustada"] > 59.67 for ln in st_grid)

    # 2. gerar_matriz_consolidada_ncm
    linhas_cons = gerar_matriz_consolidada_ncm(
        ncm="19053100",
        uf_origem="MG",
        uf_destino="SP",
        regra_estadual=regra_inter,
    )
    st_cons = [ln for ln in linhas_cons if ln["Tem ST?"] == "Sim"]
    assert len(st_cons) > 0
    for ln in st_cons:
        assert ln["MVA Original (%)"] == 59.67
        assert ln["MVA Ajustada Nacional (%)"] > 59.67
        assert ln["MVA Ajustada Importado 4% (%)"] > 59.67
        assert ln["MVA Simples Nacional (%)"] == 59.67
        assert ln["Alíq. ST (%)"] == 18.0

    # 3. avaliar_arvore_booleana_ncm
    arvore = avaliar_arvore_booleana_ncm(
        ncm="19053100",
        uf_origem="MG",
        uf_destino="SP",
        regra_estadual=regra_inter,
    )
    st_arv = [ln for ln in arvore["linhas"] if ln["Enquadramento ICMS"] == "ST"]
    assert len(st_arv) > 0
    for ln in st_arv:
        assert ln["MVA Original (%)"] == 59.67
        assert ln["MVA Ajustada Nacional (%)"] > 59.67
        assert ln["MVA Ajustada Importado 4% (%)"] > 59.67
        assert ln["MVA Simples Nacional (%)"] == 59.67
        assert ln["Alíq. ST (%)"] == 18.0


def test_mva_interna_vs_interestadual_decimal() -> None:
    # Operação interna SP -> SP: MVA Ajustada Nacional == MVA Original
    regra_sp = _regra_st_sp(mva=59.67, aliq_st=18.0)
    cons_interna = gerar_matriz_consolidada_ncm(
        ncm="19053100",
        uf_origem="SP",
        uf_destino="SP",
        regra_estadual=regra_sp,
    )
    st_int = [ln for ln in cons_interna if ln["Tem ST?"] == "Sim"]
    assert len(st_int) > 0
    for ln in st_int:
        assert ln["MVA Original (%)"] == 59.67
        assert ln["MVA Ajustada Nacional (%)"] == 59.67

    # Operação interestadual MG -> RJ (20% + 2% FCP): cálculo matemático via Decimal
    regra_rj = {
        "cest": "1600100",
        "tem_st": 1,
        "aliquota_icms": 20.0,
        "aliquota_fcp": 2.0,
        "aliquota_icms_st": 20.0,
        "margem_st": 49.0,
        "dispositivo_legal": "Convênio ICMS 102/2017",
    }
    cons_rj = gerar_matriz_consolidada_ncm(
        ncm="40111000",
        uf_origem="MG",
        uf_destino="RJ",
        regra_estadual=regra_rj,
    )
    st_rj = [ln for ln in cons_rj if ln["Tem ST?"] == "Sim"]
    assert len(st_rj) > 0
    esperado_nac = float(calcular_mva_ajustado(Decimal("49.00"), Decimal("12.00"), Decimal("20.00"), uf_destino="RJ", fcp_pct=Decimal("2.00")))
    esperado_imp = float(calcular_mva_ajustado(Decimal("49.00"), Decimal("4.00"), Decimal("20.00"), uf_destino="RJ", fcp_pct=Decimal("2.00")))
    for ln in st_rj:
        assert ln["MVA Original (%)"] == 49.0
        assert ln["MVA Ajustada Nacional (%)"] == esperado_nac
        assert ln["MVA Ajustada Importado 4% (%)"] == esperado_imp
        assert ln["Alíq. ST (%)"] == 20.0
