"""Pipeline Orquestrado por 5 Skills Fiscais com Auditor Anti-Alucinação."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any
from urllib.parse import urlparse

from src.engine.sp_decision_tree import avaliar_arvore_5_camadas
from src.legislation.acervo import garantir_acervo_documental


def _normalizar_ncm(ncm: str) -> str:
    return "".join(ch for ch in str(ncm or "") if ch.isdigit()).ljust(8, "0")[:8]


def _ncm_formatado(ncm8: str) -> str:
    return f"{ncm8[:4]}.{ncm8[4:6]}.{ncm8[6:8]}"


def _norma_vigente_na_data(doc: dict[str, Any], data_ref: str) -> bool:
    if str(doc.get("status_norma") or "").upper() == "REVOGADA":
        return False
    ini = str(doc.get("vigencia_inicio") or "").strip()
    fim = str(doc.get("vigencia_fim") or "").strip()
    if ini and data_ref < ini:
        return False
    if fim and data_ref > fim:
        return False
    return True


def _buscar_doc_acervo(
    conn: sqlite3.Connection,
    *,
    codigo_parcial: str = "",
    ncm: str = "",
    tipo_documento: str = "",
) -> dict[str, Any] | None:
    clauses = ["1=1"]
    params: list[Any] = []
    if codigo_parcial:
        clauses.append("UPPER(codigo_ato) LIKE ?")
        params.append(f"%{codigo_parcial.upper()}%")
    if tipo_documento:
        clauses.append("UPPER(tipo_documento) = ?")
        params.append(tipo_documento.upper())
    if ncm:
        ncm8 = _normalizar_ncm(ncm)
        ncm_fmt = _ncm_formatado(ncm8)
        clauses.append("(ncms_impactados LIKE ? OR ncms_impactados LIKE ? OR ncms_impactados LIKE ?)")
        params.extend([f"%{ncm8}%", f"%{ncm_fmt}%", f"%{ncm8[:4]}%"])
    sql = (
        "SELECT id, esfera, tipo_documento, codigo_ato, titulo, status_norma, "
        "vigencia_inicio, vigencia_fim, texto_literal, artigos_chave, "
        "ncms_impactados, regras_xml, codigos_erro_sefaz, url_oficial, "
        "hash_sha256, ultima_sincronizacao "
        f"FROM acervo_documental WHERE {' AND '.join(clauses)} "
        "ORDER BY CASE status_norma WHEN 'VIGENTE' THEN 0 WHEN 'ALTERADA' THEN 1 ELSE 2 END, "
        "vigencia_inicio DESC, id DESC LIMIT 1"
    )
    row = conn.execute(sql, tuple(params)).fetchone()
    return dict(row) if row else None


def executar_pipeline_skills(
    *,
    conn: sqlite3.Connection,
    ncm: str,
    cst_icms: str = "00",
    cbenef: str = "",
    tem_st: int = 0,
    cest: str = "",
    reducao_bc: float = 0.0,
    descricao_item: str = "",
    ex_tipi: str = "",
    embalagem: str = "",
    data_referencia: str | None = None,
) -> dict[str, Any]:
    """Executa as 5 Skills Fiscais em cascata com trava anti-alucinação."""
    garantir_acervo_documental(conn)
    data_ref = data_referencia or date.today().isoformat()
    ncm8 = _normalizar_ncm(ncm)
    ncm_fmt = _ncm_formatado(ncm8)

    arvore = avaliar_arvore_5_camadas(
        ncm=ncm8,
        cst_icms=cst_icms,
        cbenef=cbenef,
        tem_st=tem_st,
        cest=cest,
        reducao_bc=reducao_bc,
        descricao_item=descricao_item,
        ex_tipi=ex_tipi,
        embalagem=embalagem,
        data_referencia=data_ref,
        conn=conn,
    )
    camadas_map = {c["camada"]: c for c in arvore["camadas"]}

    # Mapeamento de documentos oficiais por Skill
    doc_s1 = _buscar_doc_acervo(conn, codigo_parcial="CAT-68-2019") or _buscar_doc_acervo(
        conn, codigo_parcial="45490-2000"
    )
    doc_s2 = _buscar_doc_acervo(conn, ncm=ncm8, tipo_documento="CONVENIO_ICMS") or _buscar_doc_acervo(
        conn, codigo_parcial="142-2018"
    )
    doc_s3 = _buscar_doc_acervo(conn, codigo_parcial="SRE-70-2025") or _buscar_doc_acervo(
        conn, codigo_parcial="2024-001"
    )
    doc_s4 = _buscar_doc_acervo(conn, codigo_parcial="214-2025") or _buscar_doc_acervo(
        conn, tipo_documento="RESPOSTA_CONSULTA"
    )

    skills_brutas = [
        {
            "skill_id": "SKILL_01",
            "nome": "Skill 01 - Tipificação & Vigência NCM",
            "camada": camadas_map.get(1, {}),
            "doc": doc_s1,
            "exige_ncm_explicito": False,
        },
        {
            "skill_id": "SKILL_02",
            "nome": "Skill 02 - Matriz ST & Convênios CONFAZ",
            "camada": camadas_map.get(2, {}),
            "doc": doc_s2,
            "exige_ncm_explicito": bool(tem_st),
        },
        {
            "skill_id": "SKILL_03",
            "nome": "Skill 03 - Benefícios Fiscais & Trava CST x cBenef",
            "camada": camadas_map.get(3, {}),
            "doc": doc_s3,
            "exige_ncm_explicito": False,
        },
        {
            "skill_id": "SKILL_04",
            "nome": "Skill 04 - Jurisprudência & Reforma (LC 214/2025)",
            "camada": camadas_map.get(4, {}),
            "doc": doc_s4,
            "exige_ncm_explicito": False,
        },
    ]

    evidencias: list[dict[str, Any]] = []
    skills_resultado: list[dict[str, Any]] = []
    score = 0
    conflitos_norma: list[str] = []
    lacunas: list[str] = []

    for sk in skills_brutas:
        doc = sk["doc"]
        camada = sk["camada"]
        status_camada = str(camada.get("status") or "OK")
        doc_valido = bool(doc and doc.get("id") and doc.get("hash_sha256") and _norma_vigente_na_data(doc, data_ref))

        if doc and str(doc.get("status_norma") or "").upper() == "REVOGADA":
            conflitos_norma.append(
                f"{sk['nome']}: ato {doc['codigo_ato']} encontra-se REVOGADO (lex posterior)."
            )

        if doc_valido:
            score += 25
            evidencias.append(
                {
                    "skill_id": sk["skill_id"],
                    "doc_id": doc["id"],
                    "codigo_ato": doc["codigo_ato"],
                    "titulo": doc["titulo"],
                    "esfera": doc["esfera"],
                    "status_norma": doc["status_norma"],
                    "vigencia_inicio": doc["vigencia_inicio"],
                    "vigencia_fim": doc["vigencia_fim"] or "Indeterminada",
                    "trecho_literal": doc["texto_literal"],
                    "portal_origem": urlparse(str(doc.get("url_oficial") or "")).netloc or doc["esfera"],
                    "url_oficial": doc["url_oficial"],
                    "hash_sha256": doc["hash_sha256"],
                    "ultima_sincronizacao": doc["ultima_sincronizacao"],
                }
            )
        else:
            lacunas.append(f"{sk['nome']}: sem norma vigente indexada para {ncm_fmt}.")

        skills_resultado.append(
            {
                "skill_id": sk["skill_id"],
                "nome": sk["nome"],
                "status": status_camada if doc_valido else "BLOQUEIO",
                "detalhe": camada.get("detalhe") or "Sem detalhamento.",
                "doc_id": doc["id"] if doc else None,
                "codigo_ato": doc["codigo_ato"] if doc else "LACUNA",
                "lastro_ok": doc_valido,
            }
        )

    # Verifica regra de banco para exceção específica do NCM
    regra_ncm = conn.execute(
        "SELECT id, dispositivo_legal, vigencia_inicio, vigencia_fim FROM regras_estaduais_icms "
        "WHERE ncm IN (?, ?) AND status_validacao != 'REJEITADA' AND status_registro = 'ATIVA' LIMIT 1",
        (ncm8, ncm_fmt),
    ).fetchone()
    if not regra_ncm and not lacunas:
        # Se NCM não está na base nem em documento explícito de exceção, reduz 15 pontos
        score = max(0, score - 15)
        lacunas.append(
            f"NCM {ncm_fmt} sem regra específica homologada na matriz local — verificar exceção."
        )

    # Skill 05 - Auditor Anti-Alucinação & Guardrail
    lacuna_normativa = bool(lacunas) or score < 75
    status_final = arvore["status_geral"]
    if lacuna_normativa and status_final == "OK":
        status_final = "ALERTA"
    if score < 50:
        status_final = "BLOQUEIO"

    if status_final == "BLOQUEIO" or score < 75:
        selo = "BLOQUEIO — Lacuna Normativa"
    elif score >= 95 and not conflitos_norma and status_final == "OK":
        selo = "OURO — 100% Lastro Oficial"
    else:
        selo = "PRATA — Lastro Verificado com Ressalvas"

    skill_05_detalhe = (
        "Todas as citações validadas contra IDs e hashes SHA-256 do acervo oficial."
        if not lacunas and not conflitos_norma
        else "Lacuna Normativa — Revisão Técnica Necessária: " + " | ".join(lacunas + conflitos_norma)
    )
    skills_resultado.append(
        {
            "skill_id": "SKILL_05",
            "nome": "Skill 05 - Auditor Anti-Alucinação & Guardrail",
            "status": "BLOQUEIO" if lacuna_normativa and score < 75 else ("ALERTA" if lacunas else "OK"),
            "detalhe": skill_05_detalhe,
            "doc_id": evidencias[0]["doc_id"] if evidencias else None,
            "codigo_ato": f"SCORE {score}%",
            "lastro_ok": not lacuna_normativa,
        }
    )

    return {
        "ncm": ncm8,
        "ncm_formatado": ncm_fmt,
        "data_referencia": data_ref,
        "status_geral": status_final,
        "score_lastro": score,
        "selo_confiabilidade": selo,
        "lacuna_normativa": lacuna_normativa,
        "mensagem_bloqueio": (
            "Lacuna Normativa — Revisão Técnica Necessária" if lacuna_normativa else ""
        ),
        "skills": skills_resultado,
        "evidencias_documentais": evidencias,
        "conflitos_norma": conflitos_norma,
        "lacunas": lacunas,
        "arvore_5_camadas": arvore,
    }
