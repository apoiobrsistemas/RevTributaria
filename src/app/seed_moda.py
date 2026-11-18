"""Carga automatizada de até 500 NCMs reais de Moda a partir do Siscomex (.gov.br)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import openpyxl

from src.automation.official_ingestor import URL_SISCOMEX_NCM_JSON, parsear_siscomex_ncm_json
from src.database import DEFAULT_DB_PATH, init_db, registrar_historico
from src.legislation.parsers import baixar_url_oficial
from src.legislation.url_guard import validar_url_oficial

CAPITULOS_MODA = frozenset({"42", "60", "61", "62", "63", "64", "65", "71"})
POSICOES_MODA = frozenset({"3303", "3304", "3305", "9003", "9004", "9101", "9102", "9615"})

DEFAULT_MODA_XLSX = (
    Path(__file__).resolve().parent.parent.parent / "templates" / "carga_moda_500_ncms.xlsx"
)


def filtrar_ncms_moda(itens_siscomex: list[dict[str, Any]], limite: int = 500) -> list[dict[str, Any]]:
    """Filtra NCMs ativos dos capítulos e posições do segmento de Moda."""
    selecionados: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for item in itens_siscomex:
        ncm = str(item.get("ncm") or "")
        if len(ncm) != 8 or ncm in vistos:
            continue
        if ncm[:2] in CAPITULOS_MODA or ncm[:4] in POSICOES_MODA:
            vistos.add(ncm)
            selecionados.append(item)
            if len(selecionados) >= limite:
                break
    return selecionados


def exportar_planilha_moda(
    itens: list[dict[str, Any]],
    caminho: str | Path = DEFAULT_MODA_XLSX,
    *,
    uf_origem: str = "SP",
    uf_destino: str = "SP",
) -> Path:
    """Exporta os NCMs de Moda para planilha .xlsx pronta para carga/consulta."""
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Moda_500_NCMs"
    ws.append(
        [
            "uf_origem",
            "uf_destino",
            "ncm",
            "cest",
            "natureza_operacao",
            "operacao_com_contribuinte",
            "vigencia_inicio",
            "cfop",
            "cst_icms",
            "aliquota_icms",
            "reducao_base_icms",
            "tem_st",
            "margem_st",
            "aliquota_icms_st",
            "codigo_beneficio_fiscal",
            "dispositivo_legal",
        ]
    )
    for item in itens:
        ws.append(
            [
                uf_origem.upper(),
                uf_destino.upper(),
                item["ncm"],
                "",
                "VENDA",
                1,
                item.get("vigencia_inicio") or "2026-01-01",
                "5102",
                "00",
                18.0,
                0.0,
                0,
                0.0,
                0.0,
                "",
                f"Siscomex Moda: {str(item.get('descricao') or '')[:80]}",
            ]
        )
    wb.save(destino)
    return destino


def executar_carga_moda_siscomex(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    limite: int = 500,
    uf_origem: str = "SP",
    uf_destino: str = "SP",
    siscomex_bytes: bytes | None = None,
    gerar_xlsx: bool = True,
) -> dict[str, Any]:
    """Baixa NCMs oficiais do Siscomex, filtra até 500 de Moda e grava no SQLite."""
    validar_url_oficial(URL_SISCOMEX_NCM_JSON)
    raw = siscomex_bytes
    if raw is None:
        raw, _ = baixar_url_oficial(URL_SISCOMEX_NCM_JSON, timeout=30)

    todos = parsear_siscomex_ncm_json(raw)
    moda = filtrar_ncms_moda(todos, limite=limite)

    conn = init_db(db_path)
    try:
        federais_inseridas = 0
        estaduais_inseridas = 0

        with conn:
            for item in moda:
                ncm = item["ncm"]
                desc = item.get("descricao") or ""
                vig_ini = item.get("vigencia_inicio") or "2026-01-01"
                vig_fim = item.get("vigencia_fim")

                existe_fed = conn.execute(
                    "SELECT id FROM regras_federais WHERE ncm = ? AND ex_tipi = '' AND cest = '' AND status_registro = 'ATIVA'",
                    (ncm,),
                ).fetchone()
                if not existe_fed:
                    cur_f = conn.execute(
                        """
                        INSERT INTO regras_federais (
                            ncm, ex_tipi, cest, descricao_ncm, vigencia_inicio, vigencia_fim,
                            dispositivo_legal, status_validacao, aceito_por
                        ) VALUES (?, '', '', ?, ?, ?, 'Tabela NCM Siscomex (Moda)', 'ACEITO', 'seed_moda')
                        """,
                        (ncm, desc, vig_ini, vig_fim),
                    )
                    registrar_historico(
                        conn,
                        tabela_origem="regras_federais",
                        registro_id=int(cur_f.lastrowid),
                        acao="CRIACAO",
                        usuario="seed_moda",
                        campo="ncm",
                        valor_novo=ncm,
                        motivo="Carga automatizada Siscomex Moda",
                        auto_commit=False,
                    )
                    federais_inseridas += 1

                existe_est = conn.execute(
                    """
                    SELECT id FROM regras_estaduais_icms
                    WHERE uf_origem = ? AND uf_destino = ? AND ncm = ? AND status_registro = 'ATIVA'
                    """,
                    (uf_origem.upper(), uf_destino.upper(), ncm),
                ).fetchone()
                if not existe_est:
                    disp = f"Siscomex Moda: {desc[:100]}" if desc else "Carga Automática Siscomex - Moda"
                    cur_e = conn.execute(
                        """
                        INSERT INTO regras_estaduais_icms (
                            uf_origem, uf_destino, ncm, cest, natureza_operacao,
                            operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                            cfop, cst_icms, aliquota_icms, dispositivo_legal, status_validacao
                        ) VALUES (?, ?, ?, '', 'VENDA', 1, '*', ?, '5102', '00', 18.0, ?, 'A_CONFERIR')
                        """,
                        (uf_origem.upper(), uf_destino.upper(), ncm, vig_ini, disp),
                    )
                    registrar_historico(
                        conn,
                        tabela_origem="regras_estaduais_icms",
                        registro_id=int(cur_e.lastrowid),
                        acao="CRIACAO",
                        usuario="seed_moda",
                        campo="ncm",
                        valor_novo=ncm,
                        motivo=disp,
                        auto_commit=False,
                    )
                    estaduais_inseridas += 1

        if gerar_xlsx:
            exportar_planilha_moda(moda, uf_origem=uf_origem, uf_destino=uf_destino)

        return {
            "total_siscomex": len(todos),
            "selecionados_moda": len(moda),
            "federais_inseridas": federais_inseridas,
            "estaduais_inseridas": estaduais_inseridas,
        }
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga automatizada de 500 NCMs de Moda (Siscomex)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--limite", type=int, default=500)
    args = parser.parse_args(argv)

    res = executar_carga_moda_siscomex(args.db, limite=args.limite)
    print(f"[SEED MODA] Concluído: {res}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
