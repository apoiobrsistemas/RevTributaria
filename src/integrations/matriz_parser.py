"""Parser de matriz tributária Linx e importador de planilhas ERP."""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import openpyxl


def separar_origem_cst(cst_icms_fiscal: str | None) -> tuple[str, str]:
    """Separa origem e CST/CSOSN de formatos como '5.60', '0.00' ou '560'."""
    bruto = (cst_icms_fiscal or "").strip()
    if not bruto:
        return "", ""

    if "." in bruto:
        partes = bruto.split(".", 1)
        origem = re.sub(r"\D", "", partes[0])[:1]
        cst = re.sub(r"\D", "", partes[1])
        return origem, cst

    digitos = re.sub(r"\D", "", bruto)
    if len(digitos) in (3, 4):
        return digitos[0], digitos[1:]
    return "", digitos


def identificar_perna_operacao(cfop: str | None, descricao_perna: str = "") -> str:
    """Identifica a perna da matriz: VENDA_CONSUMIDOR (5.102 / <UF> NC) ou COMPRA_FORNECEDOR (1.102 / MG CO)."""
    cfop_limpo = re.sub(r"\D", "", cfop or "")
    desc_upper = (descricao_perna or "").upper()

    if cfop_limpo in {"5102", "5101", "5405", "5403"} or re.search(r"\b[A-Z]{2}\s+NC\b", desc_upper):
        return "VENDA_CONSUMIDOR"
    if cfop_limpo in {"1102", "1101", "2102", "2101", "1403", "2403"} or re.search(
        r"\b[A-Z]{2}\s+CO\b", desc_upper
    ):
        return "COMPRA_FORNECEDOR"
    return "OUTRA"


def parsear_config_tributaria_linx(registros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normaliza registros de LinxConfiguracoesTributariasDetalhes."""
    resultado: list[dict[str, Any]] = []
    for reg in registros:
        cst_fiscal = str(reg.get("cst_icms_fiscal") or reg.get("cst_icms") or "")
        origem, cst = separar_origem_cst(cst_fiscal)
        cfop = str(reg.get("cfop") or "")
        desc_perna = str(
            reg.get("descricao_perna")
            or reg.get("natureza_operacao")
            or reg.get("uf_operacao")
            or ""
        )
        resultado.append(
            {
                "empresa": str(reg.get("empresa") or ""),
                "id_config_tributaria": str(
                    reg.get("id_config_tributaria") or reg.get("id_config") or ""
                ),
                "cfop": re.sub(r"\D", "", cfop),
                "uf_operacao": str(reg.get("uf_operacao") or reg.get("uf") or "").upper(),
                "cst_icms_fiscal": cst_fiscal,
                "origem_separada": origem,
                "cst_separado": cst,
                "tipo_operacao_perna": identificar_perna_operacao(cfop, desc_perna),
                "timestamp_linx": int(reg.get("timestamp") or 0),
                "payload_json": json.dumps(reg, ensure_ascii=False),
            }
        )
    return resultado


def _ler_planilha_bytes(conteudo: bytes, extensao: str) -> list[dict[str, Any]]:
    ext = extensao.lower()
    if ext == ".csv":
        texto = conteudo.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(texto), delimiter=";")
        linhas = list(reader)
        if linhas and len(linhas[0]) == 1 and "," in next(iter(linhas[0].keys())):
            reader = csv.DictReader(io.StringIO(texto), delimiter=",")
            linhas = list(reader)
        return [dict(r) for r in linhas]

    wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    try:
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header_raw = next(it, None)
        if not header_raw:
            return []
        headers = [str(h).strip() if h is not None else f"col_{i}" for i, h in enumerate(header_raw)]
        rows: list[dict[str, Any]] = []
        for row in it:
            if not any(v is not None and str(v).strip() for v in row):
                continue
            rows.append(
                {
                    headers[i]: ("" if i >= len(row) or row[i] is None else row[i])
                    for i in range(len(headers))
                }
            )
        return rows
    finally:
        wb.close()


def _pick(row: dict[str, Any], *chaves: str, default: str = "") -> str:
    lower_map = {k.strip().lower(): v for k, v in row.items()}
    for chave in chaves:
        val = lower_map.get(chave.lower())
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return default


def importar_planilha_matriz_erp(
    conn: sqlite3.Connection,
    fonte: str | Path | bytes,
    *,
    lote_importacao: str,
    extensao: str = ".xlsx",
) -> int:
    """Importa planilha/exportação de matriz tributária do ERP para config_erp_importada."""
    if isinstance(fonte, (str, Path)):
        caminho = Path(fonte)
        conteudo = caminho.read_bytes()
        ext = caminho.suffix or extensao
    else:
        conteudo = fonte
        ext = extensao

    linhas = _ler_planilha_bytes(conteudo, ext)
    inseridas = 0
    with conn:
        for row in linhas:
            ncm = re.sub(r"\D", "", _pick(row, "ncm", "cod_ncm"))
            if not ncm:
                continue
            cest = re.sub(r"\D", "", _pick(row, "cest"))
            uf_origem = _pick(row, "uf_origem", "uf_emitente", default="SP").upper()
            uf_destino = _pick(row, "uf_destino", "uf_operacao", "uf", default=uf_origem).upper()
            natureza = _pick(row, "natureza_operacao", "operacao", default="VENDA").upper()
            cod_prod = _pick(row, "codigo_produto_erp", "cod_produto", "codigo_produto")

            conn.execute(
                """
                INSERT INTO config_erp_importada (
                    lote_importacao, codigo_produto_erp, ncm, cest,
                    uf_origem, uf_destino, natureza_operacao, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lote_importacao,
                    cod_prod,
                    ncm,
                    cest,
                    uf_origem,
                    uf_destino,
                    natureza,
                    json.dumps(row, ensure_ascii=False, default=str),
                ),
            )
            inseridas += 1
    return inseridas
