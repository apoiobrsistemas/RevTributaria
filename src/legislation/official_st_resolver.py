"""Extrator determinístico on-demand de Portarias SRE/RICMS/Convênios para qualquer NCM (Zero Hardcode)."""

from __future__ import annotations

import re
from typing import Any

from src.legislation.ai_reader import citacao_existe_literalmente
from src.legislation.url_guard import validar_url_oficial


def _formatar_variantes_ncm(ncm_8: str) -> list[str]:
    d = re.sub(r"\D", "", str(ncm_8 or ""))
    variantes: list[str] = []
    if len(d) == 8:
        variantes.extend([f"{d[:4]}.{d[4:6]}.{d[6:8]}", d])
    if len(d) >= 6:
        variantes.extend([f"{d[:4]}.{d[4:6]}", d[:6]])
    if len(d) >= 4:
        variantes.append(d[:4])
    return list(dict.fromkeys(variantes))


def extrair_regra_st_texto_oficial(
    texto_norma: str,
    *,
    ncm: str,
    uf: str,
    fonte_url: str,
    numero_norma: str = "",
) -> dict[str, Any] | None:
    """Extrai IVA-ST/MVA, CEST e base legal de texto oficial (.gov.br/.leg.br) validando citação literal."""
    url_ok = validar_url_oficial(fonte_url)
    ncm_8 = re.sub(r"\D", "", str(ncm or "")).zfill(8)[:8]
    if not texto_norma or len(ncm_8) != 8:
        return None

    linhas = [ln.strip() for ln in texto_norma.splitlines() if ln.strip()]
    variantes = _formatar_variantes_ncm(ncm_8)

    trecho_encontrado = ""
    for var in variantes:
        pat = re.compile(rf"(?<!\d){re.escape(var)}(?!\d)")
        for idx, ln in enumerate(linhas):
            if pat.search(ln):
                inicio = max(0, idx - 1)
                fim = min(len(linhas), idx + 2)
                trecho_encontrado = " ".join(linhas[inicio:fim])
                break
        if trecho_encontrado:
            break

    if not trecho_encontrado:
        return None

    # Validação literal obrigatória contra o texto oficial baixado
    if not citacao_existe_literalmente(trecho_encontrado[:120], texto_norma):
        return None

    # Extrai CEST (XX.XXX.XX ou 7 dígitos)
    m_cest = re.search(r"\b(\d{2}\.\d{3}\.\d{2})\b", trecho_encontrado)
    cest_limpo = re.sub(r"\D", "", m_cest.group(1)) if m_cest else ""

    # Extrai IVA-ST / MVA (%)
    m_iva = re.search(
        r"(?:IVA[-\s]?ST|MVA(?:\s+Original)?)\D{0,25}(\d{1,3}(?:[.,]\d{1,2})?)\s*%",
        trecho_encontrado,
        re.I,
    )
    if not m_iva:
        m_iva = re.search(r"(\d{1,3}[.,]\d{2})\s*%", trecho_encontrado)
    iva_val = float(m_iva.group(1).replace(",", ".")) if m_iva else 0.0

    # Extrai alíquota interna se explicitada
    m_aliq = re.search(r"al[íi]quota\D{0,20}(\d{1,2}(?:[.,]\d{1,2})?)\s*%", trecho_encontrado, re.I)
    aliq_icms = float(m_aliq.group(1).replace(",", ".")) if m_aliq else 18.0

    # Extrai referência normativa (Portaria SRE / CAT / Artigo / Convênio)
    refs_norma = re.findall(
        r"(?:Portaria\s+(?:SRE|CAT)\s+\d+/\d{4}|Art\.?\s*313-[A-Z0-9]+|Conv[êe]nio\s+ICMS\s+\d+/\d{4})",
        f"{numero_norma} {texto_norma[:1200]} {trecho_encontrado}",
        re.I,
    )
    disp_legal = " — ".join(dict.fromkeys(r.strip() for r in refs_norma)) if refs_norma else (numero_norma or f"RICMS/{uf}")

    tem_st = 1 if (iva_val > 0 or "IVA" in trecho_encontrado.upper() or "MVA" in trecho_encontrado.upper() or "SUBSTITUIÇÃO" in trecho_encontrado.upper() or cest_limpo) else 0

    return {
        "ncm": ncm_8,
        "cest": cest_limpo,
        "tem_st": tem_st,
        "margem_st": iva_val,
        "aliquota_icms": aliq_icms,
        "aliquota_icms_st": aliq_icms,
        "dispositivo_legal": disp_legal,
        "trecho_citado": trecho_encontrado[:400],
        "fonte_url": url_ok,
        "origem_dado": "SYNC_OFICIAL_TEMPO_REAL",
    }
