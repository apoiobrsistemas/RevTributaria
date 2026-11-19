"""Inicialização e configuração obrigatória de conexões SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "revtributaria.db"
_INITIALIZED_DBS: set[tuple[str, str]] = set()


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
    db_str = str(db_path)
    is_mem = db_str == ":memory:" or db_str.startswith("file::memory:")
    cache_key = (
        "" if is_mem else str(Path(db_str).resolve()),
        str(Path(schema_path).resolve()),
    )

    conn = get_connection(db_path)
    if not is_mem and cache_key in _INITIALIZED_DBS and Path(db_str).exists():
        existe = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='regras_estaduais' LIMIT 1"
        ).fetchone()
        if existe is not None:
            return conn

    schema_sql = Path(schema_path).read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    # Reaplica os pragmas após executescript para garantir estado consistente
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.commit()
    if not is_mem:
        _INITIALIZED_DBS.add(cache_key)
    return conn
