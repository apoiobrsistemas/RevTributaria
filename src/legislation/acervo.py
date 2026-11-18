"""Acervo interno indexado de documentações fiscais oficiais e parser de NTs."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from src.legislation.extractor import hash_conteudo_limpo
from src.legislation.url_guard import validar_url_oficial

ACERVO_INICIAL: list[dict[str, str]] = [
    {
        "codigo_ato": "PORTARIA-SRE-70-2025",
        "titulo": "Portaria SRE 70/2025 — Obrigatoriedade e Trava CST x cBenef em SP",
        "esfera": "ESTADUAL_SP",
        "tipo_documento": "Portaria SRE",
        "status_norma": "VIGENTE",
        "vigencia_inicio": "2025-10-01",
        "vigencia_fim": "",
        "url_oficial": "https://portal.fazenda.sp.gov.br/servicos/nfe/Paginas/cBenef.aspx",
        "artigos_chave": "Art. 1º ao 4º; Tabela cBenef SP (SP01, SP02, SP03, SP04, SP05, SP09)",
        "ncms_impactados": "04051000,15171000,02013000,84713012,84716053,61091000,84321000",
        "regras_xml": "Tag <cBenef> obrigatória para CST 20, 30, 40, 41, 50, 51, 70, 90; vedada em CST 00, 10, 60.",
        "codigos_erro_sefaz": "930,931,932",
        "texto_literal": "Fica obrigatória a informação do Código de Benefício Fiscal (cBenef) na NF-e e NFC-e conforme compatibilidade entre CST e código de benefício divulgada pela SEFAZ-SP.",
    },
    {
        "codigo_ato": "PORTARIA-SRE-74-2025",
        "titulo": "Portaria SRE 74/2025 — Exclusão de Azeites de Oliva da ST em SP",
        "esfera": "ESTADUAL_SP",
        "tipo_documento": "Portaria SRE",
        "status_norma": "VIGENTE",
        "vigencia_inicio": "2025-10-01",
        "vigencia_fim": "",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/Portarias.aspx",
        "artigos_chave": "Art. 1º (altera Portaria CAT 68/2019 Anexo XVI); Art. 272-A RICMS/SP",
        "ncms_impactados": "15091000,15092000,15099000",
        "regras_xml": "NCM 1509.10.00 sem retenção de ICMS-ST em SP; tributação normal CST 00/20.",
        "codigos_erro_sefaz": "",
        "texto_literal": "Exclui os azeites de oliva (NCM 1509) do regime de substituição tributária no Estado de São Paulo a partir de 01/10/2025.",
    },
    {
        "codigo_ato": "PORTARIA-CAT-68-2019",
        "titulo": "Portaria CAT 68/2019 — Lista Consolidada de Mercadorias com ST em SP",
        "esfera": "ESTADUAL_SP",
        "tipo_documento": "Portaria SRE",
        "status_norma": "ALTERADA",
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": "",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/pcat682019.aspx",
        "artigos_chave": "Anexos I a XXII; Art. 313-A a 313-Z20 RICMS/SP",
        "ncms_impactados": "04051000,15171000,21032010,30049099,84713012,39241000,87082999,22021000,85071090,33030010",
        "regras_xml": "Exige tag <CEST> de 7 dígitos, <vBCST>, <pMVAST>, <vICMSST> ou <vBCEfet>/<vICMSEfet> no CST 60.",
        "codigos_erro_sefaz": "806,854,855",
        "texto_literal": "Divulga a relação de mercadorias sujeitas ao regime da substituição tributária com retenção antecipada do imposto no Estado de São Paulo.",
    },
    {
        "codigo_ato": "RICMS-SP-DEC-45490-2000",
        "titulo": "RICMS/SP Decreto 45.490/2000 — Alíquotas, Isenções (Anexo I) e Reduções (Anexo II)",
        "esfera": "ESTADUAL_SP",
        "tipo_documento": "Decreto",
        "status_norma": "VIGENTE",
        "vigencia_inicio": "2001-01-01",
        "vigencia_fim": "",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/RICMS.aspx",
        "artigos_chave": "Art. 52 (18%), Art. 54 (Genéricos 12%), Anexo I, Anexo II Art. 3º/27/52/74, Anexo III Art. 41/43",
        "ncms_impactados": "04051000,15171000,02013000,84716053,61091000,64039990,30049099",
        "regras_xml": "CST 00/20/40/41/51 conforme enquadramento no corpo e Anexos I, II e III.",
        "codigos_erro_sefaz": "528,610",
        "texto_literal": "Aprova o Regulamento do Imposto sobre Operações Relativas à Circulação de Mercadorias e sobre Prestações de Serviços de Transporte Interestadual e Intermunicipal e de Comunicação - RICMS.",
    },
    {
        "codigo_ato": "CONVENIO-ICMS-142-2018",
        "titulo": "Convênio ICMS 142/2018 — Regras Gerais de ST e Tabela CEST Nacional",
        "esfera": "CONFAZ",
        "tipo_documento": "Convênio ICMS",
        "status_norma": "VIGENTE",
        "vigencia_inicio": "2019-01-01",
        "vigencia_fim": "",
        "url_oficial": "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18",
        "artigos_chave": "Cláusula 6ª a 26ª; Anexos II a XXVI (CEST x NCM)",
        "ncms_impactados": "04051000,15171000,21032010,30049099,39241000,87082999,22021000,85071090,33030010",
        "regras_xml": "Tag <CEST> obrigatória em operações com mercadorias listadas nos Anexos do Convênio.",
        "codigos_erro_sefaz": "806",
        "texto_literal": "Dispõe sobre os regimes de substituição tributária e de antecipação de recolhimento do ICMS com encerramento de tributação, relativos ao imposto devido pelas operações subsequentes.",
    },
    {
        "codigo_ato": "CONVENIO-ICMS-109-2024-ADC49",
        "titulo": "Convênio ICMS 109/2024 & ADC 49 STF — Transferências entre Filiais",
        "esfera": "CONFAZ",
        "tipo_documento": "Convênio ICMS",
        "status_norma": "VIGENTE",
        "vigencia_inicio": "2024-11-01",
        "vigencia_fim": "",
        "url_oficial": "https://www.confaz.fazenda.gov.br/legislacao/convenios",
        "artigos_chave": "Cláusula 1ª a 6ª; LC 204/2023; ADC 49 STF",
        "ncms_impactados": "*",
        "regras_xml": "CFOPs 1.152/2.152/5.152/6.152 com CST 41 (Não Tributada) e cBenef SP030007 em SP.",
        "codigos_erro_sefaz": "930",
        "texto_literal": "Dispõe sobre a remessa interestadual de bens e mercadorias entre estabelecimentos de mesma titularidade sem incidência do ICMS, assegurada a transferência de crédito.",
    },
    {
        "codigo_ato": "NT-2024-001-NFE",
        "titulo": "Nota Técnica NF-e 2024.001 — Criação do CRT 4 (MEI) e Regras de Validação",
        "esfera": "ENCAT",
        "tipo_documento": "Nota Técnica",
        "status_norma": "VIGENTE",
        "vigencia_inicio": "2024-09-02",
        "vigencia_fim": "",
        "url_oficial": "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=Iy/5Qol1YbE=",
        "artigos_chave": "Grupo <emit><CRT>; Regras de Validação CRT=4 (MEI)",
        "ncms_impactados": "*",
        "regras_xml": "CRT=4 exige CSOSN e bloqueia destaque de ICMS próprio e PIS/COFINS por item.",
        "codigos_erro_sefaz": "481,590,591",
        "texto_literal": "Altera o leiaute da NF-e e NFC-e para incluir o Código de Regime Tributário 4 - Simples Nacional - Microempreendedor Individual - MEI.",
    },
    {
        "codigo_ato": "NT-2025-002-IBSCBS",
        "titulo": "Nota Técnica NF-e 2025.002 — Adequação XML para IBS, CBS e Imposto Seletivo",
        "esfera": "ENCAT",
        "tipo_documento": "Nota Técnica",
        "status_norma": "VIGENTE",
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": "",
        "url_oficial": "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=Iy/5Qol1YbE=",
        "artigos_chave": "Grupo <IBSCBS>, <CST>, <cClassTrib>, <IS>; LC 214/2025",
        "ncms_impactados": "*",
        "regras_xml": "Validação de <cClassTrib> e <CST> IBS/CBS contra tabela oficial SVRS/RFB.",
        "codigos_erro_sefaz": "1001,1002,1003",
        "texto_literal": "Especifica as alterações nos leiautes da NF-e e NFC-e para atender à Reforma Tributária do Consumo (IBS, CBS e Imposto Seletivo).",
    },
    {
        "codigo_ato": "NT-2015-003-DIFAL",
        "titulo": "Nota Técnica NF-e 2015.003 — ICMS Interestadual Não Contribuinte (EC 87/2015)",
        "esfera": "ENCAT",
        "tipo_documento": "Nota Técnica",
        "status_norma": "VIGENTE",
        "vigencia_inicio": "2016-01-01",
        "vigencia_fim": "",
        "url_oficial": "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=Iy/5Qol1YbE=",
        "artigos_chave": "Grupo <ICMSUFDest>; ADI 5464 STF (Dispensa Simples Nacional)",
        "ncms_impactados": "*",
        "regras_xml": "CFOP 6.108 + <ICMSUFDest> obrigatório para CRT 2 e 3 em vendas interestaduais a Não Contribuinte.",
        "codigos_erro_sefaz": "693,694,698",
        "texto_literal": "Cria o grupo de tributação do ICMS para a UF de destino (ICMSUFDest) nas operações interestaduais destinadas a consumidor final não contribuinte.",
    },
    {
        "codigo_ato": "LC-214-2025",
        "titulo": "Lei Complementar 214/2025 — Institui IBS, CBS e Imposto Seletivo",
        "esfera": "FEDERAL",
        "tipo_documento": "Lei Complementar",
        "status_norma": "VIGENTE",
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": "",
        "url_oficial": "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm",
        "artigos_chave": "Anexo I (Cesta Básica 0%), Anexo VII (Alimentos 60%), Medicamentos, Imposto Seletivo",
        "ncms_impactados": "04051000,15091000,15171000,02013000,30049099,22021000,84321000",
        "regras_xml": "Define cClassTrib e percentuais de redução/alíquota zero para transição 2026–2033.",
        "codigos_erro_sefaz": "",
        "texto_literal": "Institui o Imposto sobre Bens e Serviços (IBS), a Contribuição Social sobre Bens e Serviços (CBS) e o Imposto Seletivo (IS).",
    },
    {
        "codigo_ato": "RC-SEFAZ-SP-CONSOLIDADAS",
        "titulo": "Respostas à Consulta SEFAZ-SP — Embalagem, Destinação e Exceções NCM",
        "esfera": "ESTADUAL_SP",
        "tipo_documento": "Resposta à Consulta",
        "status_norma": "VIGENTE",
        "vigencia_inicio": "2020-01-01",
        "vigencia_fim": "",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/Respostas-Consulta.aspx",
        "artigos_chave": "RC 24891/2022, RC 29110/2024, RC 26304/2022, RC 21988/2020, RC 28412/2023, DN CAT 05/2009",
        "ncms_impactados": "04051000,15171000,21032010,30049099,84713012,02013000,39241000,87082999",
        "regras_xml": "Critérios de peso/embalagem (<=1kg vs >1kg), uso automotivo exclusivo e PPB.",
        "codigos_erro_sefaz": "",
        "texto_literal": "Interpretações formais da Consultoria Tributária da SEFAZ-SP sobre aplicação de ST, redução de base de cálculo e exceções de descrição por NCM.",
    },
]


def garantir_acervo_documental(conn: sqlite3.Connection) -> dict[str, int]:
    """Popula e atualiza de forma idempotente o acervo documental oficial com hash SHA-256."""
    inseridos = 0
    atualizados = 0
    with conn:
        for doc in ACERVO_INICIAL:
            url = validar_url_oficial(doc["url_oficial"])
            digest = hash_conteudo_limpo(f"{doc['codigo_ato']}|{doc['texto_literal']}|{doc['regras_xml']}")
            existente = conn.execute(
                "SELECT id, hash_sha256 FROM acervo_documental WHERE codigo_ato = ?",
                (doc["codigo_ato"],),
            ).fetchone()
            if existente is None:
                conn.execute(
                    """
                    INSERT INTO acervo_documental (
                        codigo_ato, titulo, esfera, tipo_documento, status_norma,
                        vigencia_inicio, vigencia_fim, url_oficial, hash_sha256,
                        artigos_chave, ncms_impactados, regras_xml, codigos_erro_sefaz, texto_literal
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        doc["codigo_ato"],
                        doc["titulo"],
                        doc["esfera"],
                        doc["tipo_documento"],
                        doc["status_norma"],
                        doc["vigencia_inicio"],
                        doc["vigencia_fim"] or None,
                        url,
                        digest,
                        doc["artigos_chave"],
                        doc["ncms_impactados"],
                        doc["regras_xml"],
                        doc["codigos_erro_sefaz"],
                        doc["texto_literal"],
                    ),
                )
                inseridos += 1
            else:
                conn.execute(
                    """
                    UPDATE acervo_documental
                    SET titulo = ?, status_norma = ?, url_oficial = ?, hash_sha256 = ?,
                        artigos_chave = ?, ncms_impactados = ?, regras_xml = ?,
                        codigos_erro_sefaz = ?, texto_literal = ?, ultima_sincronizacao = datetime('now')
                    WHERE id = ?
                    """,
                    (
                        doc["titulo"],
                        doc["status_norma"],
                        url,
                        digest,
                        doc["artigos_chave"],
                        doc["ncms_impactados"],
                        doc["regras_xml"],
                        doc["codigos_erro_sefaz"],
                        doc["texto_literal"],
                        int(existente["id"]),
                    ),
                )
                atualizados += 1
    return {"total": len(ACERVO_INICIAL), "inseridos": inseridos, "atualizados": atualizados}


def buscar_acervo(
    conn: sqlite3.Connection,
    *,
    esfera: str = "",
    tipo_documento: str = "",
    status_norma: str = "",
    termo: str = "",
) -> list[dict[str, Any]]:
    """Busca instantânea no acervo por esfera, tipo, status, código de erro SEFAZ, NT ou NCM."""
    garantir_acervo_documental(conn)
    sql = "SELECT * FROM acervo_documental WHERE 1=1"
    params: list[Any] = []
    if esfera:
        sql += " AND esfera = ?"
        params.append(esfera.upper())
    if tipo_documento:
        sql += " AND tipo_documento = ?"
        params.append(tipo_documento)
    if status_norma:
        sql += " AND status_norma = ?"
        params.append(status_norma.upper())
    if termo.strip():
        t = termo.strip()
        t_dig = re.sub(r"\D", "", t)
        like = f"%{t}%"
        if len(t_dig) >= 4:
            like_dig = f"%{t_dig}%"
            sql += (
                " AND (codigo_ato LIKE ? OR titulo LIKE ? OR artigos_chave LIKE ? "
                "OR ncms_impactados LIKE ? OR ncms_impactados LIKE ? OR codigos_erro_sefaz LIKE ? OR texto_literal LIKE ?)"
            )
            params.extend([like, like, like, like, like_dig, like, like])
        else:
            sql += (
                " AND (codigo_ato LIKE ? OR titulo LIKE ? OR artigos_chave LIKE ? "
                "OR ncms_impactados LIKE ? OR codigos_erro_sefaz LIKE ? OR texto_literal LIKE ?)"
            )
            params.extend([like, like, like, like, like, like])
    sql += " ORDER BY vigencia_inicio DESC, id ASC"
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def parsear_notas_tecnicas_portal_nfe(html: str) -> list[dict[str, str]]:
    """Extrai referências de Notas Técnicas publicadas no HTML do Portal Nacional da NF-e/ENCAT."""
    nts: list[dict[str, str]] = []
    vistos: set[str] = set()
    for match in re.finditer(r"(Nota\s+T[ée]cnica\s+(\d{4}\.\d{3})[^<\n]{0,120})", html, flags=re.IGNORECASE):
        titulo = re.sub(r"\s+", " ", match.group(1)).strip()
        num = match.group(2)
        codigo = f"NT-{num.replace('.', '-')}-NFE"
        if codigo not in vistos:
            vistos.add(codigo)
            nts.append({"codigo_ato": codigo, "numero_nt": num, "titulo": titulo})
    return nts


def indexar_nts_portal_nfe(
    conn: sqlite3.Connection,
    html: str,
    *,
    url_oficial: str = "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=Iy/5Qol1YbE=",
) -> int:
    """Indexa Notas Técnicas extraídas do Portal NF-e no acervo_documental com SHA-256."""
    validar_url_oficial(url_oficial)
    nts = parsear_notas_tecnicas_portal_nfe(html)
    inseridas = 0
    with conn:
        for nt in nts:
            digest = hash_conteudo_limpo(f"{nt['codigo_ato']}|{nt['titulo']}")
            ex = conn.execute(
                "SELECT id FROM acervo_documental WHERE codigo_ato = ?",
                (nt["codigo_ato"],),
            ).fetchone()
            if ex is None:
                conn.execute(
                    """
                    INSERT INTO acervo_documental (
                        codigo_ato, titulo, esfera, tipo_documento, status_norma,
                        vigencia_inicio, url_oficial, hash_sha256, texto_literal
                    ) VALUES (?, ?, 'ENCAT', 'Nota Técnica', 'VIGENTE', date('now'), ?, ?, ?)
                    """,
                    (nt["codigo_ato"], nt["titulo"], url_oficial, digest, nt["titulo"]),
                )
                inseridas += 1
    return inseridas
