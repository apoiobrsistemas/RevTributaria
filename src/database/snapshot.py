"""Snapshot versionado da base de regras (sincroniza a matriz local com o ambiente em nuvem)."""

from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
import tempfile
import threading
from pathlib import Path

from src.database.connection import DEFAULT_DB_PATH, init_db

_SNAPSHOT_LOCK = threading.Lock()

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent.parent / "data"
SNAPSHOT_DB_GZ = SNAPSHOT_DIR / "revtributaria_snapshot.db.gz"
SNAPSHOT_META = SNAPSHOT_DIR / "revtributaria_snapshot.json"

# Tabelas operacionais/sensíveis que NÃO vão para o snapshot público (NF-es, CNPJs, ERP)
TABELAS_EXCLUIDAS_SNAPSHOT = (
    "auditoria_divergencias",
    "nfe_eventos",
    "nfe_itens",
    "nfe_documentos",
    "nfe_sync_cursor",
    "cnpj_regimes",
    "config_erp_importada",
    "controle_execucao_diaria",
    "linx_sync_cursor",
    "linx_produtos_detalhes",
    "linx_produtos",
    "linx_config_tributarias",
    "linx_lojas",
)


def _contar_regras_ativas(conn: sqlite3.Connection) -> int:
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM regras_estaduais_icms WHERE status_registro = 'ATIVA'"
            ).fetchone()[0]
        )
    except sqlite3.Error:
        return 0


def exportar_snapshot(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, int]:
    """Gera data/revtributaria_snapshot.db.gz com as regras/fontes/acervo (sem NF-es e dados de ERP)."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_db = Path(tmp) / "snapshot.db"
        origem = sqlite3.connect(str(db_path))
        destino = sqlite3.connect(str(tmp_db))
        try:
            origem.backup(destino)
        finally:
            origem.close()
        try:
            destino.execute("PRAGMA foreign_keys = OFF;")
            for tabela in TABELAS_EXCLUIDAS_SNAPSHOT:
                try:
                    destino.execute(f"DELETE FROM [{tabela}]")
                except sqlite3.Error:
                    pass
            destino.commit()
            destino.execute("PRAGMA journal_mode = DELETE;")
            destino.execute("VACUUM;")
            regras = _contar_regras_ativas(destino)
        finally:
            destino.close()

        with open(tmp_db, "rb") as f_in, gzip.open(SNAPSHOT_DB_GZ, "wb", compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)

    meta = {"regras_estaduais_ativas": regras}
    SNAPSHOT_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def restaurar_snapshot_se_necessario(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, int | bool]:
    """Restaura o snapshot versionado quando a base local tem menos regras ativas que o snapshot."""
    resultado: dict[str, int | bool] = {"restaurado": False, "regras_antes": 0, "regras_snapshot": 0}
    if str(db_path) == ":memory:" or not SNAPSHOT_DB_GZ.exists():
        return resultado

    try:
        meta = json.loads(SNAPSHOT_META.read_text(encoding="utf-8")) if SNAPSHOT_META.exists() else {}
    except (OSError, ValueError):
        meta = {}
    regras_snapshot = int(meta.get("regras_estaduais_ativas") or 0)
    resultado["regras_snapshot"] = regras_snapshot

    with _SNAPSHOT_LOCK:
        conn = init_db(db_path)
        try:
            regras_atuais = _contar_regras_ativas(conn)
            resultado["regras_antes"] = regras_atuais
            if regras_atuais >= regras_snapshot:
                return resultado

            with tempfile.TemporaryDirectory() as tmp:
                tmp_db = Path(tmp) / "snapshot.db"
                with gzip.open(SNAPSHOT_DB_GZ, "rb") as f_in, open(tmp_db, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                origem = sqlite3.connect(str(tmp_db))
                try:
                    origem.backup(conn)
                finally:
                    origem.close()

            conn.close()
            conn = init_db(db_path)
            resultado["restaurado"] = True
            return resultado
        except sqlite3.OperationalError:
            return resultado
        finally:
            conn.close()
