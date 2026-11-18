"""Conector Web Service XML do Linx Microvix com retry exponencial e UPSERT incremental."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import xml.etree.ElementTree as ET
from typing import Any, Callable
from xml.sax.saxutils import escape

import requests

from src.integrations.matriz_parser import parsear_config_tributaria_linx

MICROVIX_ENDPOINT = "https://webapi.microvix.com.br/1.0/api/integracao"
METODOS_SUPORTADOS = frozenset(
    {
        "LinxLojas",
        "LinxProdutos",
        "LinxProdutosDetalhes",
        "LinxConfiguracoesTributariasDetalhes",
    }
)


class MicrovixError(RuntimeError):
    """Erro de comunicação ou retorno inválido do Web Service Linx Microvix."""


def obter_chave_microvix() -> str:
    """Lê a chave do portal exclusivamente da variável de ambiente MICROVIX_CHAVE."""
    chave = os.environ.get("MICROVIX_CHAVE", "").strip()
    if not chave:
        raise MicrovixError("Variável de ambiente MICROVIX_CHAVE não configurada.")
    return chave


def montar_envelope_microvix(
    *,
    metodo: str,
    chave: str,
    cnpj_emp: str,
    timestamp_inicial: int = 0,
    extra_params: dict[str, Any] | None = None,
) -> str:
    """Monta o XML de requisição para a API de integração Linx Microvix."""
    params = {
        "chave": chave,
        "cnpjEmp": cnpj_emp,
        "timestamp": str(timestamp_inicial),
    }
    if extra_params:
        for k, v in extra_params.items():
            params[str(k)] = str(v)

    param_tags = "".join(
        f'<Parameter id="{escape(k)}">{escape(v)}</Parameter>' for k, v in params.items()
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<LinxMicrovix>"
        '<Authentication user="linx_export" password="" />'
        "<ResponseFormat>xml</ResponseFormat>"
        f'<Command><Name>{escape(metodo)}</Name><Parameters>{param_tags}</Parameters></Command>'
        "</LinxMicrovix>"
    )


def parsear_resposta_microvix(xml_data: bytes | str) -> list[dict[str, str]]:
    """Mapeia ResponseData/C/D (colunas) contra ResponseData/R/D (linhas)."""
    root = ET.fromstring(xml_data)

    sucesso_el = root.find(".//ResponseResult/Success")
    if sucesso_el is not None and (sucesso_el.text or "").strip().lower() == "false":
        msg_el = root.find(".//ResponseResult/Message")
        msg = msg_el.text.strip() if msg_el is not None and msg_el.text else "Erro desconhecido"
        raise MicrovixError(f"Microvix retornou falha: {msg}")

    colunas = [
        (d.text or "").strip()
        for d in root.findall("./ResponseData/C/D")
    ]
    if not colunas:
        return []

    registros: list[dict[str, str]] = []
    for row_el in root.findall("./ResponseData/R"):
        valores = [(d.text or "").strip() for d in row_el.findall("./D")]
        registros.append(
            {
                colunas[i]: (valores[i] if i < len(valores) else "")
                for i in range(len(colunas))
            }
        )
    return registros


HttpPostFn = Callable[[str, str, dict[str, str], int], bytes]


class MicrovixClient:
    """Cliente HTTP/XML para Linx Microvix com backoff exponencial."""

    def __init__(
        self,
        *,
        chave: str | None = None,
        endpoint: str = MICROVIX_ENDPOINT,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        timeout: int = 30,
        http_post: HttpPostFn | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._chave = chave
        self.endpoint = endpoint
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.timeout = timeout
        self._http_post = http_post
        self._sleep = sleep_fn

    def _post_xml(self, envelope: str) -> bytes:
        headers = {"Content-Type": "application/xml; charset=utf-8"}
        if self._http_post is not None:
            return self._http_post(self.endpoint, envelope, headers, self.timeout)

        resp = requests.post(
            self.endpoint,
            data=envelope.encode("utf-8"),
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.content

    def consultar(
        self,
        *,
        metodo: str,
        cnpj_emp: str,
        timestamp_inicial: int = 0,
        extra_params: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        """Executa consulta XML com retry exponencial para timeouts/falhas transitórias."""
        if metodo not in METODOS_SUPORTADOS:
            raise ValueError(f"Método Microvix não suportado: {metodo}")

        chave = self._chave or obter_chave_microvix()
        envelope = montar_envelope_microvix(
            metodo=metodo,
            chave=chave,
            cnpj_emp=cnpj_emp,
            timestamp_inicial=timestamp_inicial,
            extra_params=extra_params,
        )

        ultimo_erro: Exception | None = None
        for tentativa in range(self.max_retries):
            try:
                raw = self._post_xml(envelope)
                return parsear_resposta_microvix(raw)
            except (TimeoutError, requests.RequestException, OSError) as exc:
                ultimo_erro = exc
                if tentativa < self.max_retries - 1:
                    self._sleep(self.backoff_base * (2**tentativa))

        raise MicrovixError(
            f"Falha ao consultar {metodo} após {self.max_retries} tentativas: {ultimo_erro}"
        )


def _upsert_linx_lojas(conn: sqlite3.Connection, rows: list[dict[str, str]]) -> None:
    for r in rows:
        conn.execute(
            """
            INSERT INTO linx_lojas (
                empresa, cnpj_emp, nome_emp, uf, payload_json, timestamp_linx, atualizado_em
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(empresa) DO UPDATE SET
                cnpj_emp = excluded.cnpj_emp,
                nome_emp = excluded.nome_emp,
                uf = excluded.uf,
                payload_json = excluded.payload_json,
                timestamp_linx = excluded.timestamp_linx,
                atualizado_em = datetime('now')
            """,
            (
                r.get("empresa", ""),
                r.get("cnpj_emp", ""),
                r.get("nome_emp", ""),
                r.get("uf", "").upper(),
                json.dumps(r, ensure_ascii=False),
                int(r.get("timestamp") or 0),
            ),
        )


def _upsert_linx_produtos(conn: sqlite3.Connection, rows: list[dict[str, str]]) -> None:
    for r in rows:
        conn.execute(
            """
            INSERT INTO linx_produtos (
                empresa, cod_produto, nome_produto, ncm, cest, origem_mercadoria,
                payload_json, timestamp_linx, atualizado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(empresa, cod_produto) DO UPDATE SET
                nome_produto = excluded.nome_produto,
                ncm = excluded.ncm,
                cest = excluded.cest,
                origem_mercadoria = excluded.origem_mercadoria,
                payload_json = excluded.payload_json,
                timestamp_linx = excluded.timestamp_linx,
                atualizado_em = datetime('now')
            """,
            (
                r.get("empresa", ""),
                r.get("cod_produto", ""),
                r.get("nome_produto", ""),
                r.get("ncm", ""),
                r.get("cest", ""),
                r.get("origem_mercadoria", ""),
                json.dumps(r, ensure_ascii=False),
                int(r.get("timestamp") or 0),
            ),
        )


def _upsert_linx_produtos_detalhes(
    conn: sqlite3.Connection, rows: list[dict[str, str]], cnpj_emp: str
) -> None:
    for r in rows:
        conn.execute(
            """
            INSERT INTO linx_produtos_detalhes (
                empresa, cod_produto, cnpj_emp, saldo, preco_custo, preco_venda,
                payload_json, timestamp_linx, atualizado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(empresa, cod_produto, cnpj_emp) DO UPDATE SET
                saldo = excluded.saldo,
                preco_custo = excluded.preco_custo,
                preco_venda = excluded.preco_venda,
                payload_json = excluded.payload_json,
                timestamp_linx = excluded.timestamp_linx,
                atualizado_em = datetime('now')
            """,
            (
                r.get("empresa", ""),
                r.get("cod_produto", ""),
                r.get("cnpj_emp") or cnpj_emp,
                float(r.get("quantidade") or r.get("saldo") or 0),
                float(r.get("preco_custo") or 0),
                float(r.get("preco_venda") or 0),
                json.dumps(r, ensure_ascii=False),
                int(r.get("timestamp") or 0),
            ),
        )


def _upsert_linx_config_tributarias(conn: sqlite3.Connection, rows: list[dict[str, str]]) -> None:
    normalizadas = parsear_config_tributaria_linx(rows)
    for r in normalizadas:
        conn.execute(
            """
            INSERT INTO linx_config_tributarias (
                empresa, id_config_tributaria, cfop, uf_operacao,
                cst_icms_fiscal, origem_separada, cst_separado, tipo_operacao_perna,
                payload_json, timestamp_linx, atualizado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(empresa, id_config_tributaria, cfop, uf_operacao) DO UPDATE SET
                cst_icms_fiscal = excluded.cst_icms_fiscal,
                origem_separada = excluded.origem_separada,
                cst_separado = excluded.cst_separado,
                tipo_operacao_perna = excluded.tipo_operacao_perna,
                payload_json = excluded.payload_json,
                timestamp_linx = excluded.timestamp_linx,
                atualizado_em = datetime('now')
            """,
            (
                r["empresa"],
                r["id_config_tributaria"],
                r["cfop"],
                r["uf_operacao"],
                r["cst_icms_fiscal"],
                r["origem_separada"],
                r["cst_separado"],
                r["tipo_operacao_perna"],
                r["payload_json"],
                r["timestamp_linx"],
            ),
        )


def sincronizar_metodo(
    conn: sqlite3.Connection,
    client: MicrovixClient,
    *,
    metodo: str,
    cnpj_emp: str,
) -> int:
    """Sincroniza incrementalmente um método Microvix via UPSERT e salva cursor só após commit."""
    row_cursor = conn.execute(
        "SELECT ultimo_timestamp FROM linx_sync_cursor WHERE cnpj_emp = ? AND metodo = ?",
        (cnpj_emp, metodo),
    ).fetchone()
    ts_atual = int(row_cursor["ultimo_timestamp"]) if row_cursor else 0

    registros = client.consultar(metodo=metodo, cnpj_emp=cnpj_emp, timestamp_inicial=ts_atual)
    if not registros:
        return 0

    # Transação 1: persiste os dados com UPSERT (se falhar, cursor não avança)
    with conn:
        if metodo == "LinxLojas":
            _upsert_linx_lojas(conn, registros)
        elif metodo == "LinxProdutos":
            _upsert_linx_produtos(conn, registros)
        elif metodo == "LinxProdutosDetalhes":
            _upsert_linx_produtos_detalhes(conn, registros, cnpj_emp)
        elif metodo == "LinxConfiguracoesTributariasDetalhes":
            _upsert_linx_config_tributarias(conn, registros)

    # Transação 2 (somente após commit bem-sucedido): atualiza cursor por cnpj_emp
    novo_ts = max(
        [ts_atual] + [int(r.get("timestamp") or 0) for r in registros if str(r.get("timestamp") or "").isdigit()]
    )
    with conn:
        conn.execute(
            """
            INSERT INTO linx_sync_cursor (cnpj_emp, metodo, ultimo_timestamp, atualizado_em)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(cnpj_emp, metodo) DO UPDATE SET
                ultimo_timestamp = MAX(linx_sync_cursor.ultimo_timestamp, excluded.ultimo_timestamp),
                atualizado_em = datetime('now')
            """,
            (cnpj_emp, metodo, novo_ts),
        )

    return len(registros)
