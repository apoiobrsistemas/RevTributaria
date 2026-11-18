"""Testes dos conectores Linx Microvix, parser de matriz ERP e coletor NF-e."""

from __future__ import annotations

import io
import json
import sqlite3

import openpyxl
import pytest

from src.database import init_db
from src.integrations import (
    MicrovixClient,
    identificar_perna_operacao,
    importar_planilha_matriz_erp,
    ingerir_nfe_idempotente,
    parsear_resposta_microvix,
    registrar_evento_nfe,
    separar_origem_cst,
    sincronizar_metodo,
)

XML_MICROVIX_PRODUTOS = b"""<?xml version="1.0" encoding="utf-8"?>
<LinxMicrovix>
  <ResponseResult><Success>True</Success></ResponseResult>
  <ResponseData>
    <C>
      <D>empresa</D><D>cod_produto</D><D>nome_produto</D><D>ncm</D><D>cest</D><D>origem_mercadoria</D><D>timestamp</D>
    </C>
    <R>
      <D>1</D><D>P001</D><D>Smartphone X</D><D>85171300</D><D>2105301</D><D>5</D><D>1001</D>
    </R>
  </ResponseData>
</LinxMicrovix>
"""

XML_MICROVIX_CONFIG_TRIB = b"""<?xml version="1.0" encoding="utf-8"?>
<LinxMicrovix>
  <ResponseResult><Success>True</Success></ResponseResult>
  <ResponseData>
    <C>
      <D>empresa</D><D>id_config_tributaria</D><D>cfop</D><D>uf_operacao</D><D>cst_icms_fiscal</D><D>descricao_perna</D><D>timestamp</D>
    </C>
    <R>
      <D>1</D><D>CFG10</D><D>5.102</D><D>SP</D><D>5.60</D><D>SP NC</D><D>2001</D>
    </R>
    <R>
      <D>1</D><D>CFG10</D><D>1.102</D><D>MG</D><D>0.00</D><D>MG CO</D><D>2002</D>
    </R>
  </ResponseData>
</LinxMicrovix>
"""

XML_NFE_COMPLETA = """<?xml version="1.0" encoding="utf-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe35261112345678000199550010000001231000001234" versao="4.00">
      <ide>
        <nNF>123</nNF><serie>1</serie><mod>55</mod><finNFe>1</finNFe>
        <dhEmi>2026-11-17T10:00:00-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>12345678000199</CNPJ>
        <enderEmit><UF>SP</UF></enderEmit>
      </emit>
      <dest>
        <CNPJ>98765432000188</CNPJ>
        <enderDest><UF>MG</UF></enderDest>
      </dest>
      <det nItem="1">
        <prod>
          <cProd>P001</cProd><xProd>Smartphone X</xProd>
          <NCM>85171300</NCM><CEST>2105301</CEST><CFOP>6403</CFOP>
          <vProd>1000.00</vProd><nFCI>FCI-1234-ABCD</nFCI>
        </prod>
        <imposto>
          <ICMS><ICMS10><orig>5</orig><CST>10</CST><vBC>1000.00</vBC><pICMS>12.00</pICMS><vICMS>120.00</vICMS><vBCST>1500.00</vBCST><pICMSST>18.00</pICMSST><vICMSST>150.00</vICMSST></ICMS10></ICMS>
          <PIS><PISAliq><CST>01</CST><pPIS>1.65</pPIS></PISAliq></PIS>
          <COFINS><COFINSAliq><CST>01</CST><pCOFINS>7.60</pCOFINS></COFINSAliq></COFINS>
        </imposto>
      </det>
    </infNFe>
  </NFe>
</nfeProc>
"""

XML_RES_NFE = """<?xml version="1.0" encoding="utf-8"?>
<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
  <chNFe>35261112345678000199550010000001231000001234</chNFe>
  <CNPJ>12345678000199</CNPJ>
  <dhEmi>2026-11-17T10:00:00-03:00</dhEmi>
</resNFe>
"""


def test_microvix_retry_exponencial_e_cursor_apos_commit(monkeypatch):
    monkeypatch.setenv("MICROVIX_CHAVE", "uuid-teste-microvix")
    tentativas = {"count": 0}
    sleeps: list[float] = []

    def fake_post(url: str, envelope: str, headers: dict, timeout: int) -> bytes:
        tentativas["count"] += 1
        assert "uuid-teste-microvix" in envelope
        if tentativas["count"] < 2:
            raise TimeoutError("Timeout transitório")
        if "LinxConfiguracoesTributariasDetalhes" in envelope:
            return XML_MICROVIX_CONFIG_TRIB
        return XML_MICROVIX_PRODUTOS

    client = MicrovixClient(
        max_retries=3,
        backoff_base=0.5,
        http_post=fake_post,
        sleep_fn=sleeps.append,
    )
    conn = init_db(":memory:")
    try:
        qtd = sincronizar_metodo(conn, client, metodo="LinxProdutos", cnpj_emp="12345678000199")
        assert qtd == 1
        assert sleeps == [0.5]

        cursor = conn.execute(
            "SELECT ultimo_timestamp FROM linx_sync_cursor WHERE cnpj_emp = '12345678000199' AND metodo = 'LinxProdutos'"
        ).fetchone()
        assert cursor["ultimo_timestamp"] == 1001

        # Sincroniza configurações tributárias e valida separação 5.60 -> orig=5, cst='60'
        qtd_cfg = sincronizar_metodo(
            conn,
            client,
            metodo="LinxConfiguracoesTributariasDetalhes",
            cnpj_emp="12345678000199",
        )
        assert qtd_cfg == 2

        cfgs = conn.execute(
            "SELECT cfop, origem_separada, cst_separado, tipo_operacao_perna FROM linx_config_tributarias ORDER BY cfop DESC"
        ).fetchall()
        assert [(c["cfop"], c["origem_separada"], c["cst_separado"], c["tipo_operacao_perna"]) for c in cfgs] == [
            ("5102", "5", "60", "VENDA_CONSUMIDOR"),
            ("1102", "0", "00", "COMPRA_FORNECEDOR"),
        ]
    finally:
        conn.close()


def test_parse_separacao_origem_cst_e_importacao_planilha_erp():
    assert separar_origem_cst("5.60") == ("5", "60")
    assert separar_origem_cst("0.00") == ("0", "00")
    assert identificar_perna_operacao("5.102", "SP NC") == "VENDA_CONSUMIDOR"
    assert identificar_perna_operacao("1.102", "MG CO") == "COMPRA_FORNECEDOR"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        [
            "codigo_produto_erp",
            "ncm",
            "cest",
            "uf_origem",
            "uf_destino",
            "natureza_operacao",
            "deduz_icms_fcp_custo_medio",
        ]
    )
    ws.append(["P001", "8517.13.00", "21.053.01", "SP", "MG", "VENDA", "S"])
    buf = io.BytesIO()
    wb.save(buf)

    conn = init_db(":memory:")
    try:
        inseridas = importar_planilha_matriz_erp(
            conn,
            buf.getvalue(),
            lote_importacao="LOTE-2026-11",
        )
        assert inseridas == 1
        row = conn.execute("SELECT * FROM config_erp_importada").fetchone()
        assert row["ncm"] == "85171300"
        assert row["cest"] == "2105301"
        payload = json.loads(row["payload_json"])
        assert payload["deduz_icms_fcp_custo_medio"] == "S"
    finally:
        conn.close()


def test_coletor_nfe_idempotente_precedencia_xml_completo_e_view_status():
    conn = init_db(":memory:")
    try:
        # 1. Chega primeiro o resumo resNFe (eh_xml_completo = 0)
        chave = ingerir_nfe_idempotente(
            conn,
            xml_str=XML_RES_NFE,
            cnpj_cursor="12345678000199",
            nsu="000000000000010",
            timestamp_cursor=10,
        )
        st1 = conn.execute("SELECT * FROM vw_nfe_status WHERE chave_acesso = ?", (chave,)).fetchone()
        assert st1["eh_xml_completo"] == 0
        assert st1["nivel_documento"] == "RESUMO_RESNFE"
        assert st1["status_sefaz"] == "AUTORIZADA"

        # 2. Chega o XML completo (eh_xml_completo = 1) -> sobrescreve resumo e popula itens
        ingerir_nfe_idempotente(
            conn,
            xml_str=XML_NFE_COMPLETA,
            cnpj_cursor="12345678000199",
            nsu="000000000000020",
            timestamp_cursor=20,
        )
        # 3. Reenvio tardio do resNFe NÃO pode rebaixar eh_xml_completo = 1
        ingerir_nfe_idempotente(conn, xml_str=XML_RES_NFE)

        st2 = conn.execute("SELECT * FROM vw_nfe_status WHERE chave_acesso = ?", (chave,)).fetchone()
        assert st2["eh_xml_completo"] == 1
        assert st2["nivel_documento"] == "XML_COMPLETO"
        assert st2["status_sefaz"] == "AUTORIZADA"

        itens = conn.execute("SELECT * FROM nfe_itens WHERE chave_acesso = ?", (chave,)).fetchall()
        assert len(itens) == 1
        assert itens[0]["numero_fci"] == "FCI-1234-ABCD"

        # 4. Evento de cancelamento 110111 altera status dinâmico na VIEW para CANCELADA
        registrar_evento_nfe(
            conn,
            chave_acesso=chave,
            tipo_evento="110111",
            data_evento="2026-11-17T11:00:00-03:00",
            protocolo="135260000000001",
        )
        st3 = conn.execute("SELECT * FROM vw_nfe_status WHERE chave_acesso = ?", (chave,)).fetchone()
        assert st3["status_sefaz"] == "CANCELADA"
    finally:
        conn.close()
