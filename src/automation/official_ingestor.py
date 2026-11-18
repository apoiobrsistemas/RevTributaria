"""Ingestores determinísticos (Zero IA) de bases oficiais abertas (.gov.br)."""

from __future__ import annotations

import io
import json
import re
import sqlite3
from html.parser import HTMLParser
from typing import Any

import openpyxl

from src.legislation.parsers import extrair_linhas_tipi_xlsx
from src.legislation.url_guard import validar_url_oficial

URL_SISCOMEX_NCM_JSON = (
    "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"
)
URL_TIPI_RFB = (
    "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/legislacao/documentos-e-arquivos/tipi.xlsx"
)
URL_CONFAZ_142_18 = (
    "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18"
)
URL_CONFAZ_52_91 = (
    "https://www.confaz.fazenda.gov.br/legislacao/convenios/1991/CV052_91"
)
URL_NFE_PORTAL = "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=Iy/5Qol1YbE="
URL_SVRS_CLASSTRIB_API = "https://cff.svrs.rs.gov.br/api/v1/consultas/classTrib"
URL_SISCOMEX_TABX_API = "https://portalunico.siscomex.gov.br/tabx/api/publico/tabelas"


def _so_digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def descobrir_pares_ncm_cest(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Extrai pares únicos (ncm, cest) ativos de LinxProdutos + nfe_itens autorizadas."""
    pares: set[tuple[str, str]] = set()

    # 1. LinxProdutos ativos (desativado != 'S')
    rows_linx = conn.execute(
        "SELECT ncm, cest, payload_json FROM linx_produtos"
    ).fetchall()
    for row in rows_linx:
        payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        if str(payload.get("desativado") or "N").strip().upper() == "S":
            continue
        ncm = _so_digitos(row["ncm"])
        cest = _so_digitos(row["cest"])
        if len(ncm) == 8 and ncm != "00000000":
            pares.add((ncm, cest))

    # 2. Itens de NF-e autorizadas (não complementares finNFe != '2')
    rows_nfe = conn.execute(
        """
        SELECT i.ncm, i.cest
        FROM nfe_itens i
        JOIN vw_nfe_status s ON s.chave_acesso = i.chave_acesso
        WHERE s.status_sefaz = 'AUTORIZADA'
          AND s.finalidade != '2'
          AND i.ncm != '00000000'
        """
    ).fetchall()
    for row in rows_nfe:
        ncm = _so_digitos(row["ncm"])
        cest = _so_digitos(row["cest"])
        if len(ncm) == 8 and ncm != "00000000":
            pares.add((ncm, cest))

    # 3. Regras estaduais ativas já cadastradas/importadas via planilha
    rows_est = conn.execute(
        "SELECT ncm, cest FROM regras_estaduais_icms WHERE status_registro = 'ATIVA' AND ncm != ''"
    ).fetchall()
    for row in rows_est:
        ncm = _so_digitos(row["ncm"])
        cest = _so_digitos(row["cest"])
        if len(ncm) == 8 and ncm != "00000000":
            pares.add((ncm, cest))

    return sorted(pares)


class _HTMLTableParser(HTMLParser):
    """Extrai linhas de tabelas HTML sem dependências externas."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._cur_table: list[list[str]] = []
        self._cur_row: list[str] = []
        self._cur_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "table":
            self._in_table = True
            self._cur_table = []
        elif t == "tr" and self._in_table:
            self._in_row = True
            self._cur_row = []
        elif t in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._cur_cell = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in {"td", "th"} and self._in_cell:
            self._in_cell = False
            self._cur_row.append(re.sub(r"\s+", " ", "".join(self._cur_cell)).strip())
        elif t == "tr" and self._in_row:
            self._in_row = False
            if any(self._cur_row):
                self._cur_table.append(self._cur_row)
        elif t == "table" and self._in_table:
            self._in_table = False
            if self._cur_table:
                self.tables.append(self._cur_table)

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cur_cell.append(data)


def parsear_siscomex_ncm_json(conteudo_bytes: bytes) -> list[dict[str, str]]:
    """Parseia o JSON oficial de Nomenclatura NCM do Portal Único Siscomex."""
    dados = json.loads(conteudo_bytes.decode("utf-8-sig"))
    itens = dados.get("Nomenclaturas", dados if isinstance(dados, list) else [])
    resultado: list[dict[str, str]] = []
    for item in itens:
        ncm = _so_digitos(item.get("Codigo"))
        if len(ncm) != 8:
            continue
        resultado.append(
            {
                "ncm": ncm,
                "descricao": str(item.get("Descricao") or "").strip(),
                "vigencia_inicio": _normalizar_data_br(str(item.get("Data_Inicio") or "2026-01-01")),
                "vigencia_fim": _normalizar_data_br(str(item.get("Data_Fim") or "")) or None,
            }
        )
    return resultado


def _normalizar_data_br(data_str: str) -> str:
    s = data_str.strip()
    if not s or s == "9999-12-31" or s == "31/12/9999":
        return ""
    if re.match(r"^\d{2}/\d{2}/\d{4}$", s):
        d, m, y = s.split("/")
        return f"{y}-{m}-{d}"
    return s[:10]


def ingerir_siscomex_ncm_json(
    conn: sqlite3.Connection,
    conteudo_bytes: bytes,
    *,
    url_oficial: str = URL_SISCOMEX_NCM_JSON,
    apenas_ncms: set[str] | None = None,
) -> int:
    """Atualiza regras_federais com NCMs vigentes do Siscomex."""
    validar_url_oficial(url_oficial)
    itens = parsear_siscomex_ncm_json(conteudo_bytes)
    atualizados = 0
    with conn:
        for item in itens:
            ncm = item["ncm"]
            if apenas_ncms is not None and ncm not in apenas_ncms:
                continue
            existente = conn.execute(
                "SELECT id FROM regras_federais WHERE ncm = ? AND ex_tipi = '' AND cest = '' AND status_registro = 'ATIVA'",
                (ncm,),
            ).fetchone()
            if existente:
                conn.execute(
                    """
                    UPDATE regras_federais
                    SET descricao_ncm = ?, vigencia_fim = COALESCE(?, vigencia_fim), atualizado_em = datetime('now')
                    WHERE id = ?
                    """,
                    (item["descricao"], item["vigencia_fim"], existente["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO regras_federais (
                        ncm, ex_tipi, cest, descricao_ncm, vigencia_inicio, vigencia_fim,
                        dispositivo_legal, status_validacao
                    ) VALUES (?, '', '', ?, ?, ?, 'Tabela NCM Siscomex', 'A_CONFERIR')
                    """,
                    (ncm, item["descricao"], item["vigencia_inicio"] or "2026-01-01", item["vigencia_fim"]),
                )
            atualizados += 1
    return atualizados


def parsear_tipi_xlsx(conteudo_bytes: bytes) -> list[dict[str, Any]]:
    """Parseia planilha oficial da TIPI (.xlsx) para NCM, Ex, Descrição e Alíquota IPI."""
    linhas = extrair_linhas_tipi_xlsx(conteudo_bytes)
    resultado: list[dict[str, Any]] = []
    for row in linhas:
        lower = {k.strip().lower(): v for k, v in row.items()}
        ncm = _so_digitos(lower.get("ncm") or lower.get("código") or lower.get("codigo"))
        if len(ncm) != 8:
            continue
        ex_tipi = str(lower.get("ex") or lower.get("ex_tipi") or "").strip()
        desc = str(lower.get("descrição") or lower.get("descricao") or "").strip()
        aliq_raw = str(lower.get("alíquota (%)") or lower.get("aliquota") or lower.get("ipi") or "0")
        aliq_raw = aliq_raw.replace(",", ".").replace("%", "").strip()
        try:
            aliq = float(aliq_raw) if aliq_raw and aliq_raw.upper() != "NT" else 0.0
        except ValueError:
            aliq = 0.0
        resultado.append(
            {
                "ncm": ncm,
                "ex_tipi": ex_tipi,
                "descricao": desc,
                "aliquota_ipi": aliq,
            }
        )
    return resultado


def ingerir_tipi_xlsx(
    conn: sqlite3.Connection,
    conteudo_bytes: bytes,
    *,
    url_oficial: str = URL_TIPI_RFB,
    apenas_ncms: set[str] | None = None,
) -> int:
    """Atualiza alíquotas de IPI em regras_federais a partir da TIPI oficial."""
    validar_url_oficial(url_oficial)
    itens = parsear_tipi_xlsx(conteudo_bytes)
    atualizados = 0
    with conn:
        for item in itens:
            ncm = item["ncm"]
            if apenas_ncms is not None and ncm not in apenas_ncms:
                continue
            existente = conn.execute(
                "SELECT id FROM regras_federais WHERE ncm = ? AND ex_tipi = ? AND cest = '' AND status_registro = 'ATIVA'",
                (ncm, item["ex_tipi"]),
            ).fetchone()
            if existente:
                conn.execute(
                    """
                    UPDATE regras_federais
                    SET aliquota_ipi = ?, descricao_ncm = COALESCE(NULLIF(?, ''), descricao_ncm),
                        atualizado_em = datetime('now')
                    WHERE id = ?
                    """,
                    (item["aliquota_ipi"], item["descricao"], existente["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO regras_federais (
                        ncm, ex_tipi, cest, descricao_ncm, vigencia_inicio,
                        aliquota_ipi, dispositivo_legal, status_validacao
                    ) VALUES (?, ?, '', ?, '2026-01-01', ?, 'TIPI Receita Federal', 'A_CONFERIR')
                    """,
                    (ncm, item["ex_tipi"], item["descricao"], item["aliquota_ipi"]),
                )
            atualizados += 1
    return atualizados


def parsear_convenio_142_html(html: str) -> list[dict[str, str]]:
    """Extrai pares CEST × NCM × Descrição das tabelas do Convênio ICMS 142/2018."""
    parser = _HTMLTableParser()
    parser.feed(html)
    parser.close()

    resultado: list[dict[str, str]] = []
    for table in parser.tables:
        for row in table:
            if len(row) < 3:
                continue
            cest = _so_digitos(row[1] if len(row) >= 4 else row[0])
            ncms_raw = row[2] if len(row) >= 4 else row[1]
            desc = row[3] if len(row) >= 4 else row[2]
            if len(cest) != 7:
                continue
            for ncm_match in re.findall(r"\d{4}\.?\d{2}\.?\d{2}", ncms_raw):
                ncm = _so_digitos(ncm_match)
                if len(ncm) == 8:
                    resultado.append({"cest": cest, "ncm": ncm, "descricao": desc})
    return resultado


def ingerir_convenio_142_html(
    conn: sqlite3.Connection,
    html: str,
    *,
    url_oficial: str = URL_CONFAZ_142_18,
    uf_terceiro: str = "SP",
) -> int:
    """Registra validações de CEST × NCM do Convênio 142/2018 em tabela_terceiros."""
    validar_url_oficial(url_oficial)
    itens = parsear_convenio_142_html(html)
    atualizados = 0
    with conn:
        for item in itens:
            existente = conn.execute(
                """
                SELECT id FROM tabela_terceiros
                WHERE uf_terceiro = ? AND ncm = ? AND cest = ? AND status_registro = 'ATIVA'
                """,
                (uf_terceiro.upper(), item["ncm"], item["cest"]),
            ).fetchone()
            obs = f"Conv. ICMS 142/18: {item['descricao']}"
            if existente:
                conn.execute(
                    "UPDATE tabela_terceiros SET observacao_fiscal = ?, atualizado_em = datetime('now') WHERE id = ?",
                    (obs, existente["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO tabela_terceiros (
                        uf_terceiro, ncm, cest, vigencia_inicio, observacao_fiscal,
                        dispositivo_legal, status_validacao
                    ) VALUES (?, ?, ?, '2026-01-01', ?, 'Convênio ICMS 142/2018', 'A_CONFERIR')
                    """,
                    (uf_terceiro.upper(), item["ncm"], item["cest"], obs),
                )
            atualizados += 1
    return atualizados


def parsear_convenio_52_91_html(html: str) -> set[str]:
    """Extrai NCMs listados nos Anexos I e II do Convênio ICMS 52/91."""
    parser = _HTMLTableParser()
    parser.feed(html)
    parser.close()

    ncms: set[str] = set()
    for table in parser.tables:
        for row in table:
            for cell in row:
                for ncm_match in re.findall(r"\d{4}\.?\d{2}\.?\d{2}", cell):
                    ncm = _so_digitos(ncm_match)
                    if len(ncm) == 8:
                        ncms.add(ncm)
    return ncms


def ingerir_convenio_52_91_html(
    conn: sqlite3.Connection,
    html: str,
    *,
    url_oficial: str = URL_CONFAZ_52_91,
    uf_terceiro: str = "SP",
) -> int:
    """Marca beneficio_convenio_52_91 = 1 em tabela_terceiros para NCMs do Conv. 52/91."""
    validar_url_oficial(url_oficial)
    ncms = parsear_convenio_52_91_html(html)
    atualizados = 0
    with conn:
        for ncm in sorted(ncms):
            existente = conn.execute(
                "SELECT id FROM tabela_terceiros WHERE uf_terceiro = ? AND ncm = ? AND cest = '' AND status_registro = 'ATIVA'",
                (uf_terceiro.upper(), ncm),
            ).fetchone()
            if existente:
                conn.execute(
                    "UPDATE tabela_terceiros SET beneficio_convenio_52_91 = 1, atualizado_em = datetime('now') WHERE id = ?",
                    (existente["id"],),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO tabela_terceiros (
                        uf_terceiro, ncm, cest, vigencia_inicio, beneficio_convenio_52_91,
                        dispositivo_legal, status_validacao
                    ) VALUES (?, ?, '', '2026-01-01', 1, 'Convênio ICMS 52/1991', 'A_CONFERIR')
                    """,
                    (uf_terceiro.upper(), ncm),
                )
            atualizados += 1
    return atualizados


def parsear_cbenef_xlsx(conteudo_bytes: bytes) -> list[dict[str, str]]:
    """Parseia planilha oficial de códigos cBenef por UF do Portal Nacional da NF-e."""
    wb = openpyxl.load_workbook(io.BytesIO(conteudo_bytes), read_only=True, data_only=True)
    try:
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header_raw = next(it, None)
        if not header_raw:
            return []
        headers = [str(h).strip().lower() if h is not None else f"col_{i}" for i, h in enumerate(header_raw)]
        itens: list[dict[str, str]] = []
        for row in it:
            if not any(v is not None and str(v).strip() for v in row):
                continue
            d = {headers[i]: ("" if i >= len(row) or row[i] is None else str(row[i]).strip()) for i in range(len(headers))}
            cbenef = d.get("cbenef") or d.get("codigo_beneficio") or d.get("codigo") or ""
            if cbenef:
                itens.append(
                    {
                        "uf": (d.get("uf") or "SP").upper(),
                        "codigo_beneficio_fiscal": cbenef,
                        "cst_icms": d.get("cst") or d.get("cst_icms") or "",
                        "descricao": d.get("descricao") or d.get("descrição") or "",
                    }
                )
        return itens
    finally:
        wb.close()


def ingerir_cbenef_xlsx(
    conn: sqlite3.Connection,
    conteudo_bytes: bytes,
    *,
    url_oficial: str = URL_NFE_PORTAL,
) -> int:
    """Registra regras preliminares A_CONFERIR de cBenef na tabela regras_estaduais_icms."""
    validar_url_oficial(url_oficial)
    itens = parsear_cbenef_xlsx(conteudo_bytes)
    inseridos = 0
    with conn:
        for item in itens:
            existente = conn.execute(
                """
                SELECT id FROM regras_estaduais_icms
                WHERE uf_origem = ? AND uf_destino = ? AND codigo_beneficio_fiscal = ? AND status_registro = 'ATIVA'
                """,
                (item["uf"], item["uf"], item["codigo_beneficio_fiscal"]),
            ).fetchone()
            if not existente:
                conn.execute(
                    """
                    INSERT INTO regras_estaduais_icms (
                        uf_origem, uf_destino, ncm, cest, natureza_operacao,
                        operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                        cfop, cst_icms, codigo_beneficio_fiscal, observacao_padrao,
                        dispositivo_legal, status_validacao
                    ) VALUES (?, ?, '', '', 'VENDA', 1, '*', '2026-01-01', '5102', ?, ?, ?, 'Tabela cBenef Portal NF-e', 'A_CONFERIR')
                    """,
                    (
                        item["uf"],
                        item["uf"],
                        item["cst_icms"] or "40",
                        item["codigo_beneficio_fiscal"],
                        item["descricao"],
                    ),
                )
                inseridos += 1
    return inseridos


def parsear_cclasstrib_xlsx(conteudo_bytes: bytes) -> list[dict[str, Any]]:
    """Parseia planilha oficial de transição IBS/CBS (cClassTrib) do Portal NF-e."""
    wb = openpyxl.load_workbook(io.BytesIO(conteudo_bytes), read_only=True, data_only=True)
    try:
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header_raw = next(it, None)
        if not header_raw:
            return []
        headers = [str(h).strip().lower() if h is not None else f"col_{i}" for i, h in enumerate(header_raw)]
        itens: list[dict[str, Any]] = []
        for row in it:
            if not any(v is not None and str(v).strip() for v in row):
                continue
            d = {headers[i]: ("" if i >= len(row) or row[i] is None else str(row[i]).strip()) for i in range(len(headers))}
            ncm = _so_digitos(d.get("ncm"))
            cclass = d.get("cclasstrib") or d.get("cclass_trib") or ""
            if len(ncm) == 8 and cclass:
                itens.append(
                    {
                        "ncm": ncm,
                        "cst_ibs_cbs": d.get("cst_ibs_cbs") or d.get("cst") or "000",
                        "cclass_trib": cclass,
                        "aliquota_cbs": float(str(d.get("aliquota_cbs") or 0).replace(",", ".")),
                        "aliquota_ibs_uf": float(str(d.get("aliquota_ibs_uf") or 0).replace(",", ".")),
                        "aliquota_ibs_mun": float(str(d.get("aliquota_ibs_mun") or 0).replace(",", ".")),
                        "reducao_ibs_cbs": float(str(d.get("reducao_ibs_cbs") or 0).replace(",", ".")),
                    }
                )
        return itens
    finally:
        wb.close()


def ingerir_cclasstrib_xlsx(
    conn: sqlite3.Connection,
    conteudo_bytes: bytes,
    *,
    url_oficial: str = URL_NFE_PORTAL,
) -> int:
    """Atualiza campos de Reforma Tributária (IBS/CBS + cClassTrib) em regras_federais."""
    validar_url_oficial(url_oficial)
    itens = parsear_cclasstrib_xlsx(conteudo_bytes)
    atualizados = 0
    with conn:
        for item in itens:
            existente = conn.execute(
                "SELECT id FROM regras_federais WHERE ncm = ? AND ex_tipi = '' AND cest = '' AND status_registro = 'ATIVA'",
                (item["ncm"],),
            ).fetchone()
            if existente:
                conn.execute(
                    """
                    UPDATE regras_federais
                    SET cst_ibs_cbs = ?, cclass_trib = ?, aliquota_cbs = ?,
                        aliquota_ibs_uf = ?, aliquota_ibs_mun = ?, reducao_ibs_cbs = ?,
                        atualizado_em = datetime('now')
                    WHERE id = ?
                    """,
                    (
                        item["cst_ibs_cbs"],
                        item["cclass_trib"],
                        item["aliquota_cbs"],
                        item["aliquota_ibs_uf"],
                        item["aliquota_ibs_mun"],
                        item["reducao_ibs_cbs"],
                        existente["id"],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO regras_federais (
                        ncm, ex_tipi, cest, vigencia_inicio,
                        cst_ibs_cbs, cclass_trib, aliquota_cbs, aliquota_ibs_uf,
                        aliquota_ibs_mun, reducao_ibs_cbs, dispositivo_legal, status_validacao
                    ) VALUES (?, '', '', '2026-01-01', ?, ?, ?, ?, ?, ?, 'Tabela cClassTrib Portal NF-e', 'A_CONFERIR')
                    """,
                    (
                        item["ncm"],
                        item["cst_ibs_cbs"],
                        item["cclass_trib"],
                        item["aliquota_cbs"],
                        item["aliquota_ibs_uf"],
                        item["aliquota_ibs_mun"],
                        item["reducao_ibs_cbs"],
                    ),
                )
            atualizados += 1
    return atualizados


def parsear_svrs_classtrib_json(conteudo_bytes: bytes) -> list[dict[str, Any]]:
    """Parseia resposta JSON oficial da API SVRS Conformidade Fácil (cClassTrib IBS/CBS)."""
    dados = json.loads(conteudo_bytes.decode("utf-8"))
    registros = dados if isinstance(dados, list) else dados.get("itens") or dados.get("data") or []
    itens: list[dict[str, Any]] = []
    for reg in registros:
        if not isinstance(reg, dict):
            continue
        cclass = str(reg.get("cClassTrib") or reg.get("cclass_trib") or reg.get("codigo") or "").strip()
        cst = str(reg.get("CST") or reg.get("cst") or reg.get("cst_ibs_cbs") or "000").strip()
        ncm = _so_digitos(reg.get("NCM") or reg.get("ncm"))
        if cclass and len(ncm) == 8:
            itens.append(
                {
                    "ncm": ncm,
                    "cst_ibs_cbs": cst,
                    "cclass_trib": cclass,
                    "reducao_ibs_cbs": float(str(reg.get("pRedAliq") or reg.get("reducao_ibs_cbs") or 0).replace(",", ".")),
                }
            )
    return itens


def ingerir_svrs_classtrib_json(
    conn: sqlite3.Connection,
    conteudo_bytes: bytes,
    *,
    url_oficial: str = URL_SVRS_CLASSTRIB_API,
) -> int:
    """Atualiza cClassTrib e CST IBS/CBS a partir da API JSON oficial da SVRS."""
    validar_url_oficial(url_oficial)
    itens = parsear_svrs_classtrib_json(conteudo_bytes)
    atualizados = 0
    with conn:
        for item in itens:
            cur = conn.execute(
                """
                UPDATE regras_federais
                SET cst_ibs_cbs = ?, cclass_trib = ?, reducao_ibs_cbs = ?, atualizado_em = datetime('now')
                WHERE ncm = ? AND status_registro = 'ATIVA'
                """,
                (item["cst_ibs_cbs"], item["cclass_trib"], item["reducao_ibs_cbs"], item["ncm"]),
            )
            atualizados += int(cur.rowcount)
    return atualizados
