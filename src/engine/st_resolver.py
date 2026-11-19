"""Motor de Decisão de ST em 3 Camadas: Convênio 142/2018 x Legislação UF Destino x Acordo Interestadual."""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from typing import Any

from src.database.repository import (
    buscar_convenio_142_por_prefixo,
    buscar_regra_estadual_icms,
    normalizar_cest,
    normalizar_ncm,
)
from src.database.schema_fase2 import consultar_protocolo_st
from src.legislation.confaz_ingestor import garantir_base_confaz_142_e_acordos


def _formatar_cest(cest_7: str) -> str:
    d = normalizar_cest(cest_7)
    if len(d) == 7:
        return f"{d[:2]}.{d[2:5]}.{d[5:]}"
    return cest_7


def _formatar_prefixo_ncm(pref: str) -> str:
    d = normalizar_ncm(pref)
    if len(d) == 8:
        return f"{d[:4]}.{d[4:6]}.{d[6:]}"
    if len(d) == 6:
        return f"{d[:4]}.{d[4:6]}"
    return d


def _descrever_passo_1(itens_142: list[dict[str, Any]]) -> str:
    if not itens_142:
        return "Não Elegível — NCM não consta nos Anexos II a XXVIII do Convênio ICMS 142/2018."
    pref = str(itens_142[0].get("ncm_limpo") or "")
    tipo_map = {8: "item 8 dígitos", 6: "subposição 6 dígitos", 4: "posição 4 dígitos", 2: "capítulo 2 dígitos"}
    tipo_lbl = tipo_map.get(len(pref), f"{len(pref)} dígitos")
    cests_txt = " e ".join(
        f"{_formatar_cest(str(it.get('cest') or ''))} [Seg. {it.get('segmento_codigo', '')} - {it.get('anexo', '')}]"
        for it in itens_142
    )
    qtd = len(itens_142)
    suf = "CEST localizado" if qtd == 1 else "CESTs localizados"
    return f"Elegível via {tipo_lbl} '{_formatar_prefixo_ncm(pref)}' — {qtd} {suf}: {cests_txt}."


def _buscar_convenio_142(conn: sqlite3.Connection, ncm_8: str, cest_7: str = "") -> list[dict[str, Any]]:
    """Busca elegibilidade no Convênio ICMS 142/2018 em cascata 8 -> 6 -> 4 -> 2 dígitos (todos os CESTs)."""
    garantir_base_confaz_142_e_acordos(conn)
    return buscar_convenio_142_por_prefixo(conn, ncm_8, cest_7)


def _buscar_acordo_interestadual(
    conn: sqlite3.Connection,
    *,
    uf_origem: str,
    uf_destino: str,
    ncm_8: str,
    segmentos: list[str],
    data_ref: str,
) -> dict[str, Any] | None:
    """Busca Convênio Nacional ('*') ou Protocolo Bilateral vigente em acordos_interestaduais_st."""
    rows = conn.execute(
        """
        SELECT * FROM acordos_interestaduais_st
        WHERE uf_origem IN (?, '*', 'TODAS')
          AND uf_destino IN (?, '*')
          AND vigencia_inicio <= ?
          AND (vigencia_fim IS NULL OR vigencia_fim = '' OR vigencia_fim >= ?)
        ORDER BY CASE WHEN uf_origem = ? THEN 1 ELSE 0 END DESC,
                 CASE WHEN uf_destino = ? THEN 1 ELSE 0 END DESC,
                 length(ncm_prefixo) DESC, id DESC
        """,
        (uf_origem, uf_destino, data_ref, data_ref, uf_origem, uf_destino),
    ).fetchall()
    for r in rows:
        pref = re.sub(r"\D", "", str(r["ncm_prefixo"] or ""))
        seg = str(r["segmento_cest"] or "").strip()
        if pref and ncm_8.startswith(pref):
            return dict(r)
        if seg and seg in segmentos:
            return dict(r)
    return None


def resolver_st_3_passos(
    conn: sqlite3.Connection,
    *,
    ncm: str,
    uf_origem: str = "SP",
    uf_destino: str = "SP",
    cest: str = "",
    data_operacao: str | None = None,
) -> dict[str, Any]:
    """Executa o cruzamento determinístico em 3 passos (Conv. 142/18 x UF Destino x Acordo Interestadual)."""
    ncm_8 = normalizar_ncm(ncm).zfill(8)[:8]
    cest_7 = normalizar_cest(cest)
    uf_o = uf_origem.strip().upper()[:2]
    uf_d = uf_destino.strip().upper()[:2]
    ref = data_operacao or date.today().isoformat()

    # ------------------------------------------------------------------
    # PASSO 1 — Elegibilidade Nacional (Convênio ICMS 142/2018)
    # ------------------------------------------------------------------
    itens_142 = _buscar_convenio_142(conn, ncm_8, cest_7)
    if not itens_142:
        return {
            "ncm": ncm_8,
            "uf_origem": uf_o,
            "uf_destino": uf_d,
            "data_operacao": ref,
            "elegivel_conv_142": False,
            "cests_possiveis": [],
            "segmentos": [],
            "obrigacao_uf_destino": False,
            "tem_st": False,
            "recolhe_st": "NAO_APLICAVEL",
            "acordo_aplicado": None,
            "cfop_entrada": "2.102" if uf_o != uf_d else "1.102",
            "cst_entrada": "0.00",
            "mva_original": 0.0,
            "aliquota_interna": 18.0,
            "fcp": 0.0,
            "artigo_legal": "NCM fora do Convênio ICMS 142/2018 (ST impossível)",
            "passo_1_resumo": "Não Elegível — NCM não consta nos Anexos II a XXVIII do Convênio ICMS 142/2018.",
            "passo_2_resumo": "Dispensado (bloqueado pelo Passo 1).",
            "passo_3_resumo": "Sem ST.",
        }

    cests_possiveis = list(dict.fromkeys(str(it["cest"]) for it in itens_142 if it.get("cest")))
    segmentos = list(dict.fromkeys(str(it["segmento_codigo"]) for it in itens_142 if it.get("segmento_codigo")))
    passo_1_msg = _descrever_passo_1(itens_142)

    # ------------------------------------------------------------------
    # PASSO 2 & PASSO 3 — Avaliação Individual por CEST / Segmento na UF de Destino
    # ------------------------------------------------------------------
    itens_avaliar = [it for it in itens_142 if not cest_7 or str(it.get("cest")) == cest_7] or itens_142
    segmentos_avaliados: list[dict[str, Any]] = []

    for it in itens_avaliar:
        cest_item = str(it.get("cest") or "")
        seg_item = str(it.get("segmento_codigo") or cest_item[:2])
        reg_dest = buscar_regra_estadual_icms(
            conn,
            uf_origem=uf_d,
            uf_destino=uf_d,
            ncm=ncm_8,
            cest=cest_item,
            data_referencia=ref,
            permitir_regra_geral_uf=False,
            cest_estrito=True,
        ) or buscar_regra_estadual_icms(
            conn,
            uf_origem=uf_o,
            uf_destino=uf_d,
            ncm=ncm_8,
            cest=cest_item,
            data_referencia=ref,
            permitir_regra_geral_uf=False,
            cest_estrito=True,
        )
        proto_dest = consultar_protocolo_st(
            conn,
            uf_origem=uf_o,
            uf_destino=uf_d,
            ncm=ncm_8,
            cest=cest_item,
            data_operacao=ref,
        )

        tem_st_seg = False
        mva_seg = 0.0
        aliq_seg = 18.0
        fcp_seg = 0.0
        artigo_seg = ""

        if reg_dest is not None:
            mva_seg = float(reg_dest.get("margem_st") or 0.0)
            aliq_seg = float(reg_dest.get("aliquota_icms") or 18.0)
            fcp_seg = float(reg_dest.get("aliquota_fcp") or 0.0)
            cst_reg = str(reg_dest.get("cst_icms") or "").strip()
            artigo_seg = str(reg_dest.get("dispositivo_legal") or "")
            tem_st_seg = bool(mva_seg > 0 or float(reg_dest.get("aliquota_icms_st") or 0.0) > 0 or cst_reg in {"10", "30", "60", "70"})
        elif proto_dest is not None and bool(proto_dest.get("possui_acordo_bilateral", 1)):
            tem_st_seg = True
            mva_seg = float(proto_dest.get("mva_original") or 0.0)
            aliq_seg = float(proto_dest.get("aliquota_interna_destino") or 18.0)
            fcp_seg = float(proto_dest.get("fcp_destino") or 0.0)
            artigo_seg = str(proto_dest.get("ato_legal") or "")

        recolhe_seg = "NAO_APLICAVEL"
        acordo_seg: str | None = None
        passo_3_seg = "Não aplicável (sem ST na UF de destino)."
        if tem_st_seg:
            acordo_row = _buscar_acordo_interestadual(
                conn,
                uf_origem=uf_o,
                uf_destino=uf_d,
                ncm_8=ncm_8,
                segmentos=[seg_item],
                data_ref=ref,
            )
            if acordo_row is None and proto_dest is not None:
                acordo_row = {"numero_acordo": proto_dest.get("ato_legal"), "tipo_acordo": "PROTOCOLO_BILATERAL"}
            if uf_o == uf_d:
                recolhe_seg = "INTERNA_SUBSTITUTO"
                acordo_seg = artigo_seg
                passo_3_seg = f"Operação interna ({uf_d} -> {uf_d}): substituição tributária interna."
            elif acordo_row is not None:
                recolhe_seg = "REMETENTE_RETIDO"
                acordo_seg = str(acordo_row.get("numero_acordo") or "Convênio/Protocolo")
                passo_3_seg = f"Acordo vigente ({acordo_seg}) — Retenção pelo remetente + MVA Ajustado."
            else:
                recolhe_seg = "DESTINATARIO_ANTECIPACAO"
                acordo_seg = "Sem Acordo (Antecipação Art. 426-A / GNRE)"
                passo_3_seg = "Sem Acordo Interestadual — Antecipação obrigatória na entrada (Art. 426-A RICMS / GNRE)."

        segmentos_avaliados.append(
            {
                "cest": cest_item,
                "cest_formatado": _formatar_cest(cest_item),
                "segmento_codigo": seg_item,
                "anexo": str(it.get("anexo") or ""),
                "descricao_item": str(it.get("descricao_item") or ""),
                "ncm_prefixo_casado": str(it.get("ncm_limpo") or ""),
                "tem_st": tem_st_seg,
                "recolhe_st": recolhe_seg,
                "acordo_aplicado": acordo_seg,
                "mva_original": mva_seg,
                "aliquota_interna": aliq_seg,
                "fcp": fcp_seg,
                "artigo_legal": artigo_seg or (f"Sem cobrança interna de ST em {uf_d} na data {ref}" if not tem_st_seg else "RICMS"),
                "passo_3_resumo": passo_3_seg,
                "regra_estadual": reg_dest,
            }
        )

    # Resumo consolidado do Passo 2
    if len(segmentos_avaliados) == 1:
        s0 = segmentos_avaliados[0]
        if s0["tem_st"]:
            passo_2_msg = f"Sujeito a ST em {uf_d} (CEST {s0['cest_formatado']} [Seg. {s0['segmento_codigo']}] — {s0['artigo_legal']} | IVA-ST Original {s0['mva_original']:.2f}%)."
        else:
            passo_2_msg = f"Fora da ST em {uf_d} na data {ref} (CEST {s0['cest_formatado']} [Seg. {s0['segmento_codigo']}] — {s0['artigo_legal']} | Tributado Integralmente)."
    else:
        partes_p2 = []
        for s in segmentos_avaliados:
            if s["tem_st"]:
                partes_p2.append(f"CEST {s['cest_formatado']} [Seg. {s['segmento_codigo']}]: ST vigente (IVA-ST {s['mva_original']:.2f}% | {s['artigo_legal']})")
            else:
                partes_p2.append(f"CEST {s['cest_formatado']} [Seg. {s['segmento_codigo']}]: Fora da ST / Tributado Integralmente ({s['artigo_legal']})")
        passo_2_msg = f"{len(segmentos_avaliados)} segmentos avaliados em {uf_d}: " + " | ".join(partes_p2) + "."

    principal = next((s for s in segmentos_avaliados if s["tem_st"]), segmentos_avaliados[0])

    if not principal["tem_st"]:
        return {
            "ncm": ncm_8,
            "uf_origem": uf_o,
            "uf_destino": uf_d,
            "data_operacao": ref,
            "elegivel_conv_142": True,
            "cests_possiveis": cests_possiveis,
            "segmentos": segmentos,
            "segmentos_avaliados": segmentos_avaliados,
            "obrigacao_uf_destino": False,
            "tem_st": False,
            "recolhe_st": "NAO_APLICAVEL",
            "acordo_aplicado": None,
            "cfop_entrada": "2.102" if uf_o != uf_d else "1.102",
            "cst_entrada": "0.00",
            "mva_original": 0.0,
            "aliquota_interna": principal["aliquota_interna"],
            "fcp": principal["fcp"],
            "artigo_legal": principal["artigo_legal"],
            "passo_1_resumo": passo_1_msg,
            "passo_2_resumo": passo_2_msg,
            "passo_3_resumo": "Não aplicável (sem ST na UF de destino).",
        }

    return {
        "ncm": ncm_8,
        "uf_origem": uf_o,
        "uf_destino": uf_d,
        "data_operacao": ref,
        "elegivel_conv_142": True,
        "cests_possiveis": cests_possiveis,
        "segmentos": segmentos,
        "segmentos_avaliados": segmentos_avaliados,
        "obrigacao_uf_destino": True,
        "tem_st": True,
        "recolhe_st": principal["recolhe_st"],
        "acordo_aplicado": principal["acordo_aplicado"],
        "cfop_entrada": "2.403" if uf_o != uf_d else "1.403",
        "cst_entrada": "0.60",
        "mva_original": principal["mva_original"],
        "aliquota_interna": principal["aliquota_interna"],
        "fcp": principal["fcp"],
        "artigo_legal": principal["artigo_legal"],
        "passo_1_resumo": passo_1_msg,
        "passo_2_resumo": passo_2_msg,
        "passo_3_resumo": principal["passo_3_resumo"],
    }


resolver_st_entrada = resolver_st_3_passos


def resolver_st_saida(
    conn: sqlite3.Connection,
    *,
    ncm: str,
    cest: str = "",
    uf_origem: str = "SP",
    uf_destino: str = "SP",
    perfil_destinatario: str = "CO",
    finalidade_operacao: str = "REVENDA",
    origem_mercadoria: str = "0",
    st_encerra_tributacao: bool = True,
    data_operacao: str | None = None,
) -> dict[str, Any]:
    """Validação de ST na Saída em 4 Passos (Conv. 142/18 x Vínculo Origem x UF Destino/Perfil x Acordo)."""
    from decimal import Decimal
    from src.engine.fiscal_engine import ALIQUOTAS_INTERNAS_UF
    from src.engine.fiscal_math import aliquota_interestadual, calcular_mva_ajustado

    ncm_8 = normalizar_ncm(ncm).zfill(8)[:8]
    cest_7 = normalizar_cest(cest)
    uf_o = uf_origem.strip().upper()[:2]
    uf_d = uf_destino.strip().upper()[:2]
    perfil = "NC" if str(perfil_destinatario or "CO").strip().upper().startswith("N") else "CO"
    fin = str(finalidade_operacao or "REVENDA").strip().upper()
    orig_dig = (str(origem_mercadoria or "0").strip() or "0")[0]
    ref = data_operacao or date.today().isoformat()
    interna = uf_o == uf_d

    aliq_dest_padrao, fcp_dest_padrao = ALIQUOTAS_INTERNAS_UF.get(uf_d, (Decimal("18.00"), Decimal("0.00")))
    aliq_inter = float(aliquota_interestadual(uf_o, uf_d if not interna else "MG", orig_dig) or Decimal("12.00"))

    # Passo 1 — Elegibilidade Nacional (Convênio 142/2018)
    itens_142 = _buscar_convenio_142(conn, ncm_8, cest_7)
    if not itens_142:
        cfop = "5.102" if interna else ("6.108" if perfil == "NC" else "6.102")
        return {
            "ncm": ncm_8,
            "uf_origem": uf_o,
            "uf_destino": uf_d,
            "perfil_destinatario": perfil,
            "tem_st": False,
            "st_na_origem": False,
            "st_no_destino": False,
            "cfop": cfop,
            "cst": f"{orig_dig}.00",
            "csosn": f"{orig_dig}.102",
            "aliquota_icms": float(aliq_dest_padrao) if interna else aliq_inter,
            "aliquota_st": 0.0,
            "mva_original": 0.0,
            "mva_ajustada": 0.0,
            "difal_pct": max(0.0, float(aliq_dest_padrao) - aliq_inter) if (not interna and perfil == "NC") else 0.0,
            "acordo_aplicado": None,
            "observacao": "NCM fora do Convênio ICMS 142/2018 — tributação normal.",
            "passo_1_resumo": "Não Elegível no Convênio 142/2018.",
            "passo_2_resumo": "Sem vínculo ST na origem.",
            "passo_3_resumo": "Saída tributada normal.",
            "passo_4_resumo": "Não aplicável.",
        }

    cests_possiveis = list(dict.fromkeys(str(it["cest"]) for it in itens_142 if it.get("cest")))
    segmentos = list(dict.fromkeys(str(it["segmento_codigo"]) for it in itens_142 if it.get("segmento_codigo")))
    cest_ef = cest_7 or (cests_possiveis[0] if cests_possiveis else "")
    passo_1_msg_saida = _descrever_passo_1(itens_142)

    # Passo 2 — Vínculo de ST na Origem
    reg_orig = buscar_regra_estadual_icms(
        conn, uf_origem=uf_o, uf_destino=uf_o, ncm=ncm_8, cest=cest_ef, data_referencia=ref, permitir_regra_geral_uf=False, cest_estrito=True
    )
    st_na_origem = bool(
        reg_orig
        and (
            float(reg_orig.get("margem_st") or 0) > 0
            or float(reg_orig.get("aliquota_icms_st") or 0) > 0
            or str(reg_orig.get("cst_icms") or "") in {"10", "30", "60", "70"}
        )
    )

    # Passo 3a — Saída Interna (uf_origem == uf_destino)
    if interna:
        if st_na_origem and st_encerra_tributacao:
            aliq_efet = float(aliq_dest_padrao) if perfil == "NC" else 0.0
            return {
                "ncm": ncm_8,
                "uf_origem": uf_o,
                "uf_destino": uf_d,
                "perfil_destinatario": perfil,
                "tem_st": True,
                "st_na_origem": True,
                "st_no_destino": True,
                "cfop": "5.405",
                "cst": f"{orig_dig}.60",
                "csosn": f"{orig_dig}.500",
                "aliquota_icms": 0.0,
                "aliquota_st": 0.0,
                "mva_original": 0.0,
                "mva_ajustada": 0.0,
                "icms_efetivo_pct": aliq_efet,
                "difal_pct": 0.0,
                "acordo_aplicado": reg_orig.get("dispositivo_legal") if reg_orig else None,
                "observacao": "Saída interna substituída (ST encerrada na cadeia anterior).",
                "passo_1_resumo": passo_1_msg_saida,
                "passo_2_resumo": f"ST vinculada na origem ({uf_o}) com encerramento.",
                "passo_3_resumo": f"Saída Interna: CFOP 5.405 | CST {orig_dig}.60 | CSOSN {orig_dig}.500 (sem destaque ST).",
                "passo_4_resumo": "Operação interna (dispensa protocolo interestadual).",
            }
        return {
            "ncm": ncm_8,
            "uf_origem": uf_o,
            "uf_destino": uf_d,
            "perfil_destinatario": perfil,
            "tem_st": False,
            "st_na_origem": st_na_origem,
            "st_no_destino": False,
            "cfop": "5.102",
            "cst": f"{orig_dig}.00",
            "csosn": f"{orig_dig}.102",
            "aliquota_icms": float(aliq_dest_padrao),
            "aliquota_st": 0.0,
            "mva_original": 0.0,
            "mva_ajustada": 0.0,
            "icms_efetivo_pct": 0.0,
            "difal_pct": 0.0,
            "acordo_aplicado": None,
            "observacao": "Saída interna tributada (sem encerramento de ST na origem).",
            "passo_1_resumo": f"Elegível (Conv. 142/2018) — CEST: {cest_ef}",
            "passo_2_resumo": "ST não encerra tributação na origem." if st_na_origem else "Sem ST na origem.",
            "passo_3_resumo": f"Saída Interna Tributada: CFOP 5.102 | CST {orig_dig}.00.",
            "passo_4_resumo": "Operação interna.",
        }

    # Passo 3b — Saída Interestadual para Não Contribuinte (NC) -> EC 87/2015
    if perfil == "NC":
        difal_val = round(max(0.0, float(aliq_dest_padrao) + float(fcp_dest_padrao) - aliq_inter), 2)
        cst_nc = f"{orig_dig}.60" if (st_na_origem and st_encerra_tributacao) else f"{orig_dig}.00"
        return {
            "ncm": ncm_8,
            "uf_origem": uf_o,
            "uf_destino": uf_d,
            "perfil_destinatario": "NC",
            "tem_st": False,
            "st_na_origem": st_na_origem,
            "st_no_destino": False,
            "cfop": "6.108",
            "cst": cst_nc,
            "csosn": f"{orig_dig}.500" if (st_na_origem and st_encerra_tributacao) else f"{orig_dig}.102",
            "aliquota_icms": aliq_inter,
            "aliquota_st": 0.0,
            "mva_original": 0.0,
            "mva_ajustada": 0.0,
            "difal_pct": difal_val,
            "fcp_destino": float(fcp_dest_padrao),
            "acordo_aplicado": "EC 87/2015",
            "observacao": "Saída interestadual para Não Contribuinte (CFOP 6.108 + DIFAL EC 87/2015, sem retenção de ST).",
            "passo_1_resumo": f"Elegível (Conv. 142/2018) — CEST: {cest_ef}",
            "passo_2_resumo": f"Origem ({uf_o}): {'ST encerrada' if st_na_origem else 'Tributado'}.",
            "passo_3_resumo": f"Interestadual NC: CFOP 6.108 | Inter {aliq_inter:.2f}% + DIFAL {difal_val:.2f}%.",
            "passo_4_resumo": "Não aplicável para Não Contribuinte (EC 87/2015).",
        }

    # Passo 3c & Passo 4 — Saída Interestadual para Contribuinte (CO)
    reg_dest = buscar_regra_estadual_icms(
        conn, uf_origem=uf_d, uf_destino=uf_d, ncm=ncm_8, cest=cest_ef, data_referencia=ref, permitir_regra_geral_uf=False
    ) or buscar_regra_estadual_icms(
        conn, uf_origem=uf_o, uf_destino=uf_d, ncm=ncm_8, cest=cest_ef, data_referencia=ref, permitir_regra_geral_uf=False
    )
    proto_dest = consultar_protocolo_st(conn, uf_origem=uf_o, uf_destino=uf_d, ncm=ncm_8, cest=cest_ef, data_operacao=ref)
    acordo = _buscar_acordo_interestadual(conn, uf_origem=uf_o, uf_destino=uf_d, ncm_8=ncm_8, segmentos=segmentos, data_ref=ref)
    if acordo is None and proto_dest is not None:
        acordo = {"numero_acordo": proto_dest.get("ato_legal"), "tipo_acordo": "PROTOCOLO_BILATERAL"}

    st_no_destino = bool(
        (reg_dest and (float(reg_dest.get("margem_st") or 0) > 0 or float(reg_dest.get("aliquota_icms_st") or 0) > 0 or str(reg_dest.get("cst_icms") or "") in {"10", "30", "60", "70"}))
        or (proto_dest is not None and bool(proto_dest.get("possui_acordo_bilateral", 1)))
        or (acordo is not None and reg_dest is None)
    )

    if not st_no_destino:
        return {
            "ncm": ncm_8,
            "uf_origem": uf_o,
            "uf_destino": uf_d,
            "perfil_destinatario": "CO",
            "tem_st": False,
            "st_na_origem": st_na_origem,
            "st_no_destino": False,
            "cfop": "6.102",
            "cst": f"{orig_dig}.00",
            "csosn": f"{orig_dig}.102",
            "aliquota_icms": aliq_inter,
            "aliquota_st": 0.0,
            "mva_original": 0.0,
            "mva_ajustada": 0.0,
            "difal_pct": 0.0,
            "acordo_aplicado": None,
            "observacao": f"UF de destino ({uf_d}) não exige ST para o item — saída tributada normal.",
            "passo_1_resumo": f"Elegível (Conv. 142/2018) — CEST: {cest_ef}",
            "passo_2_resumo": f"Origem ({uf_o}): {'ST na cadeia' if st_na_origem else 'Normal'}.",
            "passo_3_resumo": f"Destino ({uf_d}) não exige ST -> CFOP 6.102 | CST {orig_dig}.00.",
            "passo_4_resumo": "Dispensado (sem ST no destino).",
        }

    if acordo is not None:
        acordo_nome = str(acordo.get("numero_acordo") or "Convênio/Protocolo")
        mva_orig = float((reg_dest or {}).get("margem_st") or (proto_dest or {}).get("mva_original") or 0.0)
        aliq_st_dest = float((reg_dest or {}).get("aliquota_icms_st") or (proto_dest or {}).get("aliquota_interna_destino") or aliq_dest_padrao)
        fcp_dest = float((reg_dest or {}).get("aliquota_fcp") or (proto_dest or {}).get("fcp_destino") or fcp_dest_padrao)
        red_bc = float((reg_dest or {}).get("reducao_base_icms") or 0.0)
        uso_ativo = fin in {"USO_CONSUMO", "ATIVO_IMOBILIZADO"}
        mva_aj = 0.0 if uso_ativo else float(calcular_mva_ajustado(mva_orig, aliq_inter, aliq_st_dest, uf_destino=uf_d, fcp_pct=fcp_dest))
        cst_2 = "70" if red_bc > 0 else "10"
        return {
            "ncm": ncm_8,
            "uf_origem": uf_o,
            "uf_destino": uf_d,
            "perfil_destinatario": "CO",
            "tem_st": True,
            "st_na_origem": st_na_origem,
            "st_no_destino": True,
            "cfop": "6.404",
            "cst": f"{orig_dig}.{cst_2}",
            "csosn": f"{orig_dig}.201",
            "aliquota_icms": aliq_inter,
            "aliquota_st": aliq_st_dest,
            "mva_original": 0.0 if uso_ativo else mva_orig,
            "mva_ajustada": mva_aj,
            "difal_pct": round(max(0.0, aliq_st_dest + fcp_dest - aliq_inter), 2) if uso_ativo else 0.0,
            "acordo_aplicado": acordo_nome,
            "observacao": (
                f"{acordo_nome} — ST-DIFAL sem MVA (Cláusula 8ª Conv. 142/18)."
                if uso_ativo
                else f"{acordo_nome} — Retenção destacada na saída com direito a ressarcimento da ST anterior."
            ),
            "passo_1_resumo": f"Elegível (Conv. 142/2018) — CEST: {cest_ef}",
            "passo_2_resumo": f"Origem ({uf_o}): {'ST na cadeia anterior (ressarcimento)' if st_na_origem else 'Substituto'}.",
            "passo_3_resumo": f"Destino ({uf_d}) exige ST (Alíq. {aliq_st_dest:.2f}%).",
            "passo_4_resumo": f"COM Acordo ({acordo_nome}) -> CFOP 6.404 | CST {orig_dig}.{cst_2} | MVA Ajust. {mva_aj:.2f}%.",
        }

    # Sem Convênio / Sem Protocolo
    return {
        "ncm": ncm_8,
        "uf_origem": uf_o,
        "uf_destino": uf_d,
        "perfil_destinatario": "CO",
        "tem_st": True,
        "st_na_origem": st_na_origem,
        "st_no_destino": True,
        "cfop": "6.404",
        "cst": f"{orig_dig}.60",
        "csosn": f"{orig_dig}.500",
        "aliquota_icms": 0.0,
        "aliquota_st": 0.0,
        "mva_original": 0.0,
        "mva_ajustada": 0.0,
        "difal_pct": 0.0,
        "acordo_aplicado": None,
        "observacao": "Operação interestadual sem Convênio/Protocolo — ST a recolher pelo destinatário na entrada.",
        "passo_1_resumo": f"Elegível (Conv. 142/2018) — CEST: {cest_ef}",
        "passo_2_resumo": f"Origem ({uf_o}): {'ST anterior' if st_na_origem else 'Normal'}.",
        "passo_3_resumo": f"Destino ({uf_d}) exige ST.",
        "passo_4_resumo": f"SEM Acordo entre {uf_o} e {uf_d} -> CFOP 6.404 | CST {orig_dig}.60 (sem destaque ST).",
    }
