"""Validador Estrutural e Matemático das tags XML gIBSCBS e gIS (NT SVRS / LC 214/2025)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Any

from src.engine.fiscal_math import CEM, ZERO, _dec, _r2


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find_child(elem: ET.Element | None, name: str) -> ET.Element | None:
    if elem is None:
        return None
    for child in elem:
        if _strip_ns(child.tag) == name:
            return child
    return None


def _find_text(elem: ET.Element | None, name: str, default: str = "") -> str:
    c = _find_child(elem, name)
    if c is not None and c.text is not None:
        return c.text.strip()
    return default


def _find_descendant(elem: ET.Element, name: str) -> ET.Element | None:
    for node in elem.iter():
        if _strip_ns(node.tag) == name:
            return node
    return None


def _all_descendants(elem: ET.Element, name: str) -> list[ET.Element]:
    return [node for node in elem.iter() if _strip_ns(node.tag) == name]


def validar_xml_reforma_lc214(xml_str: str) -> dict[str, Any]:
    """Audita grupos gIBSCBS e gIS em XML NF-e/NFC-e ou trecho XML de item."""
    try:
        root = ET.fromstring(xml_str.strip())
    except ET.ParseError as exc:
        return {
            "valido": False,
            "itens_auditados": 0,
            "erros": [f"XML inválido: {exc}"],
            "alertas": [],
            "detalhes_itens": [],
        }

    dets = _all_descendants(root, "det")
    if not dets:
        # Permite validar trecho direto contendo <IBSCBS> ou <gIBSCBS>
        dets = [root]

    erros: list[str] = []
    alertas: list[str] = []
    detalhes: list[dict[str, Any]] = []
    tol = Decimal("0.02")

    for idx, det in enumerate(dets, start=1):
        n_item = det.attrib.get("nItem", str(idx))
        prod = _find_child(det, "prod")
        v_prod = _dec(_find_text(prod, "vProd", "0"))
        v_desc = _dec(_find_text(prod, "vDesc", "0"))
        v_frete = _dec(_find_text(prod, "vFrete", "0"))
        v_seg = _dec(_find_text(prod, "vSeg", "0"))
        v_outro = _dec(_find_text(prod, "vOutro", "0"))

        _imp_node = _find_child(det, "imposto")
        imposto = _imp_node if _imp_node is not None else det
        v_icms = _dec(_find_text(_find_descendant(imposto, "ICMS"), "vICMS", "0")) if _find_descendant(imposto, "ICMS") is not None else ZERO
        if v_icms == ZERO:
            for tag_v in _all_descendants(imposto, "vICMS"):
                v_icms = _dec(tag_v.text or "0")
                break
        v_pis = ZERO
        for tag_p in _all_descendants(imposto, "vPIS"):
            v_pis = _dec(tag_p.text or "0")
            break
        v_cofins = ZERO
        for tag_c in _all_descendants(imposto, "vCOFINS"):
            v_cofins = _dec(tag_c.text or "0")
            break
        v_iss = ZERO
        for tag_s in _all_descendants(imposto, "vISSQN"):
            v_iss = _dec(tag_s.text or "0")
            break

        _ibs_node = _find_descendant(imposto, "IBSCBS")
        ibscbs_node = _ibs_node if _ibs_node is not None else det
        g_ibscbs = _find_descendant(imposto, "gIBSCBS")

        if g_ibscbs is None:
            erros.append(
                f"Item {n_item}: grupo <gIBSCBS> ausente (em 2026 gera perda da compensação Art. 348 LC 214/2025)."
            )
            continue

        cst = _find_text(ibscbs_node, "CST") or _find_text(g_ibscbs, "CST")
        cclass = _find_text(ibscbs_node, "cClassTrib") or _find_text(g_ibscbs, "cClassTrib")
        v_bc = _dec(_find_text(g_ibscbs, "vBC", "0"))

        if len(cst) != 3 or not cst.isdigit():
            erros.append(f"Item {n_item}: CST IBS/CBS inválido ('{cst}', esperado 3 dígitos).")
        if len(cclass) != 6 or not cclass.isdigit():
            erros.append(f"Item {n_item}: cClassTrib inválido ('{cclass}', esperado 6 dígitos SVRS).")

        # Checagem crítica de bitributação (Art. 12 § 2º LC 214/2025)
        tributos_antigos = _r2(v_icms + v_pis + v_cofins + v_iss)
        if v_prod > ZERO and tributos_antigos > ZERO:
            valor_bruto = _r2(v_prod - v_desc + v_frete + v_seg + v_outro)
            base_limpa_esperada = max(ZERO, _r2(valor_bruto - tributos_antigos))
            if v_bc > base_limpa_esperada + tol:
                erros.append(
                    f"Item {n_item}: BITRIBUTAÇÃO DETECTADA (Art. 12 § 2º LC 214/2025) — "
                    f"vBC ({v_bc}) inclui ICMS/PIS/COFINS/ISS (base limpa esperada: {base_limpa_esperada})."
                )

        # Conferência matemática gIBSUF, gIBSMun e gCBS
        g_ibs_uf = _find_child(g_ibscbs, "gIBSUF")
        p_ibs_uf = _dec(_find_text(g_ibs_uf, "pIBSUF", "0"))
        v_ibs_uf = _dec(_find_text(g_ibs_uf, "vIBSUF", "0"))
        esp_uf = _r2(v_bc * p_ibs_uf / CEM)
        if g_ibs_uf is not None and abs(v_ibs_uf - esp_uf) > tol:
            erros.append(f"Item {n_item}: vIBSUF ({v_ibs_uf}) diverge do cálculo ({esp_uf}).")

        g_ibs_mun = _find_child(g_ibscbs, "gIBSMun")
        p_ibs_mun = _dec(_find_text(g_ibs_mun, "pIBSMun", "0"))
        v_ibs_mun = _dec(_find_text(g_ibs_mun, "vIBSMun", "0"))
        esp_mun = _r2(v_bc * p_ibs_mun / CEM)
        if g_ibs_mun is not None and abs(v_ibs_mun - esp_mun) > tol:
            erros.append(f"Item {n_item}: vIBSMun ({v_ibs_mun}) diverge do cálculo ({esp_mun}).")

        g_cbs = _find_child(g_ibscbs, "gCBS")
        p_cbs = _dec(_find_text(g_cbs, "pCBS", "0"))
        v_cbs = _dec(_find_text(g_cbs, "vCBS", "0"))
        esp_cbs = _r2(v_bc * p_cbs / CEM)
        if g_cbs is not None and abs(v_cbs - esp_cbs) > tol:
            erros.append(f"Item {n_item}: vCBS ({v_cbs}) diverge do cálculo ({esp_cbs}).")

        # Conferência opcional gIS (Imposto Seletivo)
        g_is = _find_descendant(imposto, "gIS")
        v_is = ZERO
        if g_is is not None:
            v_bc_is = _dec(_find_text(g_is, "vBCIS", "0"))
            p_is = _dec(_find_text(g_is, "pIS", "0"))
            v_is = _dec(_find_text(g_is, "vIS", "0"))
            esp_is = _r2(v_bc_is * p_is / CEM)
            if abs(v_is - esp_is) > tol:
                erros.append(f"Item {n_item}: vIS ({v_is}) diverge do cálculo ({esp_is}).")

        detalhes.append(
            {
                "item": n_item,
                "CST": cst,
                "cClassTrib": cclass,
                "vBC": str(v_bc),
                "vIBSUF": str(v_ibs_uf),
                "vIBSMun": str(v_ibs_mun),
                "vCBS": str(v_cbs),
                "vIS": str(v_is),
            }
        )

    return {
        "valido": len(erros) == 0,
        "itens_auditados": len(dets),
        "erros": erros,
        "alertas": alertas,
        "detalhes_itens": detalhes,
    }
