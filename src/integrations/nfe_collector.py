"""Coletor idempotente de XML NF-e e eventos SEFAZ (110111/110112)."""

from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET
from typing import Any


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _find_child(parent: ET.Element | None, name: str) -> ET.Element | None:
    if parent is None:
        return None
    for child in parent:
        if _local_name(child.tag) == name:
            return child
    return None


def _find_descendant(root: ET.Element, name: str) -> ET.Element | None:
    for el in root.iter():
        if _local_name(el.tag) == name:
            return el
    return None


def _text(parent: ET.Element | None, name: str, default: str = "") -> str:
    el = _find_child(parent, name)
    if el is not None and el.text is not None:
        return el.text.strip()
    return default


def _num(parent: ET.Element | None, name: str) -> float:
    val = _text(parent, name, "0")
    try:
        return float(val)
    except ValueError:
        return 0.0


def parsear_nfe_xml(xml_str: str) -> dict[str, Any]:
    """Extrai cabeçalho e itens de um XML de NF-e completo ou resumo resNFe."""
    root = ET.fromstring(xml_str)

    # Caso seja resumo resNFe
    if _local_name(root.tag) == "resNFe":
        chave = _text(root, "chNFe")
        return {
            "eh_xml_completo": 0,
            "cabecalho": {
                "chave_acesso": chave,
                "numero_nf": chave[25:34] if len(chave) == 44 else "",
                "serie": chave[22:25] if len(chave) == 44 else "",
                "modelo": chave[20:22] if len(chave) == 44 else "55",
                "finalidade": "1",
                "data_emissao": _text(root, "dhEmi"),
                "cnpj_emitente": _text(root, "CNPJ") or _text(root, "CPF"),
                "uf_emitente": "",
                "cnpj_destinatario": "",
                "uf_destinatario": "",
            },
            "itens": [],
        }

    inf_nfe = _find_descendant(root, "infNFe")
    if inf_nfe is None:
        raise ValueError("XML NF-e inválido: tag infNFe não encontrada.")

    chave = (inf_nfe.attrib.get("Id") or "").replace("NFe", "").strip()
    ide = _find_child(inf_nfe, "ide")
    emit = _find_child(inf_nfe, "emit")
    ender_emit = _find_child(emit, "enderEmit")
    dest = _find_child(inf_nfe, "dest")
    ender_dest = _find_child(dest, "enderDest")

    cabecalho = {
        "chave_acesso": chave,
        "numero_nf": _text(ide, "nNF"),
        "serie": _text(ide, "serie"),
        "modelo": _text(ide, "mod", "55"),
        "finalidade": _text(ide, "finNFe", "1"),
        "data_emissao": _text(ide, "dhEmi") or _text(ide, "dEmi"),
        "cnpj_emitente": _text(emit, "CNPJ") or _text(emit, "CPF"),
        "uf_emitente": _text(ender_emit, "UF"),
        "cnpj_destinatario": _text(dest, "CNPJ") or _text(dest, "CPF"),
        "uf_destinatario": _text(ender_dest, "UF"),
    }

    itens: list[dict[str, Any]] = []
    for child in inf_nfe:
        if _local_name(child.tag) != "det":
            continue
        n_item = int(child.attrib.get("nItem") or (len(itens) + 1))
        prod = _find_child(child, "prod")
        imposto = _find_child(child, "imposto")

        # ICMS (qualquer grupo ICMS00, ICMS10, ICMS20, ICMS60, ICMSSN102, etc.)
        icms_wrap = _find_child(imposto, "ICMS")
        icms_det = next(iter(icms_wrap), None) if icms_wrap is not None else None
        ipi_wrap = _find_child(imposto, "IPI")
        ipi_trib = _find_child(ipi_wrap, "IPITrib")
        pis_wrap = _find_child(imposto, "PIS")
        pis_det = next(iter(pis_wrap), None) if pis_wrap is not None else None
        cofins_wrap = _find_child(imposto, "COFINS")
        cofins_det = next(iter(cofins_wrap), None) if cofins_wrap is not None else None

        itens.append(
            {
                "numero_item": n_item,
                "codigo_produto": _text(prod, "cProd"),
                "descricao": _text(prod, "xProd"),
                "ncm": _text(prod, "NCM"),
                "cest": _text(prod, "CEST"),
                "origem_mercadoria": _text(icms_det, "orig", "0"),
                "cfop": _text(prod, "CFOP"),
                "cst_icms": _text(icms_det, "CST") or _text(icms_det, "CSOSN"),
                "valor_produto": _num(prod, "vProd"),
                "valor_ipi": _num(ipi_trib, "vIPI"),
                "bc_icms": _num(icms_det, "vBC"),
                "aliq_icms": _num(icms_det, "pICMS"),
                "valor_icms": _num(icms_det, "vICMS"),
                "mod_bc_st": _text(icms_det, "modBCST"),
                "mva_st": _num(icms_det, "pMVAST"),
                "red_bc_st": _num(icms_det, "pRedBCST"),
                "bc_st": _num(icms_det, "vBCST"),
                "aliq_st": _num(icms_det, "pICMSST"),
                "valor_st": _num(icms_det, "vICMSST"),
                "valor_fcp_st": _num(icms_det, "vFCPST"),
                "cst_pis": _text(pis_det, "CST"),
                "aliq_pis": _num(pis_det, "pPIS"),
                "cst_cofins": _text(cofins_det, "CST"),
                "aliq_cofins": _num(cofins_det, "pCOFINS"),
                "numero_fci": _text(prod, "nFCI") or None,
            }
        )

    return {"eh_xml_completo": 1, "cabecalho": cabecalho, "itens": itens}


def extrair_metadados_emitente_xml(xml_str: str) -> dict[str, str]:
    """Extrai CNPJ, razão social, CRT, UF, natureza da operação e perfil do destinatário."""
    root = ET.fromstring(xml_str)
    inf_nfe = _find_descendant(root, "infNFe")
    if inf_nfe is None:
        return {}
    ide = _find_child(inf_nfe, "ide")
    emit = _find_child(inf_nfe, "emit")
    ender_emit = _find_child(emit, "enderEmit")
    dest = _find_child(inf_nfe, "dest")
    ender_dest = _find_child(dest, "enderDest")

    ind_ie = _text(dest, "indIEDest", "1")
    tp_nf = _text(ide, "tpNF", "1")
    return {
        "chave_acesso": (inf_nfe.attrib.get("Id") or "").replace("NFe", "").strip(),
        "cnpj_emitente": _text(emit, "CNPJ") or _text(emit, "CPF"),
        "razao_emitente": _text(emit, "xNome"),
        "crt_emitente": _text(emit, "CRT", "3"),
        "uf_emitente": _text(ender_emit, "UF"),
        "cnpj_destinatario": _text(dest, "CNPJ") or _text(dest, "CPF"),
        "uf_destinatario": _text(ender_dest, "UF"),
        "nat_op": _text(ide, "natOp"),
        "tp_nf": tp_nf,
        "tipo_operacao_xml": "Entrada" if tp_nf == "0" else "Saída",
        "ind_ie_dest": ind_ie,
        "contribuinte_dest": "N" if ind_ie == "9" else "S",
    }


def registrar_evento_nfe(
    conn: sqlite3.Connection,
    *,
    chave_acesso: str,
    tipo_evento: str,
    data_evento: str,
    sequencia: int = 1,
    protocolo: str | None = None,
    auto_commit: bool = True,
) -> None:
    """Registra evento SEFAZ (ex.: 110111/110112) de forma idempotente via UPSERT."""
    conn.execute(
        """
        INSERT INTO nfe_eventos (chave_acesso, tipo_evento, sequencia, data_evento, protocolo)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(chave_acesso, tipo_evento, sequencia) DO UPDATE SET
            data_evento = excluded.data_evento,
            protocolo = COALESCE(excluded.protocolo, nfe_eventos.protocolo)
        """,
        (chave_acesso, tipo_evento, sequencia, data_evento, protocolo),
    )
    if auto_commit:
        conn.commit()


def ingerir_nfe_idempotente(
    conn: sqlite3.Connection,
    *,
    xml_str: str,
    cnpj_cursor: str | None = None,
    nsu: str | None = None,
    timestamp_cursor: int | None = None,
    eventos: list[dict[str, Any]] | None = None,
) -> str:
    """Ingere XML/resNFe idempotentemente (Itens+XML -> Cabeçalho -> Eventos -> Cursor)."""
    parsed = parsear_nfe_xml(xml_str)
    cab = parsed["cabecalho"]
    itens = parsed["itens"]
    eh_completo = int(parsed["eh_xml_completo"])
    chave = cab["chave_acesso"]

    with conn:
        # Cabeçalho + XML com precedência de xml_completo (1) sobre resNFe (0)
        conn.execute(
            """
            INSERT INTO nfe_documentos (
                chave_acesso, numero_nf, serie, modelo, finalidade, data_emissao,
                cnpj_emitente, uf_emitente, cnpj_destinatario, uf_destinatario,
                eh_xml_completo, xml_completo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chave_acesso) DO UPDATE SET
                numero_nf = CASE WHEN excluded.eh_xml_completo >= nfe_documentos.eh_xml_completo THEN excluded.numero_nf ELSE nfe_documentos.numero_nf END,
                serie = CASE WHEN excluded.eh_xml_completo >= nfe_documentos.eh_xml_completo THEN excluded.serie ELSE nfe_documentos.serie END,
                uf_emitente = CASE WHEN excluded.uf_emitente != '' THEN excluded.uf_emitente ELSE nfe_documentos.uf_emitente END,
                uf_destinatario = CASE WHEN excluded.uf_destinatario != '' THEN excluded.uf_destinatario ELSE nfe_documentos.uf_destinatario END,
                eh_xml_completo = MAX(nfe_documentos.eh_xml_completo, excluded.eh_xml_completo),
                xml_completo = CASE WHEN excluded.eh_xml_completo >= nfe_documentos.eh_xml_completo THEN excluded.xml_completo ELSE nfe_documentos.xml_completo END
            """,
            (
                chave,
                cab["numero_nf"],
                cab["serie"],
                cab["modelo"],
                cab["finalidade"],
                cab["data_emissao"],
                cab["cnpj_emitente"],
                cab["uf_emitente"],
                cab["cnpj_destinatario"],
                cab["uf_destinatario"],
                eh_completo,
                xml_str,
            ),
        )

        # Itens da NF-e (UPSERT idempotente)
        for item in itens:
            conn.execute(
                """
                INSERT INTO nfe_itens (
                    chave_acesso, numero_item, codigo_produto, descricao, ncm, cest,
                    origem_mercadoria, cfop, cst_icms, valor_produto, valor_ipi,
                    bc_icms, aliq_icms, valor_icms, mod_bc_st, mva_st, red_bc_st,
                    bc_st, aliq_st, valor_st, valor_fcp_st, cst_pis, aliq_pis,
                    cst_cofins, aliq_cofins, numero_fci
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chave_acesso, numero_item) DO UPDATE SET
                    codigo_produto = excluded.codigo_produto,
                    descricao = excluded.descricao,
                    ncm = excluded.ncm,
                    cest = excluded.cest,
                    origem_mercadoria = excluded.origem_mercadoria,
                    cfop = excluded.cfop,
                    cst_icms = excluded.cst_icms,
                    valor_produto = excluded.valor_produto,
                    valor_ipi = excluded.valor_ipi,
                    bc_icms = excluded.bc_icms,
                    aliq_icms = excluded.aliq_icms,
                    valor_icms = excluded.valor_icms,
                    mva_st = excluded.mva_st,
                    bc_st = excluded.bc_st,
                    aliq_st = excluded.aliq_st,
                    valor_st = excluded.valor_st,
                    valor_fcp_st = excluded.valor_fcp_st,
                    cst_pis = excluded.cst_pis,
                    aliq_pis = excluded.aliq_pis,
                    cst_cofins = excluded.cst_cofins,
                    aliq_cofins = excluded.aliq_cofins,
                    numero_fci = excluded.numero_fci
                """,
                (
                    chave,
                    item["numero_item"],
                    item["codigo_produto"],
                    item["descricao"],
                    item["ncm"],
                    item["cest"],
                    item["origem_mercadoria"],
                    item["cfop"],
                    item["cst_icms"],
                    item["valor_produto"],
                    item["valor_ipi"],
                    item["bc_icms"],
                    item["aliq_icms"],
                    item["valor_icms"],
                    item["mod_bc_st"],
                    item["mva_st"],
                    item["red_bc_st"],
                    item["bc_st"],
                    item["aliq_st"],
                    item["valor_st"],
                    item["valor_fcp_st"],
                    item["cst_pis"],
                    item["aliq_pis"],
                    item["cst_cofins"],
                    item["aliq_cofins"],
                    item["numero_fci"],
                ),
            )

        # Eventos (110111 / 110112)
        for ev in eventos or []:
            registrar_evento_nfe(
                conn,
                chave_acesso=chave,
                tipo_evento=str(ev["tipo_evento"]),
                data_evento=str(ev["data_evento"]),
                sequencia=int(ev.get("sequencia", 1)),
                protocolo=ev.get("protocolo"),
                auto_commit=False,
            )

    # Cursor salvo somente após o commit da transação acima
    if cnpj_cursor and (nsu is not None or timestamp_cursor is not None):
        with conn:
            conn.execute(
                """
                INSERT INTO nfe_sync_cursor (cnpj_emp, ultimo_nsu, ultimo_timestamp, atualizado_em)
                VALUES (?, ?, ?, datetime('now'))
                ON CONFLICT(cnpj_emp) DO UPDATE SET
                    ultimo_nsu = COALESCE(excluded.ultimo_nsu, nfe_sync_cursor.ultimo_nsu),
                    ultimo_timestamp = MAX(nfe_sync_cursor.ultimo_timestamp, excluded.ultimo_timestamp),
                    atualizado_em = datetime('now')
                """,
                (cnpj_cursor, nsu or "000000000000000", int(timestamp_cursor or 0)),
            )

    return chave
