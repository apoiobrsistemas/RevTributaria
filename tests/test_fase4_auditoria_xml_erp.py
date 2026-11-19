"""Testes da Fase 4: Auditoria em Lote XML de Entrada, Anti-XXE, Glosa SPED e Conciliação Microvix."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import openpyxl

from src.app.service import RevTributariaService
from src.integrations.microvix_conciliador import sanitizar_celula_planilha
from src.integrations.xml_entrada_parser import parsear_arquivos_entrada


def _xml_nfe(
    *,
    chave: str,
    n_nf: str,
    uf_emit: str,
    uf_dest: str,
    crt: str,
    c_prod: str,
    x_prod: str,
    ncm: str,
    cest: str,
    cfop: str,
    orig: str,
    cst: str,
    v_prod: str,
    p_icms: str,
    v_icms: str,
    v_st: str = "0.00",
) -> bytes:
    cest_tag = f"<CEST>{cest}</CEST>" if cest else ""
    icms_tag = (
        f"<ICMSSN202><orig>{orig}</orig><CSOSN>{cst}</CSOSN><vICMSST>{v_st}</vICMSST></ICMSSN202>"
        if len(cst) == 3
        else f"<ICMS00><orig>{orig}</orig><CST>{cst}</CST><vBC>{v_prod}</vBC><pICMS>{p_icms}</pICMS><vICMS>{v_icms}</vICMS></ICMS00>"
    )
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
    <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">
      <NFe>
        <infNFe Id="NFe{chave}">
          <ide><nNF>{n_nf}</nNF><serie>1</serie><dhEmi>2026-11-18T10:00:00-03:00</dhEmi><natOp>Venda</natOp><finNFe>1</finNFe><idDest>2</idDest></ide>
          <emit><CNPJ>11111111000100</CNPJ><xNome>Fornecedor Teste</xNome><enderEmit><UF>{uf_emit}</UF></enderEmit><CRT>{crt}</CRT></emit>
          <dest><CNPJ>22222222000100</CNPJ><enderDest><UF>{uf_dest}</UF></enderDest><indIEDest>1</indIEDest></dest>
          <det nItem="1">
            <prod><cProd>{c_prod}</cProd><xProd>{x_prod}</xProd><NCM>{ncm}</NCM>{cest_tag}<CFOP>{cfop}</CFOP><uCom>UN</uCom><qCom>1</qCom><vProd>{v_prod}</vProd></prod>
            <imposto><ICMS>{icms_tag}</ICMS></imposto>
          </det>
        </infNFe>
      </NFe>
    </nfeProc>"""
    return xml.encode("utf-8")


def test_parser_bloqueia_xxe_e_aceita_zip() -> None:
    xxe_xml = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><NFe/>'
    res_xxe = parsear_arquivos_entrada([("ataque.xml", xxe_xml)])
    assert len(res_xxe["notas"]) == 0
    assert len(res_xxe["erros"]) == 1
    assert "XXE" in res_xxe["erros"][0]["erro"]

    xml_ok = _xml_nfe(
        chave="35261111111111000100550010000000011000000011",
        n_nf="1",
        uf_emit="SC",
        uf_dest="SP",
        crt="1",
        c_prod="P01",
        x_prod="Bateria",
        ncm="85071090",
        cest="0100100",
        cfop="6403",
        orig="0",
        cst="202",
        v_prod="1000.00",
        p_icms="0.00",
        v_icms="0.00",
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("nota1.xml", xml_ok)
    res_zip = parsear_arquivos_entrada([("lote.zip", buf.getvalue())])
    assert len(res_zip["notas"]) == 1
    assert res_zip["notas"][0]["fornecedor_simples_nacional"] is True


def test_lote_entrada_sn_st_importado_difal_e_microvix(tmp_path: Path) -> None:
    srv = RevTributariaService(tmp_path / "fase4.db")
    try:
        conn = srv._get_conn()
        # Cadastra produto P01 no Linx Microvix com NCM divergente para testar conciliação
        with conn:
            conn.execute(
                """
                INSERT INTO linx_produtos (empresa, cod_produto, nome_produto, ncm, cest, origem_mercadoria, payload_json)
                VALUES ('1', 'P01', 'Bateria Auto', '85079090', '0100100', '0', '{}')
                """
            )

        # 1. Fornecedor SN (SC -> SP) com ST sem retenção (MVA Original 71,78% mantida)
        xml_sn_st = _xml_nfe(
            chave="35261111111111000100550010000000011000000011",
            n_nf="101",
            uf_emit="SC",
            uf_dest="SP",
            crt="1",
            c_prod="P01",
            x_prod="=CMD('calc')",  # Testa sanitização Formula Injection
            ncm="85071090",
            cest="0100100",
            cfop="6403",
            orig="0",
            cst="202",
            v_prod="1000.00",
            p_icms="0.00",
            v_icms="0.00",
            v_st="0.00",
        )
        # 2. Produto importado (orig=1) com 12% em vez de 4% -> glosa de crédito
        xml_imp = _xml_nfe(
            chave="35261111111111000100550010000000021000000022",
            n_nf="102",
            uf_emit="SC",
            uf_dest="SP",
            crt="3",
            c_prod="P02",
            x_prod="Teclado Importado",
            ncm="84716052",
            cest="",
            cfop="6102",
            orig="1",
            cst="00",
            v_prod="1000.00",
            p_icms="12.00",
            v_icms="120.00",
        )
        # 3. Uso e Consumo (CFOP 6556) SP -> MG -> DIFAL + glosa integral de crédito
        xml_uso = _xml_nfe(
            chave="35261111111111000100550010000000031000000033",
            n_nf="103",
            uf_emit="SP",
            uf_dest="MG",
            crt="3",
            c_prod="P03",
            x_prod="Material Escritório",
            ncm="48201000",
            cest="",
            cfop="6556",
            orig="0",
            cst="00",
            v_prod="1000.00",
            p_icms="12.00",
            v_icms="120.00",
        )

        res = srv.auditar_lote_entradas_xml(
            [("n1.xml", xml_sn_st), ("n2.xml", xml_imp), ("n3.xml", xml_uso)]
        )
        assert res["total_notas"] == 3
        assert res["total_itens"] == 3
        assert res["antecipacao_st_total"] > 0
        assert res["difal_fcp_total"] > 0
        assert res["credito_glosado_total"] >= 200.0  # 80.00 (importado 12% vs 4%) + 120.00 (uso/consumo)
        assert len(res["glosas_credito"]) == 2

        # Verifica MVA Original preservada para Simples Nacional
        it1 = res["itens_auditados"][0]
        assert it1["MVA Aplicada (%)"] == 71.78
        assert it1["CFOP Entrada Sugerido"] == "2403"

        # Verifica conciliação Microvix (P01 NCM divergente, P02/P03 não localizados)
        assert res["divergencias_erp"][0]["Status Cadastro ERP"] == "DIVERGENTE"
        assert "NCM divergente" in res["divergencias_erp"][0]["Divergências"]
        assert res["divergencias_erp"][1]["Status Cadastro ERP"] == "NAO_LOCALIZADO"

        # Verifica exportação Excel 4 abas e sanitização contra Formula Injection
        assert sanitizar_celula_planilha("=CMD('calc')") == "'=CMD('calc')"
        xlsx_bytes = srv.exportar_auditoria_lote_xlsx(res, res["divergencias_erp"])
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
        assert wb.sheetnames == ["Resumo Guias", "Itens Auditados", "Glosa de Créditos", "Divergências Cadastro ERP"]
        ws_itens = wb["Itens Auditados"]
        headers = [c.value for c in ws_itens[1]]
        idx_desc = headers.index("Descrição") + 1
        assert str(ws_itens.cell(row=2, column=idx_desc).value).startswith("'=CMD")
    finally:
        srv.close()
