"""Testes unitários aditivos para o Motor de Avaliação Booleana por Hipótese Legal."""

from __future__ import annotations

from src.engine import avaliar_arvore_booleana_lote, avaliar_arvore_booleana_ncm


def test_arvore_booleana_5_combinacoes() -> None:
    # 1. Tributado = Sim, ST = Não, Redução = Não, Isenção = Não -> apenas Tributado Integralmente
    r1 = avaliar_arvore_booleana_ncm(
        "39269090", "SP", "RJ", {"aliquota_icms": 18.0},
        eh_tributado_integralmente=True, pode_ter_st=False, tem_reducao_base=False, tem_isencao_ou_desoneracao=False,
    )
    assert r1["regimes_ativos"] == ["Tributado Integralmente"]
    assert all(l["Enquadramento ICMS"] == "Tributado Integralmente" for l in r1["linhas"])

    # 2. Tributado = Não, ST = Sim -> apenas ST (0.10/0.60 + margens)
    r2 = avaliar_arvore_booleana_ncm(
        "85071090", "SP", "RJ", {"cest": "0100100", "tem_st": 1, "margem_st": 40.0, "aliquota_icms": 18.0, "aliquota_icms_st": 20.0},
        eh_tributado_integralmente=False, pode_ter_st=True,
    )
    assert r2["regimes_ativos"] == ["ST"]
    assert all(l["Enquadramento ICMS"] == "ST" for l in r2["linhas"])
    assert any(l["MVA Ajustada Entrada (%)"] > 40.0 for l in r2["linhas"])
    assert any(l["MVA Ajustada Saída (%)"] > 40.0 for l in r2["linhas"])

    # 3. Tributado = Sim E ST = Sim E Importado = Sim -> todos os cenários
    r3 = avaliar_arvore_booleana_ncm(
        "85071090", "SP", "RJ", {"cest": "0100100", "tem_st": 1, "margem_st": 40.0, "aliquota_icms": 18.0, "aliquota_icms_st": 20.0},
        eh_tributado_integralmente=True, pode_ter_st=True, pode_ser_importado=True,
    )
    assert set(r3["regimes_ativos"]) == {"Tributado Integralmente", "ST"}
    assert {l["Enquadramento ICMS"] for l in r3["linhas"]} == {"Tributado Integralmente", "ST"}
    assert any("Importado" in l["Origem"] for l in r3["linhas"])

    # 4. Redução = Sim + cBenef + FCP + DIFAL
    r4 = avaliar_arvore_booleana_ncm(
        "84713019", "SP", "RJ",
        {"aliquota_icms": 18.0, "reducao_base_icms": 33.33, "codigo_beneficio_fiscal": "SP020027", "aliquota_fcp": 2.0},
        eh_tributado_integralmente=False, tem_reducao_base=True, pode_ter_st=False,
    )
    assert r4["regimes_ativos"] == ["Redução de Base"]
    nc_red = next(l for l in r4["linhas"] if l["Perfil Destinatário/Remetente"] == "Não Contribuinte")
    assert nc_red["% Redução BC ICMS"] == 33.33
    assert nc_red["Código Beneficio Fiscal (cBenef)"] == "SP020027"
    assert nc_red["FCP (%)"] == 2.0
    assert nc_red["DIFAL (%)"] > 0.0

    # 5. Lote de múltiplos NCMs via planilha/DataFrame
    lote = avaliar_arvore_booleana_lote(
        [
            {"ncm": "39269090", "uf_origem": "SP", "uf_destino": "RJ", "regra_estadual": {"aliquota_icms": 18.0}},
            {"ncm": "85071090", "uf_origem": "SP", "uf_destino": "RJ", "regra_estadual": {"cest": "0100100", "tem_st": 1, "margem_st": 40.0}},
        ]
    )
    assert len(lote["resumo_ncms"]) == 2
    assert lote["resumo_ncms"][0]["Tributado?"] == "Sim"
    assert lote["resumo_ncms"][1]["Tem ST?"] == "Sim"
    assert len(lote["linhas"]) == len(r1["linhas"]) + len(r2["linhas"])
