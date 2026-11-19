"""Schema, carga homologada e consultas determinísticas da Fase 2 (cBenef UF & Protocolos ST Bilaterais)."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import date
from typing import Any

from src.legislation.url_guard import validar_url_oficial


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _limpar_digitos(valor: str) -> str:
    return re.sub(r"\D", "", str(valor or ""))


SEED_CBENEF_UF: tuple[dict[str, Any], ...] = (
    # SP — Portaria SRE 70/2025
    {
        "uf": "SP",
        "codigo_cbenef": "SP020003",
        "descricao": "Redução de BC — Cesta Básica / Leite e Derivados (Anexo II Art. 3º RICMS/SP)",
        "cst_permitidos": "020,070",
        "dispositivo_legal": "RICMS/SP Anexo II Art. 3º + Portaria SRE 70/2025",
        "ncms_vinculados": "0401,0402,0405,0406",
        "vigencia_inicio": "2025-10-01",
        "vigencia_fim": None,
        "fonte_url": "https://portal.fazenda.sp.gov.br/servicos/nfe/Paginas/cBenef.aspx",
    },
    {
        "uf": "SP",
        "codigo_cbenef": "SP020012",
        "descricao": "Redução de BC — Máquinas e Implementos Agrícolas/Industriais (Conv. ICMS 52/91)",
        "cst_permitidos": "020,070",
        "dispositivo_legal": "RICMS/SP Anexo II Art. 12 + Convênio ICMS 52/91",
        "ncms_vinculados": "8432,8433,8424",
        "vigencia_inicio": "2025-10-01",
        "vigencia_fim": None,
        "fonte_url": "https://portal.fazenda.sp.gov.br/servicos/nfe/Paginas/cBenef.aspx",
    },
    {
        "uf": "SP",
        "codigo_cbenef": "SP040001",
        "descricao": "Isenção — Insumos Agropecuários / Hortifrutigranjeiros (Anexo I RICMS/SP)",
        "cst_permitidos": "030,040,041",
        "dispositivo_legal": "RICMS/SP Anexo I Art. 36 / Convênio ICMS 100/97",
        "ncms_vinculados": "07,08,2309,3101",
        "vigencia_inicio": "2025-10-01",
        "vigencia_fim": None,
        "fonte_url": "https://portal.fazenda.sp.gov.br/servicos/nfe/Paginas/cBenef.aspx",
    },
    {
        "uf": "SP",
        "codigo_cbenef": "SP050001",
        "descricao": "Diferimento — Operações Internas com Máquinas/Insumos Agrícolas (RICMS/SP)",
        "cst_permitidos": "051",
        "dispositivo_legal": "RICMS/SP Art. 350 / Art. 400-D + Portaria SRE 70/2025",
        "ncms_vinculados": "8432,8433",
        "vigencia_inicio": "2025-10-01",
        "vigencia_fim": None,
        "fonte_url": "https://portal.fazenda.sp.gov.br/servicos/nfe/Paginas/cBenef.aspx",
    },
    # PR
    {
        "uf": "PR",
        "codigo_cbenef": "PR820001",
        "descricao": "Redução de BC — Cesta Básica / Alimentos Essenciais (Anexo VI RICMS/PR)",
        "cst_permitidos": "020,070",
        "dispositivo_legal": "RICMS/PR Anexo VI + Tabela cBenef SEFA-PR",
        "ncms_vinculados": "0401,0405,1509,1905",
        "vigencia_inicio": "2024-01-01",
        "vigencia_fim": None,
        "fonte_url": "https://www.fazenda.pr.gov.br/Pagina/Legislacao-Tributaria",
    },
    {
        "uf": "PR",
        "codigo_cbenef": "PR800001",
        "descricao": "Isenção — Produtos Hortifrutigranjeiros e Insumos (Anexo V RICMS/PR)",
        "cst_permitidos": "030,040,041",
        "dispositivo_legal": "RICMS/PR Anexo V + Tabela cBenef SEFA-PR",
        "ncms_vinculados": "07,08,3004",
        "vigencia_inicio": "2024-01-01",
        "vigencia_fim": None,
        "fonte_url": "https://www.fazenda.pr.gov.br/Pagina/Legislacao-Tributaria",
    },
    # RS
    {
        "uf": "RS",
        "codigo_cbenef": "RS020001",
        "descricao": "Redução de BC — Mercadorias da Cesta Básica e Têxteis (RICMS/RS Art. 23)",
        "cst_permitidos": "020,070",
        "dispositivo_legal": "RICMS/RS Livro I Art. 23 + Tabela cBenef SEFAZ-RS",
        "ncms_vinculados": "0405,61,62,64",
        "vigencia_inicio": "2024-01-01",
        "vigencia_fim": None,
        "fonte_url": "https://www.sefaz.rs.gov.br/legislacao/",
    },
    {
        "uf": "RS",
        "codigo_cbenef": "RS040001",
        "descricao": "Isenção — Operações Internas Beneficiadas (RICMS/RS Livro I Art. 9º)",
        "cst_permitidos": "030,040,041",
        "dispositivo_legal": "RICMS/RS Livro I Art. 9º + Tabela cBenef SEFAZ-RS",
        "ncms_vinculados": "07,08,3004",
        "vigencia_inicio": "2024-01-01",
        "vigencia_fim": None,
        "fonte_url": "https://www.sefaz.rs.gov.br/legislacao/",
    },
    # RJ
    {
        "uf": "RJ",
        "codigo_cbenef": "RJ820001",
        "descricao": "Redução de BC — Cesta Básica / Convênio 52/91 com FECP (RICMS/RJ)",
        "cst_permitidos": "020,070",
        "dispositivo_legal": "Decreto 32.161/2002 RJ + Tabela cBenef SEFAZ-RJ",
        "ncms_vinculados": "0405,8432,8471",
        "vigencia_inicio": "2024-01-01",
        "vigencia_fim": None,
        "fonte_url": "https://www.fazenda.rj.gov.br/sefaz/faces/oracle/webcenter/portalapp/pages/navigation-renderer.jspx",
    },
    {
        "uf": "RJ",
        "codigo_cbenef": "RJ800001",
        "descricao": "Isenção — Medicamentos e Insumos Essenciais (RICMS/RJ)",
        "cst_permitidos": "030,040,041",
        "dispositivo_legal": "Manual de Benefícios Fiscais SEFAZ-RJ",
        "ncms_vinculados": "3003,3004",
        "vigencia_inicio": "2024-01-01",
        "vigencia_fim": None,
        "fonte_url": "https://www.fazenda.rj.gov.br/sefaz/faces/oracle/webcenter/portalapp/pages/navigation-renderer.jspx",
    },
    # SC
    {
        "uf": "SC",
        "codigo_cbenef": "SC820001",
        "descricao": "Redução de BC — Têxtil, Calçados e Convênio 52/91 (Anexo 2 RICMS/SC)",
        "cst_permitidos": "020,070",
        "dispositivo_legal": "RICMS/SC Anexo 2 + Tabela cBenef SEF-SC",
        "ncms_vinculados": "61,62,64,8432",
        "vigencia_inicio": "2024-01-01",
        "vigencia_fim": None,
        "fonte_url": "https://legislacao.sef.sc.gov.br/",
    },
    {
        "uf": "SC",
        "codigo_cbenef": "SC800001",
        "descricao": "Isenção — Operações Previstas no Anexo 2 Art. 1º a 6º (RICMS/SC)",
        "cst_permitidos": "030,040,041",
        "dispositivo_legal": "RICMS/SC Anexo 2 + Tabela cBenef SEF-SC",
        "ncms_vinculados": "07,08,3004",
        "vigencia_inicio": "2024-01-01",
        "vigencia_fim": None,
        "fonte_url": "https://legislacao.sef.sc.gov.br/",
    },
    # DF
    {
        "uf": "DF",
        "codigo_cbenef": "DF820001",
        "descricao": "Redução de BC — Caderno II Anexo I (RICMS/DF Dec. 18.955/1997)",
        "cst_permitidos": "020,070",
        "dispositivo_legal": "RICMS/DF Anexo I Caderno II + Tabela cBenef SEEC-DF",
        "ncms_vinculados": "0405,8471",
        "vigencia_inicio": "2024-01-01",
        "vigencia_fim": None,
        "fonte_url": "https://www.receita.fazenda.df.gov.br/legislacao",
    },
    # GO
    {
        "uf": "GO",
        "codigo_cbenef": "GO820001",
        "descricao": "Redução de BC — Anexo IX Art. 8º RCTE/GO",
        "cst_permitidos": "020,070",
        "dispositivo_legal": "RCTE/GO Anexo IX Art. 8º + Tabela cBenef ECONOMIA-GO",
        "ncms_vinculados": "0405,8432",
        "vigencia_inicio": "2024-01-01",
        "vigencia_fim": None,
        "fonte_url": "https://www.economia.go.gov.br/legislacao-tributaria",
    },
    # MG
    {
        "uf": "MG",
        "codigo_cbenef": "MG820001",
        "descricao": "Redução de BC — Parte 1 Anexo II RICMS/MG (Dec. 48.589/2023)",
        "cst_permitidos": "020,070",
        "dispositivo_legal": "RICMS/MG Dec. 48.589/2023 Anexo II + SEF-MG",
        "ncms_vinculados": "0405,61,62,8432",
        "vigencia_inicio": "2024-01-01",
        "vigencia_fim": None,
        "fonte_url": "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/",
    },
)


SEED_PROTOCOLOS_ST: tuple[dict[str, Any], ...] = (
    # Autopeças — Protocolo ICMS 41/2008 & 97/2010
    {
        "uf_origem": "SP",
        "uf_destino": "MG",
        "cest": "0100100",
        "ncm_prefixo": "850710",
        "descricao_segmento": "Autopeças — Acumuladores elétricos (baterias)",
        "ato_legal": "Protocolo ICMS 41/2008 + Convênio ICMS 142/2018",
        "possui_acordo_bilateral": 1,
        "mva_original": 71.78,
        "aliquota_interna_destino": 18.0,
        "fcp_destino": 0.0,
        "modalidade_base_st": "MVA",
        "pmpf_valor": None,
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": None,
        "observacao_legal": "Acordo bilateral vigente SP <-> MG para autopeças.",
    },
    {
        "uf_origem": "PR",
        "uf_destino": "SP",
        "cest": "0100100",
        "ncm_prefixo": "850710",
        "descricao_segmento": "Autopeças — Acumuladores elétricos (baterias)",
        "ato_legal": "Protocolo ICMS 41/2008 + Portaria SRE SP",
        "possui_acordo_bilateral": 1,
        "mva_original": 71.78,
        "aliquota_interna_destino": 18.0,
        "fcp_destino": 0.0,
        "modalidade_base_st": "MVA",
        "pmpf_valor": None,
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": None,
        "observacao_legal": "Acordo bilateral vigente PR -> SP para autopeças.",
    },
    {
        "uf_origem": "SC",
        "uf_destino": "SP",
        "cest": "0100100",
        "ncm_prefixo": "850710",
        "descricao_segmento": "Autopeças — Sem protocolo bilateral ativo SC -> SP (Antecipação)",
        "ato_legal": "RICMS/SP Art. 426-A (Antecipação Tributária na Entrada)",
        "possui_acordo_bilateral": 0,
        "mva_original": 71.78,
        "aliquota_interna_destino": 18.0,
        "fcp_destino": 0.0,
        "modalidade_base_st": "MVA",
        "pmpf_valor": None,
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": None,
        "observacao_legal": "SC denunciou protocolo de autopeças com SP; recolher antecipação na entrada em SP.",
    },
    # Eletrônicos / Smartphones — Protocolos 31/2009 / Revogação Portaria SRE 74/2025 em SP
    {
        "uf_origem": "SP",
        "uf_destino": "RJ",
        "cest": "2105300",
        "ncm_prefixo": "851713",
        "descricao_segmento": "Eletrônicos — Telefones celulares / Smartphones",
        "ato_legal": "Protocolo ICMS 136/2013 + RICMS/RJ + FECP 2%",
        "possui_acordo_bilateral": 1,
        "mva_original": 49.0,
        "aliquota_interna_destino": 20.0,
        "fcp_destino": 2.0,
        "modalidade_base_st": "MVA",
        "pmpf_valor": None,
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": None,
        "observacao_legal": "RJ inclui FECP de 2% no cálculo da MVA ajustada.",
    },
    {
        "uf_origem": "SP",
        "uf_destino": "SP",
        "cest": "2105300",
        "ncm_prefixo": "851713",
        "descricao_segmento": "Eletrônicos — Smartphones (Excluído da ST em SP pela Portaria SRE 74/2025)",
        "ato_legal": "Portaria CAT 68/2019 (Revogado em SP pela Portaria SRE 74/2025)",
        "possui_acordo_bilateral": 1,
        "mva_original": 49.0,
        "aliquota_interna_destino": 18.0,
        "fcp_destino": 0.0,
        "modalidade_base_st": "MVA",
        "pmpf_valor": None,
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": "2025-12-31",
        "observacao_legal": "Regime ST revogado em SP a partir de 01/01/2026.",
    },
    # Alimentos / Azeite (Revogado em SP pela Portaria SRE 74/2025) & Laticínios
    {
        "uf_origem": "SP",
        "uf_destino": "SP",
        "cest": "1700100",
        "ncm_prefixo": "150910",
        "descricao_segmento": "Alimentos — Azeite de oliva (Revogado da ST em SP)",
        "ato_legal": "Portaria CAT 68/2019 (Excluído pela Portaria SRE 74/2025)",
        "possui_acordo_bilateral": 1,
        "mva_original": 35.0,
        "aliquota_interna_destino": 18.0,
        "fcp_destino": 0.0,
        "modalidade_base_st": "MVA",
        "pmpf_valor": None,
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": "2025-12-31",
        "observacao_legal": "Excluído da ST em SP pela Portaria SRE 74/2025.",
    },
    {
        "uf_origem": "MG",
        "uf_destino": "SP",
        "cest": "1702100",
        "ncm_prefixo": "040510",
        "descricao_segmento": "Alimentos — Manteiga (Laticínios)",
        "ato_legal": "Protocolo ICMS 28/2009 + Portaria SRE SP",
        "possui_acordo_bilateral": 1,
        "mva_original": 32.0,
        "aliquota_interna_destino": 18.0,
        "fcp_destino": 0.0,
        "modalidade_base_st": "MVA",
        "pmpf_valor": None,
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": None,
        "observacao_legal": "Acordo bilateral MG -> SP com redução de BC interna em SP (CST 070 + SP020003).",
    },
    # Bebidas — PMPF / MVA
    {
        "uf_origem": "SP",
        "uf_destino": "PR",
        "cest": "0300700",
        "ncm_prefixo": "220210",
        "descricao_segmento": "Bebidas — Águas e refrigerantes",
        "ato_legal": "Protocolo ICMS 11/1991 + RICMS/PR Anexo IX",
        "possui_acordo_bilateral": 1,
        "mva_original": 70.0,
        "aliquota_interna_destino": 19.5,
        "fcp_destino": 0.0,
        "modalidade_base_st": "MVA",
        "pmpf_valor": None,
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": None,
        "observacao_legal": "Acordo nacional Protocolo ICMS 11/91 vigente SP -> PR.",
    },
    # Medicamentos — Convênio ICMS 234/2017 / PMC
    {
        "uf_origem": "GO",
        "uf_destino": "DF",
        "cest": "1300100",
        "ncm_prefixo": "300490",
        "descricao_segmento": "Medicamentos — Lista positiva/negativa/neutra",
        "ato_legal": "Convênio ICMS 234/2017 + RICMS/DF",
        "possui_acordo_bilateral": 1,
        "mva_original": 38.24,
        "aliquota_interna_destino": 20.0,
        "fcp_destino": 0.0,
        "modalidade_base_st": "MVA",
        "pmpf_valor": None,
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": None,
        "observacao_legal": "Acordo interestadual de medicamentos GO -> DF.",
    },
    # Perfumaria / Higiene
    {
        "uf_origem": "SP",
        "uf_destino": "RS",
        "cest": "2000100",
        "ncm_prefixo": "330300",
        "descricao_segmento": "Perfumaria e Higiene Pessoal",
        "ato_legal": "Protocolo ICMS 98/2009 + RICMS/RS Apêndice II",
        "possui_acordo_bilateral": 1,
        "mva_original": 57.5,
        "aliquota_interna_destino": 17.0,
        "fcp_destino": 0.0,
        "modalidade_base_st": "MVA",
        "pmpf_valor": None,
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": None,
        "observacao_legal": "Protocolo vigente SP -> RS para cosméticos e perfumaria.",
    },
    # Materiais de Construção
    {
        "uf_origem": "SP",
        "uf_destino": "SC",
        "cest": "1000100",
        "ncm_prefixo": "391723",
        "descricao_segmento": "Materiais de Construção — Tubos e conexões",
        "ato_legal": "Protocolo ICMS 196/2009 + RICMS/SC Anexo 3",
        "possui_acordo_bilateral": 1,
        "mva_original": 42.0,
        "aliquota_interna_destino": 17.0,
        "fcp_destino": 0.0,
        "modalidade_base_st": "MVA",
        "pmpf_valor": None,
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": None,
        "observacao_legal": "Protocolo vigente SP -> SC para materiais de construção.",
    },
)


def garantir_tabelas_fase2(conn: sqlite3.Connection) -> None:
    """Garante a existência das tabelas da Fase 2 mesmo em bancos pré-existentes."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tabela_cbenef_uf (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            uf                  TEXT NOT NULL,
            codigo_cbenef       TEXT NOT NULL,
            descricao           TEXT NOT NULL,
            cst_permitidos      TEXT NOT NULL,
            dispositivo_legal   TEXT NOT NULL,
            ncms_vinculados     TEXT NOT NULL DEFAULT '',
            vigencia_inicio     TEXT NOT NULL,
            vigencia_fim        TEXT,
            fonte_url           TEXT NOT NULL,
            hash_sha256         TEXT NOT NULL,
            UNIQUE (uf, codigo_cbenef, vigencia_inicio)
        );
        CREATE INDEX IF NOT EXISTS idx_cbenef_uf_busca
            ON tabela_cbenef_uf (uf, codigo_cbenef, vigencia_inicio, vigencia_fim);

        CREATE TABLE IF NOT EXISTS matriz_protocolos_st (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            uf_origem                   TEXT NOT NULL,
            uf_destino                  TEXT NOT NULL,
            cest                        TEXT NOT NULL DEFAULT '',
            ncm_prefixo                 TEXT NOT NULL,
            descricao_segmento          TEXT NOT NULL,
            ato_legal                   TEXT NOT NULL,
            possui_acordo_bilateral     INTEGER NOT NULL DEFAULT 1 CHECK (possui_acordo_bilateral IN (0, 1)),
            mva_original                REAL NOT NULL DEFAULT 0.0,
            aliquota_interna_destino    REAL NOT NULL DEFAULT 18.0,
            fcp_destino                 REAL NOT NULL DEFAULT 0.0,
            modalidade_base_st          TEXT NOT NULL DEFAULT 'MVA' CHECK (modalidade_base_st IN ('MVA', 'PMPF', 'PAUTA')),
            pmpf_valor                  REAL,
            vigencia_inicio             TEXT NOT NULL,
            vigencia_fim                TEXT,
            observacao_legal            TEXT NOT NULL DEFAULT '',
            UNIQUE (uf_origem, uf_destino, cest, ncm_prefixo, vigencia_inicio)
        );
        CREATE INDEX IF NOT EXISTS idx_protocolos_st_busca
            ON matriz_protocolos_st (uf_origem, uf_destino, ncm_prefixo, cest, vigencia_inicio, vigencia_fim);
        """
    )


def garantir_carga_fase2(conn: sqlite3.Connection) -> dict[str, int]:
    """Insere de forma idempotente as cargas homologadas de cBenef por UF e Protocolos ST."""
    garantir_tabelas_fase2(conn)
    cbenef_ins = 0
    proto_ins = 0
    with conn:
        for item in SEED_CBENEF_UF:
            url = validar_url_oficial(str(item["fonte_url"]))
            h = _sha256(f"{item['uf']}|{item['codigo_cbenef']}|{item['cst_permitidos']}|{item['dispositivo_legal']}")
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO tabela_cbenef_uf (
                    uf, codigo_cbenef, descricao, cst_permitidos, dispositivo_legal,
                    ncms_vinculados, vigencia_inicio, vigencia_fim, fonte_url, hash_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["uf"],
                    item["codigo_cbenef"],
                    item["descricao"],
                    item["cst_permitidos"],
                    item["dispositivo_legal"],
                    item["ncms_vinculados"],
                    item["vigencia_inicio"],
                    item["vigencia_fim"],
                    url,
                    h,
                ),
            )
            cbenef_ins += int(cur.rowcount or 0)

        for p in SEED_PROTOCOLOS_ST:
            cur_p = conn.execute(
                """
                INSERT OR IGNORE INTO matriz_protocolos_st (
                    uf_origem, uf_destino, cest, ncm_prefixo, descricao_segmento,
                    ato_legal, possui_acordo_bilateral, mva_original, aliquota_interna_destino,
                    fcp_destino, modalidade_base_st, pmpf_valor, vigencia_inicio, vigencia_fim, observacao_legal
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p["uf_origem"],
                    p["uf_destino"],
                    p["cest"],
                    p["ncm_prefixo"],
                    p["descricao_segmento"],
                    p["ato_legal"],
                    p["possui_acordo_bilateral"],
                    p["mva_original"],
                    p["aliquota_interna_destino"],
                    p["fcp_destino"],
                    p["modalidade_base_st"],
                    p["pmpf_valor"],
                    p["vigencia_inicio"],
                    p["vigencia_fim"],
                    p["observacao_legal"],
                ),
            )
            proto_ins += int(cur_p.rowcount or 0)

    return {"cbenef_inseridos": cbenef_ins, "protocolos_inseridos": proto_ins}


def consultar_cbenef_uf(
    conn: sqlite3.Connection,
    *,
    uf: str,
    cst: str = "",
    ncm: str = "",
    data_operacao: str | None = None,
) -> list[dict[str, Any]]:
    """Consulta códigos cBenef vigentes na UF compatíveis com CST e NCM na data da operação."""
    garantir_carga_fase2(conn)
    data_ref = data_operacao or date.today().isoformat()
    uf_u = uf.strip().upper()
    cst_norm = cst.strip().zfill(2) if cst.strip() and len(cst.strip()) <= 2 else cst.strip()
    cst_3 = f"0{cst_norm}" if len(cst_norm) == 2 else cst_norm
    ncm_dig = _limpar_digitos(ncm)

    rows = conn.execute(
        """
        SELECT * FROM tabela_cbenef_uf
        WHERE uf = ?
          AND vigencia_inicio <= ?
          AND (vigencia_fim IS NULL OR vigencia_fim = '' OR vigencia_fim >= ?)
        ORDER BY codigo_cbenef ASC
        """,
        (uf_u, data_ref, data_ref),
    ).fetchall()

    resultados: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        permitidos = {c.strip() for c in str(d["cst_permitidos"]).split(",") if c.strip()}
        if cst_3 and cst_3 not in permitidos and cst_norm not in permitidos:
            continue
        ncms_vinc = [x.strip() for x in str(d.get("ncms_vinculados") or "").split(",") if x.strip()]
        if ncm_dig and ncms_vinc and not any(ncm_dig.startswith(pref) for pref in ncms_vinc):
            # Mantém mesmo sem match exato de prefixo como segunda prioridade, marcando afinidade
            d["afinidade_ncm"] = False
        else:
            d["afinidade_ncm"] = True
        resultados.append(d)

    resultados.sort(key=lambda x: (not x["afinidade_ncm"], x["codigo_cbenef"]))
    return resultados


def consultar_protocolo_st(
    conn: sqlite3.Connection,
    *,
    uf_origem: str,
    uf_destino: str,
    ncm: str,
    cest: str = "",
    data_operacao: str | None = None,
) -> dict[str, Any] | None:
    """Consulta Protocolo/Convênio ST vigente na data da operação para (uf_origem, uf_destino, ncm/cest)."""
    garantir_carga_fase2(conn)
    data_ref = data_operacao or date.today().isoformat()
    uf_o = uf_origem.strip().upper()
    uf_d = uf_destino.strip().upper()
    ncm_dig = _limpar_digitos(ncm)
    cest_dig = _limpar_digitos(cest)

    rows = conn.execute(
        """
        SELECT * FROM matriz_protocolos_st
        WHERE uf_origem = ? AND uf_destino = ?
          AND vigencia_inicio <= ?
          AND (vigencia_fim IS NULL OR vigencia_fim = '' OR vigencia_fim >= ?)
        ORDER BY length(ncm_prefixo) DESC, id DESC
        """,
        (uf_o, uf_d, data_ref, data_ref),
    ).fetchall()

    for r in rows:
        pref = _limpar_digitos(str(r["ncm_prefixo"] or ""))
        cest_row = _limpar_digitos(str(r["cest"] or ""))
        if cest_dig and cest_row and cest_dig == cest_row:
            return dict(r)
        if ncm_dig and pref and ncm_dig.startswith(pref):
            return dict(r)
    return None
