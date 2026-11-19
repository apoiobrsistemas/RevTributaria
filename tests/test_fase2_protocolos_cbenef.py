"""Testes da Fase 2: Protocolos Bilaterais CONFAZ, Tabelas cBenef UF, Vigências e Crawler."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from src.app.service import RevTributariaService
from src.automation.sync_job import main as sync_job_main
from src.database.connection import init_db
from src.database.schema_fase2 import (
    consultar_cbenef_uf,
    consultar_protocolo_st,
    garantir_carga_fase2,
)
from src.engine.fiscal_engine import resolver_parametros_estaduais
from src.legislation.acervo import (
    parsear_protocolos_confaz_html,
    parsear_tabela_cbenef_html,
)


def test_carga_fase2_idempotente_e_vigencia_portaria_sre_74(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "fase2.db")
    try:
        r1 = garantir_carga_fase2(conn)
        assert r1["cbenef_inseridos"] >= 15
        assert r1["protocolos_inseridos"] >= 10

        r2 = garantir_carga_fase2(conn)
        assert r2 == {"cbenef_inseridos": 0, "protocolos_inseridos": 0}

        # Em 2025-06-01 o protocolo/ST de smartphone em SP estava vigente
        p_2025 = consultar_protocolo_st(
            conn, uf_origem="SP", uf_destino="SP", ncm="85171300", data_operacao="2025-06-01"
        )
        assert p_2025 is not None

        # Em 2026-11-18 foi revogado pela Portaria SRE 74/2025 (vigencia_fim = 2025-12-31)
        p_2026 = consultar_protocolo_st(
            conn, uf_origem="SP", uf_destino="SP", ncm="85171300", data_operacao="2026-11-18"
        )
        assert p_2026 is None
    finally:
        conn.close()


def test_resolucao_bilateral_st_e_cbenef_por_uf(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "bilateral.db")
    try:
        # SP -> RJ (Protocolo 136/2013 + FECP 2%)
        res_rj = resolver_parametros_estaduais(
            conn,
            uf_origem="SP",
            uf_destino="RJ",
            ncm="85171300",
            cst="10",
            direcao="SAIDA",
            data_operacao="2026-11-18",
        )
        assert res_rj["protocolo_encontrado"] is True
        assert res_rj["tem_protocolo_st"] is True
        assert res_rj["mva_original"] == Decimal("49.0")
        assert res_rj["fcp_destino"] == Decimal("2.0")

        # SC -> SP (sem protocolo ativo -> Antecipação na Entrada)
        res_sc_sp = resolver_parametros_estaduais(
            conn,
            uf_origem="SC",
            uf_destino="SP",
            ncm="85071090",
            cst="00",
            direcao="ENTRADA",
            data_operacao="2026-11-18",
        )
        assert res_sc_sp["protocolo_encontrado"] is True
        assert res_sc_sp["tem_protocolo_st"] is False

        # Consulta cBenef PR e SP
        cb_sp = consultar_cbenef_uf(conn, uf="SP", cst="020", ncm="04051000")
        assert any(c["codigo_cbenef"] == "SP020003" for c in cb_sp)
        cb_pr = consultar_cbenef_uf(conn, uf="PR", cst="020", ncm="04051000")
        assert any(c["codigo_cbenef"] == "PR820001" for c in cb_pr)
    finally:
        conn.close()


def test_trava_rigida_cst_x_cbenef_no_servico(tmp_path: Path) -> None:
    srv = RevTributariaService(tmp_path / "trava_cb.db")
    try:
        # 1. CST 020 sem cBenef -> VERMELHO (Rejeição 930/931)
        res_sem = srv.simular_operacao_bidirecional(
            direcao="SAIDA",
            finalidade="COMERCIALIZACAO",
            uf_origem="SP",
            uf_destino="SP",
            ncm="04051000",
            valor_produto="1000.00",
            cst_ou_csosn="20",
            reducao_bc_pct="61.11",
            cbenef="",
        )
        assert res_sem["semaforo_risco"] == "VERMELHO"
        assert "SP020003" in res_sem["cbenef_validos_uf"]

        # 2. CST 020 com cBenef inválido -> VERMELHO (Rejeição 932)
        res_inv = srv.simular_operacao_bidirecional(
            direcao="SAIDA",
            finalidade="COMERCIALIZACAO",
            uf_origem="SP",
            uf_destino="SP",
            ncm="04051000",
            valor_produto="1000.00",
            cst_ou_csosn="20",
            reducao_bc_pct="61.11",
            cbenef="SP999999",
        )
        assert res_inv["semaforo_risco"] == "VERMELHO"

        # 3. CST 000 com cBenef indevido -> VERMELHO (Rejeição 933)
        res_00_cb = srv.simular_operacao_bidirecional(
            direcao="SAIDA",
            finalidade="COMERCIALIZACAO",
            uf_origem="SP",
            uf_destino="SP",
            ncm="04051000",
            valor_produto="1000.00",
            cst_ou_csosn="00",
            cbenef="SP020003",
        )
        assert res_00_cb["semaforo_risco"] == "VERMELHO"
        assert any("933" in a for a in res_00_cb["alertas_preventivos"])

        # 4. CST 020 com cBenef válido SP020003 -> VERDE
        res_ok = srv.simular_operacao_bidirecional(
            direcao="SAIDA",
            finalidade="COMERCIALIZACAO",
            uf_origem="SP",
            uf_destino="SP",
            ncm="04051000",
            valor_produto="1000.00",
            cst_ou_csosn="20",
            reducao_bc_pct="61.11",
            cbenef="SP020003",
        )
        assert res_ok["semaforo_risco"] == "VERDE"
    finally:
        srv.close()


def test_parsers_crawler_cbenef_e_protocolos_confaz(tmp_path: Path) -> None:
    html_cb = "<tr><td>SP020003</td><td>Redução BC</td></tr><tr><td>SP040001</td></tr>"
    parsed_cb = parsear_tabela_cbenef_html(html_cb, "SP")
    assert [x["codigo_cbenef"] for x in parsed_cb] == ["SP020003", "SP040001"]

    html_confaz = "<p>Protocolo ICMS 41/2008 e Convênio ICMS nº 142/2018 atualizados.</p>"
    parsed_cf = parsear_protocolos_confaz_html(html_confaz)
    assert len(parsed_cf) == 2

    assert sync_job_main(["--db", str(tmp_path / "bot_f2.db"), "--dry-run"]) == 0
