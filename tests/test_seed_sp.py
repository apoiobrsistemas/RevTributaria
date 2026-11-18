"""Testes do Seed híbrido inicial de SP, planilha modelo e fixtures XML."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from src.app.seed_sp import DEFAULT_TEMPLATE_XLSX, executar_seed_sp
from src.app.service import RevTributariaService
from src.database import get_connection
from src.engine import auditar_config_erp
from src.legislation import validar_url_oficial

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_seed_sp_20_ncms_grupos_status_misto_e_template_xlsx(tmp_path):
    db_file = tmp_path / "seed_sp_test.db"

    res1 = executar_seed_sp(db_file, usar_rede=False, gerar_template=True)
    assert res1["federais_inseridas"] == 20
    assert res1["estaduais_inseridas"] == 20
    assert res1["terceiros_inseridas"] == 5
    assert res1["erp_importadas"] == 2

    # Idempotente na segunda execução
    res2 = executar_seed_sp(db_file, usar_rede=False, gerar_template=False)
    assert res2["federais_inseridas"] == 0
    assert res2["estaduais_inseridas"] == 0
    assert res2["terceiros_inseridas"] == 0
    assert res2["erp_importadas"] == 0

    conn = get_connection(db_file)
    try:
        # Whitelist de domínios oficiais
        fontes = conn.execute("SELECT url_oficial FROM fontes_legais").fetchall()
        assert len(fontes) >= 6
        for f in fontes:
            validar_url_oficial(f["url_oficial"])

        # Status misto: 15 ACEITO e 5 A_CONFERIR
        aceitas = conn.execute(
            "SELECT COUNT(*) FROM regras_estaduais_icms WHERE status_validacao = 'ACEITO'"
        ).fetchone()[0]
        a_conferir = conn.execute(
            "SELECT COUNT(*) FROM regras_estaduais_icms WHERE status_validacao = 'A_CONFERIR'"
        ).fetchone()[0]
        assert aceitas == 15
        assert a_conferir == 5

        # Auditoria Frente B sobre config_erp_importada gerada pelo seed
        divs_erp = auditar_config_erp(conn, lote_importacao="SEED-SP-ERP")
        campos_erp = {d.campo_divergente for d in divs_erp}
        assert "config_placeholder" in campos_erp
        assert "deduz_icms_fcp_custo_medio" in campos_erp
    finally:
        conn.close()

    # Planilha modelo gerada em templates/modelo_carga_regras_sp.xlsx
    assert DEFAULT_TEMPLATE_XLSX.exists()
    wb = openpyxl.load_workbook(DEFAULT_TEMPLATE_XLSX, read_only=True)
    try:
        ws = wb.active
        linhas = list(ws.iter_rows(values_only=True))
        assert len(linhas) == 21  # cabeçalho + 20 regras
    finally:
        wb.close()


def test_auditoria_ponta_a_ponta_fixtures_xml_sp(tmp_path):
    db_file = tmp_path / "seed_xml_test.db"
    srv = RevTributariaService(db_file)
    try:
        srv.executar_seed_sp(usar_rede=False)

        xml_ok = (FIXTURES_DIR / "nfe_sp_correta.xml").read_text(encoding="utf-8")
        res_ok = srv.executar_auditoria_nfe(xml_ok)
        assert res_ok["total_divergencias"] == 0

        xml_div = (FIXTURES_DIR / "nfe_sp_divergente.xml").read_text(encoding="utf-8")
        res_div = srv.executar_auditoria_nfe(xml_div)
        assert res_div["total_divergencias"] >= 1
        campos = {d["campo_divergente"] for d in res_div["divergencias"]}
        assert "aliq_icms" in campos
        assert "cst_icms" in campos

        # Comparativo 2 linhas por item (Nota x Lei) + CNPJ Regime
        cmp_ok = srv.gerar_comparativo_nfe_item_a_item(res_ok["chave_acesso"])
        assert cmp_ok["itens_ok"] == cmp_ok["total_itens"]
        assert len(cmp_ok["linhas"]) == cmp_ok["total_itens"] * 2
        assert cmp_ok["linhas"][0]["Check"] == "✅"
        assert cmp_ok["linhas"][0]["Registro"] == "NF-e (Nota)"
        assert cmp_ok["linhas"][1]["Registro"] == "Lei (Esperado)"

        cmp_div = srv.gerar_comparativo_nfe_item_a_item(
            res_div["chave_acesso"], regime_emitente="Lucro Presumido"
        )
        assert cmp_div["itens_divergentes"] >= 1
        assert cmp_div["emitente"]["regime_apuracao"] == "Lucro Presumido"
        assert any(l["Check"] == "❌" for l in cmp_div["linhas"])
        assert len(cmp_div["celulas_divergentes"]) >= 1

        # XML com NCM inédito (73181500): sistema deve incluir automaticamente antes de validar
        xml_novo = xml_ok.replace("85171300", "73181500").replace("35261012345678000199550010000010011000010011", "35261012345678000199550010000099991000099999")
        res_novo = srv.executar_auditoria_nfe(xml_novo)
        assert res_novo["ncms_federais_adicionados"] == 1
        assert res_novo["ncms_estaduais_adicionados"] == 1
        cmp_novo = srv.gerar_comparativo_nfe_item_a_item(res_novo["chave_acesso"])
        assert cmp_novo["total_itens"] >= 1
    finally:
        srv.close()



def test_carga_moda_siscomex_filtragem_e_idempotencia(tmp_path):
    import json
    from src.app.seed_moda import executar_carga_moda_siscomex

    siscomex_mock = json.dumps(
        {
            "Nomenclaturas": [
                {"Codigo": "6109.10.00", "Descricao": "Camisetas de algodão", "Data_Inicio": "01/04/2022", "Data_Fim": "31/12/9999"},
                {"Codigo": "6403.99.90", "Descricao": "Outros calçados de couro", "Data_Inicio": "01/04/2022", "Data_Fim": "31/12/9999"},
                {"Codigo": "4202.21.00", "Descricao": "Bolsas de couro", "Data_Inicio": "01/04/2022", "Data_Fim": "31/12/9999"},
                {"Codigo": "8703.23.10", "Descricao": "Automóveis (não moda)", "Data_Inicio": "01/04/2022", "Data_Fim": "31/12/9999"},
            ]
        }
    ).encode("utf-8")

    db_file = tmp_path / "moda_test.db"
    res1 = executar_carga_moda_siscomex(
        db_file, limite=500, siscomex_bytes=siscomex_mock, gerar_xlsx=False
    )
    assert res1["selecionados_moda"] == 3
    assert res1["federais_inseridas"] == 3
    assert res1["estaduais_inseridas"] == 3

    res2 = executar_carga_moda_siscomex(
        db_file, limite=500, siscomex_bytes=siscomex_mock, gerar_xlsx=False
    )
    assert res2["federais_inseridas"] == 0
    assert res2["estaduais_inseridas"] == 0
