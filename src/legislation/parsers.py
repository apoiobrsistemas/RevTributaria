"""Parsers compartilhados entre ingestão inicial e Vigia Noturno."""

from __future__ import annotations

import io
import re
from html.parser import HTMLParser
from typing import Any

from src.legislation.url_guard import OfficialURL, validar_url_oficial


class _FallbackHTMLTextExtractor(HTMLParser):
    """Extrator HTML simples caso BeautifulSoup4 não esteja instalado."""

    def __init__(self) -> None:
        super().__init__()
        self._ignorar_profundidade = 0
        self._partes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "nav", "header", "footer", "noscript"}:
            self._ignorar_profundidade += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "nav", "header", "footer", "noscript"}:
            if self._ignorar_profundidade > 0:
                self._ignorar_profundidade -= 1

    def handle_data(self, data: str) -> None:
        if self._ignorar_profundidade == 0:
            texto = data.strip()
            if texto:
                self._partes.append(texto)

    def obter_texto(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._partes)).strip()


def extrair_texto_html(html: str) -> str:
    """Extrai o corpo textual limpo de HTML removendo scripts, estilos e navegação."""
    try:
        from bs4 import BeautifulSoup  # type: ignore[import-not-found]

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        return re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    except ImportError:
        parser = _FallbackHTMLTextExtractor()
        parser.feed(html)
        parser.close()
        return parser.obter_texto()


def extrair_texto_pdf(conteudo_bytes: bytes) -> str:
    """Extrai texto de PDF oficial usando pypdf."""
    from pypdf import PdfReader  # type: ignore[import-not-found]

    reader = PdfReader(io.BytesIO(conteudo_bytes))
    paginas = [page.extract_text() or "" for page in reader.pages]
    return re.sub(r"\s+", " ", "\n".join(paginas)).strip()


def extrair_texto_docx(conteudo_bytes: bytes) -> str:
    """Extrai texto de documento DOCX oficial usando python-docx."""
    from docx import Document  # type: ignore[import-not-found]

    doc = Document(io.BytesIO(conteudo_bytes))
    paragrafos = [p.text for p in doc.paragraphs if p.text.strip()]
    return re.sub(r"\s+", " ", "\n".join(paragrafos)).strip()


def extrair_linhas_tipi_xlsx(conteudo_bytes: bytes) -> list[dict[str, str]]:
    """Extrai linhas da planilha oficial da TIPI (.xlsx) usando openpyxl."""
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(conteudo_bytes), read_only=True, data_only=True)
    try:
        ws = wb.active
        linhas_iter = ws.iter_rows(values_only=True)
        cabecalho_raw = next(linhas_iter, None)
        if not cabecalho_raw:
            return []
        cabecalho = [str(c).strip() if c is not None else f"col_{i}" for i, c in enumerate(cabecalho_raw)]
        resultado: list[dict[str, str]] = []
        for row in linhas_iter:
            if not any(cell is not None and str(cell).strip() for cell in row):
                continue
            item = {
                cabecalho[i]: ("" if i >= len(row) or row[i] is None else str(row[i]).strip())
                for i in range(len(cabecalho))
            }
            resultado.append(item)
        return resultado
    finally:
        wb.close()


def baixar_url_oficial(
    url: OfficialURL | str,
    *,
    usar_playwright: bool = False,
    timeout: int = 30,
) -> tuple[bytes, str]:
    """Baixa conteúdo exclusivamente de URLs validadas na whitelist oficial."""
    url_validada = str(url) if isinstance(url, OfficialURL) else validar_url_oficial(url)

    if usar_playwright:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url_validada, wait_until="networkidle", timeout=timeout * 1000)
                html = page.content()
                return html.encode("utf-8"), "text/html"
            finally:
                browser.close()

    import requests

    resp = requests.get(
        url_validada,
        timeout=timeout,
        headers={"User-Agent": "RevTributaria-OfficialLawWatcher/1.0"},
    )
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "application/octet-stream").split(";")[0].strip()
    return resp.content, content_type


def extrair_texto_por_tipo(conteudo_bytes: bytes, content_type: str, url: str = "") -> str:
    """Despacha o conteúdo baixado para o extrator adequado conforme tipo/extensão."""
    ct = content_type.lower()
    url_lower = url.lower()

    if "pdf" in ct or url_lower.endswith(".pdf"):
        return extrair_texto_pdf(conteudo_bytes)
    if "wordprocessingml" in ct or url_lower.endswith(".docx"):
        return extrair_texto_docx(conteudo_bytes)
    if "spreadsheetml" in ct or url_lower.endswith(".xlsx"):
        linhas = extrair_linhas_tipi_xlsx(conteudo_bytes)
        return "\n".join(" | ".join(f"{k}: {v}" for k, v in row.items() if v) for row in linhas)

    html = conteudo_bytes.decode("utf-8", errors="replace")
    return extrair_texto_html(html)


def _limpar_para_comparacao(valor: Any) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()
