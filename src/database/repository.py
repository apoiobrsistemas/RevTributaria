"""Repositório de regras fiscais com optimistic locking e histórico append-only."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

TABELAS_REGRAS_PERMITIDAS = frozenset(
    {
        "regras_federais",
        "regras_estaduais_icms",
        "tabela_terceiros",
        "regras_servicos",
    }
)

CAMPOS_PROTEGIDOS = frozenset({"id", "versao", "criado_em", "atualizado_em"})


class OptimisticLockError(Exception):
    """Lançada quando a versão informada diverge da versão persistida no banco."""


def _iso_date(data_referencia: date | str | None) -> str:
    if data_referencia is None:
        return date.today().isoformat()
    if isinstance(data_referencia, date):
        return data_referencia.isoformat()
    return data_referencia


def _validar_tabela(tabela: str) -> str:
    if tabela not in TABELAS_REGRAS_PERMITIDAS:
        raise ValueError(f"Tabela '{tabela}' não permitida para operação de repositório.")
    return tabela


def buscar_regra_estadual_icms(
    conn: sqlite3.Connection,
    *,
    uf_origem: str,
    uf_destino: str,
    ncm: str,
    cest: str = "",
    natureza_operacao: str = "VENDA",
    operacao_com_contribuinte: bool = True,
    origem_mercadoria: str = "0",
    data_referencia: date | str | None = None,
    apenas_aceitas: bool = False,
) -> dict[str, Any] | None:
    """Busca a regra estadual de ICMS ativa mais específica e vigente."""
    ref = _iso_date(data_referencia)
    contrib = 1 if operacao_com_contribuinte else 0

    sql = """
        SELECT *
        FROM regras_estaduais_icms
        WHERE status_registro = 'ATIVA'
          AND uf_origem = ?
          AND uf_destino = ?
          AND natureza_operacao = ?
          AND operacao_com_contribuinte = ?
          AND (ncm = ? OR ncm = '')
          AND (cest = ? OR cest = '')
          AND (origem_mercadoria = ? OR origem_mercadoria = '*')
          AND vigencia_inicio <= ?
          AND (vigencia_fim IS NULL OR vigencia_fim >= ?)
    """
    params: list[Any] = [
        uf_origem.upper(),
        uf_destino.upper(),
        natureza_operacao,
        contrib,
        ncm,
        cest,
        origem_mercadoria,
        ref,
        ref,
    ]

    if apenas_aceitas:
        sql += " AND status_validacao = 'ACEITO'"
    else:
        sql += " AND status_validacao != 'REJEITADO'"

    sql += """
        ORDER BY
            CASE WHEN ncm = ? THEN 1 ELSE 0 END DESC,
            CASE WHEN cest != '' AND cest = ? THEN 1 ELSE 0 END DESC,
            CASE WHEN origem_mercadoria = ? THEN 1 ELSE 0 END DESC,
            vigencia_inicio DESC,
            id DESC
        LIMIT 1
    """
    params.extend([ncm, cest, origem_mercadoria])

    row = conn.execute(sql, params).fetchone()
    return dict(row) if row is not None else None


def buscar_regra_federal(
    conn: sqlite3.Connection,
    *,
    ncm: str,
    cest: str = "",
    ex_tipi: str = "",
    data_referencia: date | str | None = None,
    apenas_aceitas: bool = False,
) -> dict[str, Any] | None:
    """Busca a regra federal ativa (IPI, PIS/COFINS, IBS/CBS) mais específica."""
    ref = _iso_date(data_referencia)

    sql = """
        SELECT *
        FROM regras_federais
        WHERE status_registro = 'ATIVA'
          AND ncm = ?
          AND (cest = ? OR cest = '')
          AND (ex_tipi = ? OR ex_tipi = '')
          AND vigencia_inicio <= ?
          AND (vigencia_fim IS NULL OR vigencia_fim >= ?)
    """
    params: list[Any] = [ncm, cest, ex_tipi, ref, ref]

    if apenas_aceitas:
        sql += " AND status_validacao = 'ACEITO'"
    else:
        sql += " AND status_validacao != 'REJEITADO'"

    sql += """
        ORDER BY
            CASE WHEN ex_tipi != '' AND ex_tipi = ? THEN 1 ELSE 0 END DESC,
            CASE WHEN cest != '' AND cest = ? THEN 1 ELSE 0 END DESC,
            vigencia_inicio DESC,
            id DESC
        LIMIT 1
    """
    params.extend([ex_tipi, cest])

    row = conn.execute(sql, params).fetchone()
    return dict(row) if row is not None else None


def buscar_regra_terceiro(
    conn: sqlite3.Connection,
    *,
    uf_terceiro: str,
    ncm: str,
    cest: str = "",
    cnpj_terceiro: str = "*",
    tipo_entrada: str = "REVENDA",
    origem_mercadoria: str = "0",
    data_referencia: date | str | None = None,
) -> dict[str, Any] | None:
    """Busca regra ativa na tabela_terceiros para entradas/importados/FCI."""
    ref = _iso_date(data_referencia)

    sql = """
        SELECT *
        FROM tabela_terceiros
        WHERE status_registro = 'ATIVA'
          AND uf_terceiro = ?
          AND ncm = ?
          AND (cest = ? OR cest = '')
          AND (cnpj_terceiro = ? OR cnpj_terceiro = '*')
          AND tipo_entrada = ?
          AND (origem_mercadoria = ? OR origem_mercadoria = '*')
          AND vigencia_inicio <= ?
          AND (vigencia_fim IS NULL OR vigencia_fim >= ?)
          AND status_validacao != 'REJEITADO'
        ORDER BY
            CASE WHEN cnpj_terceiro = ? AND cnpj_terceiro != '*' THEN 1 ELSE 0 END DESC,
            CASE WHEN cest != '' AND cest = ? THEN 1 ELSE 0 END DESC,
            CASE WHEN origem_mercadoria = ? THEN 1 ELSE 0 END DESC,
            vigencia_inicio DESC,
            id DESC
        LIMIT 1
    """
    params = [
        uf_terceiro.upper(),
        ncm,
        cest,
        cnpj_terceiro,
        tipo_entrada,
        origem_mercadoria,
        ref,
        ref,
        cnpj_terceiro,
        cest,
        origem_mercadoria,
    ]
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row is not None else None


def buscar_regra_servico(
    conn: sqlite3.Connection,
    *,
    cnae: str,
    municipio_prestacao_ibge: str,
    codigo_servico_lc116: str = "",
    natureza_operacao_servico: str = "PRESTACAO",
    data_referencia: date | str | None = None,
) -> dict[str, Any] | None:
    """Busca regra ativa de serviços (ISS + PIS/COFINS + CSRF) por CNAE/Município."""
    ref = _iso_date(data_referencia)

    sql = """
        SELECT *
        FROM regras_servicos
        WHERE status_registro = 'ATIVA'
          AND cnae = ?
          AND municipio_prestacao_ibge = ?
          AND natureza_operacao_servico = ?
          AND (codigo_servico_lc116 = ? OR codigo_servico_lc116 IS NULL OR codigo_servico_lc116 = '')
          AND vigencia_inicio <= ?
          AND (vigencia_fim IS NULL OR vigencia_fim >= ?)
          AND status_validacao != 'REJEITADO'
        ORDER BY
            CASE WHEN codigo_servico_lc116 = ? THEN 1 ELSE 0 END DESC,
            vigencia_inicio DESC,
            id DESC
        LIMIT 1
    """
    params = [
        cnae,
        municipio_prestacao_ibge,
        natureza_operacao_servico,
        codigo_servico_lc116,
        ref,
        ref,
        codigo_servico_lc116,
    ]
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row is not None else None


def registrar_historico(
    conn: sqlite3.Connection,
    *,
    tabela_origem: str,
    registro_id: int,
    acao: str,
    usuario: str,
    campo: str | None = None,
    valor_anterior: str | None = None,
    valor_novo: str | None = None,
    motivo: str | None = None,
    auto_commit: bool = True,
) -> int:
    """Insere um registro append-only na tabela historico_alteracoes."""
    cur = conn.execute(
        """
        INSERT INTO historico_alteracoes (
            tabela_origem, registro_id, acao, campo,
            valor_anterior, valor_novo, motivo, usuario
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tabela_origem,
            registro_id,
            acao,
            campo,
            valor_anterior,
            valor_novo,
            motivo,
            usuario,
        ),
    )
    if auto_commit:
        conn.commit()
    return int(cur.lastrowid)


def atualizar_regra_com_lock(
    conn: sqlite3.Connection,
    *,
    tabela: str,
    registro_id: int,
    versao_atual: int,
    alteracoes: dict[str, Any],
    usuario: str,
    motivo: str | None = None,
) -> int:
    """Atualiza uma regra usando optimistic locking e grava diff campo-a-campo na mesma transação.

    Retorna a nova versão do registro.
    """
    _validar_tabela(tabela)
    if not alteracoes:
        raise ValueError("Nenhuma alteração informada.")

    campos_invalidos = set(alteracoes.keys()) & CAMPOS_PROTEGIDOS
    if campos_invalidos:
        raise ValueError(f"Campos protegidos não podem ser alterados diretamente: {sorted(campos_invalidos)}")

    with conn:
        atual = conn.execute(f"SELECT * FROM {tabela} WHERE id = ?", (registro_id,)).fetchone()
        if atual is None:
            raise LookupError(f"Registro {registro_id} não encontrado em {tabela}.")

        colunas_validas = set(atual.keys())
        desconhecidas = set(alteracoes.keys()) - colunas_validas
        if desconhecidas:
            raise ValueError(f"Colunas inexistentes em {tabela}: {sorted(desconhecidas)}")

        if int(atual["versao"]) != versao_atual:
            raise OptimisticLockError(
                f"Conflito de versão em {tabela}#{registro_id}: esperada {versao_atual}, atual {atual['versao']}."
            )

        diffs: list[tuple[str, str | None, str | None]] = []
        campos_update: list[str] = []
        valores_update: list[Any] = []

        for campo, novo_valor in alteracoes.items():
            valor_antigo = atual[campo]
            if valor_antigo != novo_valor:
                diffs.append(
                    (
                        campo,
                        None if valor_antigo is None else str(valor_antigo),
                        None if novo_valor is None else str(novo_valor),
                    )
                )
            campos_update.append(f"{campo} = ?")
            valores_update.append(novo_valor)

        if not diffs:
            return versao_atual

        set_clause = ", ".join(campos_update) + ", versao = versao + 1, atualizado_em = datetime('now')"
        valores_update.extend([registro_id, versao_atual])

        cur = conn.execute(
            f"UPDATE {tabela} SET {set_clause} WHERE id = ? AND versao = ?",
            valores_update,
        )
        if cur.rowcount != 1:
            raise OptimisticLockError(
                f"Falha de concorrência ao atualizar {tabela}#{registro_id} (versão {versao_atual})."
            )

        for campo, val_ant, val_nov in diffs:
            registrar_historico(
                conn,
                tabela_origem=tabela,
                registro_id=registro_id,
                acao="EDICAO",
                usuario=usuario,
                campo=campo,
                valor_anterior=val_ant,
                valor_novo=val_nov,
                motivo=motivo,
                auto_commit=False,
            )

        return versao_atual + 1


def soft_delete_regra(
    conn: sqlite3.Connection,
    *,
    tabela: str,
    registro_id: int,
    versao_atual: int,
    usuario: str,
    motivo: str,
    vigencia_fim: str | None = None,
) -> int:
    """Realiza soft delete (status_registro = 'EXCLUIDA') com optimistic locking e histórico."""
    _validar_tabela(tabela)
    with conn:
        atual = conn.execute(f"SELECT * FROM {tabela} WHERE id = ?", (registro_id,)).fetchone()
        if atual is None:
            raise LookupError(f"Registro {registro_id} não encontrado em {tabela}.")
        if int(atual["versao"]) != versao_atual:
            raise OptimisticLockError(
                f"Conflito de versão em {tabela}#{registro_id}: esperada {versao_atual}, atual {atual['versao']}."
            )

        novo_vig_fim = vigencia_fim or date.today().isoformat()
        cur = conn.execute(
            f"""
            UPDATE {tabela}
            SET status_registro = 'EXCLUIDA',
                vigencia_fim = COALESCE(vigencia_fim, ?),
                versao = versao + 1,
                atualizado_em = datetime('now')
            WHERE id = ? AND versao = ?
            """,
            (novo_vig_fim, registro_id, versao_atual),
        )
        if cur.rowcount != 1:
            raise OptimisticLockError(
                f"Falha de concorrência ao excluir logicamente {tabela}#{registro_id}."
            )

        registrar_historico(
            conn,
            tabela_origem=tabela,
            registro_id=registro_id,
            acao="EXCLUSAO",
            usuario=usuario,
            campo="status_registro",
            valor_anterior=str(atual["status_registro"]),
            valor_novo="EXCLUIDA",
            motivo=motivo,
            auto_commit=False,
        )
        return versao_atual + 1
