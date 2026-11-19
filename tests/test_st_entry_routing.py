"""Testes de regressão para roteamento reverso de entrada ST, prefixo 6/4 dígitos e convênios nacionais."""

from __future__ import annotations

from pathlib import Path

from src.database.connection import init_db
from src.database.repository import buscar_regra_estadual_icms
from src.database.schema_fase2 import consultar_protocolo_st
from src.engine import gerar_matriz_consolidada_ncm


def test_busca_ncm_6_digitos_com_pontos_e_fallback_hierarquico(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "st_prefix.db")
    try:
        with conn:
            # Regra cadastrada apenas na subposição de 6 dígitos com pontos ("4011.10")
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                    origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms,
                    aliquota_icms_st, margem_st, dispositivo_legal, status_validacao
                ) VALUES ('MG', 'SP', '4011.10', '16.001.00', 'VENDA', 1, '*', '2026-01-01', '2403', '60', 18.0, 18.0, 42.0, 'Art. 310 RICMS/SP - Anexo XVII Port. CAT 68/2019 - Convênio ICMS 102/2017', 'ACEITO')
                """
            )
            # Regra genérica UF (Art. 52) que NÃO deve vencer a regra específica de 6 dígitos
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                    origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms,
                    aliquota_icms_st, margem_st, dispositivo_legal, status_validacao
                ) VALUES ('MG', 'SP', '', '', 'VENDA', 1, '*', '2026-01-01', '2102', '00', 18.0, 0.0, 0.0, 'RICMS/SP Art. 52', 'ACEITO')
                """
            )

        for ncm_q in ("40111000", "4011.10.00"):
            reg = buscar_regra_estadual_icms(conn, uf_origem="MG", uf_destino="SP", ncm=ncm_q)
            assert reg is not None
            assert reg["camada_resolucao"] == 3
            assert reg["margem_st"] == 42.0
            assert "Art. 310" in reg["dispositivo_legal"]
    finally:
        conn.close()


def test_convenio_nacional_todas_ufs_e_entrada_sem_protocolo_art_426a(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "conv_nac.db")
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO matriz_protocolos_st (
                    uf_origem, uf_destino, cest, ncm_prefixo, descricao_segmento,
                    ato_legal, possui_acordo_bilateral, mva_original, aliquota_interna_destino,
                    fcp_destino, modalidade_base_st, vigencia_inicio, observacao_legal
                ) VALUES ('*', 'SP', '1600100', '4011', 'Pneumáticos', 'Convênio ICMS 102/2017', 1, 42.0, 18.0, 0.0, 'MVA', '2026-01-01', 'Abrangência Nacional')
                """
            )

        ufs_teste = ["DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI"]
        for uf_o in ufs_teste:
            proto = consultar_protocolo_st(conn, uf_origem=uf_o, uf_destino="SP", ncm="40111000", cest="1600100")
            assert proto is not None
            assert proto["ato_legal"] == "Convênio ICMS 102/2017"

            matriz = gerar_matriz_consolidada_ncm(
                "40111000",
                uf_o,
                "SP",
                {
                    "cest": "1600100",
                    "tem_st": 1,
                    "tem_acordo_st": True,
                    "aliquota_icms": 18.0,
                    "aliquota_icms_st": 18.0,
                    "margem_st": 42.0,
                    "dispositivo_legal": "RICMS/SP Art. 310 - Anexo XVII Port. CAT 68/2019 - Convênio ICMS 102/2017",
                },
            )
            compras_rn = [r for r in matriz if r["Natureza de Operação"] == "(E) Compra para Comercialização" and r["Regime Tributário"] == "Regime Normal"]
            compras_sn = [r for r in matriz if r["Natureza de Operação"] == "(E) Compra para Comercialização" and r["Regime Tributário"] == "Simples Nacional"]
            assert all(r["CFOP Interestadual"] == "2.403" for r in compras_rn)
            assert any(r["CST (Orig.CST)"] in {"0.60", "2.60"} for r in compras_rn)
            assert all(r["MVA Ajustada Nacional (%)"] > 42.0 for r in compras_rn)
            assert all(r["CSOSN (Orig.CSOSN)"] in {"0.500", "2.500"} for r in compras_sn)

        # Cenário B: Sem Convênio/Protocolo -> continua CFOP 2.403 / CSOSN 0.500 (Art. 426-A), nunca 2.102 / 0.00 / 0.101
        matriz_sem_proto = gerar_matriz_consolidada_ncm(
            "40111000",
            "RO",
            "SP",
            {
                "cest": "1600100",
                "tem_st": 1,
                "tem_acordo_st": False,
                "aliquota_icms": 18.0,
                "aliquota_icms_st": 18.0,
                "margem_st": 42.0,
                "dispositivo_legal": "RICMS/SP Art. 310",
            },
        )
        compras_sem = [r for r in matriz_sem_proto if r["Natureza de Operação"] == "(E) Compra para Comercialização"]
        assert all(r["CFOP Interestadual"] == "2.403" for r in compras_sem)
        assert all("426-A" in r["Responsável ST"] for r in compras_sem)
        assert not any(r["CFOP Interestadual"] == "2.102" or r["CST (Orig.CST)"] == "0.00" for r in compras_sem)
    finally:
        conn.close()
