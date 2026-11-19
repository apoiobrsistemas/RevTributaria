"""Testes do Exportador Oficial de Configuração Tributária Linx Terceiros (71 colunas)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import openpyxl

from src.app.service import RevTributariaService
from src.integrations.linx_terceiro_exporter import (
    COLUNAS_LAYOUT_LINX_TERCEIRO,
    converter_linhas_para_layout_linx_terceiro,
)


def test_exportador_linx_terceiro_71_colunas_e_formatacao(tmp_path: Path) -> None:
    assert len(COLUNAS_LAYOUT_LINX_TERCEIRO) == 71

    srv = RevTributariaService(tmp_path / "linx_exp.db")
    try:
        srv.executar_seed_sp(usar_rede=False)
        srv.salvar_ids_naturezas_operacao({"Venda de Mercadorias": 43, "Outras Saídas": 72})
        ids_nat = srv.listar_ids_naturezas_operacao()

        linhas = srv.consultar_matriz_operacional_todas_ufs(
            ncm="85071090",
            uf_origem="SP",
            ufs_destino=["SP", "MG"],
        )
        linhas = RevTributariaService.aplicar_ids_natureza_nas_linhas(linhas, ids_nat)
        vendas = [l for l in linhas if l["Natureza de Operação"] == "Venda de Mercadorias"]
        assert len(vendas) >= 2

        convertidas = converter_linhas_para_layout_linx_terceiro(
            vendas,
            id_config_inicial=1,
            ids_natureza=ids_nat,
        )
        reg0 = convertidas[0]
        assert list(reg0.keys()) == list(COLUNAS_LAYOUT_LINX_TERCEIRO)
        assert reg0["ID Config"] == str(vendas[0]["NCM"])
        assert reg0["Natureza de Operação"] == 43
        assert "." not in str(reg0["CFOP"])
        assert "." in str(reg0["CST ICMS"])
        assert "." in str(reg0["CSOSN"])
        assert reg0["Deduz ICMS/FCP do custo médio (S/N)"] in {"S", "N"}
        assert reg0["Operação de Receita (S/N)"] == "S"
        assert reg0["Número da FCI"] in {"S", "N"}

        # Valida exportação XLSX e CSV via serviço
        xlsx_bytes = srv.exportar_linx_terceiro_xlsx(vendas, id_config_inicial=1)
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
        ws = wb.active
        headers_xlsx = [c.value for c in ws[1]]
        assert headers_xlsx == list(COLUNAS_LAYOUT_LINX_TERCEIRO)
        assert ws.cell(row=2, column=2).value == 43

        csv_bytes = srv.exportar_linx_terceiro_csv(vendas, id_config_inicial=10)
        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")), delimiter=",")
        rows_csv = list(reader)
        assert reader.fieldnames == list(COLUNAS_LAYOUT_LINX_TERCEIRO)
        assert rows_csv[0]["ID Config"] == str(vendas[0]["NCM"])
        assert rows_csv[0]["Natureza de Operação"] == "43"
    finally:
        srv.close()


def test_exportar_tabela_crua_e_zip_por_ncm_origem_cst() -> None:
    import zipfile
    from src.integrations.linx_terceiro_exporter import (
        exportar_layout_linx_terceiro_por_ncm_origem_zip,
        exportar_tabela_crua_xlsx,
    )

    linhas_mock = [
        {"NCM": "85071090", "CST ICMS": "0.00", "CFOP": "5102", "UF da Operação": "SP", "Natureza de Operação": "Venda"},
        {"NCM": "85071090", "CST ICMS": "2.00", "CFOP": "5102", "UF da Operação": "SP", "Natureza de Operação": "Venda"},
        {"NCM": "85071090", "CST ICMS": "2.41", "CFOP": "5102", "UF da Operação": "RJ", "Natureza de Operação": "Venda"},
        {"NCM": "85071090", "CST ICMS": "2.60", "CFOP": "5405", "UF da Operação": "MG", "Natureza de Operação": "Venda"},
        {"NCM": "61046000", "CST ICMS": "1.20", "CFOP": "6102", "UF da Operação": "PR", "Natureza de Operação": "Venda"},
    ]

    cru_bytes = exportar_tabela_crua_xlsx(linhas_mock)
    wb_cru = openpyxl.load_workbook(io.BytesIO(cru_bytes))
    ws_cru = wb_cru.active
    assert [c.value for c in ws_cru[1]] == list(linhas_mock[0].keys())
    assert ws_cru.max_row == 6

    zip_bytes = exportar_layout_linx_terceiro_por_ncm_origem_zip(linhas_mock, formato="xlsx")
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        nomes = sorted(zf.namelist())
        assert nomes == [
            "61046000_CST_1xx.xlsx",
            "85071090_CST_0xx.xlsx",
            "85071090_CST_2xx.xlsx",
        ]
        wb_2xx = openpyxl.load_workbook(io.BytesIO(zf.read("85071090_CST_2xx.xlsx")))
        ws_2xx = wb_2xx.active
        # 1 header + 3 linhas (2.00, 2.41, 2.60)
        assert ws_2xx.max_row == 4
