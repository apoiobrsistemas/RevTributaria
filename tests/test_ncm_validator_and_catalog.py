"""Testes do catálogo completo de fontes oficiais, validador de NCMs/exceções e robô diário."""

from __future__ import annotations

from src.app.service import RevTributariaService
from src.automation.sync_job import main as sync_job_main
from src.database import init_db
from src.engine import validar_matriz_ncms
from src.legislation import (
    CATALOGO_FONTES_OFICIAIS,
    garantir_fontes_oficiais,
    validar_url_oficial,
)


def test_catalogo_oficial_completo_e_idempotente(tmp_path):
    for fonte in CATALOGO_FONTES_OFICIAIS:
        validar_url_oficial(fonte["url_oficial"])

    db_file = tmp_path / "cat.db"
    conn = init_db(db_file)
    try:
        res1 = garantir_fontes_oficiais(conn)
        assert res1["total_catalogo"] >= 20
        assert res1["inseridas"] == res1["total_catalogo"]

        res2 = garantir_fontes_oficiais(conn)
        assert res2["inseridas"] == 0
        assert res2["ja_existentes"] == res1["total_catalogo"]
    finally:
        conn.close()


def test_validador_ncm_detecta_excecoes_cbenef_st_isencao_vigencia_monofasico(tmp_path):
    db_file = tmp_path / "val.db"
    conn = init_db(db_file)
    try:
        with conn:
            # Regra federal monofásica inconsistente (alíquota > 0 com CST 04)
            conn.execute(
                """
                INSERT INTO regras_federais (
                    ncm, vigencia_inicio, cst_pis_saida, aliquota_pis, cst_cofins_saida, aliquota_cofins
                ) VALUES ('33030010', '2026-01-01', '04', 1.65, '04', 7.60)
                """
            )
            # Regra federal válida para 84321000
            conn.execute(
                """
                INSERT INTO regras_federais (
                    ncm, vigencia_inicio, cst_pis_saida, aliquota_pis, cst_cofins_saida, aliquota_cofins, cclass_trib
                ) VALUES ('84321000', '2026-01-01', '01', 1.65, '01', 7.60, '200030')
                """
            )
            # Tabela terceiros com Convênio 52/91 para 84321000
            conn.execute(
                """
                INSERT INTO tabela_terceiros (
                    uf_terceiro, ncm, vigencia_inicio, beneficio_convenio_52_91
                ) VALUES ('SP', '84321000', '2026-01-01', 1)
                """
            )
            # 1) CST 00 com cBenef indevido + Conv 52/91 não aplicado
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao,
                    operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                    cfop, cst_icms, aliquota_icms, reducao_base_icms, codigo_beneficio_fiscal
                ) VALUES ('SP', 'SP', '84321000', '', 'VENDA', 1, '*', '2026-01-01', '5102', '00', 18.0, 0.0, 'SP020027')
                """
            )
            # 2) CST 20 sem redução + cBenef com prefixo errado
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao,
                    operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                    cfop, cst_icms, aliquota_icms, reducao_base_icms, codigo_beneficio_fiscal
                ) VALUES ('SP', 'SP', '84716053', '', 'VENDA', 1, '*', '2026-01-01', '5102', '20', 18.0, 0.0, 'SP010001')
                """
            )
            # 3) CST 40 com alíquota > 0
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao,
                    operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                    cfop, cst_icms, aliquota_icms, codigo_beneficio_fiscal
                ) VALUES ('SP', 'SP', '33030010', '', 'VENDA', 1, '*', '2026-01-01', '5102', '40', 18.0, 'SP010010')
                """
            )
            # 4) CST 10 sem CEST e sem MVA
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao,
                    operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                    cfop, cst_icms, tem_st, aliquota_icms, margem_st
                ) VALUES ('SP', 'SP', '85071090', '', 'VENDA', 1, '*', '2026-01-01', '5405', '10', 1, 18.0, 0.0)
                """
            )
            # 5) CST 60 sem ICMS Efetivo + sobreposição de vigência
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao,
                    operacao_com_contribuinte, origem_mercadoria, vigencia_inicio, vigencia_fim,
                    cfop, cst_icms, tem_st, aliquota_icms, aliquota_icms_efetivo, status_validacao
                ) VALUES ('SP', 'SP', '22021000', '0300700', 'VENDA', 1, '*', '2026-01-01', '2026-06-30', '5405', '60', 1, 0.0, 0.0, 'ACEITO')
                """
            )
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao,
                    operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                    cfop, cst_icms, tem_st, aliquota_icms, aliquota_icms_efetivo
                ) VALUES ('SP', 'SP', '22021000', '0300700', 'VENDA', 1, '*', '2026-06-01', '5405', '60', 1, 0.0, 18.0)
                """
            )

        res = validar_matriz_ncms(conn, uf_origem="SP", persistir=True)
        codigos = {a.codigo_regra for a in res["achados"]}

        assert "CST00_COM_CBENEF" in codigos
        assert "CONV52_NAO_APLICADO" in codigos
        assert "CST20_SEM_REDUCAO" in codigos
        assert "CBENEF_PREFIXO_INCOMPATIVEL" in codigos
        assert "ISENCAO_COM_ALIQUOTA" in codigos
        assert "ST_CEST_INVALIDO" in codigos
        assert "ST_MVA_AUSENTE" in codigos
        assert "ICMS_EFETIVO_AUSENTE" in codigos
        assert "VIGENCIA_SOBREPOSTA" in codigos
        assert "MONOFASICO_COM_ALIQUOTA" in codigos
        assert "ACEITO_SEM_LASTRO_LEGAL" in codigos
        assert res["ncms_com_erro"] >= 4
    finally:
        conn.close()


def test_service_e_sync_job_dry_run_end_to_end(tmp_path):
    db_file = tmp_path / "srv.db"
    srv = RevTributariaService(db_file)
    try:
        cat = srv.garantir_catalogo_fontes_oficiais()
        assert cat["total_catalogo"] >= 20
        res_val = srv.executar_validacao_ncms(uf_origem="SP")
        assert res_val["total_ncms_mapeados"] == 0
        resumo = srv.obter_resumo_mapeamento_ncms()
        assert resumo["ncms_estaduais_distintos"] == 0
    finally:
        srv.close()

    rc = sync_job_main(["--db", str(db_file), "--uf-origem", "SP", "--dry-run"])
    assert rc == 0


def test_arvore_5_camadas_casos_criticos_e_trava_sre_70_74(tmp_path):
    db_file = tmp_path / "arvore.db"
    srv = RevTributariaService(db_file)
    try:
        casos = srv.listar_casos_criticos_sp()
        assert len(casos) == 10
        ncms_casos = {c["ncm"] for c in casos}
        assert {"04051000", "15091000", "30049099"}.issubset(ncms_casos)

        # 1. Azeite 15091000 com ST ativa deve ser BLOQUEADO pela Portaria SRE 74/2025
        res_azeite_err = srv.avaliar_arvore_5_camadas_individual(
            ncm="15091000",
            cst_icms="60",
            tem_st=1,
            cest="1700100",
            descricao_item="Azeite de oliva",
            data_referencia="2026-11-18",
        )
        assert res_azeite_err["status_geral"] == "BLOQUEIO"

        # 2. Azeite 15091000 sem ST (CST 00) passa na Camada 3 e 4
        res_azeite_ok = srv.avaliar_arvore_5_camadas_individual(
            ncm="15091000",
            cst_icms="00",
            tem_st=0,
            descricao_item="Azeite de oliva",
            embalagem="500ml",
            data_referencia="2026-11-18",
        )
        assert res_azeite_ok["status_geral"] in {"OK", "ALERTA"}
        assert res_azeite_ok["camadas"][2]["status"] == "OK"

        # 3. Manteiga 04051000 com CST 20 e cBenef SP020003 (Portaria SRE 70/2025)
        res_manteiga = srv.avaliar_arvore_5_camadas_individual(
            ncm="04051000",
            cst_icms="20",
            cbenef="SP020003",
            reducao_bc=61.11,
            descricao_item="Manteiga 200g",
            embalagem="200g",
        )
        assert res_manteiga["camadas"][3]["status"] == "OK"

        # 4. Mapa 8 portais e simulador SHA-256
        mapa = srv.obter_mapa_8_portais_sp()
        assert len(mapa) == 8
        for p in mapa:
            validar_url_oficial(p["url_oficial"])

        sim = srv.simular_monitor_diario_sha256(simular_alteracao_portal="Portarias SRE / CAT")
        assert len(sim) == 8
        assert any(r["status"] == "MUDANCA_DETECTADA" for r in sim)
    finally:
        srv.close()


def test_svrs_classtrib_json_ingestor_e_catalogo_expandido(tmp_path):
    from src.automation.official_ingestor import ingerir_svrs_classtrib_json

    assert len(CATALOGO_FONTES_OFICIAIS) >= 32
    db_file = tmp_path / "svrs.db"
    conn = init_db(db_file)
    try:
        with conn:
            conn.execute(
                "INSERT INTO regras_federais (ncm, vigencia_inicio) VALUES ('85171300', '2026-01-01')"
            )
        payload = b'[{"NCM":"8517.13.00","CST":"200","cClassTrib":"200030","pRedAliq":"60.0"}]'
        qtd = ingerir_svrs_classtrib_json(conn, payload)
        assert qtd == 1
        row = conn.execute("SELECT cst_ibs_cbs, cclass_trib, reducao_ibs_cbs FROM regras_federais WHERE ncm='85171300'").fetchone()
        assert row["cst_ibs_cbs"] == "200"
        assert row["cclass_trib"] == "200030"
        assert float(row["reducao_ibs_cbs"]) == 60.0
    finally:
        conn.close()


def test_rotina_diaria_ao_abrir_executa_uma_vez_por_dia(tmp_path):
    db_file = tmp_path / "diaria.db"
    srv = RevTributariaService(db_file)
    try:
        def _fake_sync(_url: str) -> bytes:
            return b'{"Nomenclaturas": []}'

        def _fake_vigia(_url: str, _pw: bool) -> tuple[bytes, str]:
            return b"<html><body>Texto oficial vigente</body></html>", "text/html"

        res1 = srv.executar_rotina_diaria_ao_abrir(
            data_hoje="2026-11-18",
            fetcher_sync=_fake_sync,
            fetcher_vigia=_fake_vigia,
        )
        assert res1["executado_agora"] is True
        assert res1["ultima_data"] == "2026-11-18"
        assert res1["resumo"]["catalogo"]["total_catalogo"] >= 32

        # Segunda abertura no mesmo dia: não rebaixa tudo novamente
        res2 = srv.executar_rotina_diaria_ao_abrir(
            data_hoje="2026-11-18",
            fetcher_sync=_fake_sync,
            fetcher_vigia=_fake_vigia,
        )
        assert res2["executado_agora"] is False

        # Dia seguinte: executa automaticamente de novo
        res3 = srv.executar_rotina_diaria_ao_abrir(
            data_hoje="2026-11-19",
            fetcher_sync=_fake_sync,
            fetcher_vigia=_fake_vigia,
        )
        assert res3["executado_agora"] is True
        assert res3["ultima_data"] == "2026-11-19"
    finally:
        srv.close()


def test_consolidar_regras_todos_ncms_base(tmp_path):
    db_file = tmp_path / "cons.db"
    srv = RevTributariaService(db_file)
    try:
        conn = srv._get_conn()
        with conn:
            conn.execute("INSERT INTO regras_federais (ncm, descricao_ncm, vigencia_inicio) VALUES ('85171300', 'Celular', '2026-01-01')")
            conn.execute("INSERT INTO regras_federais (ncm, descricao_ncm, vigencia_inicio) VALUES ('61091000', 'Camiseta', '2026-01-01')")
        res = srv.consolidar_regras_todos_ncms_base(uf_origem="SP")
        assert res["ncms_inseridos_sp"] == 2
        assert res["federais_cclasstrib_atualizados"] == 2
        qtd_est = conn.execute("SELECT COUNT(DISTINCT ncm) FROM regras_estaduais_icms WHERE status_registro = 'ATIVA' AND fonte_legal_id IS NOT NULL").fetchone()[0]
        assert qtd_est == 2
    finally:
        srv.close()

