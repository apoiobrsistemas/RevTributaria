"""Validador Determinístico de Regras da NF-e (Portal Nacional nfe.fazenda.gov.br — Zero IA)."""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Mapping

NFE_PORTAL_URL = "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w="


def parsear_tabela_dominio_nfe(conteudo: bytes, *, formato: str = "json") -> list[dict[str, str]]:
    """Importa/parseia tabelas oficiais de domínio (CST/CSOSN x CFOP x cBenef x CEST) do Portal NF-e."""
    txt = conteudo.decode("utf-8-sig", errors="replace").strip()
    if formato.lower() == "json" or txt.startswith("[") or txt.startswith("{"):
        data = json.loads(txt)
        itens = data if isinstance(data, list) else data.get("regras", [])
        return [
            {
                "cst": str(it.get("cst") or "").strip(),
                "csosn": str(it.get("csosn") or "").strip(),
                "cfop": re.sub(r"\D", "", str(it.get("cfop") or "")),
                "cbenef": str(it.get("cbenef") or "").strip().upper(),
                "cest": re.sub(r"\D", "", str(it.get("cest") or "")),
                "regra_sefaz": str(it.get("regra_sefaz") or "Portal NF-e"),
            }
            for it in itens
        ]

    delim = ";" if txt.count(";") >= txt.count(",") else ","
    reader = csv.DictReader(io.StringIO(txt), delimiter=delim)
    return [
        {
            "cst": str(r.get("cst") or r.get("CST") or "").strip(),
            "csosn": str(r.get("csosn") or r.get("CSOSN") or "").strip(),
            "cfop": re.sub(r"\D", "", str(r.get("cfop") or r.get("CFOP") or "")),
            "cbenef": str(r.get("cbenef") or r.get("cBenef") or "").strip().upper(),
            "cest": re.sub(r"\D", "", str(r.get("cest") or r.get("CEST") or "")),
            "regra_sefaz": str(r.get("regra_sefaz") or "Portal NF-e"),
        }
        for r in reader
    ]


def validar_combinacao_sintatica_nfe(row: Mapping[str, Any]) -> dict[str, Any]:
    """Valida combinação CST/CSOSN x CFOP x cBenef x CEST contra regras de rejeição SEFAZ."""
    erros: list[str] = []

    cst_raw = str(row.get("CST ICMS") or row.get("CST (Orig.CST)") or "").strip()
    cst_2d = cst_raw.split(".")[-1] if "." in cst_raw else cst_raw
    csosn_raw = str(row.get("CSOSN") or row.get("CSOSN (Orig.CSOSN)") or "").strip()
    csosn_3d = csosn_raw.split(".")[-1] if "." in csosn_raw else csosn_raw
    cbenef = str(row.get("Código Beneficio Fiscal") or row.get("Código cBenef") or "").strip().upper()
    cest = re.sub(r"\D", "", str(row.get("CEST") or ""))
    cfop = re.sub(r"\D", "", str(row.get("CFOP") or row.get("CFOP Interno") or ""))
    aliq_efet = float(row.get("Alíquota ICMS Efetivo") or row.get("Alíq. ICMS Efetivo (%)") or 0.0)
    perfil = str(row.get("Perfil (NC/CO)") or row.get("Perfil Destinatário/Remetente") or "").upper()
    sentido = str(row.get("Sentido") or "").upper()

    # Regra 1: Rejeição SEFAZ 930/931 — CST 00 não pode ter cBenef
    if cst_2d == "00" and cbenef:
        erros.append(f"Rejeição 930/931: CST 00 incompatível com cBenef '{cbenef}'.")

    # Regra 2: Rejeição SEFAZ 806 / Convênio 142/18 — CST 10/30/60/70 ou CSOSN 201/202/203/500 exige CEST de 7 dígitos
    exige_cest = cst_2d in {"10", "30", "60", "70"} or csosn_3d in {"201", "202", "203", "500"}
    if exige_cest and len(cest) != 7:
        erros.append(f"Rejeição 806 (Conv. 142/18): CST/CSOSN de ST ({cst_2d}/{csosn_3d}) exige CEST válido de 7 dígitos.")

    # Regra 3: NT 2018.005 — vBCEfet/vICMSEfet no CST 60/500 para Não Contribuinte
    if (cst_2d == "60" or csosn_3d == "500") and ("NC" in perfil or "NÃO CONTRIBUINTE" in perfil) and aliq_efet <= 0.0:
        erros.append("NT 2018.005: CST 60/CSOSN 500 em operação com Não Contribuinte recomenda Alíquota ICMS Efetivo > 0.")

    # Regra 4: Coerência CFOP x Sentido
    if cfop and sentido == "ENTRADA" and cfop[0] not in {"1", "2", "3"}:
        erros.append(f"CFOP '{cfop}' inválido para operação de Entrada (esperado 1.xxx/2.xxx/3.xxx).")
    if cfop and sentido == "SAÍDA" and cfop[0] not in {"5", "6", "7"}:
        erros.append(f"CFOP '{cfop}' inválido para operação de Saída (esperado 5.xxx/6.xxx/7.xxx).")

    return {
        "valido": len(erros) == 0,
        "erros": erros,
        "status_nt": "APROVADA" if not erros else f"ALERTA_NT: {' | '.join(erros)}",
    }


def validar_linhas_matriz_nt(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Valida todas as linhas da matriz contra as regras sintáticas da NF-e sem remover colunas."""
    for row in linhas:
        res = validar_combinacao_sintatica_nfe(row)
        row["Validação NT SEFAZ"] = res["status_nt"]
    return linhas
