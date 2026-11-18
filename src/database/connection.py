"""Inicialização e configuração obrigatória de conexões SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "revtributaria.db"


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Abre conexão SQLite com WAL, synchronous NORMAL, foreign_keys e busy_timeout."""
    target = str(db_path)
    conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def init_db(
    db_path: str | Path = DEFAULT_DB_PATH,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> sqlite3.Connection:
    """Executa o schema.sql na conexão configurada e retorna a conexão pronta."""
    schema_sql = Path(schema_path).read_text(encoding="utf-8")
    conn = get_connection(db_path)
    conn.executescript(schema_sql)
    # Reaplica os pragmas após executescript para garantir estado consistente
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.commit()
    return conn
