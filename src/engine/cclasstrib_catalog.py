"""Catálogo determinístico NCM x cClassTrib x CST_IBS_CBS x Imposto Seletivo (SVRS / LC 214/2025)."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

TABELA_CCLASSTRIB: tuple[dict[str, Any], ...] = (
    # Anexo I — Cesta Básica Nacional (Alíquota Zero — Art. 125 LC 214/2025)
    {
        "prefixos_ncm": ("1006", "0713", "0201", "0202", "0203", "0204", "0207", "0401", "0405", "0901", "1701", "1101", "1102", "1905", "1509"),
        "cst_ibs_cbs": "200",
        "cclass_trib": "200003",
        "reducao_pct": Decimal("100.00"),
        "anexo_legal": "Anexo I da LC 214/2025 (Cesta Básica Nacional de Alimentos)",
        "artigo_legal": "Art. 125 da LC 214/2025",
        "descricao_enquadramento": "Alíquota Zero (redução de 100%) — Cesta Básica Nacional",
        "sujeito_is": False,
        "aliquota_is_padrao": Decimal("0.00"),
        "cclass_trib_is": "",
    },
    # Anexos II a XI — Hortifrutigranjeiros e Alimentos in natura (Redução 60% / Zero conforme Anexo)
    {
        "prefixos_ncm": ("07", "08", "0406", "1902"),
        "cst_ibs_cbs": "200",
        "cclass_trib": "200034",
        "reducao_pct": Decimal("60.00"),
        "anexo_legal": "Anexo XV / Anexos II a XI da LC 214/2025",
        "artigo_legal": "Art. 135 da LC 214/2025",
        "descricao_enquadramento": "Redução de 60% na alíquota — Alimentos / Hortifrutis",
        "sujeito_is": False,
        "aliquota_is_padrao": Decimal("0.00"),
        "cclass_trib_is": "",
    },
    # Medicamentos e Dispositivos Médicos / Acessibilidade (Redução 60% — Anexos III e IV)
    {
        "prefixos_ncm": ("3003", "3004", "9018", "9021"),
        "cst_ibs_cbs": "200",
        "cclass_trib": "200030",
        "reducao_pct": Decimal("60.00"),
        "anexo_legal": "Anexos III e IV da LC 214/2025",
        "artigo_legal": "Art. 131 e Art. 132 da LC 214/2025",
        "descricao_enquadramento": "Redução de 60% na alíquota — Medicamentos e Dispositivos Médicos",
        "sujeito_is": False,
        "aliquota_is_padrao": Decimal("0.00"),
        "cclass_trib_is": "",
    },
    # Insumos Agropecuários (Redução 60% — Anexo IX)
    {
        "prefixos_ncm": ("2309", "3101", "3102", "3105", "8432", "8433"),
        "cst_ibs_cbs": "200",
        "cclass_trib": "200032",
        "reducao_pct": Decimal("60.00"),
        "anexo_legal": "Anexo IX da LC 214/2025",
        "artigo_legal": "Art. 138 da LC 214/2025",
        "descricao_enquadramento": "Redução de 60% na alíquota — Insumos Agropecuários",
        "sujeito_is": False,
        "aliquota_is_padrao": Decimal("0.00"),
        "cclass_trib_is": "",
    },
    # Higiene Pessoal e Limpeza Básica (Redução 60% — Anexo II)
    {
        "prefixos_ncm": ("3305", "3306", "3401"),
        "cst_ibs_cbs": "200",
        "cclass_trib": "200035",
        "reducao_pct": Decimal("60.00"),
        "anexo_legal": "Anexo II da LC 214/2025",
        "artigo_legal": "Art. 130 da LC 214/2025",
        "descricao_enquadramento": "Redução de 60% na alíquota — Higiene Pessoal e Limpeza",
        "sujeito_is": False,
        "aliquota_is_padrao": Decimal("0.00"),
        "cclass_trib_is": "",
    },
    # Imposto Seletivo (IS) — Tabaco / Cigarros (Art. 409+ LC 214/2025)
    {
        "prefixos_ncm": ("2402", "2403"),
        "cst_ibs_cbs": "000",
        "cclass_trib": "000001",
        "reducao_pct": Decimal("0.00"),
        "anexo_legal": "Anexo XVII da LC 214/2025 (Imposto Seletivo — Fumo)",
        "artigo_legal": "Art. 409 e Art. 412 da LC 214/2025",
        "descricao_enquadramento": "Tributação Padrão IBS/CBS + Imposto Seletivo (Tabaco)",
        "sujeito_is": True,
        "aliquota_is_padrao": Decimal("25.00"),
        "cclass_trib_is": "001001",
    },
    # Imposto Seletivo (IS) — Bebidas Alcoólicas e Açucaradas
    {
        "prefixos_ncm": ("2202", "2203", "2204", "2205", "2206", "2208"),
        "cst_ibs_cbs": "000",
        "cclass_trib": "000001",
        "reducao_pct": Decimal("0.00"),
        "anexo_legal": "Anexo XVII da LC 214/2025 (Imposto Seletivo — Bebidas)",
        "artigo_legal": "Art. 409 e Art. 413 da LC 214/2025",
        "descricao_enquadramento": "Tributação Padrão IBS/CBS + Imposto Seletivo (Bebidas Alcoólicas/Açucaradas)",
        "sujeito_is": True,
        "aliquota_is_padrao": Decimal("10.00"),
        "cclass_trib_is": "001002",
    },
    # Imposto Seletivo (IS) — Veículos Poluentes, Embarcações, Aeronaves e Minerais
    {
        "prefixos_ncm": ("8703", "8802", "8903", "2601", "2709"),
        "cst_ibs_cbs": "000",
        "cclass_trib": "000001",
        "reducao_pct": Decimal("0.00"),
        "anexo_legal": "Anexo XVII da LC 214/2025 (Imposto Seletivo — Veículos/Minerais)",
        "artigo_legal": "Art. 409 e Art. 414 da LC 214/2025",
        "descricao_enquadramento": "Tributação Padrão IBS/CBS + Imposto Seletivo (Veículos/Aeronaves/Minerais)",
        "sujeito_is": True,
        "aliquota_is_padrao": Decimal("5.00"),
        "cclass_trib_is": "001003",
    },
)


def consultar_enquadramento_cclasstrib(ncm: str) -> dict[str, Any]:
    """Retorna o enquadramento oficial SVRS (CST_IBS_CBS, cClassTrib, Anexo LC 214/2025 e IS)."""
    ncm_dig = re.sub(r"\D", "", str(ncm or ""))
    melhor: dict[str, Any] | None = None
    melhor_len = 0

    for item in TABELA_CCLASSTRIB:
        for pref in item["prefixos_ncm"]:
            if ncm_dig.startswith(pref) and len(pref) > melhor_len:
                melhor = item
                melhor_len = len(pref)

    if melhor is not None:
        return {
            "ncm": ncm_dig,
            "cst_ibs_cbs": melhor["cst_ibs_cbs"],
            "cclass_trib": melhor["cclass_trib"],
            "reducao_pct": melhor["reducao_pct"],
            "anexo_legal": melhor["anexo_legal"],
            "artigo_legal": melhor["artigo_legal"],
            "descricao_enquadramento": melhor["descricao_enquadramento"],
            "sujeito_is": bool(melhor["sujeito_is"]),
            "aliquota_is_padrao": melhor["aliquota_is_padrao"],
            "cclass_trib_is": melhor["cclass_trib_is"],
        }

    return {
        "ncm": ncm_dig,
        "cst_ibs_cbs": "000",
        "cclass_trib": "000001",
        "reducao_pct": Decimal("0.00"),
        "anexo_legal": "Regra Geral (Tributação Integral)",
        "artigo_legal": "Art. 12 e Art. 14 da LC 214/2025",
        "descricao_enquadramento": "Tributação Integral Padrão IBS/CBS (sem redução)",
        "sujeito_is": False,
        "aliquota_is_padrao": Decimal("0.00"),
        "cclass_trib_is": "",
    }
