"""Testes do Acervo Documental, Parser de NTs e Pipeline das 5 Skills com Anti-Alucinação."""

from __future__ import annotations

from pathlib import Path

from src.app.service import RevTributariaService
from src.automation.sync_job import main as sync_job_main
from src.legislation.acervo import indexar_nts_portal_nfe, parsear_notas_tecnicas_portal_nfe


def test_acervo_busca_por_erro_sefaz_e_filtros(tmp_path: Path) -> None:
    srv = RevTributariaService(tmp_path / "test_acervo.db")
    try:
        res_carga = srv.garantir_acervo_oficial()
        assert res_carga["inseridos"] >= 10

        docs_930 = srv.buscar_acervo_documental(termo="930")
        assert any("SRE-70-2025" in d["codigo_ato"] for d in docs_930)

        docs_encat = srv.buscar_acervo_documental(esfera="ENCAT", status_norma="VIGENTE")
        assert len(docs_encat) >= 2
        assert all(d["esfera"] == "ENCAT" and d["status_norma"] == "VIGENTE" for d in docs_encat)
    finally:
        srv.close()


def test_parser_e_indexacao_nts_portal_nfe(tmp_path: Path) -> None:
    html_simulado = """
    <html><body>
      <a href="/portal/exibirArquivo.aspx?conteudo=123">Nota Técnica 2025.003 - Reforma Tributária IBS/CBS v1.10</a>
      <a href="/portal/exibirArquivo.aspx?conteudo=456">Nota Técnica 2024.099 - Validação cBenef x CST</a>
    </body></html>
    """
    nts = parsear_notas_tecnicas_portal_nfe(html_simulado)
    assert len(nts) == 2
    assert any(nt["codigo_ato"] == "NT-2025-003-NFE" for nt in nts)

    srv = RevTributariaService(tmp_path / "test_nts.db")
    try:
        qtd = indexar_nts_portal_nfe(srv._get_conn(), html_simulado)
        srv._get_conn().commit()
        assert qtd >= 1
        achados = srv.buscar_acervo_documental(termo="2025.003")
        assert len(achados) == 1
        assert len(achados[0]["hash_sha256"]) == 64
    finally:
        srv.close()


def test_pipeline_5_skills_com_lastro_e_bloqueio_lacuna(tmp_path: Path) -> None:
    srv = RevTributariaService(tmp_path / "test_skills.db")
    try:
        # NCM sem regra específica na matriz local -> aciona alerta de lacuna normativa
        res_lacuna = srv.executar_pipeline_skills_ncm(
            ncm="99999999",
            cst_icms="00",
            cbenef="",
            tem_st=0,
        )
        assert len(res_lacuna["skills"]) == 5
        assert res_lacuna["skills"][4]["skill_id"] == "SKILL_05"
        assert res_lacuna["lacuna_normativa"] is True
        assert "Lacuna Normativa" in res_lacuna["mensagem_bloqueio"]
        assert 0 <= res_lacuna["score_lastro"] <= 100
        assert len(res_lacuna["evidencias_documentais"]) >= 3

        # Carrega seed SP e valida NCM mapeado com 100% lastro
        srv.executar_seed_sp(usar_rede=False)
        res_ok = srv.executar_pipeline_skills_ncm(
            ncm="84716052",
            cst_icms="00",
            cbenef="",
            tem_st=0,
        )
        assert res_ok["score_lastro"] == 100
        assert res_ok["lacuna_normativa"] is False
        assert res_ok["selo_confiabilidade"] in (
            "OURO — 100% Lastro Oficial",
            "PRATA — Lastro Verificado com Ressalvas",
        )
        assert all(ev["hash_sha256"] for ev in res_ok["evidencias_documentais"])

        # NCM com ST revogada em SP (85171300) deve ser bloqueado pelo guardrail
        res_bloq = srv.executar_pipeline_skills_ncm(
            ncm="85171300",
            cst_icms="60",
            cbenef="",
            tem_st=1,
            cest="2105300",
        )
        assert res_bloq["status_geral"] == "BLOQUEIO"
    finally:
        srv.close()


def test_sync_job_dry_run_garante_acervo(tmp_path: Path) -> None:
    db_file = tmp_path / "bot_dry.db"
    rc = sync_job_main(["--db", str(db_file), "--dry-run"])
    assert rc == 0
    srv = RevTributariaService(db_file)
    try:
        docs = srv.buscar_acervo_documental()
        assert len(docs) >= 10
    finally:
        srv.close()
