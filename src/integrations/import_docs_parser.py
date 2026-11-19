"""Parsers idempotentes para DUIMP (JSON/XML), DI (XML/PDF) e NF-e de Entrada (CFOP 3.xxx)."""

from __future__ import annotations

import io
import json
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Any

import openpyxl

from src.engine.import_engine import ContextoImportacaoDireta, calcular_importacao_direta
from src.integrations.microvix_conciliador import sanitizar_celula_planilha


class ImportacaoDocError(ValueError):
    """Erro de parsing ou segurança em documento de comércio exterior."""


def _validar_xml_seguro(conteudo: bytes) -> ET.Element:
    txt = conteudo.decode("utf-8-sig", errors="replace")
    if "<!DOCTYPE" in txt.upper() or "<!ENTITY" in txt.upper():
        raise ImportacaoDocError("XML bloqueado por conter declaração DOCTYPE/ENTITY (proteção XXE).")
    try:
        return ET.fromstring(txt)
    except ET.ParseError as exc:
        raise ImportacaoDocError(f"XML inválido: {exc}") from exc


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _find_text(elem: ET.Element | None, *nomes: str, default: str = "") -> str:
    if elem is None:
        return default
    alvo = set(nomes)
    for node in elem.iter():
        if _strip_ns(node.tag) in alvo and node.text is not None:
            return node.text.strip()
    return default


def _dec(val: Any, default: str = "0") -> Decimal:
    if val is None or val == "":
        return Decimal(default)
    if isinstance(val, Decimal):
        return val
    s = str(val).strip().replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return Decimal(default)


def parsear_duimp(conteudo: bytes) -> dict[str, Any]:
    """Extrai cabeçalho e itens/tributos de DUIMP em JSON ou XML do Portal Único Siscomex."""
    txt = conteudo.decode("utf-8-sig", errors="replace").strip()
    if txt.startswith("{") or txt.startswith("["):
        data = json.loads(txt)
        if isinstance(data, list):
            data = data[0] if data else {}
        ident = data.get("identificacao") or data
        numero = str(ident.get("numero") or data.get("numeroDuimp") or "DUIMP-000")
        data_reg = str(ident.get("dataRegistro") or data.get("dataRegistro") or "2026-01-01")[:10]
        uf_des = str(data.get("ufDesembaraco") or ident.get("ufDesembaraco") or "SP").upper()[:2]
        uf_dest = str(data.get("ufDestino") or uf_des).upper()[:2]
        despesas = data.get("despesasAduaneiras") or {}
        siscomex = float(_dec(despesas.get("taxaSiscomex") or data.get("taxaSiscomex") or 0))
        afrmm = float(_dec(despesas.get("afrmm") or data.get("afrmm") or 0))
        outras = float(_dec(despesas.get("outras") or data.get("outrasDespesas") or 0))

        itens_raw = data.get("itens") or data.get("adicoes") or []
        itens: list[dict[str, Any]] = []
        cif_total = Decimal("0")
        for idx, it in enumerate(itens_raw, start=1):
            merc = it.get("mercadoria") or it
            trib = it.get("tributos") or it
            ncm = re.sub(r"\D", "", str(merc.get("ncm") or it.get("ncm") or "")).zfill(8)[:8]
            cif = _dec(merc.get("valorAduaneiro") or it.get("valorAduaneiro") or it.get("valorCif") or 0)
            cif_total += cif
            itens.append(
                {
                    "numero_adicao": str(it.get("numeroAdicao") or f"{idx:03d}"),
                    "numero_item": int(it.get("numeroItem") or idx),
                    "ncm": ncm,
                    "cest": re.sub(r"\D", "", str(merc.get("cest") or it.get("cest") or "")),
                    "descricao": str(merc.get("descricao") or it.get("descricao") or f"Item {idx}"),
                    "valor_aduaneiro": float(cif),
                    "ii_declarado": float(_dec(trib.get("ii") or it.get("valorII") or 0)),
                    "ipi_declarado": float(_dec(trib.get("ipi") or it.get("valorIPI") or 0)),
                    "pis_imp_declarado": float(_dec(trib.get("pis") or it.get("valorPIS") or 0)),
                    "cofins_imp_declarado": float(_dec(trib.get("cofins") or it.get("valorCOFINS") or 0)),
                    "bc_icms_declarada": float(_dec(trib.get("bcIcms") or 0)),
                    "icms_declarado": float(_dec(trib.get("icms") or 0)),
                    "origem_declarada": str(it.get("origem") or "1"),
                    "cfop_declarado": str(it.get("cfop") or "3.102"),
                    "cst_declarado": str(it.get("cst") or "00"),
                }
            )
        return {
            "tipo_documento": "DUIMP",
            "numero_documento": numero,
            "data_registro": data_reg,
            "uf_desembaraco": uf_des,
            "uf_destino": uf_dest,
            "taxa_cambio": float(_dec(data.get("taxaCambio") or 1)),
            "valor_aduaneiro_total": float(cif_total),
            "siscomex_total": siscomex,
            "afrmm_total": afrmm,
            "outras_despesas_total": outras,
            "itens": itens,
        }

    # XML DUIMP
    root = _validar_xml_seguro(conteudo)
    numero = _find_text(root, "numero", "numeroDuimp", default="DUIMP-XML")
    data_reg = _find_text(root, "dataRegistro", default="2026-01-01")[:10]
    uf_des = _find_text(root, "ufDesembaraco", default="SP").upper()[:2]
    itens = []
    cif_total = Decimal("0")
    for idx, node in enumerate(root.iter(), start=1):
        if _strip_ns(node.tag) in {"item", "adicao"}:
            ncm = re.sub(r"\D", "", _find_text(node, "ncm"))
            if len(ncm) != 8:
                continue
            cif = _dec(_find_text(node, "valorAduaneiro", "valorCif", default="0"))
            cif_total += cif
            itens.append(
                {
                    "numero_adicao": _find_text(node, "numeroAdicao", default=f"{len(itens)+1:03d}"),
                    "numero_item": len(itens) + 1,
                    "ncm": ncm,
                    "cest": "",
                    "descricao": _find_text(node, "descricao", default=f"Item {len(itens)+1}"),
                    "valor_aduaneiro": float(cif),
                    "ii_declarado": float(_dec(_find_text(node, "ii", "valorII", default="0"))),
                    "ipi_declarado": float(_dec(_find_text(node, "ipi", "valorIPI", default="0"))),
                    "pis_imp_declarado": float(_dec(_find_text(node, "pis", "valorPIS", default="0"))),
                    "cofins_imp_declarado": float(_dec(_find_text(node, "cofins", "valorCOFINS", default="0"))),
                    "bc_icms_declarada": 0.0,
                    "icms_declarado": 0.0,
                    "origem_declarada": "1",
                    "cfop_declarado": "3.102",
                    "cst_declarado": "00",
                }
            )
    return {
        "tipo_documento": "DUIMP",
        "numero_documento": numero,
        "data_registro": data_reg,
        "uf_desembaraco": uf_des,
        "uf_destino": uf_des,
        "taxa_cambio": float(_dec(_find_text(root, "taxaCambio", default="1"))),
        "valor_aduaneiro_total": float(cif_total),
        "siscomex_total": float(_dec(_find_text(root, "taxaSiscomex", default="0"))),
        "afrmm_total": float(_dec(_find_text(root, "afrmm", default="0"))),
        "outras_despesas_total": 0.0,
        "itens": itens,
    }


def parsear_di_xml(conteudo: bytes) -> dict[str, Any]:
    """Extrai <declaracaoImportacao>, <adicao> e <mercadoria> do XML oficial da DI (Siscomex)."""
    root = _validar_xml_seguro(conteudo)
    numero = _find_text(root, "numeroDI", "numeroDi", default="DI-000")
    data_reg = _find_text(root, "dataRegistro", default="2026-01-01")[:10]
    uf_des = _find_text(root, "urfDespachoCodigoUF", "ufDesembaraco", "ufImportador", default="SP").upper()[:2]
    siscomex = float(_dec(_find_text(root, "taxaSiscomexValor", "valorTaxaSiscomex", default="0")))
    afrmm = float(_dec(_find_text(root, "afrmmValor", "valorAfrmm", default="0")))

    adicoes = [n for n in root.iter() if _strip_ns(n.tag) == "adicao"]
    itens: list[dict[str, Any]] = []
    cif_total = Decimal("0")
    for idx, ad in enumerate(adicoes, start=1):
        ncm = re.sub(r"\D", "", _find_text(ad, "dadosMercadoriaCodigoNcm", "codigoNcm", "ncm")).zfill(8)[:8]
        cif = _dec(_find_text(ad, "condicaoVendaValorReais", "valorAduaneiroReais", "valorReais", default="0"))
        if cif == Decimal("0"):
            cif = _dec(_find_text(ad, "dadosMercadoriaValorTotalReais", default="0"))
        cif_total += cif
        itens.append(
            {
                "numero_adicao": _find_text(ad, "numeroAdicao", default=f"{idx:03d}"),
                "numero_item": idx,
                "ncm": ncm,
                "cest": "",
                "descricao": _find_text(ad, "descricaoMercadoria", "xProd", default=f"Adição {idx}"),
                "valor_aduaneiro": float(cif),
                "ii_declarado": float(_dec(_find_text(ad, "iiAliquotaValorRecolher", "valorII", default="0"))),
                "ipi_declarado": float(_dec(_find_text(ad, "ipiAliquotaValorRecolher", "valorIPI", default="0"))),
                "pis_imp_declarado": float(_dec(_find_text(ad, "pisPasepAliquotaValorRecolher", "valorPIS", default="0"))),
                "cofins_imp_declarado": float(_dec(_find_text(ad, "cofinsAliquotaValorRecolher", "valorCOFINS", default="0"))),
                "bc_icms_declarada": 0.0,
                "icms_declarado": 0.0,
                "origem_declarada": "1",
                "cfop_declarado": "3.102",
                "cst_declarado": "00",
            }
        )

    return {
        "tipo_documento": "DI_XML",
        "numero_documento": numero,
        "data_registro": data_reg,
        "uf_desembaraco": uf_des,
        "uf_destino": uf_des,
        "taxa_cambio": float(_dec(_find_text(root, "taxaCambio", default="1"))),
        "valor_aduaneiro_total": float(cif_total),
        "siscomex_total": siscomex,
        "afrmm_total": afrmm,
        "outras_despesas_total": 0.0,
        "itens": itens,
    }


def parsear_di_pdf(conteudo: bytes) -> dict[str, Any]:
    """Extrai dados principais de Extrato PDF da DI / Comprovante de Importação."""
    texto = ""
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(io.BytesIO(conteudo))
        texto = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        texto = conteudo.decode("latin-1", errors="ignore")

    m_di = re.search(r"(?:DI|Declara[çc][ãa]o)\s*(?:n[º°]?|:)?\s*(\d{2}/\d{7}-\d|\d{10})", texto, re.I)
    numero = m_di.group(1) if m_di else "DI-PDF-001"
    ncms = re.findall(r"\b(\d{4}\.?\d{2}\.?\d{2})\b", texto)
    ncms_limpos = [re.sub(r"\D", "", n) for n in ncms if len(re.sub(r"\D", "", n)) == 8]
    if not ncms_limpos:
        ncms_limpos = ["85171300"]

    m_cif = re.search(r"Valor\s+Aduaneiro[^\d]*([\d\.,]+)", texto, re.I)
    cif_val = float(_dec(m_cif.group(1).replace(".", "").replace(",", ".") if m_cif else "1000.00"))
    itens = [
        {
            "numero_adicao": f"{idx:03d}",
            "numero_item": idx,
            "ncm": ncm,
            "cest": "",
            "descricao": f"Adição PDF {idx} ({ncm})",
            "valor_aduaneiro": round(cif_val / len(ncms_limpos), 2),
            "ii_declarado": 0.0,
            "ipi_declarado": 0.0,
            "pis_imp_declarado": 0.0,
            "cofins_imp_declarado": 0.0,
            "bc_icms_declarada": 0.0,
            "icms_declarado": 0.0,
            "origem_declarada": "1",
            "cfop_declarado": "3.102",
            "cst_declarado": "00",
        }
        for idx, ncm in enumerate(dict.fromkeys(ncms_limpos), start=1)
    ]
    return {
        "tipo_documento": "DI_PDF",
        "numero_documento": numero,
        "data_registro": "2026-01-01",
        "uf_desembaraco": "SP",
        "uf_destino": "SP",
        "taxa_cambio": 1.0,
        "valor_aduaneiro_total": cif_val,
        "siscomex_total": 0.0,
        "afrmm_total": 0.0,
        "outras_despesas_total": 0.0,
        "itens": itens,
    }


def parsear_nfe_entrada_importacao_xml(conteudo: bytes) -> dict[str, Any]:
    """Audita XML de NF-e de Entrada (CFOP 3.xxx), grupos <DI> e <adi>, base por dentro e rateio."""
    root = _validar_xml_seguro(conteudo)
    chave = _find_text(root, "chNFe", default="NFE-IMP-000")
    if chave == "NFE-IMP-000":
        inf = next((n for n in root.iter() if _strip_ns(n.tag) == "infNFe"), None)
        if inf is not None and inf.attrib.get("Id"):
            chave = inf.attrib["Id"].replace("NFe", "")
    data_em = _find_text(root, "dhEmi", "dEmi", default="2026-01-01")[:10]
    uf_des = _find_text(root, "UFDesemb", "UF", default="SP").upper()[:2]

    itens: list[dict[str, Any]] = []
    cif_total = Decimal("0")
    afrmm_total = Decimal("0")
    for idx, det in enumerate((n for n in root.iter() if _strip_ns(n.tag) == "det"), start=1):
        prod = next((c for c in det if _strip_ns(c.tag) == "prod"), None)
        imp = next((c for c in det if _strip_ns(c.tag) == "imposto"), None)
        ncm = re.sub(r"\D", "", _find_text(prod, "NCM")).zfill(8)[:8]
        cfop = _find_text(prod, "CFOP", default="3102")
        vprod = _dec(_find_text(prod, "vProd", default="0"))
        vafrmm = _dec(_find_text(prod, "vAFRMM", default="0"))
        afrmm_total += vafrmm
        cif_total += vprod

        origem = _find_text(imp, "orig", default="1")
        cst_icms = _find_text(imp, "CST", default="00")
        bc_icms = _dec(_find_text(imp, "vBC", default="0"))
        v_icms = _dec(_find_text(imp, "vICMS", default="0"))
        v_ii = _dec(_find_text(imp, "vII", default="0"))
        v_ipi = _dec(_find_text(imp, "vIPI", default="0"))
        v_pis = _dec(_find_text(imp, "vPIS", default="0"))
        v_cof = _dec(_find_text(imp, "vCOFINS", default="0"))

        itens.append(
            {
                "numero_adicao": _find_text(prod, "nAdicao", default=f"{idx:03d}"),
                "numero_item": int(det.attrib.get("nItem") or idx),
                "ncm": ncm,
                "cest": re.sub(r"\D", "", _find_text(prod, "CEST")),
                "descricao": _find_text(prod, "xProd", default=f"Item {idx}"),
                "valor_aduaneiro": float(vprod),
                "ii_declarado": float(v_ii),
                "ipi_declarado": float(v_ipi),
                "pis_imp_declarado": float(v_pis),
                "cofins_imp_declarado": float(v_cof),
                "bc_icms_declarada": float(bc_icms),
                "icms_declarado": float(v_icms),
                "origem_declarada": origem,
                "cfop_declarado": cfop,
                "cst_declarado": cst_icms,
                "ndi": _find_text(prod, "nDI"),
                "uf_desemb_di": _find_text(prod, "UFDesemb", default=uf_des),
            }
        )

    return {
        "tipo_documento": "NFE_ENTRADA_3XXX",
        "numero_documento": chave,
        "data_registro": data_em,
        "uf_desembaraco": uf_des,
        "uf_destino": uf_des,
        "taxa_cambio": 1.0,
        "valor_aduaneiro_total": float(cif_total),
        "siscomex_total": 0.0,
        "afrmm_total": float(afrmm_total),
        "outras_despesas_total": float(_dec(_find_text(root, "vOutro", default="0"))),
        "itens": itens,
    }


def parsear_documento_importacao_auto(nome_arquivo: str, conteudo: bytes) -> dict[str, Any]:
    """Detecta automaticamente o tipo (DUIMP JSON/XML, DI XML/PDF, NF-e Entrada 3.xxx XML) e faz o parsing."""
    nome_l = nome_arquivo.lower()
    if nome_l.endswith(".json"):
        return parsear_duimp(conteudo)
    if nome_l.endswith(".pdf"):
        return parsear_di_pdf(conteudo)
    txt = conteudo.decode("utf-8-sig", errors="replace")
    if "<nfeProc" in txt or "<NFe" in txt or "<infNFe" in txt:
        return parsear_nfe_entrada_importacao_xml(conteudo)
    if "<declaracaoImportacao" in txt or "<numeroDI" in txt:
        return parsear_di_xml(conteudo)
    return parsear_duimp(conteudo)


def auditar_documento_importacao(
    doc: dict[str, Any],
    *,
    regras_por_ncm: dict[str, dict[str, Any]] | None = None,
    uf_destino: str | None = None,
) -> dict[str, Any]:
    """Confronta item a item o documento importado com o cálculo oficial da lei."""
    regras_map = regras_por_ncm or {}
    itens = doc.get("itens") or []
    cif_total = sum(_dec(it.get("valor_aduaneiro")) for it in itens) or Decimal("1")
    siscomex_tot = _dec(doc.get("siscomex_total"))
    afrmm_tot = _dec(doc.get("afrmm_total"))
    outras_tot = _dec(doc.get("outras_despesas_total"))
    uf_des = str(doc.get("uf_desembaraco") or "SP").upper()[:2]
    uf_dest = str(uf_destino or doc.get("uf_destino") or uf_des).upper()[:2]

    auditados: list[dict[str, Any]] = []
    status_geral = "OK"

    for it in itens:
        ncm = str(it.get("ncm") or "")
        regra = regras_map.get(ncm)
        cif_it = _dec(it.get("valor_aduaneiro"))
        fator = cif_it / cif_total if cif_total > 0 else Decimal("0")

        ctx = ContextoImportacaoDireta(
            ncm=ncm,
            cest=str(it.get("cest") or (regra or {}).get("cest") or ""),
            uf_desembaraco=uf_des,
            uf_destino=uf_dest,
            sem_similar_nacional_camex=bool((regra or {}).get("sem_similar_nacional_camex", False)),
            valor_aduaneiro_cif=cif_it,
            taxa_siscomex=(siscomex_tot * fator),
            afrmm=(afrmm_tot * fator),
            outras_despesas_aduaneiras=(outras_tot * fator),
            aliquota_ii=_dec((regra or {}).get("aliquota_ii"), "0"),
            aliquota_ipi=_dec((regra or {}).get("aliquota_ipi"), "0"),
            aliquota_pis_imp=_dec((regra or {}).get("aliquota_pis_imp"), "2.10"),
            aliquota_cofins_imp=_dec((regra or {}).get("aliquota_cofins_imp"), "9.65"),
            adicional_cofins_imp=_dec((regra or {}).get("adicional_cofins_imp"), "1.00"),
            aliquota_icms_interna=_dec(regra["aliquota_icms_interna"]) if regra and regra.get("aliquota_icms_interna") is not None else None,
            aliquota_fcp=_dec(regra["aliquota_fcp"]) if regra and regra.get("aliquota_fcp") is not None else None,
            tem_st=bool((regra or {}).get("tem_st", False)),
            mva_original_st=_dec((regra or {}).get("mva_original_st"), "0"),
        )
        calc = calcular_importacao_direta(ctx)
        divs: list[str] = []

        if regra is None:
            divs.append("SEM_REGRA: NCM sem regra TEC/CAMEX cadastrada em regras_importacao_ncm (aplicada alíquota padrão).")
            st_item = "SEM_REGRA"
        else:
            st_item = "OK"

        # Confronto II, IPI, PIS, COFINS e Base ICMS Por Dentro (quando declarados > 0)
        tol = Decimal("1.00")
        for campo_doc, campo_lei, label in [
            ("ii_declarado", "valor_ii", "II"),
            ("ipi_declarado", "valor_ipi", "IPI"),
            ("pis_imp_declarado", "valor_pis_imp", "PIS-Importação"),
            ("cofins_imp_declarado", "valor_cofins_imp", "COFINS-Importação"),
            ("bc_icms_declarada", "base_icms_por_dentro", "Base ICMS Por Dentro"),
            ("icms_declarado", "valor_icms_importacao", "ICMS-Importação"),
        ]:
            v_doc = _dec(it.get(campo_doc))
            v_lei = _dec(calc.get(campo_lei))
            if v_doc > 0 and abs(v_doc - v_lei) > tol:
                divs.append(f"{label}: declarado R$ {v_doc:.2f} vs esperado pela lei R$ {v_lei:.2f}")
                st_item = "DIVERGENTE"

        orig_doc = str(it.get("origem_declarada") or "1")
        if orig_doc != calc["origem_entrada"] and doc.get("tipo_documento") == "NFE_ENTRADA_3XXX":
            divs.append(f"Origem: declarada '{orig_doc}' vs esperada '{calc['origem_entrada']}' (CAMEX)")
            st_item = "DIVERGENTE"

        if st_item == "DIVERGENTE":
            status_geral = "DIVERGENTE"
        elif st_item == "SEM_REGRA" and status_geral == "OK":
            status_geral = "SEM_REGRA"

        auditados.append(
            {
                "Adição": it.get("numero_adicao"),
                "Item": it.get("numero_item"),
                "NCM": ncm,
                "Descrição": it.get("descricao"),
                "CIF (R$)": calc["valor_aduaneiro_cif"],
                "II Doc": f"{_dec(it.get('ii_declarado')):.2f}",
                "II Lei": calc["valor_ii"],
                "IPI Doc": f"{_dec(it.get('ipi_declarado')):.2f}",
                "IPI Lei": calc["valor_ipi"],
                "PIS Imp Lei": calc["valor_pis_imp"],
                "COFINS Imp Lei": calc["valor_cofins_imp"],
                "BC ICMS Por Dentro": calc["base_icms_por_dentro"],
                "ICMS Imp Lei": calc["valor_icms_importacao"],
                "Origem Lei": calc["origem_entrada"],
                "CFOP Entrada": calc["cfop_entrada"],
                "CST Entrada": calc["cst_icms_entrada"],
                "Saída Inter %": calc["aliquota_saida_interestadual"],
                "Status": st_item,
                "Divergências": " | ".join(divs) if divs else "Conforme legislação",
            }
        )

    return {
        "numero_documento": doc.get("numero_documento"),
        "tipo_documento": doc.get("tipo_documento"),
        "status_conciliacao": status_geral,
        "itens_auditados": auditados,
    }


def exportar_espelho_importacao_xlsx(itens_auditados: list[dict[str, Any]]) -> bytes:
    """Exporta o Espelho Conferido de Importação / NF-e de Entrada 3.xxx em .xlsx."""
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(title="Espelho_Importacao_3xxx")
    if itens_auditados:
        cols = list(itens_auditados[0].keys())
        ws.append(cols)
        for row in itens_auditados:
            ws.append([sanitizar_celula_planilha(row.get(c, "")) for c in cols])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
