"""Testes de Governança Determinística (nt_validator.py + backtest_guard.py)."""

from __future__ import annotations

import json
from pathlib import Path

from src.database.connection import init_db
from src.engine.backtest_guard import (
    classificar_confiabilidade_deterministica,
    validar_regra_contra_historico_xml,
    verificar_vigencia_futura_agendada,
)
from src.legislation.nt_validator import (
    parsear_tabela_dominio_nfe,
    validar_combinacao_sintatica_nfe,
)


def test_nt_validator_regras_sefaz_e_parse_dominio() -> None:
    json_bytes = json.dumps(
        [{"cst": "00", "cfop": "5102", "cbenef": "", "cest": "", "regra_sefaz": "NT 2019.001"}]
    ).encode("utf-8")
    parsed = parsear_tabela_dominio_nfe(json_bytes, formato="json")
    assert len(parsed) == 1
    assert parsed[0]["cfop"] == "5102"

    # Rejeição 930/931: CST 00 com cBenef
    r1 = validar_combinacao_sintatica_nfe({"CST ICMS": "0.00", "Código Beneficio Fiscal": "SP020000", "CFOP": "5102"})
    assert r1["valido"] is False
    assert any("930/931" in e for e in r1["erros"])

    # Rejeição 806: CST 10 sem CEST válido de 7 dígitos
    r2 = validar_combinacao_sintatica_nfe({"CST ICMS": "0.10", "CEST": "", "CFOP": "5403"})
    assert r2["valido"] is False
    assert any("806" in e for e in r2["erros"])

    # Combinação válida com CEST de 7 dígitos
    r3 = validar_combinacao_sintatica_nfe({"CST ICMS": "0.10", "CEST": "0100100", "CFOP": "5403", "Sentido": "Saída"})
    assert r3["valido"] is True
    assert r3["status_nt"] == "APROVADA"


def test_vigencia_futura_backtest_xml_e_selo_confiabilidade(tmp_path: Path) -> None:
    conn = init_db(tmp_path / "bt.db")
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao, operacao_com_contribuinte,
                    vigencia_inicio, cfop, cst_icms, aliquota_icms, margem_st, aliquota_icms_st,
                    dispositivo_legal, status_validacao
                ) VALUES ('SP', 'RJ', '85071090', '0100100', 'VENDA', 1, '2027-01-01', '6403', '10', 18.0, 40.0, 20.0, 'Convênio ICMS 142/2018', 'ACEITO')
                """
            )
            conn.execute(
                """
                INSERT INTO nfe_documentos (
                    chave_acesso, numero_nf, serie, modelo, finalidade, data_emissao,
                    cnpj_emitente, uf_emitente, cnpj_destinatario, uf_destinatario, eh_xml_completo, xml_completo
                ) VALUES ('35261100000000000000550010000000011000000010', '1', '1', '55', '1', '2026-11-10', '11111111000111', 'SP', '22222222000122', 'RJ', 1, '<NFe/>')
                """
            )
            conn.execute(
                """
                INSERT INTO nfe_itens (
                    chave_acesso, numero_item, ncm, cest, origem_mercadoria, cfop, cst_icms,
                    valor_produto, aliq_icms, valor_st
                ) VALUES ('35261100000000000000550010000000011000000010', 1, '85071090', '0100100', '0', '6403', '10', 1000.0, 12.0, 150.0)
                """
            )

        vig = verificar_vigencia_futura_agendada(conn, ncm="85071090", uf_origem="SP", uf_destino="RJ", data_operacao="2026-11-19")
        assert vig["possui_vigencia_futura"] is True
        assert "2027-01-01" in str(vig["alerta"])

        bt_ok = validar_regra_contra_historico_xml(
            conn, "85071090", "SP", regra_candidata={"aliquota_icms": 12.0, "tem_st": 1}
        )
        assert bt_ok["status_backtest"] == "CONFORME_HISTORICO"

        bt_div = validar_regra_contra_historico_xml(
            conn, "85071090", "SP", regra_candidata={"aliquota_icms": 18.0, "tem_st": 0}
        )
        assert bt_div["status_backtest"] == "DIVERGE_HISTORICO_SEFAZ"
        assert len(bt_div["divergencias"]) == 2

        assert classificar_confiabilidade_deterministica({"status_validacao": "A_CONFERIR"}) == "A Conferir"
        assert classificar_confiabilidade_deterministica(
            {"status_validacao": "ACEITO", "trecho_literal_lei": "Art. 1º RICMS"}
        ) == "Texto Legal Validado Literalmente + Aceite Fiscal"
        assert classificar_confiabilidade_deterministica(
            {"status_validacao": "ACEITO", "dispositivo_legal": "Convênio ICMS 142/2018"}
        ) == "Validado via Tabela Oficial .xlsx/.json"
    finally:
        conn.close()
