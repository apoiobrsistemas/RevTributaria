"""Testes do pipeline de auditoria Frente A (XML NF-e) e Frente B (Matriz ERP)."""

from __future__ import annotations

import json

from src.database import init_db
from src.engine import auditar_config_erp, auditar_nfe_contra_lei
from src.integrations import ingerir_nfe_idempotente

XML_NFE_DIVERGENTE = """<?xml version="1.0" encoding="utf-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe35261199999999000100550010000000011000000019" versao="4.00">
      <ide><nNF>1</nNF><serie>1</serie><mod>55</mod><finNFe>1</finNFe><dhEmi>2026-06-01T10:00:00-03:00</dhEmi></ide>
      <emit><CNPJ>99999999000100</CNPJ><enderEmit><UF>SP</UF></enderEmit></emit>
      <dest><CNPJ>88888888000100</CNPJ><enderDest><UF>SP</UF></enderDest></dest>
      <det nItem="1">
        <prod><cProd>P1</cProd><xProd>Prod 1</xProd><NCM>85171300</NCM><CEST>2105301</CEST><CFOP>5102</CFOP><vProd>1000.00</vProd></prod>
        <imposto>
          <ICMS><ICMS00><orig>0</orig><CST>00</CST><vBC>1000.00</vBC><pICMS>12.00</pICMS><vICMS>120.00</vICMS></ICMS00></ICMS>
          <PIS><PISAliq><CST>01</CST><pPIS>1.65</pPIS></PISAliq></PIS>
          <COFINS><COFINSAliq><CST>01</CST><pCOFINS>7.60</pCOFINS></COFINSAliq></COFINS>
        </imposto>
      </det>
      <det nItem="2">
        <prod><cProd>P2</cProd><xProd>Demonstracao</xProd><NCM>85171300</NCM><CFOP>5912</CFOP><vProd>100.00</vProd></prod>
        <imposto><ICMS><ICMS40><orig>0</orig><CST>40</CST></ICMS40></ICMS></imposto>
      </det>
    </infNFe>
  </NFe>
</nfeProc>
"""


def test_auditoria_frente_a_13_etapas_short_circuit_e_deduplicacao():
    conn = init_db(":memory:")
    try:
        conn.execute(
            """
            INSERT INTO regras_estaduais_icms (
                uf_origem, uf_destino, ncm, cest, natureza_operacao,
                operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                cfop, cst_icms, aliquota_icms, status_validacao
            ) VALUES ('SP', 'SP', '85171300', '2105301', 'VENDA', 1, '*', '2026-01-01', '5405', '60', 18.0, 'ACEITO')
            """
        )
        conn.execute(
            """
            INSERT INTO regras_federais (
                ncm, cest, vigencia_inicio, aliquota_pis, aliquota_cofins, status_validacao
            ) VALUES ('85171300', '2105301', '2026-01-01', 1.65, 7.60, 'ACEITO')
            """
        )
        conn.commit()

        chave = ingerir_nfe_idempotente(conn, xml_str=XML_NFE_DIVERGENTE)
        divs = auditar_nfe_contra_lei(conn, chave)

        # Item 2 (CFOP 5912 demonstração) faz short-circuit com SEM_REGRA
        item2_divs = [d for d in divs if d.numero_item == 2]
        assert len(item2_divs) == 1
        assert item2_divs[0].severidade == "SEM_REGRA"

        # Item 1: diverge em aliq_icms (12 vs 18), valor_icms (120 vs 180), cst_icms (00 vs 60) e cfop (5102 vs 5405)
        # Deduplicação: cst_icms e cfop apontam apenas reflexo sem repetir causa raiz
        item1_divs = {d.campo_divergente: d for d in divs if d.numero_item == 1}
        assert "aliq_icms" in item1_divs
        assert "valor_icms" in item1_divs
        assert "Reflexo" in item1_divs["cst_icms"].mensagem_ajuste
        assert "Reflexo" in item1_divs["cfop"].mensagem_ajuste
    finally:
        conn.close()


def test_auditoria_frente_b_flags_erp_e_placeholder():
    conn = init_db(":memory:")
    try:
        conn.execute(
            """
            INSERT INTO regras_estaduais_icms (
                uf_origem, uf_destino, ncm, cest, natureza_operacao,
                operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                cfop, cst_icms, aliquota_icms, gera_credito_debito,
                deduz_icms_fcp_custo_medio, somar_icms_st_fcp_st_custo_medio,
                escriturar_sem_tributacao_como, icms_st_pago_em_guia, status_validacao
            ) VALUES (
                'SP', 'SP', '85171300', '', 'VENDA', 1, '*', '2026-01-01',
                '5405', '60', 18.0, 0, 0, 1, 'OUTRAS', 1, 'ACEITO'
            )
            """
        )

        # Linha 1: ERP com flags divergentes
        conn.execute(
            """
            INSERT INTO config_erp_importada (
                lote_importacao, codigo_produto_erp, ncm, cest,
                uf_origem, uf_destino, natureza_operacao, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "LOTE-1",
                "PROD-01",
                "85171300",
                "",
                "SP",
                "SP",
                "VENDA",
                json.dumps(
                    {
                        "deduz_icms_fcp_custo_medio": "S",
                        "somar_st_fcp_custo_medio": "N",
                        "gera_credito_debito": "S",
                        "escriturar_sem_tributacao": "ISENTAS",
                        "icms_st_pago_empresa_guia": "N",
                    }
                ),
            ),
        )

        # Linha 2: Configuração placeholder deve ser bloqueada
        conn.execute(
            """
            INSERT INTO config_erp_importada (
                lote_importacao, codigo_produto_erp, ncm, cest,
                uf_origem, uf_destino, natureza_operacao, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("LOTE-1", "PLACEHOLDER", "85171300", "", "SP", "SP", "VENDA", "{}"),
        )
        conn.commit()

        divs = auditar_config_erp(conn, lote_importacao="LOTE-1")
        campos = {d.campo_divergente for d in divs}
        assert {
            "deduz_icms_fcp_custo_medio",
            "somar_st_fcp_custo_medio",
            "gera_credito_debito",
            "escriturar_sem_tributacao",
            "icms_st_pago_empresa_guia",
            "config_placeholder",
        }.issubset(campos)
    finally:
        conn.close()



def test_tolerancias_auditoria():
    from src.engine import dentro_tolerancia_percentual, dentro_tolerancia_valor

    assert dentro_tolerancia_percentual("18.01", "18.00")
    assert not dentro_tolerancia_percentual("18.02", "18.00")
    assert dentro_tolerancia_valor("100.05", "100.00")
    assert not dentro_tolerancia_valor("100.15", "100.00")
