"""Motor matemático puro para Importação Direta do Exterior (DI / DUIMP / NF-e CFOP 3.xxx)."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import openpyxl

from src.engine.fiscal_engine import (
    ALIQUOTAS_INTERNAS_UF,
    aliquota_interestadual,
    calcular_mva_ajustado,
)

CEM = Decimal("100")
Q2 = Decimal("0.01")
Q4 = Decimal("0.0001")

CFOP_POR_FINALIDADE_IMPORTACAO: dict[str, str] = {
    "COMERCIALIZACAO": "3.102",
    "INDUSTRIALIZACAO": "3.101",
    "ATIVO_IMOBILIZADO": "3.551",
    "USO_CONSUMO": "3.556",
    "OUTRAS": "3.949",
}


def _d(val: Any, default: str = "0") -> Decimal:
    if val is None or val == "":
        return Decimal(default)
    if isinstance(val, Decimal):
        return val
    s = str(val).strip().replace("%", "").replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return Decimal(default)


def _r2(val: Decimal) -> Decimal:
    return val.quantize(Q2, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ContextoImportacaoDireta:
    ncm: str
    cest: str = ""
    uf_desembaraco: str = "SP"
    uf_destino: str = "SP"
    finalidade: str = "COMERCIALIZACAO"
    sem_similar_nacional_camex: bool = False
    valor_fob: Decimal = Decimal("0.00")
    frete_internacional: Decimal = Decimal("0.00")
    seguro_internacional: Decimal = Decimal("0.00")
    valor_aduaneiro_cif: Decimal | None = None
    taxa_siscomex: Decimal = Decimal("0.00")
    afrmm: Decimal = Decimal("0.00")
    outras_despesas_aduaneiras: Decimal = Decimal("0.00")
    aliquota_ii: Decimal = Decimal("0.00")
    aliquota_ipi: Decimal = Decimal("0.00")
    aliquota_pis_imp: Decimal = Decimal("2.10")
    aliquota_cofins_imp: Decimal = Decimal("9.65")
    adicional_cofins_imp: Decimal = Decimal("1.00")
    aliquota_icms_interna: Decimal | None = None
    aliquota_fcp: Decimal | None = None
    reducao_bc_icms: Decimal = Decimal("0.00")
    tem_st: bool = False
    mva_original_st: Decimal = Decimal("0.00")
    regime_especial_estadual: str = ""
    aliquota_cbs: Decimal = Decimal("0.90")
    aliquota_ibs: Decimal = Decimal("0.10")
    uf_saida_subsequente: str = "RJ"
    operacao_saida_contribuinte: bool = True


def calcular_importacao_direta(ctx: ContextoImportacaoDireta) -> dict[str, Any]:
    """Calcula todos os tributos da importação direta (II, IPI, PIS/COFINS-Imp, ICMS por dentro, ST, IBS/CBS) e espelho de saída."""
    ncm_limpo = re.sub(r"\D", "", str(ctx.ncm or "")).zfill(8)[:8]
    uf_des = str(ctx.uf_desembaraco or "SP").strip().upper()[:2]
    uf_dest = str(ctx.uf_destino or uf_des).strip().upper()[:2]
    uf_sai = str(ctx.uf_saida_subsequente or "RJ").strip().upper()[:2]
    fin = str(ctx.finalidade or "COMERCIALIZACAO").strip().upper()

    cif = (
        _d(ctx.valor_aduaneiro_cif)
        if ctx.valor_aduaneiro_cif is not None
        else (_d(ctx.valor_fob) + _d(ctx.frete_internacional) + _d(ctx.seguro_internacional))
    )
    cif = _r2(cif)

    aliq_ii = _d(ctx.aliquota_ii)
    aliq_ipi = _d(ctx.aliquota_ipi)
    aliq_pis = _d(ctx.aliquota_pis_imp, "2.10")
    aliq_cof = _d(ctx.aliquota_cofins_imp, "9.65")
    adic_cof = _d(ctx.adicional_cofins_imp, "1.00")

    aliq_uf_padrao, fcp_uf_padrao = ALIQUOTAS_INTERNAS_UF.get(uf_dest, (Decimal("18.00"), Decimal("0.00")))
    aliq_icms_nom = _d(ctx.aliquota_icms_interna) if ctx.aliquota_icms_interna is not None else aliq_uf_padrao
    aliq_fcp = _d(ctx.aliquota_fcp) if ctx.aliquota_fcp is not None else fcp_uf_padrao
    red_bc = _d(ctx.reducao_bc_icms)

    valor_ii = _r2(cif * (aliq_ii / CEM))
    base_ipi = _r2(cif + valor_ii)
    valor_ipi = _r2(base_ipi * (aliq_ipi / CEM))
    valor_pis_imp = _r2(cif * (aliq_pis / CEM))
    aliq_cof_total = aliq_cof + adic_cof
    valor_cofins_imp = _r2(cif * (aliq_cof_total / CEM))

    siscomex = _r2(_d(ctx.taxa_siscomex))
    afrmm = _r2(_d(ctx.afrmm))
    outras = _r2(_d(ctx.outras_despesas_aduaneiras))

    # LC 87/96 Art. 13, V: Base "por dentro"
    aliq_icms_efetiva = aliq_icms_nom * (Decimal("1") - (red_bc / CEM))
    soma_antes_por_dentro = cif + valor_ii + valor_ipi + valor_pis_imp + valor_cofins_imp + siscomex + afrmm + outras
    divisor = Decimal("1") - ((aliq_icms_efetiva + aliq_fcp) / CEM)
    if divisor <= Decimal("0"):
        divisor = Decimal("0.01")
    base_icms_por_dentro = _r2(soma_antes_por_dentro / divisor)
    valor_icms_imp = _r2(base_icms_por_dentro * (aliq_icms_efetiva / CEM))
    valor_fcp_imp = _r2(base_icms_por_dentro * (aliq_fcp / CEM))

    # ICMS-ST na Entrada (quando aplicável ao NCM/CEST)
    mva_orig = _d(ctx.mva_original_st)
    mva_aplicada = Decimal("0.00")
    base_st = Decimal("0.00")
    valor_st = Decimal("0.00")
    if ctx.tem_st and mva_orig > Decimal("0"):
        mva_aplicada = calcular_mva_ajustado(
            mva_orig,
            aliq_icms_efetiva,
            aliq_icms_nom,
            uf_destino=uf_dest,
            fcp_pct=aliq_fcp,
        )
        base_st = _r2((base_icms_por_dentro + valor_ipi) * (Decimal("1") + (mva_aplicada / CEM)))
        st_bruto = _r2(base_st * ((aliq_icms_nom + aliq_fcp) / CEM))
        valor_st = _r2(max(Decimal("0.00"), st_bruto - (valor_icms_imp + valor_fcp_imp)))

    # Reforma Tributária LC 214/2025 (IBS/CBS na importação)
    valor_cbs = _r2(cif * (_d(ctx.aliquota_cbs, "0.90") / CEM))
    valor_ibs = _r2(cif * (_d(ctx.aliquota_ibs, "0.10") / CEM))

    # Origem, CFOP e CSTs da Entrada (CFOP 3.xxx)
    orig_entrada = "6" if ctx.sem_similar_nacional_camex else "1"
    cfop_entrada = CFOP_POR_FINALIDADE_IMPORTACAO.get(fin, "3.102")
    if ctx.tem_st:
        cst_2 = "10"
    elif red_bc > Decimal("0"):
        cst_2 = "20"
    else:
        cst_2 = "00"
    cst_icms_entrada = f"{orig_entrada}.{cst_2}"
    cst_ipi_entrada = "00" if aliq_ipi > Decimal("0") else "49"
    cst_pc_entrada = "50" if fin in {"COMERCIALIZACAO", "INDUSTRIALIZACAO"} else "70"

    # Espelho da Saída Subsequente (Equiparação a Industrial + Res. Senado 13/2012)
    orig_saida = "7" if orig_entrada == "6" else "2"
    if ctx.tem_st:
        cfop_saida_int = "5.403"
        cfop_saida_inter = "6.403"
    else:
        cfop_saida_int = "5.102"
        cfop_saida_inter = "6.102"

    if orig_saida == "2":
        aliq_saida_inter = Decimal("4.00")
    else:
        # Origem 7 (sem similar nacional CAMEX): não se sujeita aos 4%, mantém 7%/12%
        aliq_saida_inter = aliquota_interestadual(uf_dest, uf_sai if uf_sai != uf_dest else "MG", "7")

    custo_desembaracado = _r2(
        cif + valor_ii + valor_ipi + valor_pis_imp + valor_cofins_imp + siscomex + afrmm + outras + valor_icms_imp + valor_fcp_imp + valor_st
    )

    return {
        "ncm": ncm_limpo,
        "cest": str(ctx.cest or "").strip(),
        "uf_desembaraco": uf_des,
        "uf_destino": uf_dest,
        "finalidade": fin,
        "origem_entrada": orig_entrada,
        "sem_similar_nacional_camex": bool(ctx.sem_similar_nacional_camex),
        "cfop_entrada": cfop_entrada,
        "cst_icms_entrada": cst_icms_entrada,
        "cst_ipi_entrada": cst_ipi_entrada,
        "cst_pis_cofins_entrada": cst_pc_entrada,
        "valor_aduaneiro_cif": f"{cif:.2f}",
        "aliquota_ii": f"{aliq_ii:.2f}",
        "valor_ii": f"{valor_ii:.2f}",
        "base_ipi": f"{base_ipi:.2f}",
        "aliquota_ipi": f"{aliq_ipi:.2f}",
        "valor_ipi": f"{valor_ipi:.2f}",
        "aliquota_pis_imp": f"{aliq_pis:.2f}",
        "valor_pis_imp": f"{valor_pis_imp:.2f}",
        "aliquota_cofins_imp_total": f"{aliq_cof_total:.2f}",
        "valor_cofins_imp": f"{valor_cofins_imp:.2f}",
        "taxa_siscomex": f"{siscomex:.2f}",
        "afrmm": f"{afrmm:.2f}",
        "outras_despesas_aduaneiras": f"{outras:.2f}",
        "aliquota_icms_interna": f"{aliq_icms_nom:.2f}",
        "aliquota_icms_efetiva": f"{aliq_icms_efetiva:.2f}",
        "aliquota_fcp": f"{aliq_fcp:.2f}",
        "base_icms_por_dentro": f"{base_icms_por_dentro:.2f}",
        "valor_icms_importacao": f"{valor_icms_imp:.2f}",
        "valor_fcp_importacao": f"{valor_fcp_imp:.2f}",
        "mva_aplicada_st": f"{mva_aplicada:.2f}",
        "base_icms_st": f"{base_st:.2f}",
        "valor_icms_st": f"{valor_st:.2f}",
        "valor_cbs": f"{valor_cbs:.2f}",
        "valor_ibs": f"{valor_ibs:.2f}",
        "custo_total_desembaracado": f"{custo_desembaracado:.2f}",
        "regime_especial_estadual": str(ctx.regime_especial_estadual or ""),
        # Espelho Saída Subsequente
        "origem_saida_subsequente": orig_saida,
        "cfop_saida_interna": cfop_saida_int,
        "cfop_saida_interestadual": cfop_saida_inter,
        "aliquota_saida_interestadual": f"{aliq_saida_inter:.2f}",
        "equiparado_industrial_ipi": True,
        "cst_ipi_saida": "50" if aliq_ipi > Decimal("0") else "53",
    }


def gerar_matriz_importacao_lote(itens: list[ContextoImportacaoDireta]) -> list[dict[str, Any]]:
    """Gera a matriz linha a linha (Entrada 3.xxx + Espelho Saída Subsequente) para uma lista de NCMs."""
    return [calcular_importacao_direta(it) for it in itens]


def parsear_planilha_lote_importacao(nome_arquivo: str, conteudo: bytes) -> list[dict[str, Any]]:
    """Lê planilha .xlsx ou .csv de cotação/pré-embarque com NCM, CIF/FOB, Frete, Seguro, Siscomex, AFRMM e Finalidade."""
    nome_l = nome_arquivo.lower()
    registros_brutos: list[dict[str, Any]] = []

    if nome_l.endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(conteudo), data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        headers = [str(h or "").strip() for h in next(it, ())]
        for row in it:
            if not any(v is not None and str(v).strip() != "" for v in row):
                continue
            registros_brutos.append({headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))})
    else:
        txt = conteudo.decode("utf-8-sig", errors="replace")
        delim = ";" if txt.count(";") >= txt.count(",") else ","
        reader = csv.DictReader(io.StringIO(txt), delimiter=delim)
        for row in reader:
            registros_brutos.append(dict(row))

    def _pick(r: dict[str, Any], *keys: str, default: Any = "") -> Any:
        lower_map = {str(k).strip().lower(): v for k, v in r.items()}
        for k in keys:
            if k.lower() in lower_map and str(lower_map[k.lower()] or "").strip() != "":
                return lower_map[k.lower()]
        return default

    saida: list[dict[str, Any]] = []
    for r in registros_brutos:
        ncm = re.sub(r"\D", "", str(_pick(r, "NCM", "ncm")))
        if len(ncm) != 8:
            continue
        sem_sim_raw = str(_pick(r, "Sem_Similar_CAMEX", "sem_similar_nacional_camex", "sem_similar", default="N")).strip().upper()
        saida.append(
            {
                "ncm": ncm,
                "cest": re.sub(r"\D", "", str(_pick(r, "CEST", "cest", default=""))),
                "valor_aduaneiro_cif": _d(_pick(r, "Valor Aduaneiro", "CIF", "valor_aduaneiro_cif", "Valor Aduaneiro/CIF", default="1000")),
                "frete_internacional": _d(_pick(r, "Frete", "frete_internacional", default="0")),
                "seguro_internacional": _d(_pick(r, "Seguro", "seguro_internacional", default="0")),
                "taxa_siscomex": _d(_pick(r, "Siscomex", "Taxa Siscomex", "taxa_siscomex", default="0")),
                "afrmm": _d(_pick(r, "AFRMM", "afrmm", default="0")),
                "outras_despesas_aduaneiras": _d(_pick(r, "Despesas", "Outras Despesas", "outras_despesas_aduaneiras", default="0")),
                "finalidade": str(_pick(r, "Finalidade", "finalidade", default="COMERCIALIZACAO")).strip().upper(),
                "aliquota_ii": _d(_pick(r, "Aliq_II", "Alíquota II", "aliquota_ii", default="0")),
                "aliquota_ipi": _d(_pick(r, "Aliq_IPI", "Alíquota IPI", "aliquota_ipi", default="0")),
                "sem_similar_nacional_camex": sem_sim_raw in {"S", "SIM", "1", "TRUE"},
            }
        )
    return saida
