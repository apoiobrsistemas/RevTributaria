"""Testes do módulo de Importação Direta (DI / DUIMP / NF-e Entrada CFOP 3.xxx)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from src.app.service import RevTributariaService
from src.engine.import_engine import ContextoImportacaoDireta, calcular_importacao_direta
from src.integrations.import_docs_parser import (
    auditar_documento_importacao,
    parsear_di_xml,
    parsear_duimp,
)


def test_calculo_icms_importacao_por_dentro_e_origem_1_vs_6() -> None:
    # Origem 1 (com similar nacional) -> na saída interestadual vira Origem 2 a 4.00%
    res_orig1 = calcular_importacao_direta(
        ContextoImportacaoDireta(
            ncm="85171300",
            uf_desembaraco="SP",
            uf_destino="SP",
            finalidade="COMERCIALIZACAO",
            sem_similar_nacional_camex=False,
            valor_aduaneiro_cif=Decimal("10000.00"),
            taxa_siscomex=Decimal("154.23"),
            aliquota_ii=Decimal("16.00"),
            aliquota_ipi=Decimal("15.00"),
            aliquota_pis_imp=Decimal("2.10"),
            aliquota_cofins_imp=Decimal("9.65"),
            adicional_cofins_imp=Decimal("1.00"),
            aliquota_icms_interna=Decimal("18.00"),
            uf_saida_subsequente="RJ",
        )
    )
    assert res_orig1["origem_entrada"] == "1"
    assert res_orig1["cfop_entrada"] == "3.102"
    assert res_orig1["cst_icms_entrada"] == "1.00"
    assert res_orig1["valor_ii"] == "1600.00"
    assert res_orig1["base_ipi"] == "11600.00"
    assert res_orig1["valor_ipi"] == "1740.00"
    assert res_orig1["valor_pis_imp"] == "210.00"
    assert res_orig1["valor_cofins_imp"] == "1065.00"
    # Soma antes por dentro = 10000 + 1600 + 1740 + 210 + 1065 + 154.23 = 14769.23
    # Base por dentro = 14769.23 / 0.82 = 18011.26; ICMS = 18011.26 * 0.18 = 3242.03
    assert res_orig1["base_icms_por_dentro"] == "18011.26"
    assert res_orig1["valor_icms_importacao"] == "3242.03"
    assert res_orig1["origem_saida_subsequente"] == "2"
    assert res_orig1["aliquota_saida_interestadual"] == "4.00"
    assert res_orig1["equiparado_industrial_ipi"] is True

    # Origem 6 (sem similar CAMEX) -> na saída interestadual SP->RJ vira Origem 7 a 12.00% (não 4%)
    res_orig6 = calcular_importacao_direta(
        ContextoImportacaoDireta(
            ncm="84715010",
            uf_desembaraco="SP",
            uf_destino="SP",
            finalidade="INDUSTRIALIZACAO",
            sem_similar_nacional_camex=True,
            valor_aduaneiro_cif=Decimal("10000.00"),
            aliquota_ii=Decimal("0.00"),
            aliquota_ipi=Decimal("0.00"),
            uf_saida_subsequente="RJ",
        )
    )
    assert res_orig6["origem_entrada"] == "6"
    assert res_orig6["cfop_entrada"] == "3.101"
    assert res_orig6["origem_saida_subsequente"] == "7"
    assert res_orig6["aliquota_saida_interestadual"] == "12.00"


def test_parsers_di_xml_e_duimp_json_com_auditoria(tmp_path: Path) -> None:
    di_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <ListaDeclaracoes>
      <declaracaoImportacao>
        <numeroDI>2600123456</numeroDI>
        <dataRegistro>2026-11-10</dataRegistro>
        <urfDespachoCodigoUF>SP</urfDespachoCodigoUF>
        <taxaSiscomexValor>154.23</taxaSiscomexValor>
        <adicao>
          <numeroAdicao>001</numeroAdicao>
          <dadosMercadoriaCodigoNcm>85171300</dadosMercadoriaCodigoNcm>
          <descricaoMercadoria>TERMINAL PORTATIL</descricaoMercadoria>
          <condicaoVendaValorReais>10000.00</condicaoVendaValorReais>
          <iiAliquotaValorRecolher>1600.00</iiAliquotaValorRecolher>
          <ipiAliquotaValorRecolher>1740.00</ipiAliquotaValorRecolher>
          <pisPasepAliquotaValorRecolher>210.00</pisPasepAliquotaValorRecolher>
          <cofinsAliquotaValorRecolher>1065.00</cofinsAliquotaValorRecolher>
        </adicao>
      </declaracaoImportacao>
    </ListaDeclaracoes>"""

    doc_di = parsear_di_xml(di_xml)
    assert doc_di["tipo_documento"] == "DI_XML"
    assert doc_di["numero_documento"] == "2600123456"
    assert doc_di["itens"][0]["ncm"] == "85171300"

    duimp_json = json.dumps(
        {
            "identificacao": {"numero": "26BR0000001234", "dataRegistro": "2026-11-12"},
            "ufDesembaraco": "SP",
            "despesasAduaneiras": {"taxaSiscomex": 154.23, "afrmm": 0.0},
            "itens": [
                {
                    "numeroAdicao": "001",
                    "numeroItem": 1,
                    "mercadoria": {"ncm": "85171300", "descricao": "TERMINAL", "valorAduaneiro": 10000.00},
                    "tributos": {"ii": 1200.00, "ipi": 1740.00, "pis": 210.00, "cofins": 1065.00},
                }
            ],
        }
    ).encode("utf-8")

    doc_duimp = parsear_duimp(duimp_json)
    assert doc_duimp["tipo_documento"] == "DUIMP"
    assert doc_duimp["numero_documento"] == "26BR0000001234"

    srv = RevTributariaService(tmp_path / "imp.db")
    try:
        srv.sincronizar_tec_camex_padrao()
        aud_di = srv.registrar_e_auditar_documento_importacao("di.xml", di_xml, uf_destino="SP")
        assert aud_di["status_conciliacao"] == "OK"

        # II divergente na DUIMP (1200 vs 1600 esperado)
        aud_duimp = srv.registrar_e_auditar_documento_importacao("duimp.json", duimp_json, uf_destino="SP")
        assert aud_duimp["status_conciliacao"] == "DIVERGENTE"
        assert "II:" in aud_duimp["itens_auditados"][0]["Divergências"]
    finally:
        srv.close()
