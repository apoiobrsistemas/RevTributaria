"""Motor Fiscal Determinístico Bidirecional (Saída vs Entrada Inversa, CST/CSOSN, RBC, ST, DIFAL e Crédito)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from src.engine.fiscal_math import (
    CEM,
    ZERO,
    UM,
    _dec,
    _r2,
    aliquota_interestadual,
    calcular_mva_ajustado,
)

DIRECOES_OPERACAO = ("SAIDA", "ENTRADA")
FINALIDADES_OPERACAO = (
    "COMERCIALIZACAO",
    "INDUSTRIALIZACAO",
    "USO_CONSUMO",
    "ATIVO_IMOBILIZADO",
    "DEVOLUCAO",
)

# Alíquota modal interna ICMS (%) e FCP padrão por UF (27 UFs)
ALIQUOTAS_INTERNAS_UF: dict[str, tuple[Decimal, Decimal]] = {
    "AC": (Decimal("19.00"), Decimal("0.00")),
    "AL": (Decimal("19.00"), Decimal("1.00")),
    "AM": (Decimal("20.00"), Decimal("0.00")),
    "AP": (Decimal("18.00"), Decimal("0.00")),
    "BA": (Decimal("20.50"), Decimal("0.00")),
    "CE": (Decimal("20.00"), Decimal("0.00")),
    "DF": (Decimal("20.00"), Decimal("0.00")),
    "ES": (Decimal("17.00"), Decimal("0.00")),
    "GO": (Decimal("19.00"), Decimal("0.00")),
    "MA": (Decimal("22.00"), Decimal("0.00")),
    "MG": (Decimal("18.00"), Decimal("0.00")),
    "MS": (Decimal("17.00"), Decimal("0.00")),
    "MT": (Decimal("17.00"), Decimal("0.00")),
    "PA": (Decimal("19.00"), Decimal("0.00")),
    "PB": (Decimal("20.00"), Decimal("0.00")),
    "PE": (Decimal("20.50"), Decimal("0.00")),
    "PI": (Decimal("21.00"), Decimal("0.00")),
    "PR": (Decimal("19.50"), Decimal("0.00")),
    "RJ": (Decimal("20.00"), Decimal("2.00")),
    "RN": (Decimal("18.00"), Decimal("0.00")),
    "RO": (Decimal("19.50"), Decimal("0.00")),
    "RR": (Decimal("20.00"), Decimal("0.00")),
    "RS": (Decimal("17.00"), Decimal("0.00")),
    "SC": (Decimal("17.00"), Decimal("0.00")),
    "SE": (Decimal("19.00"), Decimal("0.00")),
    "SP": (Decimal("18.00"), Decimal("0.00")),
    "TO": (Decimal("20.00"), Decimal("0.00")),
}

DESCRICOES_CST_CSOSN: dict[str, str] = {
    "00": "CST 000 — Tributada integralmente",
    "000": "CST 000 — Tributada integralmente",
    "10": "CST 010 — Tributada e com cobrança do ICMS por ST",
    "010": "CST 010 — Tributada e com cobrança do ICMS por ST",
    "20": "CST 020 — Com redução de base de cálculo (RBC)",
    "020": "CST 020 — Com redução de base de cálculo (RBC)",
    "30": "CST 030 — Isenta ou não tributada e com cobrança de ICMS por ST",
    "030": "CST 030 — Isenta ou não tributada e com cobrança de ICMS por ST",
    "40": "CST 040 — Isenta",
    "040": "CST 040 — Isenta",
    "41": "CST 041 — Não tributada",
    "041": "CST 041 — Não tributada",
    "50": "CST 050 — Suspensão",
    "050": "CST 050 — Suspensão",
    "51": "CST 051 — Diferimento",
    "051": "CST 051 — Diferimento",
    "60": "CST 060 — ICMS cobrado anteriormente por ST",
    "060": "CST 060 — ICMS cobrado anteriormente por ST",
    "70": "CST 070 — Com redução de base de cálculo e cobrança de ICMS por ST",
    "070": "CST 070 — Com redução de base de cálculo e cobrança de ICMS por ST",
    "90": "CST 090 — Outras",
    "090": "CST 090 — Outras",
    "101": "CSOSN 101 — Tributada pelo Simples Nacional com permissão de crédito (Art. 23 LC 123/2006)",
    "102": "CSOSN 102 — Tributada pelo Simples Nacional sem permissão de crédito",
    "103": "CSOSN 103 — Isenção do ICMS no Simples Nacional para faixa de receita bruta",
    "201": "CSOSN 201 — Simples Nacional com permissão de crédito e cobrança de ICMS por ST",
    "202": "CSOSN 202 — Simples Nacional sem permissão de crédito e cobrança de ICMS por ST",
    "203": "CSOSN 203 — Isenção no Simples Nacional para faixa e cobrança de ICMS por ST",
    "300": "CSOSN 300 — Imune",
    "400": "CSOSN 400 — Não tributada pelo Simples Nacional",
    "500": "CSOSN 500 — ICMS cobrado anteriormente por ST ou por antecipação",
    "900": "CSOSN 900 — Outros",
}


@dataclass(frozen=True)
class ContextoOperacaoFiscal:
    """Entrada pura e determinística para avaliação bidirecional (Saída ou Entrada)."""

    direcao: str  # SAIDA | ENTRADA
    finalidade: str  # COMERCIALIZACAO | INDUSTRIALIZACAO | USO_CONSUMO | ATIVO_IMOBILIZADO | DEVOLUCAO
    uf_origem: str
    uf_destino: str
    ncm: str
    valor_produto: Decimal
    quantidade: Decimal = Decimal("1")
    valor_ipi: Decimal = ZERO
    valor_frete: Decimal = ZERO
    valor_despesas: Decimal = ZERO
    valor_desconto: Decimal = ZERO
    origem_mercadoria: str = "0"
    operacao_com_contribuinte: bool = True
    cst_ou_csosn: str = "00"
    cbenef: str = ""
    cest: str = ""
    aliquota_icms_proprio: Decimal | None = None
    aliquota_interna_destino: Decimal | None = None
    aliquota_fcp: Decimal | None = None
    reducao_bc_pct: Decimal = ZERO
    reducao_bc_st_pct: Decimal = ZERO
    percentual_diferimento_pct: Decimal = ZERO
    tem_st: bool = False
    tem_protocolo_st: bool = False
    st_retida_na_origem: bool = False
    mva_original_pct: Decimal = ZERO
    pmpf_unitario: Decimal = ZERO
    fornecedor_simples_nacional: bool = False
    aliquota_credito_sn_pct: Decimal = ZERO
    utiliza_bc_dupla_difal: bool = True
    fci_pct: Decimal | None = None


def _resolver_cfop_esperado(
    *,
    direcao: str,
    finalidade: str,
    interestadual: bool,
    importacao_direta: bool,
    tem_st: bool,
) -> str:
    if direcao == "ENTRADA":
        prefixo = "3" if importacao_direta else ("2" if interestadual else "1")
        if finalidade == "DEVOLUCAO":
            return f"{prefixo}411" if tem_st else f"{prefixo}202"
        if finalidade == "USO_CONSUMO":
            return f"{prefixo}407" if tem_st else f"{prefixo}556"
        if finalidade == "ATIVO_IMOBILIZADO":
            return f"{prefixo}406" if tem_st else f"{prefixo}551"
        if finalidade == "INDUSTRIALIZACAO":
            return f"{prefixo}401" if tem_st else f"{prefixo}101"
        return f"{prefixo}403" if tem_st else f"{prefixo}102"

    # SAIDA
    prefixo = "6" if interestadual else "5"
    if finalidade == "DEVOLUCAO":
        return f"{prefixo}411" if tem_st else f"{prefixo}202"
    if finalidade == "ATIVO_IMOBILIZADO":
        return f"{prefixo}551"
    if finalidade == "USO_CONSUMO":
        return f"{prefixo}949"
    return f"{prefixo}403" if (tem_st and interestadual) else (f"{prefixo}405" if tem_st else f"{prefixo}102")


def avaliar_operacao_bidirecional(
    ctx: ContextoOperacaoFiscal,
    *,
    regra_est: Mapping[str, Any] | None = None,
    regra_fed: Mapping[str, Any] | None = None,
    cbenef_validos: list[Mapping[str, Any]] | None = None,
    ato_legal_st: str = "",
) -> dict[str, Any]:
    """Executa o roteador bidirecional completo (Saída x Entrada Inversa) em Decimal puro."""
    direcao = ctx.direcao.strip().upper()
    if direcao not in DIRECOES_OPERACAO:
        raise ValueError(f"Direção inválida: {ctx.direcao}. Use SAIDA ou ENTRADA.")
    finalidade = ctx.finalidade.strip().upper()
    if finalidade not in FINALIDADES_OPERACAO:
        raise ValueError(f"Finalidade inválida: {ctx.finalidade}.")

    uf_o = ctx.uf_origem.strip().upper()
    uf_d = ctx.uf_destino.strip().upper()
    interestadual = uf_o != uf_d

    # Na ENTRADA, nossa empresa é UF_Destino (recebedor); na SAIDA, nossa empresa é UF_Origem (emissor)
    uf_legislacao_aplicavel = uf_d if direcao == "ENTRADA" else uf_o
    papel_nossa_empresa = (
        f"RECEBEDOR ({uf_d}) — Fornecedor Emissor ({uf_o})"
        if direcao == "ENTRADA"
        else f"EMISSOR ({uf_o}) — Destinatário ({uf_d})"
    )

    aliq_modal_dest, fcp_padrao_dest = ALIQUOTAS_INTERNAS_UF.get(uf_d, (Decimal("18.00"), ZERO))
    aliq_modal_orig, fcp_padrao_orig = ALIQUOTAS_INTERNAS_UF.get(uf_o, (Decimal("18.00"), ZERO))

    aliq_intra_dest = ctx.aliquota_interna_destino if ctx.aliquota_interna_destino is not None else aliq_modal_dest
    fcp_pct = ctx.aliquota_fcp if ctx.aliquota_fcp is not None else (
        fcp_padrao_dest if direcao == "ENTRADA" or interestadual else fcp_padrao_orig
    )

    if ctx.aliquota_icms_proprio is not None:
        aliq_propria = _dec(ctx.aliquota_icms_proprio)
    elif interestadual:
        aliq_propria = aliquota_interestadual(uf_o, uf_d, ctx.origem_mercadoria)
    else:
        aliq_propria = aliq_modal_orig

    cst_raw = str(ctx.cst_ou_csosn or "00").strip()
    cst_norm = cst_raw.zfill(2) if len(cst_raw) <= 2 else cst_raw
    is_csosn = len(cst_norm) == 3 and cst_norm[0] in {"1", "2", "3", "4", "5", "9"}
    cst_2 = cst_norm[-2:] if not is_csosn else cst_norm

    valor_merc = _dec(ctx.valor_produto) + _dec(ctx.valor_frete) + _dec(ctx.valor_despesas) - _dec(ctx.valor_desconto)
    valor_merc = max(ZERO, valor_merc)
    ipi = _dec(ctx.valor_ipi)

    # 1. Base de Cálculo e ICMS Próprio por CST / CSOSN
    red_bc = _dec(ctx.reducao_bc_pct)
    bc_icms_proprio = valor_merc
    valor_icms_proprio = ZERO
    valor_isento_nao_trib = ZERO
    valor_icms_diferido = ZERO

    if cst_2 in {"20", "70"}:
        bc_icms_proprio = _r2(valor_merc * (UM - red_bc / CEM))
        valor_icms_proprio = _r2(bc_icms_proprio * aliq_propria / CEM)
        valor_isento_nao_trib = _r2(valor_merc - bc_icms_proprio)
    elif cst_2 in {"30", "40", "41", "50", "60"} or cst_norm in {"103", "300", "400", "500"}:
        bc_icms_proprio = ZERO
        valor_icms_proprio = ZERO
        valor_isento_nao_trib = _r2(valor_merc)
    elif cst_2 == "51":
        icms_cheio = _r2(valor_merc * aliq_propria / CEM)
        perc_dif = _dec(ctx.percentual_diferimento_pct)
        valor_icms_diferido = _r2(icms_cheio * perc_dif / CEM)
        valor_icms_proprio = _r2(icms_cheio - valor_icms_diferido)
    elif cst_norm in {"101", "201"}:
        bc_icms_proprio = _r2(valor_merc)
        valor_icms_proprio = _r2(bc_icms_proprio * _dec(ctx.aliquota_credito_sn_pct) / CEM)
    elif cst_norm in {"102", "202", "203", "900"}:
        bc_icms_proprio = ZERO
        valor_icms_proprio = ZERO
    else:
        # CST 00 / 10 / 90
        bc_icms_proprio = _r2(valor_merc)
        valor_icms_proprio = _r2(bc_icms_proprio * aliq_propria / CEM)

    # 2. ICMS-ST (CST 010 / 030 / 070 / CSOSN 201 / 202 / 203 ou ST na Entrada)
    aplica_st = ctx.tem_st or cst_2 in {"10", "30", "70"} or cst_norm in {"201", "202", "203"}
    mva_original = _dec(ctx.mva_original_pct)
    # Trava Convênio ICMS 142/2018: fornecedor Simples Nacional NÃO ajusta MVA
    nao_ajusta_mva = ctx.fornecedor_simples_nacional or not interestadual
    mva_aplicada = calcular_mva_ajustado(
        mva_original,
        aliq_propria,
        aliq_intra_dest,
        uf_destino=uf_d,
        fcp_pct=fcp_pct,
        reducao_bc_pct=ctx.reducao_bc_st_pct,
        nao_ajusta_mva=nao_ajusta_mva,
    ) if aplica_st else ZERO

    bc_st = ZERO
    valor_icms_st = ZERO
    valor_fcp_st = ZERO
    antecipacao_st_entrada = ZERO

    if aplica_st and finalidade not in {"USO_CONSUMO", "ATIVO_IMOBILIZADO"}:
        if _dec(ctx.pmpf_unitario) > ZERO:
            bc_st = _r2(_dec(ctx.pmpf_unitario) * _dec(ctx.quantidade))
        else:
            base_para_mva = valor_merc + ipi
            bc_st_bruta = base_para_mva * (UM + mva_aplicada / CEM)
            bc_st = _r2(bc_st_bruta * (UM - _dec(ctx.reducao_bc_st_pct) / CEM))

        icms_proprio_deducao = valor_icms_proprio
        if ctx.fornecedor_simples_nacional and is_csosn:
            icms_proprio_deducao = _r2(valor_merc * aliq_propria / CEM)
        icms_st_bruto = _r2(bc_st * aliq_intra_dest / CEM)
        valor_icms_st = max(ZERO, _r2(icms_st_bruto - icms_proprio_deducao))
        valor_fcp_st = _r2(bc_st * fcp_pct / CEM)

        if direcao == "ENTRADA" and (not ctx.tem_protocolo_st or not ctx.st_retida_na_origem):
            antecipacao_st_entrada = _r2(valor_icms_st + valor_fcp_st)

    # 3. DIFAL (Saída para Não Contribuinte EC 87/2015 OU Entrada Uso/Consumo & Ativo)
    difal_valor = ZERO
    fcp_difal = ZERO
    exige_difal_saida = direcao == "SAIDA" and interestadual and not ctx.operacao_com_contribuinte
    exige_difal_entrada = direcao == "ENTRADA" and interestadual and finalidade in {"USO_CONSUMO", "ATIVO_IMOBILIZADO"}

    if exige_difal_saida or exige_difal_entrada:
        base_difal = valor_merc + ipi
        if ctx.utiliza_bc_dupla_difal and (aliq_intra_dest + fcp_pct) < CEM:
            icms_origem_val = _r2(base_difal * aliq_propria / CEM)
            base_dupla = _r2((base_difal - icms_origem_val) / (UM - (aliq_intra_dest + fcp_pct) / CEM))
            difal_valor = max(ZERO, _r2((base_dupla * aliq_intra_dest / CEM) - icms_origem_val))
            fcp_difal = _r2(base_dupla * fcp_pct / CEM)
        else:
            dif_aliq = max(ZERO, aliq_intra_dest - aliq_propria)
            difal_valor = _r2(base_difal * dif_aliq / CEM)
            fcp_difal = _r2(base_difal * fcp_pct / CEM)

    # 4. Direito a Crédito de ICMS na Entrada
    credito_admitido = ZERO
    regra_credito_detalhe = "Não aplicável (operação de saída)."
    if direcao == "ENTRADA":
        if cst_2 in {"10", "30", "60", "70"} or cst_norm in {"201", "202", "203", "500"} or aplica_st:
            credito_admitido = ZERO
            regra_credito_detalhe = "Crédito VEDADO: mercadoria sujeita à Substituição Tributária definitiva (CST 010/030/060/070)."
        elif finalidade == "USO_CONSUMO":
            credito_admitido = ZERO
            regra_credito_detalhe = "Crédito VEDADO: aquisição para Uso e Consumo (LC 87/1996 Art. 33, I)."
        elif cst_2 in {"40", "41", "50"} or cst_norm in {"102", "103", "300", "400"}:
            credito_admitido = ZERO
            regra_credito_detalhe = "Crédito VEDADO: operação isenta, não tributada ou Simples Nacional sem permissão de crédito."
        elif cst_norm == "101":
            credito_admitido = valor_icms_proprio
            regra_credito_detalhe = f"Crédito SN admitido ({ctx.aliquota_credito_sn_pct}% conforme Art. 23 LC 123/2006)."
        elif cst_2 == "20":
            credito_admitido = valor_icms_proprio
            regra_credito_detalhe = f"Crédito proporcional à Base Reduzida ({red_bc}% de redução — estorno proporcional)."
        else:
            credito_admitido = valor_icms_proprio
            regra_credito_detalhe = f"Crédito integral admitido limitado à alíquota destacada ({aliq_propria}%)."

    # 5. Semáforo de Risco, CFOP e Alertas Preventivos
    alertas: list[str] = []
    risco = "VERDE"

    cbenef_val = ctx.cbenef.strip().upper()
    codigos_validos = [str(c.get("codigo_cbenef") or "").upper() for c in (cbenef_validos or []) if c.get("codigo_cbenef")]

    if cst_2 in {"20", "30", "40", "41", "50", "51", "70"}:
        if not cbenef_val:
            sugestao = f" Sugestões vigentes em {uf_legislacao_aplicavel}: {', '.join(codigos_validos[:5])}." if codigos_validos else ""
            alertas.append(
                f"BLOQUEIO SEFAZ (Rejeição 930/931 — NT 2019.001 / SRE 70/2025): CST {cst_norm} exige preenchimento de cBenef válido na UF {uf_legislacao_aplicavel}.{sugestao}"
            )
            risco = "VERMELHO"
        elif codigos_validos and cbenef_val not in codigos_validos:
            alertas.append(
                f"BLOQUEIO SEFAZ (Rejeição 932): cBenef '{cbenef_val}' inválido, expirado ou incompatível com CST {cst_norm} em {uf_legislacao_aplicavel}. Válidos: {', '.join(codigos_validos[:5])}."
            )
            risco = "VERMELHO"
    elif cst_2 in {"00", "10", "60"} and cbenef_val:
        alertas.append(
            f"REJEIÇÃO SEFAZ (933 — NT 2019.001): cBenef '{cbenef_val}' incompatível com CST {cst_norm} (tributação sem benefício de isenção/redução)."
        )
        risco = "VERMELHO"

    if direcao == "ENTRADA" and aplica_st and not ctx.tem_protocolo_st:
        alertas.append(
            f"ANTECIPAÇÃO NA ENTRADA (GNRE/DARE): NCM sujeito à ST em {uf_d} sem protocolo/convênio com {uf_o}. Recolher R$ {antecipacao_st_entrada} na entrada."
        )
        if risco != "VERMELHO":
            risco = "AMARELO"
    elif direcao == "ENTRADA" and aplica_st and ctx.tem_protocolo_st and not ctx.st_retida_na_origem:
        alertas.append(
            f"GLOSA / RESPONSABILIDADE SOLIDÁRIA: Há protocolo ST entre {uf_o} e {uf_d}, mas fornecedor não reteve. Exigir carta de correção/complemento ou recolher R$ {antecipacao_st_entrada}."
        )
        risco = "VERMELHO"

    if direcao == "ENTRADA" and ctx.fornecedor_simples_nacional and aplica_st:
        alertas.append(
            "CONVÊNIO ICMS 142/2018 (Cláusula 11 §1º): Remetente Simples Nacional — mantida MVA Original (vedado ajuste de MVA)."
        )

    if exige_difal_entrada:
        alertas.append(
            f"DIFAL DE ENTRADA ({finalidade}): Devido ao estado {uf_d} o valor de R$ {difal_valor} + FCP R$ {fcp_difal}."
        )
        if risco == "VERDE":
            risco = "AMARELO"

    cfop_esperado = _resolver_cfop_esperado(
        direcao=direcao,
        finalidade=finalidade,
        interestadual=interestadual,
        importacao_direta=False,
        tem_st=aplica_st,
    )

    bases_legais = [
        f"LC 87/1996 (Lei Kandir) — Operação {direcao} ({uf_o} -> {uf_d})",
        f"RICMS/{uf_legislacao_aplicavel} — Legislação aplicada ao papel {papel_nossa_empresa}",
    ]
    if aplica_st:
        bases_legais.append("Convênio ICMS 142/2018 (Regime ST, CEST e MVA Original/Ajustada)")
    if exige_difal_saida or exige_difal_entrada:
        bases_legais.append("EC 87/2015 / LC 190/2022 (DIFAL e FCP)")
    if is_csosn:
        bases_legais.append("LC 123/2006 Art. 23 (Simples Nacional / CSOSN)")
    if regra_est and regra_est.get("dispositivo_legal"):
        bases_legais.append(str(regra_est["dispositivo_legal"]))

    memoria = [
        {"etapa": "1. Vetor & Papel Jurídico", "valor": papel_nossa_empresa},
        {"etapa": "2. CST / CSOSN", "valor": DESCRICOES_CST_CSOSN.get(cst_norm, cst_norm)},
        {"etapa": "3. CFOP Esperado", "valor": cfop_esperado},
        {"etapa": "4. Base de Cálculo ICMS Próprio", "valor": f"R$ {bc_icms_proprio} (Redução {red_bc}%)"},
        {"etapa": "5. Alíquota ICMS Próprio", "valor": f"{aliq_propria}% -> ICMS R$ {valor_icms_proprio}"},
        {"etapa": "6. MVA Original / Aplicada", "valor": f"{mva_original}% / {mva_aplicada}% (SN={'Sim' if ctx.fornecedor_simples_nacional else 'Não'})"},
        {"etapa": "7. Base ST & ICMS-ST / FCP-ST", "valor": f"BC ST R$ {bc_st} | ICMS-ST R$ {valor_icms_st} | FCP-ST R$ {valor_fcp_st}"},
        {"etapa": "8. Antecipação Entrada (GNRE/DARE)", "valor": f"R$ {antecipacao_st_entrada}"},
        {"etapa": "9. DIFAL / FCP", "valor": f"DIFAL R$ {difal_valor} | FCP R$ {fcp_difal}"},
        {"etapa": "10. Crédito Admitido na Entrada", "valor": f"R$ {credito_admitido} — {regra_credito_detalhe}"},
    ]

    return {
        "direcao": direcao,
        "finalidade": finalidade,
        "papel_nossa_empresa": papel_nossa_empresa,
        "uf_legislacao_aplicavel": uf_legislacao_aplicavel,
        "cfop_esperado": cfop_esperado,
        "cst_ou_csosn": cst_norm,
        "cbenef_obrigatorio": cst_2 in {"20", "30", "40", "41", "50", "51", "70"},
        "cbenef_validos_uf": codigos_validos,
        "ato_legal_st": ato_legal_st,
        "bc_icms_proprio": str(bc_icms_proprio),
        "aliquota_icms_proprio": str(aliq_propria),
        "valor_icms_proprio": str(valor_icms_proprio),
        "valor_isento_nao_tributado": str(valor_isento_nao_trib),
        "valor_icms_diferido": str(valor_icms_diferido),
        "mva_original_pct": str(_r2(mva_original)),
        "mva_aplicada_pct": str(mva_aplicada),
        "bc_st": str(bc_st),
        "valor_icms_st": str(valor_icms_st),
        "valor_fcp_st": str(valor_fcp_st),
        "antecipacao_st_entrada": str(antecipacao_st_entrada),
        "difal_valor": str(difal_valor),
        "fcp_difal": str(fcp_difal),
        "credito_admitido": str(credito_admitido),
        "regra_credito_detalhe": regra_credito_detalhe,
        "semaforo_risco": risco,
        "alertas_preventivos": alertas,
        "bases_legais": bases_legais,
        "memoria_calculo": memoria,
    }


def resolver_parametros_estaduais(
    conn: Any,
    *,
    uf_origem: str,
    uf_destino: str,
    ncm: str,
    cest: str = "",
    cst: str = "00",
    direcao: str = "SAIDA",
    data_operacao: str | None = None,
) -> dict[str, Any]:
    """Resolve automaticamente Protocolo/Convênio ST bilateral e cBenef válidos por UF/CST/Vigência."""
    from src.database.schema_fase2 import consultar_cbenef_uf, consultar_protocolo_st

    uf_o = uf_origem.strip().upper()
    uf_d = uf_destino.strip().upper()
    dir_u = direcao.strip().upper()
    uf_cbenef = uf_d if dir_u == "ENTRADA" else uf_o

    proto = consultar_protocolo_st(
        conn,
        uf_origem=uf_o,
        uf_destino=uf_d,
        ncm=ncm,
        cest=cest,
        data_operacao=data_operacao,
    )
    cbenef_lista = consultar_cbenef_uf(
        conn,
        uf=uf_cbenef,
        cst=cst,
        ncm=ncm,
        data_operacao=data_operacao,
    )

    aliq_modal_d, fcp_padrao_d = ALIQUOTAS_INTERNAS_UF.get(uf_d, (Decimal("18.00"), ZERO))
    if proto is not None:
        return {
            "protocolo_encontrado": True,
            "tem_protocolo_st": bool(proto["possui_acordo_bilateral"]),
            "tem_st": True,
            "cest_resolvido": str(proto.get("cest") or cest),
            "mva_original": Decimal(str(proto.get("mva_original") or 0)),
            "aliquota_interna_destino": Decimal(str(proto.get("aliquota_interna_destino") or aliq_modal_d)),
            "fcp_destino": Decimal(str(proto.get("fcp_destino") or fcp_padrao_d)),
            "modalidade_base_st": str(proto.get("modalidade_base_st") or "MVA"),
            "pmpf_valor": Decimal(str(proto["pmpf_valor"])) if proto.get("pmpf_valor") is not None else ZERO,
            "ato_legal_st": str(proto.get("ato_legal") or ""),
            "observacao_st": str(proto.get("observacao_legal") or ""),
            "uf_cbenef": uf_cbenef,
            "cbenef_validos_uf": cbenef_lista,
            "cbenef_sugerido": str(cbenef_lista[0]["codigo_cbenef"]) if cbenef_lista else "",
        }

    return {
        "protocolo_encontrado": False,
        "tem_protocolo_st": False,
        "tem_st": False,
        "cest_resolvido": cest,
        "mva_original": ZERO,
        "aliquota_interna_destino": aliq_modal_d,
        "fcp_destino": fcp_padrao_d,
        "modalidade_base_st": "MVA",
        "pmpf_valor": ZERO,
        "ato_legal_st": f"Sem protocolo/convênio bilateral vigente para {uf_o} -> {uf_d} na data informada.",
        "observacao_st": "",
        "uf_cbenef": uf_cbenef,
        "cbenef_validos_uf": cbenef_lista,
        "cbenef_sugerido": str(cbenef_lista[0]["codigo_cbenef"]) if cbenef_lista else "",
    }
