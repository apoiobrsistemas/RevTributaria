"""Testes de descoberta automática, ingestores oficiais e camada de serviço."""

from __future__ import annotations

import io
import json

import openpyxl
import pytest

from src.app import RevTributariaService
from src.automation import descobrir_pares_ncm_cest, ingerir_siscomex_ncm_json
from src.automation.sync_job import main as sync_job_main
from src.integrations import ingerir_nfe_idempotente, registrar_evento_nfe
from src.legislation import DominioNaoOficialError


def _tipi_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["NCM", "EX", "Descrição", "Alíquota (%)"])
    ws.append(["8517.13.00", "", "Smartphones", "0"])
    ws.append(["8432.10.00", "", "Arados", "5"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cclasstrib_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["NCM", "CST_IBS_CBS", "cClassTrib", "aliquota_cbs", "aliquota_ibs_uf", "aliquota_ibs_mun", "reducao_ibs_cbs"])
    ws.append(["8517.13.00", "000", "200001", "8.80", "15.00", "2.70", "60.00"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_descoberta_automatica_pares_e_sincronizacao_bases_oficiais():
    srv = RevTributariaService(":memory:")
    conn = srv._get_conn()
    try:
        # Produto ativo no Linx
        conn.execute(
            """
            INSERT INTO linx_produtos (empresa, cod_produto, nome_produto, ncm, cest, origem_mercadoria, payload_json)
            VALUES ('1', 'P1', 'Smartphone', '85171300', '2105301', '5', '{"desativado": "N"}')
            """
        )
        # Produto desativado no Linx (deve ser ignorado)
        conn.execute(
            """
            INSERT INTO linx_produtos (empresa, cod_produto, nome_produto, ncm, cest, origem_mercadoria, payload_json)
            VALUES ('1', 'P2', 'Antigo', '99999999', '', '0', '{"desativado": "S"}')
            """
        )
        # NF-e autorizada
        xml_ok = """<?xml version="1.0" encoding="utf-8"?>
        <nfeProc xmlns="http://www.portalfiscal.inf.br/nfe"><NFe>
          <infNFe Id="NFe35261111111111000100550010000000101000000101">
            <ide><nNF>10</nNF><serie>1</serie><mod>55</mod><finNFe>1</finNFe><dhEmi>2026-06-01T10:00:00-03:00</dhEmi></ide>
            <emit><CNPJ>11111111000100</CNPJ><enderEmit><UF>SP</UF></enderEmit></emit>
            <dest><CNPJ>22222222000100</CNPJ><enderDest><UF>SP</UF></enderDest></dest>
            <det nItem="1"><prod><cProd>P3</cProd><xProd>Arado</xProd><NCM>84321000</NCM><CFOP>5102</CFOP><vProd>500.00</vProd></prod>
              <imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST></ICMS00></ICMS></imposto></det>
          </infNFe></NFe></nfeProc>"""
        ingerir_nfe_idempotente(conn, xml_str=xml_ok)

        # NF-e cancelada (NCM 77777777 deve ser ignorado)
        xml_canc = xml_ok.replace("000000101000000101", "000000111000000111").replace("84321000", "77777777")
        chave_canc = ingerir_nfe_idempotente(conn, xml_str=xml_canc)
        registrar_evento_nfe(conn, chave_acesso=chave_canc, tipo_evento="110111", data_evento="2026-06-01T12:00:00-03:00")
        conn.commit()

        pares = descobrir_pares_ncm_cest(conn)
        assert pares == [("84321000", ""), ("85171300", "2105301")]

        siscomex_json = json.dumps(
            {
                "Nomenclaturas": [
                    {"Codigo": "8517.13.00", "Descricao": "Smartphones", "Data_Inicio": "01/01/2026", "Data_Fim": "31/12/9999"},
                    {"Codigo": "8432.10.00", "Descricao": "Arados", "Data_Inicio": "01/01/2026", "Data_Fim": "31/12/9999"},
                ]
            }
        ).encode("utf-8")

        html_142 = """
        <table>
          <tr><th>Item</th><th>CEST</th><th>NCM/SH</th><th>Descrição</th></tr>
          <tr><td>53.0</td><td>21.053.01</td><td>8517.13.00</td><td>Telefones celulares</td></tr>
        </table>
        """
        html_52_91 = "<table><tr><td>1</td><td>8432.10.00</td><td>Arados</td></tr></table>"

        resumo = srv.sincronizar_bases_oficiais(
            fontes={
                "siscomex": siscomex_json,
                "tipi": _tipi_bytes(),
                "confaz_142": html_142,
                "confaz_52_91": html_52_91,
                "cclasstrib": _cclasstrib_bytes(),
            },
            uf_origem="SP",
            ufs_destino=("SP",),
        )

        assert resumo["pares_descobertos"] == 2
        assert resumo["siscomex_atualizados"] == 2
        assert resumo["tipi_atualizados"] == 2
        assert resumo["confaz_142_atualizados"] == 1
        assert resumo["confaz_52_91_atualizados"] == 1
        assert resumo["cclasstrib_atualizados"] == 1
        assert resumo["fila_estadual_criada"] == 2

        # Verifica aprovação via serviço com optimistic lock + simulação
        regra_est = conn.execute(
            "SELECT id, versao FROM regras_estaduais_icms WHERE ncm = '85171300'"
        ).fetchone()
        nova_v = srv.aprovar_ou_editar_regra(
            tabela="regras_estaduais_icms",
            registro_id=regra_est["id"],
            versao_atual=regra_est["versao"],
            alteracoes={"aliquota_icms": 18.0},
            usuario="fiscal_sp",
            motivo="Validado na fila A_CONFERIR",
            aprovar=True,
        )
        assert nova_v == 2

        sim = srv.simular_calculo_item(
            uf_origem="SP",
            uf_destino="SP",
            ncm="85171300",
            cest="2105301",
            valor="1000.00",
        )
        assert sim["valor_icms_proprio"] == "180.00"
        assert sim["cclass_trib"] == "200001"
        assert sim["valor_cbs"] == "35.20"
    finally:
        srv.close()


def test_ingestao_bloqueia_url_nao_oficial_e_sync_job_dry_run(tmp_path):
    srv = RevTributariaService(":memory:")
    conn = srv._get_conn()
    try:
        with pytest.raises(DominioNaoOficialError):
            ingerir_siscomex_ncm_json(
                conn,
                b'{"Nomenclaturas": []}',
                url_oficial="https://site-privado.com.br/ncm.json",
            )
    finally:
        srv.close()

    db_file = tmp_path / "sync_test.db"
    assert sync_job_main(["--db", str(db_file), "--dry-run"]) == 0
