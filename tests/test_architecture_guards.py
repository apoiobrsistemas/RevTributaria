"""Testes de arquitetura SQLite, separação de domínios, optimistic locking e auditoria."""

from __future__ import annotations

import pytest

from src.database import (
    OptimisticLockError,
    atualizar_regra_com_lock,
    buscar_regra_estadual_icms,
    buscar_regra_federal,
    buscar_regra_servico,
    init_db,
    soft_delete_regra,
)
from src.legislation import (
    DominioNaoOficialError,
    citacao_existe_literalmente,
    validar_url_oficial,
)


def _colunas(conn, tabela: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}


def test_pragmas_obrigatorios_wal_fk_busy_timeout(tmp_path):
    db_file = tmp_path / "teste_wal.db"
    conn = init_db(db_file)
    try:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        busy_timeout = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        synchronous = conn.execute("PRAGMA synchronous;").fetchone()[0]

        assert str(journal_mode).lower() == "wal"
        assert foreign_keys == 1
        assert busy_timeout == 5000
        assert synchronous == 1  # NORMAL
    finally:
        conn.close()


def test_separacao_estrita_mercadorias_vs_servicos_e_sem_colunas_calculadas():
    conn = init_db(":memory:")
    try:
        cols_serv = _colunas(conn, "regras_servicos")
        cols_est = _colunas(conn, "regras_estaduais_icms")
        cols_fed = _colunas(conn, "regras_federais")
        cols_terc = _colunas(conn, "tabela_terceiros")

        # Separação estrita entre Mercadorias e Serviços
        assert "ncm" not in cols_serv
        assert "cest" not in cols_serv
        assert "cnae" in cols_serv
        assert "codigo_servico_lc116" in cols_serv
        assert "municipio_prestacao_ibge" in cols_serv

        assert "cnae" not in cols_est
        assert "aliquota_iss" not in cols_est
        assert "cnae" not in cols_fed

        # Presença dos campos de Reforma Tributária e FCI
        assert {
            "cst_ibs_cbs",
            "cclass_trib",
            "aliquota_ibs_uf",
            "aliquota_ibs_mun",
            "aliquota_cbs",
        }.issubset(cols_fed)
        assert {"numero_fci", "conteudo_importacao_pct"}.issubset(cols_terc)

        # Nenhuma coluna calculada persistida nas tabelas de regras
        colunas_proibidas = {
            "mva_ajustado",
            "reducao_derivada",
            "cst_esperado",
            "cfop_esperado",
            "cfop_entrada_esperado",
            "cst_icms_esperado",
        }
        for cols in (cols_serv, cols_est, cols_fed, cols_terc):
            assert cols.isdisjoint(colunas_proibidas)
    finally:
        conn.close()


def test_optimistic_locking_e_historico_campo_a_campo():
    conn = init_db(":memory:")
    try:
        cur = conn.execute(
            """
            INSERT INTO regras_estaduais_icms (
                uf_origem, uf_destino, ncm, cest, natureza_operacao,
                operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                cfop, cst_icms, aliquota_icms, reducao_base_icms
            ) VALUES ('SP', 'SP', '85171300', '', 'VENDA', 1, '*', '2026-01-01', '5102', '00', 18.0, 0.0)
            """
        )
        regra_id = int(cur.lastrowid)
        conn.commit()

        # Atualização válida na versão 1 -> vai para versão 2 e registra 2 diffs
        nova_versao = atualizar_regra_com_lock(
            conn,
            tabela="regras_estaduais_icms",
            registro_id=regra_id,
            versao_atual=1,
            alteracoes={"aliquota_icms": 12.0, "cst_icms": "20"},
            usuario="arquiteto_fiscal",
            motivo="Adequação ao Decreto Estadual",
        )
        assert nova_versao == 2

        regra = buscar_regra_estadual_icms(
            conn,
            uf_origem="SP",
            uf_destino="SP",
            ncm="85171300",
            data_referencia="2026-06-01",
        )
        assert regra is not None
        assert regra["versao"] == 2
        assert regra["aliquota_icms"] == 12.0
        assert regra["cst_icms"] == "20"

        historico = conn.execute(
            """
            SELECT acao, campo, valor_anterior, valor_novo, usuario, motivo
            FROM historico_alteracoes
            WHERE tabela_origem = 'regras_estaduais_icms' AND registro_id = ?
            ORDER BY id
            """,
            (regra_id,),
        ).fetchall()
        assert len(historico) == 2
        assert [(h["campo"], h["valor_anterior"], h["valor_novo"]) for h in historico] == [
            ("aliquota_icms", "18", "12.0"),
            ("cst_icms", "00", "20"),
        ]

        # Tentativa com versão obsoleta deve falhar com OptimisticLockError
        with pytest.raises(OptimisticLockError):
            atualizar_regra_com_lock(
                conn,
                tabela="regras_estaduais_icms",
                registro_id=regra_id,
                versao_atual=1,
                alteracoes={"aliquota_icms": 7.0},
                usuario="outro_usuario",
            )

        # Soft delete com versão atual (2) -> versão 3, não aparece mais nas buscas ativas
        v3 = soft_delete_regra(
            conn,
            tabela="regras_estaduais_icms",
            registro_id=regra_id,
            versao_atual=2,
            usuario="arquiteto_fiscal",
            motivo="Regra substituída",
        )
        assert v3 == 3
        assert (
            buscar_regra_estadual_icms(
                conn,
                uf_origem="SP",
                uf_destino="SP",
                ncm="85171300",
                data_referencia="2026-06-01",
            )
            is None
        )
    finally:
        conn.close()


def test_busca_federal_e_servicos():
    conn = init_db(":memory:")
    try:
        conn.execute(
            """
            INSERT INTO regras_federais (
                ncm, vigencia_inicio, cst_ibs_cbs, cclass_trib,
                aliquota_cbs, aliquota_ibs_uf, aliquota_ibs_mun
            ) VALUES ('85171300', '2026-01-01', '000', '000001', 8.80, 15.0, 2.7)
            """
        )
        conn.execute(
            """
            INSERT INTO regras_servicos (
                cnae, codigo_servico_lc116, natureza_operacao_servico,
                municipio_prestacao_ibge, municipio_recolhimento_ibge,
                vigencia_inicio, quem_pagara_iss, identificador_iss_retido, aliquota_iss
            ) VALUES ('6201501', '01.01', 'PRESTACAO', '3550308', '3550308', '2026-01-01', 'PRESTADOR', 0, 2.0)
            """
        )
        conn.commit()

        fed = buscar_regra_federal(conn, ncm="85171300", data_referencia="2026-06-01")
        assert fed is not None
        assert fed["cclass_trib"] == "000001"

        serv = buscar_regra_servico(
            conn,
            cnae="6201501",
            municipio_prestacao_ibge="3550308",
            codigo_servico_lc116="01.01",
            data_referencia="2026-06-01",
        )
        assert serv is not None
        assert serv["aliquota_iss"] == 2.0
    finally:
        conn.close()



def test_guardrail_url_oficial_e_citacao_literal():
    assert validar_url_oficial("https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp87.htm")
    with pytest.raises(DominioNaoOficialError):
        validar_url_oficial("https://consultoria-privada.com.br/ricms")

    assert citacao_existe_literalmente(
        "aliquota interna de 18%",
        "Art. 52. A alíquota interna de 18% aplica-se às operações internas.",
    )
    assert not citacao_existe_literalmente(
        "alíquota interna de 25%",
        "Art. 52. A alíquota interna de 18% aplica-se às operações internas.",
    )
