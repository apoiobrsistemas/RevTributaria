"""Camada de conexão e repositório SQLite (WAL mode)."""

from src.database.connection import DEFAULT_DB_PATH, DEFAULT_SCHEMA_PATH, get_connection, init_db
from src.database.repository import (
    OptimisticLockError,
    atualizar_regra_com_lock,
    buscar_regra_estadual_icms,
    buscar_regra_federal,
    buscar_regra_servico,
    buscar_regra_terceiro,
    registrar_historico,
    soft_delete_regra,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "DEFAULT_SCHEMA_PATH",
    "OptimisticLockError",
    "atualizar_regra_com_lock",
    "buscar_regra_estadual_icms",
    "buscar_regra_federal",
    "buscar_regra_servico",
    "buscar_regra_terceiro",
    "get_connection",
    "init_db",
    "registrar_historico",
    "soft_delete_regra",
]
