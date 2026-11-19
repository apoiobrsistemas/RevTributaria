"""Testes unitários aditivos para o Validador de ST na Saída em 4 Passos (CO e NC)."""

from __future__ import annotations

from pathlib import Path

from src.database.connection import init_db
from src.engine.st_resolver import resolver_st_saida
from src.legislation.confaz_ingestor import garantir_base_confaz_142_e_acordos


def test_st_saida_4_passos_todos_cenarios(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "st_saida.db")
    try:
        garantir_base_confaz_142_e_acordos(conn)
        with conn:
            # Pneumáticos 4011 (SP e MG com ST)
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                    origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms,
                    aliquota_icms_st, margem_st, dispositivo_legal, status_validacao
                ) VALUES ('SP', 'SP', '4011', '1600100', 'VENDA', 1, '*', '2026-01-01', '5405', '60', 18.0, 18.0, 42.0, 'Art. 310 RICMS/SP', 'ACEITO')
                """
            )
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                    origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms,
                    aliquota_icms_st, margem_st, dispositivo_legal, status_validacao
                ) VALUES ('MG', 'MG', '4011', '1600100', 'VENDA', 1, '*', '2026-01-01', '5405', '60', 18.0, 18.0, 42.0, 'RICMS/MG', 'ACEITO')
                """
            )
            # Biscoitos 1905.31.00 (ST em SC, sem protocolo SP -> SC)
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                    origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms,
                    aliquota_icms_st, margem_st, dispositivo_legal, status_validacao
                ) VALUES ('SC', 'SC', '19053100', '1705300', 'VENDA', 1, '*', '2026-01-01', '5405', '60', 17.0, 17.0, 59.67, 'RICMS/SC', 'ACEITO')
                """
            )

        # 1. Saída Interna (SP -> SP) de item com ST (4011.10.00) -> CFOP 5.405, CST 0.60 / 2.60, CSOSN 0.500
        s_int_nac = resolver_st_saida(
            conn, ncm="4011.10.00", uf_origem="SP", uf_destino="SP", perfil_destinatario="CO", origem_mercadoria="0", data_operacao="2026-11-19"
        )
        s_int_imp = resolver_st_saida(
            conn, ncm="4011.10.00", uf_origem="SP", uf_destino="SP", perfil_destinatario="CO", origem_mercadoria="2", data_operacao="2026-11-19"
        )
        assert s_int_nac["cfop"] == "5.405"
        assert s_int_nac["cst"] == "0.60"
        assert s_int_nac["csosn"] == "0.500"
        assert s_int_nac["aliquota_st"] == 0.0
        assert s_int_imp["cst"] == "2.60"

        # 2. Saída Interestadual (SP -> MG) para CO com Convênio Nacional (102/2017) -> CFOP 6.404, CST 0.10 (Nac. 12%) e 2.10 (Imp. 4%) + MVA Ajustado
        s_inter_nac = resolver_st_saida(
            conn, ncm="4011.10.00", uf_origem="SP", uf_destino="MG", perfil_destinatario="CO", origem_mercadoria="0", data_operacao="2026-11-19"
        )
        s_inter_imp = resolver_st_saida(
            conn, ncm="4011.10.00", uf_origem="SP", uf_destino="MG", perfil_destinatario="CO", origem_mercadoria="2", data_operacao="2026-11-19"
        )
        assert s_inter_nac["cfop"] == "6.404"
        assert s_inter_nac["cst"] == "0.10"
        assert s_inter_nac["aliquota_icms"] == 12.0
        assert s_inter_nac["mva_ajustada"] > s_inter_nac["mva_original"]
        assert s_inter_nac["acordo_aplicado"] == "Convênio ICMS 102/2017"

        assert s_inter_imp["cfop"] == "6.404"
        assert s_inter_imp["cst"] == "2.10"
        assert s_inter_imp["aliquota_icms"] == 4.0
        assert s_inter_imp["mva_ajustada"] > s_inter_nac["mva_ajustada"]

        # 3. Saída Interestadual para CO de item com ST SEM Protocolo/Convênio (SP -> SC 1905.31.00) -> CST 0.60 / 2.60 sem destaque ST
        s_sem_proto = resolver_st_saida(
            conn, ncm="1905.31.00", uf_origem="SP", uf_destino="SC", perfil_destinatario="CO", origem_mercadoria="0", data_operacao="2026-11-19"
        )
        assert s_sem_proto["cst"] == "0.60"
        assert s_sem_proto["aliquota_st"] == 0.0
        assert s_sem_proto["mva_ajustada"] == 0.0
        assert "sem Convênio/Protocolo" in s_sem_proto["observacao"]

        # 4. Saída Interestadual para Não Contribuinte (NC) -> CFOP 6.108 com DIFAL e sem retenção ST
        s_nc = resolver_st_saida(
            conn, ncm="4011.10.00", uf_origem="SP", uf_destino="MG", perfil_destinatario="NC", origem_mercadoria="0", data_operacao="2026-11-19"
        )
        assert s_nc["cfop"] == "6.108"
        assert s_nc["tem_st"] is False
        assert s_nc["aliquota_st"] == 0.0
        assert s_nc["difal_pct"] > 0.0
    finally:
        conn.close()
