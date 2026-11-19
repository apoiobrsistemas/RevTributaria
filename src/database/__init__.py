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
from src.database.schema_fase2 import (
    consultar_cbenef_uf,
    consultar_protocolo_st,
    garantir_carga_fase2,
    garantir_tabelas_fase2,
)
from src.database.snapshot import exportar_snapshot, restaurar_snapshot_se_necessario

__all__ = [
    "DEFAULT_DB_PATH",
    "DEFAULT_SCHEMA_PATH",
    "OptimisticLockError",
    "atualizar_regra_com_lock",
    "buscar_regra_estadual_icms",
    "buscar_regra_federal",
    "buscar_regra_servico",
    "buscar_regra_terceiro",
    "consultar_cbenef_uf",
    "consultar_protocolo_st",
    "exportar_snapshot",
    "garantir_carga_fase2",
    "garantir_tabelas_fase2",
    "get_connection",
    "init_db",
    "registrar_historico",
    "restaurar_snapshot_se_necessario",
    "soft_delete_regra",
]
