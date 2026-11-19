"""Testes do Exportador Oficial Linx Microvix (71 colunas A-BS e validador pré-exportação)."""

from __future__ import annotations

import io
from pathlib import Path

import openpyxl

from src.database.connection import init_db
from src.integrations.microvix_config_exporter import (
    COLUNAS_MICROVIX_71,
    SHEET_NAME_MICROVIX,
    exportar_microvix_xlsx,
    gerar_linhas_microvix,
    validar_planilha_microvix,
)


def test_layout_71_colunas_formatos_e_inversao_uf(tmp_path: Path) -> None:
    assert len(COLUNAS_MICROVIX_71) == 71
    conn = init_db(tmp_path / "mx.db")
    try:
        # SAIDA: UF_empresa=SP, UF_parceiro=MG -> UF da Operação = MG
        linhas_saida = gerar_linhas_microvix(
            conn=conn,
            id_configs="1",
            natureza_operacao="43",
            direcao="SAIDA",
            finalidade="COMERCIALIZACAO",
            uf_empresa="SP",
            uf_parceiro="MG",
            operacao_com_contribuinte=True,
            ncm="85071090",
            origem_mercadoria="3",
            cst_icms="10",
            csosn="202",
        )
        assert len(linhas_saida) == 1
        r_s = linhas_saida[0]
        assert r_s["UF da Operação"] == "MG"
        assert r_s["CST ICMS"] == "3.10"
        assert r_s["CSOSN"] == "3.202"
        assert r_s["CFOP"] == "6403"
        assert r_s["Número da FCI"] == "S"
        assert r_s["CNAE"] is None

        # ENTRADA: UF_empresa=SP, UF_parceiro=SC -> UF da Operação = SC
        linhas_ent = gerar_linhas_microvix(
            conn=conn,
            id_configs="2",
            natureza_operacao="10",
            direcao="ENTRADA",
            finalidade="USO_CONSUMO",
            uf_empresa="SP",
            uf_parceiro="SC",
            operacao_com_contribuinte=True,
            ncm="84713012",
            origem_mercadoria="0",
            cst_icms="00",
            csosn="102",
        )
        r_e = linhas_ent[0]
        assert r_e["UF da Operação"] == "SC"
        assert r_e["CFOP"] == "2556"
        assert r_e["Utiliza base de cálculo Dupla (DIFAL)"] == "S"
        assert r_e["Número da FCI"] == "N"
    finally:
        conn.close()


def test_modo_nacional_27_ufs_5_ids_270_linhas_e_xlsx_valido(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "mx_270.db")
    try:
        linhas = gerar_linhas_microvix(
            conn=conn,
            id_configs="1,2,3,4,5",
            natureza_operacao="43",
            direcao="SAIDA",
            finalidade="COMERCIALIZACAO",
            uf_empresa="SP",
            ncm="85071090",
            origem_mercadoria="0",
            cst_icms="00",
            csosn="102",
            regime_pis_cofins="Lucro Real",
            modo_nacional_27_ufs=True,
        )
        assert len(linhas) == 270  # 5 IDs x 27 UFs x 2 (N/S)

        val_mem = validar_planilha_microvix(linhas)
        assert val_mem["valido"] is True
        assert val_mem["total_linhas"] == 270

        xlsx_bytes = exportar_microvix_xlsx(linhas)
        val_xlsx = validar_planilha_microvix(xlsx_bytes)
        assert val_xlsx["valido"] is True
        assert val_xlsx["total_linhas"] == 270

        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
        assert wb.sheetnames == [SHEET_NAME_MICROVIX]
        ws = wb[SHEET_NAME_MICROVIX]
        assert ws.cell(row=2, column=6).number_format == "@"   # CST ICMS
        assert ws.cell(row=2, column=9).number_format == "0.00"  # Alíquota ICMS
    finally:
        conn.close()
