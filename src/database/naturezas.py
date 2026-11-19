"""Persistência e aplicação de IDs configuráveis por Natureza de Operação."""

from __future__ import annotations

import sqlite3
from typing import Any

NATUREZAS_OPERACAO_PADRAO = (
    "Compra para Comercialização",
    "Venda de Mercadorias",
    "Devolução de Compra",
    "Devolução de Venda",
    "Entrada de Transferência entre Filiais",
    "Saída de Transferência entre Filiais",
    "Outras Entradas",
    "Outras Saídas",
)


def _garantir_tabela_naturezas(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS naturezas_operacao_ids (
            natureza_operacao TEXT PRIMARY KEY,
            id_natureza       INTEGER NOT NULL DEFAULT 0,
            atualizado_em     TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def listar_ids_naturezas_operacao_db(conn: sqlite3.Connection) -> dict[str, int]:
    """Retorna os IDs externos configurados para cada Natureza de Operação."""
    with conn:
        _garantir_tabela_naturezas(conn)
        for nat in NATUREZAS_OPERACAO_PADRAO:
            conn.execute(
                "INSERT OR IGNORE INTO naturezas_operacao_ids (natureza_operacao, id_natureza) VALUES (?, 0)",
                (nat,),
            )
    rows = conn.execute(
        "SELECT natureza_operacao, id_natureza FROM naturezas_operacao_ids"
    ).fetchall()
    mapa_db = {str(r["natureza_operacao"]): int(r["id_natureza"] or 0) for r in rows}
    resultado: dict[str, int] = {}
    for nat in NATUREZAS_OPERACAO_PADRAO:
        resultado[nat] = mapa_db.get(nat, 0)
    for nat, val in sorted(mapa_db.items()):
        if nat not in resultado:
            resultado[nat] = val
    return resultado


def salvar_ids_naturezas_operacao_db(
    conn: sqlite3.Connection,
    mapa_ids: dict[str, int],
) -> dict[str, int]:
    """Salva/atualiza os IDs externos das Naturezas de Operação no SQLite."""
    with conn:
        _garantir_tabela_naturezas(conn)
        for nat, val in mapa_ids.items():
            nat_limpa = str(nat or "").strip()
            if not nat_limpa:
                continue
            id_int = max(0, int(val or 0))
            conn.execute(
                """
                INSERT INTO naturezas_operacao_ids (natureza_operacao, id_natureza, atualizado_em)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(natureza_operacao) DO UPDATE SET
                    id_natureza = excluded.id_natureza,
                    atualizado_em = datetime('now')
                """,
                (nat_limpa, id_int),
            )
    return listar_ids_naturezas_operacao_db(conn)


def aplicar_ids_natureza_nas_linhas(
    linhas: list[dict[str, Any]],
    mapa_ids: dict[str, int],
) -> list[dict[str, Any]]:
    """Insere a coluna 'ID Natureza' imediatamente à esquerda de 'Natureza de Operação'."""
    if not linhas:
        return []
    saida: list[dict[str, Any]] = []
    for linha in linhas:
        nat = str(linha.get("Natureza de Operação") or "")
        id_nat = mapa_ids.get(nat, 0)
        id_val: int | str = id_nat if id_nat > 0 else ""
        novo: dict[str, Any] = {}
        inserido = False
        for k, v in linha.items():
            if k == "ID Natureza":
                continue
            if k == "Natureza de Operação" and not inserido:
                novo["ID Natureza"] = id_val
                inserido = True
            novo[k] = v
        if not inserido:
            novo = {"ID Natureza": id_val, **novo}
        saida.append(novo)
    return saida
