"""Testes da Fase 3: Reforma Tributária 2026-2033 (LC 214/2025), cClassTrib, IS e XML gIBSCBS."""

from __future__ import annotations

from decimal import Decimal

from src.app.service import RevTributariaService
from src.engine.cclasstrib_catalog import consultar_enquadramento_cclasstrib
from src.engine.reforma_tributaria_engine import (
    ContextoReformaLC214,
    calcular_transicao_lc214,
)
from src.engine.xml_reforma_validator import validar_xml_reforma_lc214


def test_cclasstrib_cesta_basica_anexos_e_imposto_seletivo() -> None:
    cesta = consultar_enquadramento_cclasstrib("10063021")  # Arroz -> Anexo I
    assert cesta["cst_ibs_cbs"] == "200"
    assert cesta["cclass_trib"] == "200003"
    assert cesta["reducao_pct"] == Decimal("100.00")
    assert "Anexo I" in cesta["anexo_legal"]

    med = consultar_enquadramento_cclasstrib("30049099")  # Medicamentos -> 60%
    assert med["cst_ibs_cbs"] == "200"
    assert med["reducao_pct"] == Decimal("60.00")

    cerveja = consultar_enquadramento_cclasstrib("22030000")  # Bebida alcoólica -> IS
    assert cerveja["sujeito_is"] is True
    assert cerveja["aliquota_is_padrao"] > Decimal("0")


def test_cronograma_2026_a_2033_calculo_por_fora_e_zfm() -> None:
    # 2026: 0,90% CBS + 0,10% IBS com compensação em PIS/COFINS
    r2026 = calcular_transicao_lc214(
        ContextoReformaLC214(
            ano_calendario=2026,
            ncm="85071090",
            valor_operacao_bruto=Decimal("1000.00"),
            icms_atual=Decimal("180.00"),
            pis_atual=Decimal("16.50"),
            cofins_atual=Decimal("76.00"),
        )
    )
    # Base limpa por fora = 1000 - (180 + 16.50 + 76) = 727.50
    assert Decimal(r2026["base_limpa_por_fora"]) == Decimal("727.50")
    assert Decimal(r2026["valor_cbs"]) == Decimal("6.55")
    assert Decimal(r2026["valor_ibs_total"]) == Decimal("0.72")
    assert Decimal(r2026["compensacao_2026"]) == Decimal("7.27")

    # 2026 sem gIBSCBS -> perde compensação e gera alerta
    r2026_sem = calcular_transicao_lc214(
        ContextoReformaLC214(
            ano_calendario=2026,
            ncm="85071090",
            valor_operacao_bruto=Decimal("1000.00"),
            icms_atual=Decimal("180.00"),
            pis_atual=Decimal("16.50"),
            cofins_atual=Decimal("76.00"),
            xml_contem_gibscbs=False,
        )
    )
    assert Decimal(r2026_sem["compensacao_2026"]) == Decimal("0")
    assert any("Art. 348" in a for a in r2026_sem["alertas_reforma"])

    # 2027 com ZFM concorrente -> mantém IPI
    r2027_zfm = calcular_transicao_lc214(
        ContextoReformaLC214(
            ano_calendario=2027,
            ncm="85071090",
            valor_operacao_bruto=Decimal("1000.00"),
            icms_atual=Decimal("180.00"),
            ipi_atual=Decimal("50.00"),
            concorrente_zfm=True,
        )
    )
    assert Decimal(r2027_zfm["pis_residual"]) == Decimal("0.00")
    assert Decimal(r2027_zfm["ipi_residual"]) == Decimal("50.00")

    # 2029..2032 escalonamento federativo (ICMS 90/80/70/60%)
    for ano, fator_icms in [(2029, "162.00"), (2030, "144.00"), (2031, "126.00"), (2032, "108.00")]:
        r_esc = calcular_transicao_lc214(
            ContextoReformaLC214(
                ano_calendario=ano,
                ncm="85071090",
                valor_operacao_bruto=Decimal("1000.00"),
                icms_atual=Decimal("180.00"),
            )
        )
        assert r_esc["icms_residual"] == fator_icms

    # 2033+: ICMS=0, IBS+CBS plenos e Cesta Básica=0
    r2033_cesta = calcular_transicao_lc214(
        ContextoReformaLC214(
            ano_calendario=2033,
            ncm="10063021",
            valor_operacao_bruto=Decimal("1000.00"),
            icms_atual=Decimal("0.00"),
        )
    )
    assert Decimal(r2033_cesta["icms_residual"]) == Decimal("0.00")
    assert Decimal(r2033_cesta["valor_cbs"]) == Decimal("0.00")
    assert Decimal(r2033_cesta["valor_ibs_total"]) == Decimal("0.00")


def test_entrada_split_payment_e_simples_nacional() -> None:
    r_retido = calcular_transicao_lc214(
        ContextoReformaLC214(
            ano_calendario=2027,
            ncm="85071090",
            valor_operacao_bruto=Decimal("1000.00"),
            direcao="ENTRADA",
            split_payment_liquidado=False,
        )
    )
    assert Decimal(r_retido["credito_ibs_cbs_entrada"]) == Decimal("0")
    assert "Split Payment" in r_retido["regra_credito_reforma"]

    r_sn = calcular_transicao_lc214(
        ContextoReformaLC214(
            ano_calendario=2027,
            ncm="85071090",
            valor_operacao_bruto=Decimal("1000.00"),
            direcao="ENTRADA",
            fornecedor_simples_nacional=True,
            simples_regime_hibrido=False,
        )
    )
    assert Decimal(r_sn["credito_ibs_cbs_entrada"]) == Decimal("0")
    assert "Simples Nacional" in r_sn["regra_credito_reforma"]


def test_validador_xml_gibscbs_gis_e_deteccao_bitributacao(tmp_path) -> None:
    xml_ok = """
    <det nItem="1">
      <prod><vProd>1000.00</vProd></prod>
      <imposto>
        <ICMS><ICMS00><vICMS>180.00</vICMS></ICMS00></ICMS>
        <PIS><PISAliq><vPIS>16.50</vPIS></PISAliq></PIS>
        <COFINS><COFINSAliq><vCOFINS>76.00</vCOFINS></COFINSAliq></COFINS>
        <IBSCBS>
          <CST>000</CST>
          <cClassTrib>000001</cClassTrib>
          <gIBSCBS>
            <vBC>727.50</vBC>
            <gIBSUF><pIBSUF>0.05</pIBSUF><vIBSUF>0.36</vIBSUF></gIBSUF>
            <gIBSMun><pIBSMun>0.05</pIBSMun><vIBSMun>0.36</vIBSMun></gIBSMun>
            <gCBS><pCBS>0.90</pCBS><vCBS>6.55</vCBS></gCBS>
          </gIBSCBS>
        </IBSCBS>
      </imposto>
    </det>
    """
    res_ok = validar_xml_reforma_lc214(xml_ok)
    assert res_ok["valido"] is True

    # vBC = 1000.00 incluindo ICMS/PIS/COFINS -> erro crítico de bitributação
    xml_bitrib = xml_ok.replace("<vBC>727.50</vBC>", "<vBC>1000.00</vBC>")
    res_bi = validar_xml_reforma_lc214(xml_bitrib)
    assert res_bi["valido"] is False
    assert any("BITRIBUTAÇÃO" in e for e in res_bi["erros"])

    srv = RevTributariaService(tmp_path / "ref.db")
    try:
        r_srv = srv.simular_reforma_lc214(
            ano_calendario=2026,
            ncm="85071090",
            valor_operacao_bruto="1000.00",
            icms_atual="180.00",
            pis_atual="16.50",
            cofins_atual="76.00",
        )
        assert r_srv["cclass_trib"] == "000001"
        assert srv.validar_xml_reforma(xml_ok)["valido"] is True
    finally:
        srv.close()
