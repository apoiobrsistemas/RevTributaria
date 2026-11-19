"""Motor de Decisão de ST em 3 Camadas: Convênio 142/2018 x Legislação UF Destino x Acordo Interestadual."""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from typing import Any

from src.database.repository import buscar_regra_estadual_icms, normalizar_cest, normalizar_ncm
from src.database.schema_fase2 import consultar_protocolo_st
from src.legislation.confaz_ingestor import garantir_base_confaz_142_e_acordos


def _buscar_convenio_142(conn: sqlite3.Connection, ncm_8: str, cest_7: str = "") -> list[dict[str, Any]]:
    """Busca elegibilidade no Convênio ICMS 142/2018 em cascata 8 -> 6 -> 4 dígitos (e por CEST)."""
    garantir_base_confaz_142_e_acordos(conn)
    candidatos = [ncm_8]
    if len(ncm_8) >= 6:
        candidatos.append(ncm_8[:6])
    if len(ncm_8) >= 4:
        candidatos.append(ncm_8[:4])

    placeholders = ",".join("?" for _ in candidatos)
    sql = f"""
        SELECT * FROM convenio_142_anexos
        WHERE ncm_limpo IN ({placeholders})
           OR (? != '' AND cest = ?)
        ORDER BY length(ncm_limpo) DESC, id ASC
    """
    rows = conn.execute(sql, candidatos + [cest_7, cest_7]).fetchall()
    return [dict(r) for r in rows]


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
    cest_ef = cest_7 or (cests_possiveis[0] if cests_possiveis else "")

    # ------------------------------------------------------------------
    # PASSO 2 — Obrigação Interna na UF de Destino (RICMS / Portarias SRE)
    # ------------------------------------------------------------------
    reg_dest = buscar_regra_estadual_icms(
        conn,
        uf_origem=uf_d,
        uf_destino=uf_d,
        ncm=ncm_8,
        cest=cest_ef,
        data_referencia=ref,
        permitir_regra_geral_uf=False,
    ) or buscar_regra_estadual_icms(
        conn,
        uf_origem=uf_o,
        uf_destino=uf_d,
        ncm=ncm_8,
        cest=cest_ef,
        data_referencia=ref,
        permitir_regra_geral_uf=False,
    )

    proto_dest = consultar_protocolo_st(
        conn,
        uf_origem=uf_o,
        uf_destino=uf_d,
        ncm=ncm_8,
        cest=cest_ef,
        data_operacao=ref,
    )

    tem_st_regra = False
    mva_orig = 0.0
    aliq_int = 18.0
    fcp = 0.0
    artigo = ""

    if reg_dest is not None:
        mva_orig = float(reg_dest.get("margem_st") or 0.0)
        aliq_int = float(reg_dest.get("aliquota_icms") or 18.0)
        fcp = float(reg_dest.get("aliquota_fcp") or 0.0)
        cst_reg = str(reg_dest.get("cst_icms") or "").strip()
        artigo = str(reg_dest.get("dispositivo_legal") or "")
        tem_st_regra = bool(mva_orig > 0 or float(reg_dest.get("aliquota_icms_st") or 0.0) > 0 or cst_reg in {"10", "30", "60", "70"})
    elif proto_dest is not None and bool(proto_dest.get("possui_acordo_bilateral", 1)):
        tem_st_regra = True
        mva_orig = float(proto_dest.get("mva_original") or 0.0)
        aliq_int = float(proto_dest.get("aliquota_interna_destino") or 18.0)
        fcp = float(proto_dest.get("fcp_destino") or 0.0)
        artigo = str(proto_dest.get("ato_legal") or "")

    if not tem_st_regra:
        return {
            "ncm": ncm_8,
            "uf_origem": uf_o,
            "uf_destino": uf_d,
            "data_operacao": ref,
            "elegivel_conv_142": True,
            "cests_possiveis": cests_possiveis,
            "segmentos": segmentos,
            "obrigacao_uf_destino": False,
            "tem_st": False,
            "recolhe_st": "NAO_APLICAVEL",
            "acordo_aplicado": None,
            "cfop_entrada": "2.102" if uf_o != uf_d else "1.102",
            "cst_entrada": "0.00",
            "mva_original": 0.0,
            "aliquota_interna": aliq_int,
            "fcp": fcp,
            "artigo_legal": artigo or f"Sem cobrança interna de ST em {uf_d} na data {ref}",
            "passo_1_resumo": f"Elegível (Conv. 142/2018) — CEST(s): {', '.join(cests_possiveis)}",
            "passo_2_resumo": f"Fora da ST em {uf_d} na data {ref} ({artigo or 'Tributado Integralmente'}).",
            "passo_3_resumo": "Não aplicável (sem ST na UF de destino).",
        }

    # ------------------------------------------------------------------
    # PASSO 3 — Responsável na Operação Interestadual (uf_origem -> uf_destino)
    # ------------------------------------------------------------------
    acordo = _buscar_acordo_interestadual(
        conn,
        uf_origem=uf_o,
        uf_destino=uf_d,
        ncm_8=ncm_8,
        segmentos=segmentos,
        data_ref=ref,
    )
    if acordo is None and proto_dest is not None:
        acordo = {"numero_acordo": proto_dest.get("ato_legal"), "tipo_acordo": "PROTOCOLO_BILATERAL"}

    if uf_o == uf_d:
        recolhe_st = "INTERNA_SUBSTITUTO"
        passo_3 = f"Operação interna ({uf_d} -> {uf_d}): substituição tributária interna."
        acordo_nome = artigo
    elif acordo is not None:
        recolhe_st = "REMETENTE_RETIDO"
        acordo_nome = str(acordo.get("numero_acordo") or "Convênio/Protocolo")
        passo_3 = f"Acordo vigente ({acordo_nome}) — Retenção pelo remetente + MVA Ajustado."
    else:
        recolhe_st = "DESTINATARIO_ANTECIPACAO"
        acordo_nome = "Sem Acordo (Antecipação Art. 426-A / GNRE)"
        passo_3 = "Sem Acordo Interestadual — Antecipação obrigatória na entrada (Art. 426-A RICMS / GNRE)."

    return {
        "ncm": ncm_8,
        "uf_origem": uf_o,
        "uf_destino": uf_d,
        "data_operacao": ref,
        "elegivel_conv_142": True,
        "cests_possiveis": cests_possiveis,
        "segmentos": segmentos,
        "obrigacao_uf_destino": True,
        "tem_st": True,
        "recolhe_st": recolhe_st,
        "acordo_aplicado": acordo_nome,
        "cfop_entrada": "2.403" if uf_o != uf_d else "1.403",
        "cst_entrada": "0.60",
        "mva_original": mva_orig,
        "aliquota_interna": aliq_int,
        "fcp": fcp,
        "artigo_legal": artigo,
        "passo_1_resumo": f"Elegível (Conv. 142/2018) — CEST(s): {', '.join(cests_possiveis)}",
        "passo_2_resumo": f"Sujeito a ST em {uf_d} ({artigo or 'RICMS'} | IVA-ST Original {mva_orig:.2f}%).",
        "passo_3_resumo": passo_3,
    }
