"""Testes do Motor de Decisão de ST em 3 Passos (Conv. 142/18 x UF Destino x Acordo Interestadual)."""

from __future__ import annotations

from pathlib import Path

from src.database.connection import init_db
from src.engine.st_resolver import resolver_st_3_passos
from src.legislation.confaz_ingestor import garantir_base_confaz_142_e_acordos, parsear_convenio_142_texto


def test_parse_convenio_142_explosao_multi_ncm() -> None:
    texto = """
    ANEXO XVII
    16.001.00 | 4011.10.00, 4011.20, 4011 | Pneumáticos novos de borracha
    """
    itens = parsear_convenio_142_texto(texto)
    ncms = {i["ncm_limpo"] for i in itens}
    assert ncms == {"40111000", "401120", "4011"}
    assert all(i["cest"] == "1600100" and i["segmento_codigo"] == "16" for i in itens)


def test_st_resolver_3_passos_4_cenarios(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "st_3steps.db")
    try:
        garantir_base_confaz_142_e_acordos(conn)
        with conn:
            # 1. Pneumáticos 4011 (SP Art. 310)
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                    origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms,
                    aliquota_icms_st, margem_st, dispositivo_legal, status_validacao
                ) VALUES ('SP', 'SP', '4011', '1600100', 'VENDA', 1, '*', '2026-01-01', '1403', '60', 18.0, 18.0, 42.0, 'Art. 310 RICMS/SP', 'ACEITO')
                """
            )
            # 2. Uísque 2208.30.20 em SP excluído da ST em 01/10/2026 (vigencia_fim 2026-09-30)
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                    origem_mercadoria, vigencia_inicio, vigencia_fim, cfop, cst_icms, aliquota_icms,
                    aliquota_icms_st, margem_st, dispositivo_legal, status_validacao
                ) VALUES ('SP', 'SP', '22083020', '2800100', 'VENDA', 1, '*', '2020-01-01', '2026-09-30', '5405', '60', 25.0, 25.0, 70.0, 'Antigo Art. 313-C', 'ACEITO')
                """
            )
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                    origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms,
                    aliquota_icms_st, margem_st, dispositivo_legal, status_validacao
                ) VALUES ('SP', 'SP', '22083020', '', 'VENDA', 1, '*', '2026-10-01', '5102', '00', 25.0, 0.0, 0.0, 'Exclusão ST Bebidas Quentes SP 10/2026', 'ACEITO')
                """
            )
            # 3. Biscoitos 1905.31.00 Portaria SRE 12/2026 IVA 59.67%
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                    origem_mercadoria, vigencia_inicio, cfop, cst_icms, aliquota_icms,
                    aliquota_icms_st, margem_st, dispositivo_legal, status_validacao
                ) VALUES ('SP', 'SP', '19053100', '1705300', 'VENDA', 1, '*', '2026-01-01', '5405', '60', 18.0, 18.0, 59.67, 'Portaria SRE 12/2026', 'ACEITO')
                """
            )

        # Caso 1: 4011.10.00 MG -> SP (Passo 1 OK, Passo 2 ST SP Art. 310, Passo 3 Convênio Nacional 102/2017)
        r1 = resolver_st_3_passos(conn, ncm="4011.10.00", uf_origem="MG", uf_destino="SP", data_operacao="2026-11-19")
        assert r1["elegivel_conv_142"] is True
        assert r1["obrigacao_uf_destino"] is True
        assert r1["tem_st"] is True
        assert r1["recolhe_st"] == "REMETENTE_RETIDO"
        assert r1["acordo_aplicado"] == "Convênio ICMS 102/2017"
        assert r1["cfop_entrada"] == "2.403"
        assert r1["cst_entrada"] == "0.60"

        # Caso 2: 2208.30.20 em SP pós-01/10/2026 -> Passo 1 OK, Passo 2 Fora da ST em SP
        r2 = resolver_st_3_passos(conn, ncm="2208.30.20", uf_origem="MG", uf_destino="SP", data_operacao="2026-11-19")
        assert r2["elegivel_conv_142"] is True
        assert r2["obrigacao_uf_destino"] is False
        assert r2["tem_st"] is False
        assert r2["cfop_entrada"] == "2.102"
        assert r2["cst_entrada"] == "0.00"

        # Caso 3: 1905.31.00 Biscoitos -> Passo 1 OK CEST 1705300, Passo 2 ST SP Portaria SRE 12/2026 IVA 59.67%
        r3 = resolver_st_3_passos(conn, ncm="1905.31.00", uf_origem="SC", uf_destino="SP", data_operacao="2026-11-19")
        assert r3["elegivel_conv_142"] is True
        assert "1705300" in r3["cests_possiveis"]
        assert r3["tem_st"] is True
        assert r3["mva_original"] == 59.67
        assert r3["recolhe_st"] == "DESTINATARIO_ANTECIPACAO"  # SC -> SP sem protocolo para biscoitos
        assert r3["cfop_entrada"] == "2.403"

        # Caso 4: NCM fora do Convênio 142/2018 -> Bloqueio imediato no Passo 1
        r4 = resolver_st_3_passos(conn, ncm="9999.88.77", uf_origem="MG", uf_destino="SP", data_operacao="2026-11-19")
        assert r4["elegivel_conv_142"] is False
        assert r4["tem_st"] is False
        assert r4["recolhe_st"] == "NAO_APLICAVEL"
    finally:
        conn.close()
