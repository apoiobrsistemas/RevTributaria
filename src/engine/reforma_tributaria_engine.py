"""Motor Cronológico da Reforma Tributária 2026-2033+ (EC 132/2023 e LC 214/2025)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.engine.cclasstrib_catalog import consultar_enquadramento_cclasstrib
from src.engine.fiscal_math import CEM, ZERO, UM, _dec, _r2

# Alíquotas de referência padrão estimadas (LC 214/2025)
ALIQ_CBS_PADRAO_PLENA = Decimal("8.80")
ALIQ_IBS_UF_PADRAO_PLENA = Decimal("15.00")
ALIQ_IBS_MUN_PADRAO_PLENA = Decimal("2.70")

CRONOGRAMA_TRANSICAO_LC214: dict[int, dict[str, Any]] = {
    2026: {
        "fase": "2026 — Ano-Teste (CBS 0,90% + IBS 0,10%)",
        "cbs_ref_pct": Decimal("0.90"),
        "ibs_uf_ref_pct": Decimal("0.05"),
        "ibs_mun_ref_pct": Decimal("0.05"),
        "fator_pis_cofins": Decimal("1.00"),
        "fator_ipi": Decimal("1.00"),
        "fator_icms_iss": Decimal("1.00"),
        "is_ativo": False,
        "compensacao_2026": True,
    },
    2027: {
        "fase": "2027 — Extinção PIS/COFINS & Entrada CBS Plena + IS",
        "cbs_ref_pct": ALIQ_CBS_PADRAO_PLENA,
        "ibs_uf_ref_pct": Decimal("0.05"),
        "ibs_mun_ref_pct": Decimal("0.05"),
        "fator_pis_cofins": Decimal("0.00"),
        "fator_ipi": Decimal("0.00"),
        "fator_icms_iss": Decimal("1.00"),
        "is_ativo": True,
        "compensacao_2026": False,
    },
    2028: {
        "fase": "2028 — CBS Plena + IS (Manutenção IBS-Teste 0,10%)",
        "cbs_ref_pct": ALIQ_CBS_PADRAO_PLENA,
        "ibs_uf_ref_pct": Decimal("0.05"),
        "ibs_mun_ref_pct": Decimal("0.05"),
        "fator_pis_cofins": Decimal("0.00"),
        "fator_ipi": Decimal("0.00"),
        "fator_icms_iss": Decimal("1.00"),
        "is_ativo": True,
        "compensacao_2026": False,
    },
    2029: {
        "fase": "2029 — Transição Federativa (90% ICMS/ISS | 10% IBS)",
        "cbs_ref_pct": ALIQ_CBS_PADRAO_PLENA,
        "ibs_uf_ref_pct": _r2(ALIQ_IBS_UF_PADRAO_PLENA * Decimal("0.10")),
        "ibs_mun_ref_pct": _r2(ALIQ_IBS_MUN_PADRAO_PLENA * Decimal("0.10")),
        "fator_pis_cofins": Decimal("0.00"),
        "fator_ipi": Decimal("0.00"),
        "fator_icms_iss": Decimal("0.90"),
        "is_ativo": True,
        "compensacao_2026": False,
    },
    2030: {
        "fase": "2030 — Transição Federativa (80% ICMS/ISS | 20% IBS)",
        "cbs_ref_pct": ALIQ_CBS_PADRAO_PLENA,
        "ibs_uf_ref_pct": _r2(ALIQ_IBS_UF_PADRAO_PLENA * Decimal("0.20")),
        "ibs_mun_ref_pct": _r2(ALIQ_IBS_MUN_PADRAO_PLENA * Decimal("0.20")),
        "fator_pis_cofins": Decimal("0.00"),
        "fator_ipi": Decimal("0.00"),
        "fator_icms_iss": Decimal("0.80"),
        "is_ativo": True,
        "compensacao_2026": False,
    },
    2031: {
        "fase": "2031 — Transição Federativa (70% ICMS/ISS | 30% IBS)",
        "cbs_ref_pct": ALIQ_CBS_PADRAO_PLENA,
        "ibs_uf_ref_pct": _r2(ALIQ_IBS_UF_PADRAO_PLENA * Decimal("0.30")),
        "ibs_mun_ref_pct": _r2(ALIQ_IBS_MUN_PADRAO_PLENA * Decimal("0.30")),
        "fator_pis_cofins": Decimal("0.00"),
        "fator_ipi": Decimal("0.00"),
        "fator_icms_iss": Decimal("0.70"),
        "is_ativo": True,
        "compensacao_2026": False,
    },
    2032: {
        "fase": "2032 — Transição Federativa (60% ICMS/ISS | 40% IBS)",
        "cbs_ref_pct": ALIQ_CBS_PADRAO_PLENA,
        "ibs_uf_ref_pct": _r2(ALIQ_IBS_UF_PADRAO_PLENA * Decimal("0.40")),
        "ibs_mun_ref_pct": _r2(ALIQ_IBS_MUN_PADRAO_PLENA * Decimal("0.40")),
        "fator_pis_cofins": Decimal("0.00"),
        "fator_ipi": Decimal("0.00"),
        "fator_icms_iss": Decimal("0.60"),
        "is_ativo": True,
        "compensacao_2026": False,
    },
    2033: {
        "fase": "2033+ — Vigência Plena CBS + IBS (Extinção Total ICMS/ISS)",
        "cbs_ref_pct": ALIQ_CBS_PADRAO_PLENA,
        "ibs_uf_ref_pct": ALIQ_IBS_UF_PADRAO_PLENA,
        "ibs_mun_ref_pct": ALIQ_IBS_MUN_PADRAO_PLENA,
        "fator_pis_cofins": Decimal("0.00"),
        "fator_ipi": Decimal("0.00"),
        "fator_icms_iss": Decimal("0.00"),
        "is_ativo": True,
        "compensacao_2026": False,
    },
}


@dataclass(frozen=True)
class ContextoReformaLC214:
    """Entrada determinística pura para cálculo da transição LC 214/2025."""

    ano_calendario: int
    ncm: str
    valor_operacao_bruto: Decimal
    direcao: str = "SAIDA"  # SAIDA | ENTRADA
    icms_atual: Decimal = ZERO
    pis_atual: Decimal = ZERO
    cofins_atual: Decimal = ZERO
    ipi_atual: Decimal = ZERO
    iss_atual: Decimal = ZERO
    concorrente_zfm: bool = False
    fornecedor_simples_nacional: bool = False
    simples_regime_hibrido: bool = False
    split_payment_liquidado: bool = True
    xml_contem_gibscbs: bool = True
    reducao_custom_pct: Decimal | None = None


def calcular_transicao_lc214(ctx: ContextoReformaLC214) -> dict[str, Any]:
    """Calcula tributação dual (Sistema Atual x Reforma LC 214/2025) de 2026 a 2033+."""
    ano = max(2026, int(ctx.ano_calendario))
    chave_ano = 2033 if ano >= 2033 else ano
    param_ano = CRONOGRAMA_TRANSICAO_LC214[chave_ano]

    enq = consultar_enquadramento_cclasstrib(ctx.ncm)
    reducao_pct = _dec(ctx.reducao_custom_pct) if ctx.reducao_custom_pct is not None else _dec(enq["reducao_pct"])
    fator_red = max(ZERO, UM - (reducao_pct / CEM))

    # Base limpa "por fora" (Art. 12 § 2º LC 214/2025): exclui ICMS, PIS, COFINS e ISS embutidos
    tributos_embutidos = _dec(ctx.icms_atual) + _dec(ctx.pis_atual) + _dec(ctx.cofins_atual) + _dec(ctx.iss_atual)
    base_limpa_por_fora = max(ZERO, _r2(_dec(ctx.valor_operacao_bruto) - tributos_embutidos))

    # Em 2026 (ano-teste), alíquotas de teste são 0,90% CBS e 0,10% IBS (salvo alíquota zero da Cesta Básica)
    aliq_cbs_efetiva = _r2(param_ano["cbs_ref_pct"] * fator_red)
    aliq_ibs_uf_efetiva = _r2(param_ano["ibs_uf_ref_pct"] * fator_red)
    aliq_ibs_mun_efetiva = _r2(param_ano["ibs_mun_ref_pct"] * fator_red)

    valor_cbs = _r2(base_limpa_por_fora * aliq_cbs_efetiva / CEM)
    valor_ibs_uf = _r2(base_limpa_por_fora * aliq_ibs_uf_efetiva / CEM)
    valor_ibs_mun = _r2(base_limpa_por_fora * aliq_ibs_mun_efetiva / CEM)
    valor_ibs_total = _r2(valor_ibs_uf + valor_ibs_mun)

    # Imposto Seletivo (a partir de 2027)
    valor_is = ZERO
    aliq_is = ZERO
    if param_ano["is_ativo"] and enq["sujeito_is"]:
        aliq_is = _dec(enq["aliquota_is_padrao"])
        valor_is = _r2(base_limpa_por_fora * aliq_is / CEM)

    # Tributos residuais do sistema atual durante a transição
    icms_residual = _r2(_dec(ctx.icms_atual) * param_ano["fator_icms_iss"])
    iss_residual = _r2(_dec(ctx.iss_atual) * param_ano["fator_icms_iss"])
    pis_residual = _r2(_dec(ctx.pis_atual) * param_ano["fator_pis_cofins"])
    cofins_residual = _r2(_dec(ctx.cofins_atual) * param_ano["fator_pis_cofins"])
    fator_ipi = Decimal("1.00") if ctx.concorrente_zfm else param_ano["fator_ipi"]
    ipi_residual = _r2(_dec(ctx.ipi_atual) * fator_ipi)

    # Compensação 2026 (Art. 348 LC 214/2025)
    compensacao_2026 = ZERO
    alertas: list[str] = []
    if param_ano["compensacao_2026"]:
        if ctx.xml_contem_gibscbs:
            compensacao_2026 = min(_r2(pis_residual + cofins_residual), _r2(valor_cbs + valor_ibs_total))
        else:
            alertas.append(
                "ALERTA CRÍTICO 2026 (Art. 348 LC 214/2025): XML sem grupo gIBSCBS perde a dispensa/compensação de 0,90% CBS + 0,10% IBS contra PIS/COFINS."
            )

    if ctx.concorrente_zfm and ano >= 2027:
        alertas.append(
            "EXCEÇÃO ZONA FRANCA DE MANAUS (ZFM): IPI mantido para produtos com Processo Produtivo Básico concorrente na ZFM."
        )

    # Regras de Crédito Financeiro & Split Payment na Entrada (Art. 47 LC 214/2025)
    credito_ibs_cbs_entrada = ZERO
    regra_credito_reforma = "Não aplicável (operação de saída)."
    if ctx.direcao.strip().upper() == "ENTRADA":
        if ctx.fornecedor_simples_nacional and not ctx.simples_regime_hibrido:
            credito_ibs_cbs_entrada = ZERO
            regra_credito_reforma = (
                "Crédito IBS/CBS BLOQUEADO: fornecedor optante pelo Simples Nacional fora do regime híbrido."
            )
            alertas.append(regra_credito_reforma)
        elif not ctx.split_payment_liquidado:
            credito_ibs_cbs_entrada = ZERO
            regra_credito_reforma = (
                "Crédito IBS/CBS RETIDO (Split Payment — Art. 47 LC 214/2025): aproveitamento condicionado à extinção/liquidação do débito na etapa anterior."
            )
            alertas.append(regra_credito_reforma)
        else:
            credito_ibs_cbs_entrada = _r2(valor_cbs + valor_ibs_total)
            regra_credito_reforma = (
                f"Crédito financeiro integral admitido (R$ {credito_ibs_cbs_entrada}) via liquidação Split Payment (Art. 47 LC 214/2025)."
            )

    carga_sistema_atual = _r2(
        _dec(ctx.icms_atual) + _dec(ctx.pis_atual) + _dec(ctx.cofins_atual) + _dec(ctx.ipi_atual) + _dec(ctx.iss_atual)
    )
    carga_liquida_reforma = _r2(
        icms_residual
        + iss_residual
        + pis_residual
        + cofins_residual
        + ipi_residual
        + valor_cbs
        + valor_ibs_total
        + valor_is
        - compensacao_2026
    )

    return {
        "ano_calendario": ano,
        "fase_transicao": param_ano["fase"],
        "ncm": enq["ncm"],
        "cst_ibs_cbs": enq["cst_ibs_cbs"],
        "cclass_trib": enq["cclass_trib"],
        "reducao_aliquota_pct": str(_r2(reducao_pct)),
        "anexo_legal": enq["anexo_legal"],
        "artigo_legal": enq["artigo_legal"],
        "sujeito_imposto_seletivo": enq["sujeito_is"],
        "cclass_trib_is": enq["cclass_trib_is"],
        "base_limpa_por_fora": str(base_limpa_por_fora),
        "aliq_cbs_efetiva": str(aliq_cbs_efetiva),
        "aliq_ibs_uf_efetiva": str(aliq_ibs_uf_efetiva),
        "aliq_ibs_mun_efetiva": str(aliq_ibs_mun_efetiva),
        "aliq_is_efetiva": str(aliq_is),
        "valor_cbs": str(valor_cbs),
        "valor_ibs_uf": str(valor_ibs_uf),
        "valor_ibs_mun": str(valor_ibs_mun),
        "valor_ibs_total": str(valor_ibs_total),
        "valor_is": str(valor_is),
        "compensacao_2026": str(compensacao_2026),
        "icms_residual": str(icms_residual),
        "pis_residual": str(pis_residual),
        "cofins_residual": str(cofins_residual),
        "ipi_residual": str(ipi_residual),
        "iss_residual": str(iss_residual),
        "credito_ibs_cbs_entrada": str(credito_ibs_cbs_entrada),
        "regra_credito_reforma": regra_credito_reforma,
        "carga_sistema_atual": str(carga_sistema_atual),
        "carga_liquida_transicao": str(carga_liquida_reforma),
        "alertas_reforma": alertas,
    }
