"""Parser seguro de NF-e de Entrada (.xml e .zip) com proteção anti-XXE."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal
from typing import Any

from src.engine.fiscal_math import ZERO, _dec

_XXE_PATTERN = re.compile(r"<!\s*(DOCTYPE|ENTITY)\b", re.IGNORECASE)


class XMLSegurancaError(ValueError):
    """Erro disparado quando XML contém DOCTYPE/ENTITY (risco XXE) ou está malformado."""


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find_child(elem: ET.Element | None, name: str) -> ET.Element | None:
    if elem is None:
        return None
    for ch in elem:
        if _strip_ns(ch.tag) == name:
            return ch
    return None


def _find_text(elem: ET.Element | None, name: str, default: str = "") -> str:
    c = _find_child(elem, name)
    if c is not None and c.text is not None:
        return c.text.strip()
    return default


def _find_descendant(elem: ET.Element | None, name: str) -> ET.Element | None:
    if elem is None:
        return None
    for node in elem.iter():
        if _strip_ns(node.tag) == name:
            return node
    return None


def _parse_xml_seguro(xml_bytes: bytes) -> ET.Element:
    texto = xml_bytes.decode("utf-8", errors="replace")
    if _XXE_PATTERN.search(texto):
        raise XMLSegurancaError("XML rejeitado pela trava anti-XXE (DOCTYPE/ENTITY proibido).")
    try:
        return ET.fromstring(texto)
    except ET.ParseError as exc:
        raise XMLSegurancaError(f"XML malformado: {exc}") from exc


def _extrair_grupo_icms(icms_node: ET.Element | None) -> dict[str, Any]:
    if icms_node is None:
        return {
            "orig": "0",
            "cst_csosn": "00",
            "pRedBC": ZERO,
            "vBC": ZERO,
            "pICMS": ZERO,
            "vICMS": ZERO,
            "pMVAST": ZERO,
            "pRedBCST": ZERO,
            "vBCST": ZERO,
            "pICMSST": ZERO,
            "vICMSST": ZERO,
            "vFCPST": ZERO,
            "vICMSSTRet": ZERO,
        }
    sub = next(iter(icms_node), None)
    if sub is None:
        sub = icms_node
    cst = _find_text(sub, "CST") or _find_text(sub, "CSOSN") or "00"
    return {
        "orig": _find_text(sub, "orig", "0"),
        "cst_csosn": cst,
        "pRedBC": _dec(_find_text(sub, "pRedBC", "0")),
        "vBC": _dec(_find_text(sub, "vBC", "0")),
        "pICMS": _dec(_find_text(sub, "pICMS", "0")),
        "vICMS": _dec(_find_text(sub, "vICMS", "0")),
        "pMVAST": _dec(_find_text(sub, "pMVAST", "0")),
        "pRedBCST": _dec(_find_text(sub, "pRedBCST", "0")),
        "vBCST": _dec(_find_text(sub, "vBCST", "0")),
        "pICMSST": _dec(_find_text(sub, "pICMSST", "0")),
        "vICMSST": _dec(_find_text(sub, "vICMSST", "0")),
        "vFCPST": _dec(_find_text(sub, "vFCPST", "0")),
        "vICMSSTRet": _dec(_find_text(sub, "vICMSSTRet", "0")),
    }


def parsear_nfe_entrada_xml(xml_bytes: bytes, *, nome_arquivo: str = "") -> dict[str, Any]:
    """Extrai cabeçalho, emitente (CRT), destinatário e itens completos de NF-e v4.00+."""
    root = _parse_xml_seguro(xml_bytes)
    inf_nfe = _find_descendant(root, "infNFe")
    if inf_nfe is None:
        raise XMLSegurancaError("Nó <infNFe> não encontrado no XML.")

    chave = re.sub(r"\D", "", inf_nfe.attrib.get("Id", ""))
    if len(chave) != 44:
        prot_ch = _find_text(_find_descendant(root, "infProt"), "chNFe")
        if prot_ch:
            chave = re.sub(r"\D", "", prot_ch)

    ide = _find_child(inf_nfe, "ide")
    emit = _find_child(inf_nfe, "emit")
    dest = _find_child(inf_nfe, "dest")
    ender_emit = _find_child(emit, "enderEmit")
    ender_dest = _find_child(dest, "enderDest")

    emit_crt = _find_text(emit, "CRT", "3")
    nota: dict[str, Any] = {
        "arquivo": nome_arquivo,
        "chave_acesso": chave,
        "nNF": _find_text(ide, "nNF"),
        "serie": _find_text(ide, "serie", "1"),
        "dhEmi": _find_text(ide, "dhEmi") or _find_text(ide, "dEmi"),
        "natOp": _find_text(ide, "natOp"),
        "finNFe": _find_text(ide, "finNFe", "1"),
        "idDest": _find_text(ide, "idDest", "1"),
        "emit_cnpj": re.sub(r"\D", "", _find_text(emit, "CNPJ") or _find_text(emit, "CPF")),
        "emit_nome": _find_text(emit, "xNome"),
        "emit_uf": _find_text(ender_emit, "UF").upper(),
        "emit_crt": emit_crt,
        "fornecedor_simples_nacional": emit_crt in {"1", "2"},
        "dest_cnpj": re.sub(r"\D", "", _find_text(dest, "CNPJ") or _find_text(dest, "CPF")),
        "dest_uf": _find_text(ender_dest, "UF").upper(),
        "dest_ind_ie_dest": _find_text(dest, "indIEDest", "1"),
        "xml_raw": xml_bytes.decode("utf-8", errors="replace"),
        "itens": [],
    }

    for idx, det in enumerate(inf_nfe, start=0):
        if _strip_ns(det.tag) != "det":
            continue
        n_item = int(det.attrib.get("nItem") or (len(nota["itens"]) + 1))
        prod = _find_child(det, "prod")
        imposto = _find_child(det, "imposto")

        icms_data = _extrair_grupo_icms(_find_child(imposto, "ICMS"))
        ipi_node = _find_descendant(_find_child(imposto, "IPI"), "IPITrib")
        v_ipi = _dec(_find_text(ipi_node, "vIPI", "0"))

        pis_node = _find_child(imposto, "PIS")
        pis_sub = next(iter(pis_node), None) if pis_node is not None else None
        cof_node = _find_child(imposto, "COFINS")
        cof_sub = next(iter(cof_node), None) if cof_node is not None else None

        g_ibscbs = _find_descendant(imposto, "gIBSCBS")

        nota["itens"].append(
            {
                "nItem": n_item,
                "cProd": _find_text(prod, "cProd"),
                "cEAN": _find_text(prod, "cEAN"),
                "xProd": _find_text(prod, "xProd"),
                "NCM": re.sub(r"\D", "", _find_text(prod, "NCM")),
                "CEST": re.sub(r"\D", "", _find_text(prod, "CEST")),
                "CFOP": re.sub(r"\D", "", _find_text(prod, "CFOP")),
                "uCom": _find_text(prod, "uCom"),
                "qCom": _dec(_find_text(prod, "qCom", "1")),
                "vProd": _dec(_find_text(prod, "vProd", "0")),
                "vFrete": _dec(_find_text(prod, "vFrete", "0")),
                "vSeg": _dec(_find_text(prod, "vSeg", "0")),
                "vOutro": _dec(_find_text(prod, "vOutro", "0")),
                "vDesc": _dec(_find_text(prod, "vDesc", "0")),
                "vIPI": v_ipi,
                "cBenef": _find_text(prod, "cBenef").upper(),
                "cst_pis": _find_text(pis_sub, "CST"),
                "vPIS": _dec(_find_text(pis_sub, "vPIS", "0")),
                "cst_cofins": _find_text(cof_sub, "CST"),
                "vCOFINS": _dec(_find_text(cof_sub, "vCOFINS", "0")),
                "tem_gibscbs": g_ibscbs is not None,
                **icms_data,
            }
        )

    return nota


def parsear_arquivos_entrada(arquivos: list[tuple[str, bytes]]) -> dict[str, Any]:
    """Processa múltiplos .xml ou .zip contendo NF-es de entrada com tratamento seguro."""
    notas: list[dict[str, Any]] = []
    erros: list[dict[str, str]] = []

    for nome, conteudo in arquivos:
        nome_low = nome.lower()
        if nome_low.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
                    for info in zf.infolist():
                        if info.is_dir() or not info.filename.lower().endswith(".xml"):
                            continue
                        if info.file_size > 20 * 1024 * 1024:
                            erros.append({"arquivo": info.filename, "erro": "Arquivo XML excede 20 MB no ZIP."})
                            continue
                        try:
                            notas.append(parsear_nfe_entrada_xml(zf.read(info.filename), nome_arquivo=info.filename))
                        except Exception as exc:
                            erros.append({"arquivo": info.filename, "erro": str(exc)})
            except zipfile.BadZipFile as exc:
                erros.append({"arquivo": nome, "erro": f"ZIP inválido: {exc}"})
        else:
            try:
                notas.append(parsear_nfe_entrada_xml(conteudo, nome_arquivo=nome))
            except Exception as exc:
                erros.append({"arquivo": nome, "erro": str(exc)})

    return {"notas": notas, "erros": erros}
