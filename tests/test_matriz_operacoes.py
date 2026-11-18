"""Testes da consulta linha a linha de matriz tributária por NCM e operação."""

from __future__ import annotations

import io

import openpyxl

from src.app.seed_sp import executar_seed_sp
from src.app.service import RevTributariaService


def test_consulta_matriz_completa_ncm_st_e_tributado(tmp_path):
    db_file = tmp_path / "matriz_op.db"
    executar_seed_sp(db_file, usar_rede=False, gerar_template=False)

    srv = RevTributariaService(db_file)
    try:
        linhas = srv.consultar_matriz_completa_ncm(
            ncm="85071090",
            uf_origem="SP",
            uf_destino="RJ",
            data_referencia="2026-06-01",
            incluir_tributado_se_st=True,
        )
        # 2 regimes (ST + Tributado Integralmente) x (Compra(2) + Venda(4) + DevCompra(2) + DevVenda(2) + EntTransf(2) + SaiTransf(2) + OutEnt(2) + OutSai(4)) = 40 linhas
        assert len(linhas) == 40

        naturezas = {l["Natureza de Operação"] for l in linhas}
        assert naturezas == {
            "(E) - COMPRA PARA COMERCIALIZAÇÃO",
            "(S) - VENDA",
            "(S) - DEVOLUÇÃO DE COMPRAS",
            "(E) - DEVOLUÇÃO DE VENDAS",
            "(E) - ENTRADA DE TRANSFERÊNCIA ENTRE FILIAIS",
            "(S) - SAÍDA DE TRANSFERÊNCIA ENTRE FILIAIS",
            "(E) - OUTRAS ENTRADAS",
            "(S) - OUTRAS SAÍDAS",
        }

        # Verifica Compra com ST Nacional vs Importado
        compras_st = [
            l for l in linhas
            if l["Natureza de Operação"] == "(E) - COMPRA PARA COMERCIALIZAÇÃO" and l["Regime ICMS"] == "ST"
        ]
        nac = next(l for l in compras_st if l["Origem"] == "Nacional")
        imp = next(l for l in compras_st if l["Origem"] == "Importado")
        assert nac["CFOP Interno"] == "1403"
        assert nac["CFOP Interestadual"] == "2403"
        assert nac["CST"] == "0.10"
        assert nac["Alíq. Interestadual (%)"] == 12.0
        assert nac["% MVA Ajustada"] > nac["% MVA Original"]

        assert imp["CST"] == "2.10"
        assert imp["Alíq. Interestadual (%)"] == 4.0

        # Verifica Venda ST Contribuinte (6404) vs Não Contribuinte (6108)
        vendas_st = [
            l for l in linhas
            if l["Natureza de Operação"] == "(S) - VENDA" and l["Regime ICMS"] == "ST"
        ]
        v_contrib = [l for l in vendas_st if l["Contribuinte"] == "Sim"]
        v_nc = [l for l in vendas_st if l["Contribuinte"] == "Não"]
        assert all(l["CFOP Interestadual"] == "6404" for l in v_contrib)
        assert all(l["CFOP Interestadual"] == "6108" for l in v_nc)

        # Verifica Devoluções
        dev_compra = next(
            l for l in linhas
            if l["Natureza de Operação"] == "(S) - DEVOLUÇÃO DE COMPRAS" and l["Regime ICMS"] == "ST"
        )
        assert (dev_compra["CFOP Interno"], dev_compra["CFOP Interestadual"]) == ("5411", "6411")

        dev_venda = next(
            l for l in linhas
            if l["Natureza de Operação"] == "(E) - DEVOLUÇÃO DE VENDAS" and l["Regime ICMS"] == "ST"
        )
        assert (dev_venda["CFOP Interno"], dev_venda["CFOP Interestadual"]) == ("1411", "2411")

        # Verifica exportação .xlsx
        xlsx_bytes = srv.exportar_matriz_ncm_xlsx(linhas)
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True)
        try:
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            assert len(rows) == 41  # cabeçalho + 40 linhas
        finally:
            wb.close()
    finally:
        srv.close()
