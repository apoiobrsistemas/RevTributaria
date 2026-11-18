"""Motor matemático tributário puro em Python (Decimal, zero I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

CENT = Decimal("0.01")
CEM = Decimal("100")
UM = Decimal("1")
ZERO = Decimal("0.00")

# Estados onde o FCP integra a alíquota interna na fórmula do MVA Ajustado
FUNDO_NA_MVA = frozenset({"RJ", "PR", "BA", "SE", "AL"})

# Estados do Sul e Sudeste (exceto ES)
UFS_SUL_SUDESTE_12_PCT = frozenset({"SP", "MG", "RJ", "PR", "RS", "SC"})
ORIGENS_IMPORTADAS_4_PCT = frozenset({"1", "2", "3", "8"})


def _dec(valor: Any, default: str = "0") -> Decimal:
    if valor is None or valor == "":
        return Decimal(default)
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


def _r2(valor: Decimal) -> Decimal:
    return valor.quantize(CENT, rounding=ROUND_HALF_UP)


def origem_por_fci(
    conteudo_importacao_pct: Decimal | float | str | None,
    origem_atual: str = "0",
) -> str:
    """Define a origem da mercadoria conforme percentual de conteúdo de importação (FCI)."""
    if conteudo_importacao_pct is None or conteudo_importacao_pct == "":
        return origem_atual
    ci = _dec(conteudo_importacao_pct)
    if ci > Decimal("70"):
        return "8"
    if ci > Decimal("40"):
        return "3"
    return "5"


def aliquota_interestadual(
    uf_origem: str,
    uf_destino: str,
    origem_mercadoria: str = "0",
    conteudo_importacao_pct: Decimal | float | str | None = None,
    beneficio_convenio_52_91: bool = False,
) -> Decimal | None:
    """Calcula a alíquota interestadual aplicável (4%, 7%, 12% ou Conv. 52/91)."""
    orig = uf_origem.upper()
    dest = uf_destino.upper()
    if orig == dest:
        return None

    origem_efetiva = origem_por_fci(conteudo_importacao_pct, origem_mercadoria)
    if origem_efetiva in ORIGENS_IMPORTADAS_4_PCT:
        inter = Decimal("4.00")
    elif orig in UFS_SUL_SUDESTE_12_PCT and dest not in UFS_SUL_SUDESTE_12_PCT:
        inter = Decimal("7.00")
    else:
        inter = Decimal("12.00")

    if beneficio_convenio_52_91:
        carga_52_91 = (
            Decimal("8.80")
            if dest in UFS_SUL_SUDESTE_12_PCT
            else Decimal("5.14")
        )
        inter = min(inter, carga_52_91)

    return inter


def calcular_reducao_por_carga(
    carga_pct: Decimal | float | str,
    aliquota_icms_pct: Decimal | float | str,
    *,
    uf_destino: str = "",
    fcp_pct: Decimal | float | str = ZERO,
) -> Decimal:
    """Calcula redução de base (%) derivada da carga tributária final.

    No RJ, o FECP compõe o denominador: 1 - carga / (aliquota + fcp).
    Nos demais estados: 1 - carga / aliquota.
    """
    carga = _dec(carga_pct)
    aliq = _dec(aliquota_icms_pct)
    fcp = _dec(fcp_pct)

    denom = (aliq + fcp) if uf_destino.upper() == "RJ" else aliq
    if denom <= ZERO:
        return ZERO
    reducao = (UM - (carga / denom)) * CEM
    return max(ZERO, _r2(reducao))


def calcular_mva_ajustado(
    mva_original_pct: Decimal | float | str,
    aliq_inter_pct: Decimal | float | str,
    aliq_interna_destino_pct: Decimal | float | str,
    *,
    uf_destino: str = "",
    fcp_pct: Decimal | float | str = ZERO,
    reducao_bc_pct: Decimal | float | str = ZERO,
    aliquota_mva_especial_pct: Decimal | float | str = ZERO,
    nao_ajusta_mva: bool = False,
) -> Decimal:
    """Calcula a MVA Ajustada (%) aplicando FCP no MVA apenas para FUNDO_NA_MVA."""
    mva_orig = _dec(mva_original_pct)
    if nao_ajusta_mva:
        return _r2(mva_orig)

    inter = _dec(aliq_inter_pct)
    aliq_intra = _dec(aliq_interna_destino_pct)
    fcp = _dec(fcp_pct)
    red_bc = _dec(reducao_bc_pct)
    mva_esp = _dec(aliquota_mva_especial_pct)

    fundo_mva = fcp if uf_destino.upper() in FUNDO_NA_MVA else ZERO
    if mva_esp > ZERO:
        interna_efetiva = mva_esp
    else:
        interna_efetiva = (aliq_intra + fundo_mva) * (UM - red_bc / CEM)

    if inter >= interna_efetiva or interna_efetiva >= CEM:
        return _r2(mva_orig)

    mva_aj = (((UM + mva_orig / CEM) * (UM - inter / CEM)) / (UM - interna_efetiva / CEM)) - UM
    return _r2(mva_aj * CEM)


def derivar_cst_cfop_esperados(
    regra_icms: Mapping[str, Any],
    *,
    operacao_interestadual: bool,
    tem_st: bool,
) -> tuple[str, str]:
    """Deriva dinamicamente (nunca persistido) CST e CFOP esperados para a operação."""
    cfop_base = str(regra_icms.get("cfop") or "")
    cst_base = str(regra_icms.get("cst_icms") or regra_icms.get("csosn") or "")

    if not cfop_base and operacao_interestadual:
        cfop_base = "6403" if tem_st else "6102"
    elif not cfop_base:
        cfop_base = "5405" if tem_st else "5102"

    if not cst_base:
        if tem_st:
            cst_base = "10" if operacao_interestadual else "60"
        elif _dec(regra_icms.get("reducao_base_icms")) > ZERO:
            cst_base = "20"
        else:
            cst_base = "00"

    return cst_base, cfop_base


@dataclass(frozen=True)
class ItemCalculo:
    """Entrada pura para o cálculo tributário de 11 blocos."""

    valor_produto: Decimal
    uf_origem: str
    uf_destino: str
    ncm: str
    cest: str = ""
    origem_mercadoria: str = "0"
    operacao_com_contribuinte: bool = True
    valor_frete: Decimal = ZERO
    valor_seguro: Decimal = ZERO
    valor_outras_despesas: Decimal = ZERO
    valor_desconto: Decimal = ZERO
    valor_ipi: Decimal | None = None
    conteudo_importacao_pct: Decimal | None = None
    deduzir_tributos_atuais_ibs_cbs: bool = False


@dataclass(frozen=True)
class ResultadoFiscal:
    """Saída pura com todos os valores calculados em Decimal."""

    origem_efetiva: str
    valor_operacao: Decimal
    aliquota_inter_aplicada: Decimal | None
    reducao_bc_aplicada: Decimal
    cst_esperado: str
    cfop_esperado: str

    # IPI
    valor_ipi: Decimal

    # ICMS Próprio e FCP
    bc_icms: Decimal
    aliquota_icms: Decimal
    valor_icms_proprio: Decimal
    valor_icms_diferido: Decimal
    valor_icms_desonerado: Decimal
    valor_fcp: Decimal

    # ICMS-ST
    mva_aplicada: Decimal
    bc_st: Decimal
    valor_icms_st: Decimal
    valor_fcp_st: Decimal

    # ICMS Efetivo
    bc_icms_efetivo: Decimal
    valor_icms_efetivo: Decimal

    # DIFAL
    bc_difal: Decimal
    valor_difal: Decimal
    valor_fcp_difal: Decimal

    # PIS / COFINS
    valor_pis: Decimal
    valor_cofins: Decimal

    # Reforma Tributária (IBS / CBS)
    cclass_trib: str
    bc_ibs_cbs: Decimal
    valor_cbs: Decimal
    valor_ibs_uf: Decimal
    valor_ibs_mun: Decimal
    valor_ibs_total: Decimal


def _get(regra: Mapping[str, Any] | None, campo: str, default: Any = 0) -> Any:
    if regra is None:
        return default
    val = regra.get(campo, default)
    return default if val is None else val


def calcular_item(
    item: ItemCalculo,
    regra_icms: Mapping[str, Any],
    regra_federal: Mapping[str, Any] | None = None,
    regra_terceiro: Mapping[str, Any] | None = None,
) -> ResultadoFiscal:
    """Executa o cálculo puro dos 11 blocos tributários sem nenhum I/O."""
    valor_operacao = _r2(
        _dec(item.valor_produto)
        + _dec(item.valor_frete)
        + _dec(item.valor_seguro)
        + _dec(item.valor_outras_despesas)
        - _dec(item.valor_desconto)
    )

    origem_efetiva = origem_por_fci(item.conteudo_importacao_pct, item.origem_mercadoria)
    operacao_inter = item.uf_origem.upper() != item.uf_destino.upper()
    conv_52_91 = bool(_get(regra_terceiro, "beneficio_convenio_52_91", 0))

    # 1. IPI
    if item.valor_ipi is not None:
        valor_ipi = _r2(_dec(item.valor_ipi))
    else:
        aliq_ipi = _dec(_get(regra_federal, "aliquota_ipi", 0))
        valor_ipi = _r2(valor_operacao * aliq_ipi / CEM)

    # 2. Alíquota ICMS e Redução de Base
    aliq_inter = aliquota_interestadual(
        item.uf_origem,
        item.uf_destino,
        origem_efetiva,
        item.conteudo_importacao_pct,
        beneficio_convenio_52_91=conv_52_91,
    )
    aliq_icms_regra = _dec(_get(regra_icms, "aliquota_icms", 0))
    if operacao_inter and aliq_inter is not None:
        if aliq_inter == Decimal("4.00") or conv_52_91 or aliq_icms_regra == ZERO:
            aliq_icms = aliq_inter
        else:
            aliq_icms = aliq_icms_regra
    else:
        aliq_icms = aliq_icms_regra

    aliq_fcp = _dec(_get(regra_icms, "aliquota_fcp", 0))
    red_bc_icms = _dec(_get(regra_icms, "reducao_base_icms", 0))
    bc_icms_base = valor_operacao + (valor_ipi if not item.operacao_com_contribuinte else ZERO)
    bc_icms = _r2(bc_icms_base * (UM - red_bc_icms / CEM))

    valor_icms_bruto = _r2(bc_icms * aliq_icms / CEM)
    aliq_diferimento = _dec(_get(regra_icms, "aliquota_diferimento", 0))
    valor_icms_diferido = _r2(valor_icms_bruto * aliq_diferimento / CEM)
    valor_icms_proprio = _r2(valor_icms_bruto - valor_icms_diferido)

    aliq_deson = _dec(_get(regra_icms, "aliquota_icms_desonerado", 0))
    valor_icms_desonerado = _r2(bc_icms_base * aliq_deson / CEM) if aliq_deson > ZERO else ZERO

    considerar_red_fcp = bool(_get(regra_icms, "considerar_red_bc_icms_no_fcp", 1))
    bc_fcp = bc_icms if considerar_red_fcp else bc_icms_base
    valor_fcp = _r2(bc_fcp * aliq_fcp / CEM)

    # 3. ICMS-ST (MVA Ajustado vs. Estimativa Simplificada)
    tem_st = bool(_get(regra_icms, "tem_st", 0))
    mva_aplicada = ZERO
    bc_st = ZERO
    valor_icms_st = ZERO
    valor_fcp_st = ZERO

    if tem_st:
        regime_estimativa = bool(_get(regra_icms, "regime_estimativa_simplificado_st", 0))
        if regime_estimativa:
            carga_media = _dec(_get(regra_icms, "percentual_carga_tributaria_media", 0))
            bc_st = _r2(valor_operacao + valor_ipi)
            valor_icms_st = _r2(bc_st * carga_media / CEM)
        else:
            mva_orig = _dec(_get(regra_icms, "margem_st", 0))
            aliq_st = _dec(_get(regra_icms, "aliquota_icms_st", 0))
            red_st = _dec(_get(regra_icms, "reducao_icms_st", 0))
            nao_ajusta = bool(_get(regra_icms, "nao_ajusta_mva", 0))
            mva_esp = _dec(_get(regra_icms, "aliquota_mva_especial", 0))
            usa_bc_icms_st = bool(_get(regra_icms, "utiliza_base_icms_para_st", 0))
            nao_deduz_icms = bool(_get(regra_icms, "nao_deduzir_icms_calculo_st", 0))

            if operacao_inter and aliq_st > ZERO:
                mva_aplicada = calcular_mva_ajustado(
                    mva_orig,
                    aliq_icms,
                    aliq_st,
                    uf_destino=item.uf_destino,
                    fcp_pct=aliq_fcp,
                    reducao_bc_pct=red_st,
                    aliquota_mva_especial_pct=mva_esp,
                    nao_ajusta_mva=nao_ajusta,
                )
            else:
                mva_aplicada = _r2(mva_orig)

            base_para_st = bc_icms if usa_bc_icms_st else (valor_operacao + valor_ipi)
            bc_st_bruta = base_para_st * (UM + mva_aplicada / CEM)
            bc_st = _r2(bc_st_bruta * (UM - red_st / CEM))
            icms_st_cheio = _r2(bc_st * aliq_st / CEM)
            deducao = ZERO if nao_deduz_icms else valor_icms_proprio
            valor_icms_st = max(ZERO, _r2(icms_st_cheio - deducao))
            valor_fcp_st = _r2(bc_st * aliq_fcp / CEM)

    # 4. ICMS Efetivo (obrigatório quando CST 60 / CSOSN 500)
    aliq_efetivo = _dec(_get(regra_icms, "aliquota_icms_efetivo", 0))
    red_efetivo = _dec(_get(regra_icms, "reducao_base_icms_efetivo", 0))
    if aliq_efetivo > ZERO:
        bc_icms_efetivo = _r2(valor_operacao * (UM - red_efetivo / CEM))
        valor_icms_efetivo = _r2(bc_icms_efetivo * aliq_efetivo / CEM)
    else:
        bc_icms_efetivo = ZERO
        valor_icms_efetivo = ZERO

    # 5. DIFAL (Base Única vs. Base Dupla)
    aliq_dest_difal = _dec(_get(regra_icms, "aliquota_interna_uf_destino_difal", 0))
    bc_difal = ZERO
    valor_difal = ZERO
    valor_fcp_difal = ZERO

    if operacao_inter and not tem_st and aliq_dest_difal > ZERO:
        somar_ipi_difal = bool(_get(regra_icms, "somar_ipi_base_difal_fcp", 0))
        base_difal_ini = valor_operacao + (valor_ipi if somar_ipi_difal else ZERO)
        bc_dupla = bool(_get(regra_icms, "utiliza_bc_dupla_difal", 0))

        if bc_dupla:
            bc_1 = base_difal_ini - valor_icms_proprio
            denom = UM - (aliq_dest_difal + aliq_fcp) / CEM
            bc_difal = _r2(bc_1 / denom)
            valor_difal = max(ZERO, _r2((bc_difal * aliq_dest_difal / CEM) - valor_icms_proprio))
            valor_fcp_difal = _r2(bc_difal * aliq_fcp / CEM)
        else:
            aliq_inter_difal = _dec(_get(regra_icms, "aliquota_interestadual_difal", 0)) or aliq_icms
            diff_aliq = max(ZERO, aliq_dest_difal - aliq_inter_difal)
            bc_difal = _r2(base_difal_ini)
            valor_difal = _r2(bc_difal * diff_aliq / CEM)
            valor_fcp_difal = _r2(bc_difal * aliq_fcp / CEM)
            valor_fcp = ZERO

    # 6. PIS / COFINS
    aliq_pis = _dec(_get(regra_federal, "aliquota_pis", 0))
    aliq_cofins = _dec(_get(regra_federal, "aliquota_cofins", 0))
    valor_pis = _r2(valor_operacao * aliq_pis / CEM)
    valor_cofins = _r2(valor_operacao * aliq_cofins / CEM)

    # 7. Reforma Tributária (IBS / CBS)
    if item.deduzir_tributos_atuais_ibs_cbs:
        bc_ibs_cbs = max(ZERO, _r2(valor_operacao - valor_icms_proprio - valor_pis - valor_cofins))
    else:
        bc_ibs_cbs = valor_operacao

    red_ibs_cbs = _dec(_get(regra_federal, "reducao_ibs_cbs", 0))
    fator_ibs_cbs = UM - (red_ibs_cbs / CEM)
    aliq_cbs = _dec(_get(regra_federal, "aliquota_cbs", 0)) * fator_ibs_cbs
    aliq_ibs_uf = _dec(_get(regra_federal, "aliquota_ibs_uf", 0)) * fator_ibs_cbs
    aliq_ibs_mun = _dec(_get(regra_federal, "aliquota_ibs_mun", 0)) * fator_ibs_cbs

    valor_cbs = _r2(bc_ibs_cbs * aliq_cbs / CEM)
    valor_ibs_uf = _r2(bc_ibs_cbs * aliq_ibs_uf / CEM)
    valor_ibs_mun = _r2(bc_ibs_cbs * aliq_ibs_mun / CEM)
    valor_ibs_total = _r2(valor_ibs_uf + valor_ibs_mun)

    cst_esp, cfop_esp = derivar_cst_cfop_esperados(
        regra_icms, operacao_interestadual=operacao_inter, tem_st=tem_st
    )

    return ResultadoFiscal(
        origem_efetiva=origem_efetiva,
        valor_operacao=valor_operacao,
        aliquota_inter_aplicada=aliq_inter,
        reducao_bc_aplicada=red_bc_icms,
        cst_esperado=cst_esp,
        cfop_esperado=cfop_esp,
        valor_ipi=valor_ipi,
        bc_icms=bc_icms,
        aliquota_icms=aliq_icms,
        valor_icms_proprio=valor_icms_proprio,
        valor_icms_diferido=valor_icms_diferido,
        valor_icms_desonerado=valor_icms_desonerado,
        valor_fcp=valor_fcp,
        mva_aplicada=mva_aplicada,
        bc_st=bc_st,
        valor_icms_st=valor_icms_st,
        valor_fcp_st=valor_fcp_st,
        bc_icms_efetivo=bc_icms_efetivo,
        valor_icms_efetivo=valor_icms_efetivo,
        bc_difal=bc_difal,
        valor_difal=valor_difal,
        valor_fcp_difal=valor_fcp_difal,
        valor_pis=valor_pis,
        valor_cofins=valor_cofins,
        cclass_trib=str(_get(regra_federal, "cclass_trib", "") or ""),
        bc_ibs_cbs=bc_ibs_cbs,
        valor_cbs=valor_cbs,
        valor_ibs_uf=valor_ibs_uf,
        valor_ibs_mun=valor_ibs_mun,
        valor_ibs_total=valor_ibs_total,
    )
