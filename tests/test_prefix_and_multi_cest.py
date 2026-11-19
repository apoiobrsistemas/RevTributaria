"""Testes de regressão para busca hierárquica por prefixo no Convênio 142/2018, Multi-CEST e explode de células."""

from __future__ import annotations

from pathlib import Path

from src.app.service import RevTributariaService
from src.database.connection import init_db
from src.engine.st_resolver import resolver_st_3_passos
from src.legislation.confaz_ingestor import (
    garantir_base_confaz_142_e_acordos,
    higienizar_convenio_142_sqlite,
    parsear_convenio_142_texto,
)


def _setup_db(tmp_path: Path):
    db_path = tmp_path / "test_multi_cest.db"
    conn = init_db(db_path, Path("schema.sql"))
    garantir_base_confaz_142_e_acordos(conn)
    return db_path, conn


def test_explode_multi_ncm_convenio_142_e_higienizacao_sqlite(tmp_path: Path) -> None:
    _, conn = _setup_db(tmp_path)
    try:
        texto = """
        ANEXO XII
        12.004.00 8536.50, 8536.90 Interruptores, seccionadores e comutadores
        """
        parsed = parsear_convenio_142_texto(texto)
        ncms_parsed = [p["ncm_limpo"] for p in parsed]
        assert "853650" in ncms_parsed
        assert "853690" in ncms_parsed
        assert all(p["cest"] == "1200400" for p in parsed)
        assert all(p["tamanho_prefixo"] == 6 for p in parsed)

        # Simula registro legado sujo gravado no SQLite com múltiplos NCMs e pontos
        conn.execute(
            """
            INSERT INTO convenio_142_anexos (anexo, segmento_codigo, cest, ncm_limpo, ncm_raw, descricao_item)
            VALUES ('Anexo XII', '12', '12.004.99', '8536.50, 8536.90', '8536.50, 8536.90', 'Teste sujo')
            """
        )
        stats = higienizar_convenio_142_sqlite(conn)
        assert stats["atualizados"] >= 1
        assert stats["explodidos"] >= 1

        rows = conn.execute(
            "SELECT ncm_limpo, cest, tamanho_prefixo FROM convenio_142_anexos WHERE cest = '1200499' ORDER BY ncm_limpo"
        ).fetchall()
        assert [(r["ncm_limpo"], r["cest"], r["tamanho_prefixo"]) for r in rows] == [
            ("853650", "1200499", 6),
            ("853690", "1200499", 6),
        ]
    finally:
        conn.close()


def test_ncm_85365090_multi_cest_passo_1_e_passo_2_sp(tmp_path: Path) -> None:
    db_path, conn = _setup_db(tmp_path)
    try:
        # Regra SP vigente para Materiais Elétricos (CEST 12.004.00)
        conn.execute(
            """
            INSERT INTO regras_estaduais_icms (
                uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms, margem_st,
                aliquota_icms_st, dispositivo_legal, status_registro, status_validacao
            ) VALUES (
                'SP', 'SP', '85365090', '1200400', 'VENDA', 1,
                '0', '2026-01-01', '5405', '60', 18.0, 45.0,
                18.0, 'RICMS/SP Art. 313-Z17', 'ATIVA', 'ACEITO'
            )
            """
        )
        # Regra SP excluída da ST para Autopeças (CEST 01.055.00 - Portaria SRE 34/2026)
        conn.execute(
            """
            INSERT INTO regras_estaduais_icms (
                uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms, margem_st,
                aliquota_icms_st, dispositivo_legal, status_registro, status_validacao
            ) VALUES (
                'SP', 'SP', '85365090', '0105500', 'VENDA', 1,
                '0', '2026-01-01', '5102', '00', 18.0, 0.0,
                0.0, 'Portaria SRE 34/2026 (Exclusão Autopeças da ST)', 'ATIVA', 'ACEITO'
            )
            """
        )
        conn.commit()

        diag = resolver_st_3_passos(
            conn, ncm="8536.50.90", uf_origem="MG", uf_destino="SP", data_operacao="2026-06-01"
        )
        assert diag["elegivel_conv_142"] is True
        assert "1200400" in diag["cests_possiveis"]
        assert "0105500" in diag["cests_possiveis"]
        assert "8536.50" in diag["passo_1_resumo"]

        segs = {s["cest"]: s for s in diag["segmentos_avaliados"]}
        assert segs["1200400"]["tem_st"] is True
        assert segs["0105500"]["tem_st"] is False

        srv = RevTributariaService(db_path)
        try:
            arvore = srv.executar_arvore_booleana_ncm(
                ncm="8536.50.90", uf_origem="MG", uf_destino="SP", data_referencia="2026-06-01"
            )
            linhas = arvore["linhas"]
            assert any("12.004.00" in ln["Natureza de Operação"] and ln["CFOP Interestadual"] in {"2.403", "6.404"} for ln in linhas)
            assert any("01.055.00" in ln["Natureza de Operação"] and ln["CFOP Interestadual"] in {"2.102", "6.102", "6.108"} for ln in linhas)

            matriz = srv.consultar_matriz_operacional(
                ncm="8536.50.90", uf_origem="MG", uf_destino="SP", data_referencia="2026-06-01"
            )
            assert any("12.004.00" in ln.get("Natureza de Operação", "") for ln in matriz)
            assert any("01.055.00" in ln.get("Natureza de Operação", "") for ln in matriz)
        finally:
            srv.close()
    finally:
        conn.close()


def test_ncm_40111000_casa_posicao_4_digitos_4011_e_libera_passo_2(tmp_path: Path) -> None:
    _, conn = _setup_db(tmp_path)
    try:
        # Remove linha 401110 para garantir que o match ocorra pela posição de 4 dígitos '4011'
        conn.execute("UPDATE convenio_142_anexos SET ncm_limpo = '401199' WHERE ncm_limpo = '401110'")
        conn.execute(
            """
            INSERT INTO regras_estaduais_icms (
                uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms, margem_st,
                aliquota_icms_st, dispositivo_legal, status_registro, status_validacao
            ) VALUES (
                'SP', 'SP', '40111000', '1600100', 'VENDA', 1,
                '0', '2026-01-01', '5405', '60', 18.0, 42.0,
                18.0, 'RICMS/SP Art. 310 / Convênio ICMS 102/2017', 'ATIVA', 'ACEITO'
            )
            """
        )
        conn.commit()

        diag = resolver_st_3_passos(
            conn, ncm="4011.10.00", uf_origem="MG", uf_destino="SP", data_operacao="2026-06-01"
        )
        assert diag["elegivel_conv_142"] is True
        assert "1600100" in diag["cests_possiveis"]
        assert "4011" in diag["passo_1_resumo"]
        assert diag["tem_st"] is True
        assert diag["recolhe_st"] == "REMETENTE_RETIDO"
        assert "102/2017" in str(diag["acordo_aplicado"])
    finally:
        conn.close()
