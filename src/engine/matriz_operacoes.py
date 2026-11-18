"""Gerador dinâmico da matriz tributária linha a linha por NCM e operação."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from src.engine.fiscal_math import _dec, aliquota_interestadual, calcular_mva_ajustado


def _fmt_cst_com_origem(origem_num: str, cst: str) -> str:
    cst_clean = (cst or "00").strip().zfill(2)
    return f"{origem_num}.{cst_clean}"


def _aliquotas_fed(
    regra_fed: Mapping[str, Any] | None,
    eh_entrada: bool,
) -> dict[str, Any]:
    if not regra_fed:
        return {
            "ipi_cst": "49" if eh_entrada else "99",
            "ipi_aliq": 0.0,
            "pis_cst": "98" if eh_entrada else "01",
            "pis_aliq": 0.0 if eh_entrada else 1.65,
            "cofins_cst": "98" if eh_entrada else "01",
            "cofins_aliq": 0.0 if eh_entrada else 7.60,
        }
    return {
        "ipi_cst": str(
            (regra_fed.get("cst_ipi_entrada") if eh_entrada else regra_fed.get("cst_ipi_saida"))
            or ("49" if eh_entrada else "99")
        ),
        "ipi_aliq": float(_dec(regra_fed.get("aliquota_ipi"))),
        "pis_cst": str(
            (regra_fed.get("cst_pis_entrada") if eh_entrada else regra_fed.get("cst_pis_saida"))
            or ("98" if eh_entrada else "01")
        ),
        "pis_aliq": float(_dec(regra_fed.get("aliquota_pis"))),
        "cofins_cst": str(
            (regra_fed.get("cst_cofins_entrada") if eh_entrada else regra_fed.get("cst_cofins_saida"))
            or ("98" if eh_entrada else "01")
        ),
        "cofins_aliq": float(_dec(regra_fed.get("aliquota_cofins"))),
    }


def gerar_linhas_matriz_ncm(
    *,
    ncm: str,
    uf_origem: str,
    uf_destino: str,
    regra_est: Mapping[str, Any],
    regra_fed: Mapping[str, Any] | None = None,
    incluir_tributado_se_st: bool = False,
) -> list[dict[str, Any]]:
    """Gera dinamicamente as linhas de Compra, Venda, Dev. Compra e Dev. Venda para um NCM.

    Cobre Nacional vs. Importado (4%), Contribuinte vs. Não Contribuinte e ST vs. Tributado Integralmente.
    """
    uf_o = uf_origem.upper()
    uf_d = uf_destino.upper()
    tem_st_regra = bool(regra_est.get("tem_st"))
    aliq_interna = float(_dec(regra_est.get("aliquota_icms"), "18"))
    red_bc = float(_dec(regra_est.get("reducao_base_icms"), "0"))
    aliq_st = float(_dec(regra_est.get("aliquota_icms_st"), "0"))
    mva_orig = float(_dec(regra_est.get("margem_st"), "0"))
    aliq_fcp = float(_dec(regra_est.get("aliquota_fcp"), "0"))
    obs = str(regra_est.get("dispositivo_legal") or "")
    cest = str(regra_est.get("cest") or "")

    regimes_a_gerar = ["ST"] if tem_st_regra else ["Tributado Integralmente"]
    if tem_st_regra and incluir_tributado_se_st:
        regimes_a_gerar.append("Tributado Integralmente")

    if not tem_st_regra and red_bc > 0:
        regimes_a_gerar = ["Redução BC"]

    operacoes = [
        {
            "natureza": "(E) - COMPRA PARA COMERCIALIZAÇÃO",
            "eh_entrada": True,
            "cfop_int_norm": "1102",
            "cfop_inter_norm": "2102",
            "cfop_int_st": "1403",
            "cfop_inter_st": "2403",
            "contribuintes": [True],
        },
        {
            "natureza": "(S) - VENDA",
            "eh_entrada": False,
            "cfop_int_norm": "5102",
            "cfop_inter_norm_contrib": "6102",
            "cfop_inter_norm_nc": "6108",
            "cfop_int_st": "5405",
            "cfop_inter_st_contrib": "6404",
            "cfop_inter_st_nc": "6108",
            "contribuintes": [True, False],
        },
        {
            "natureza": "(S) - DEVOLUÇÃO DE COMPRAS",
            "eh_entrada": False,
            "cfop_int_norm": "5202",
            "cfop_inter_norm": "6202",
            "cfop_int_st": "5411",
            "cfop_inter_st": "6411",
            "contribuintes": [True],
        },
        {
            "natureza": "(E) - DEVOLUÇÃO DE VENDAS",
            "eh_entrada": True,
            "cfop_int_norm": "1202",
            "cfop_inter_norm": "2202",
            "cfop_int_st": "1411",
            "cfop_inter_st": "2411",
            "contribuintes": [True],
        },
        {
            "natureza": "(E) - ENTRADA DE TRANSFERÊNCIA ENTRE FILIAIS",
            "eh_entrada": True,
            "cfop_int_norm": "1152",
            "cfop_inter_norm": "2152",
            "cfop_int_st": "1409",
            "cfop_inter_st": "2409",
            "contribuintes": [True],
        },
        {
            "natureza": "(S) - SAÍDA DE TRANSFERÊNCIA ENTRE FILIAIS",
            "eh_entrada": False,
            "cfop_int_norm": "5152",
            "cfop_inter_norm": "6152",
            "cfop_int_st": "5409",
            "cfop_inter_st": "6409",
            "contribuintes": [True],
        },
        {
            "natureza": "(E) - OUTRAS ENTRADAS",
            "eh_entrada": True,
            "cfop_int_norm": "1949",
            "cfop_inter_norm": "2949",
            "cfop_int_st": "1949",
            "cfop_inter_st": "2949",
            "contribuintes": [True],
        },
        {
            "natureza": "(S) - OUTRAS SAÍDAS",
            "eh_entrada": False,
            "cfop_int_norm": "5949",
            "cfop_inter_norm_contrib": "6949",
            "cfop_inter_norm_nc": "6949",
            "cfop_int_st": "5949",
            "cfop_inter_st_contrib": "6949",
            "cfop_inter_st_nc": "6949",
            "contribuintes": [True, False],
        },
    ]

    linhas: list[dict[str, Any]] = []

    for regime in regimes_a_gerar:
        eh_st = regime == "ST"
        for op in operacoes:
            fed = _aliquotas_fed(regra_fed, op["eh_entrada"])
            for contrib in op["contribuintes"]:
                for origem_label, orig_cod in [("Nacional", "0"), ("Importado", "2")]:
                    aliq_inter_dec = aliquota_interestadual(uf_o, uf_d if uf_d != uf_o else "MG", orig_cod)
                    aliq_inter = float(aliq_inter_dec or Decimal("12.00"))

                    if eh_st:
                        cfop_int = op["cfop_int_st"]
                        if "cfop_inter_st_contrib" in op:
                            cfop_inter = op["cfop_inter_st_contrib"] if contrib else op["cfop_inter_st_nc"]
                        else:
                            cfop_inter = op["cfop_inter_st"]

                        if op["natureza"] in {"(E) - COMPRA PARA COMERCIALIZAÇÃO", "(S) - DEVOLUÇÃO DE COMPRAS"}:
                            cst_cod = "10"
                            csosn_cod = "201"
                        else:
                            cst_cod = "60"
                            csosn_cod = "500"

                        mva_aj = float(
                            calcular_mva_ajustado(
                                mva_orig,
                                aliq_inter,
                                aliq_st or aliq_interna,
                                uf_destino=uf_d,
                                fcp_pct=aliq_fcp,
                                reducao_bc_pct=0,
                            )
                        )
                        aliq_st_exib = aliq_st or aliq_interna
                        mva_orig_exib = mva_orig
                    else:
                        cfop_int = op["cfop_int_norm"]
                        if "cfop_inter_norm_contrib" in op:
                            cfop_inter = op["cfop_inter_norm_contrib"] if contrib else op["cfop_inter_norm_nc"]
                        else:
                            cfop_inter = op["cfop_inter_norm"]

                        cst_cod = "20" if red_bc > 0 else "00"
                        csosn_cod = "102"
                        mva_aj = 0.0
                        mva_orig_exib = 0.0
                        aliq_st_exib = 0.0

                    linhas.append(
                        {
                            "NCM": ncm,
                            "CEST": cest,
                            "UF Origem": uf_o,
                            "UF Destino": uf_d,
                            "Natureza de Operação": op["natureza"],
                            "Origem": origem_label,
                            "Contribuinte": "Sim" if contrib else "Não",
                            "Regime ICMS": regime,
                            "CFOP Interno": cfop_int,
                            "Alíq. Interna (%)": 0.0 if (eh_st and cst_cod == "60") else aliq_interna,
                            "CFOP Interestadual": cfop_inter,
                            "Alíq. Interestadual (%)": 0.0 if (eh_st and cst_cod == "60" and contrib) else aliq_inter,
                            "CST": _fmt_cst_com_origem(orig_cod, cst_cod),
                            "CSOSN": f"{orig_cod}.{csosn_cod}",
                            "Red. BC ICMS (%)": 0.0 if eh_st else red_bc,
                            "Alíq. ST (%)": aliq_st_exib,
                            "% MVA Original": mva_orig_exib,
                            "% MVA Ajustada": mva_aj,
                            "IPI CST": fed["ipi_cst"],
                            "IPI Alíq. (%)": fed["ipi_aliq"],
                            "PIS CST": fed["pis_cst"],
                            "PIS Alíq. (%)": fed["pis_aliq"],
                            "COFINS CST": fed["cofins_cst"],
                            "COFINS Alíq. (%)": fed["cofins_aliq"],
                            "Observações": obs,
                        }
                    )

    return linhas
