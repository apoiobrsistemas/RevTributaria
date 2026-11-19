"""Testes de conformidade da UI Streamlit (Zero SQL) e métodos de serviço para a UI."""

from __future__ import annotations

import ast
from pathlib import Path

from src.app import RevTributariaService


def test_ui_app_zero_sqlite_e_sintaxe_valida():
    ui_dir = Path(__file__).resolve().parent.parent / "src" / "ui"
    arquivos_ui = list(ui_dir.rglob("*.py"))
    assert len(arquivos_ui) >= 6

    for py_file in arquivos_ui:
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

        assert "sqlite3" not in imports, f"sqlite3 encontrado em {py_file}"
        assert "SELECT " not in source
        assert "INSERT INTO " not in source
        assert "UPDATE " not in source


def test_service_metodos_ui_fluxo_completo():
    srv = RevTributariaService(":memory:")
    try:
        reg_id = srv.criar_regra_estadual_manual(
            uf_origem="SP",
            uf_destino="SP",
            ncm="85171300",
            cfop="5102",
            cst_icms="00",
            aliquota_icms=18.0,
            dispositivo_legal="RICMS/SP Art. 52",
            usuario="auditor_ui",
        )
        assert reg_id >= 1

        resumo_antes = srv.obter_resumo_sidebar()
        assert resumo_antes["regras_a_conferir"] == 1
        assert resumo_antes["regras_aceitas"] == 0

        regras = srv.listar_regras_estaduais(uf_origem="SP", ncm="85171300", status_validacao="A_CONFERIR")
        assert len(regras) == 1

        aprovadas = srv.aprovar_em_lote([(regras[0]["id"], regras[0]["versao"])], usuario="auditor_ui")
        assert aprovadas == 1

        resumo_depois = srv.obter_resumo_sidebar()
        assert resumo_depois["regras_a_conferir"] == 0
        assert resumo_depois["regras_aceitas"] == 1

        hist = srv.listar_historico_regra("regras_estaduais_icms", reg_id)
        assert len(hist) >= 2
    finally:
        srv.close()



def test_template_padrao_e_importacao_lote_xlsx_e_csv():
    srv = RevTributariaService(":memory:")
    try:
        tpl = srv.gerar_template_carga_ncms_bytes()
        assert len(tpl) > 100

        # Importa o próprio template .xlsx
        res_xlsx = srv.importar_regras_lote(tpl, extensao=".xlsx", usuario="teste_lote")
        assert res_xlsx == {"inseridas": 2, "ignoradas": 0}

        # Importa CSV com 1 linha válida e 1 NCM inválido
        csv_bytes = (
            "uf_origem;uf_destino;ncm;cest;cfop;cst_icms;aliquota_icms;tem_st;margem_st\n"
            "SP;RJ;85171300;2105301;6403;10;12,0;1;49,0\n"
            "SP;SP;123;;5102;00;18,0;0;0\n"
        ).encode("utf-8")
        res_csv = srv.importar_regras_lote(csv_bytes, extensao=".csv", usuario="teste_csv")
        assert res_csv == {"inseridas": 1, "ignoradas": 1}

        regras_rj = srv.listar_regras_estaduais(uf_origem="SP", uf_destino="RJ", ncm="85171300")
        assert len(regras_rj) == 1
        assert regras_rj[0]["margem_st"] == 49.0
    finally:
        srv.close()


def test_ids_naturezas_operacao_persistencia_e_coluna(tmp_path):
    db_file = tmp_path / "nat_ids.db"
    srv = RevTributariaService(db_file)
    try:
        iniciais = srv.listar_ids_naturezas_operacao()
        assert len(iniciais) == 8
        assert iniciais["Venda de Mercadorias"] == 0

        salvos = srv.salvar_ids_naturezas_operacao(
            {"Venda de Mercadorias": 3, "Outras Saídas": 72}
        )
        assert salvos["Venda de Mercadorias"] == 3
        assert salvos["Outras Saídas"] == 72

        # Altera novamente (3 -> 25) e valida persistência em nova instância
        srv.salvar_ids_naturezas_operacao({"Venda de Mercadorias": 25})
    finally:
        srv.close()

    srv2 = RevTributariaService(db_file)
    try:
        carregados = srv2.listar_ids_naturezas_operacao()
        assert carregados["Venda de Mercadorias"] == 25
        assert carregados["Outras Saídas"] == 72

        linhas = [
            {"Regime Tributário": "Lucro Real", "NCM": "85071090", "Natureza de Operação": "Venda de Mercadorias", "CFOP": "5.102"},
            {"Regime Tributário": "Lucro Real", "NCM": "85071090", "Natureza de Operação": "Outras Saídas", "CFOP": "5.949"},
        ]
        com_ids = RevTributariaService.aplicar_ids_natureza_nas_linhas(linhas, carregados)
        chaves = list(com_ids[0].keys())
        assert chaves.index("ID Natureza") == chaves.index("Natureza de Operação") - 1
        assert com_ids[0]["ID Natureza"] == 25
        assert com_ids[1]["ID Natureza"] == 72
    finally:
        srv2.close()
