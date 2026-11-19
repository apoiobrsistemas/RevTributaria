"""Ingestor Determinístico do Convênio ICMS 142/2018 (Anexos II a XXVIII) e Acordos CONFAZ."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from src.legislation.url_guard import validar_url_oficial

URL_CONVENIO_142 = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18"

# Base inicial estruturada dos Anexos II a XXVIII do Convênio ICMS 142/2018 (para operação offline/determinística)
_SEED_CONVENIO_142: tuple[tuple[str, str, str, str, str], ...] = (
    # (anexo, segmento_codigo, cest, ncm_limpo, descricao_item)
    ("Anexo II", "01", "0100100", "850710", "Acumuladores elétricos de chumbo (Autopeças)"),
    ("Anexo II", "01", "0100100", "85071090", "Baterias / Acumuladores elétricos de chumbo"),
    ("Anexo III", "02", "0200100", "2208", "Bebidas alcoólicas destiladas (Seg. 02 / Anexo III)"),
    ("Anexo IV", "03", "0300100", "2203", "Cervejas e chopes"),
    ("Anexo V", "04", "0400100", "2402", "Cigarros e produtos derivados do fumo"),
    ("Anexo VI", "05", "0500100", "2523", "Cimentos"),
    ("Anexo VII", "06", "0600100", "2710", "Combustíveis e lubrificantes"),
    ("Anexo XI", "10", "1000600", "39172300", "Tubos rígidos de polímeros de cloreto de vinila (PVC)"),
    ("Anexo XI", "10", "1000700", "39181000", "Revestimentos de pavimentos de polímeros de cloreto de vinila"),
    ("Anexo XI", "10", "1004700", "73083000", "Portas, janelas e seus caixilhos de ferro ou aço"),
    ("Anexo XII", "12", "1200400", "853650", "Interruptores, seccionadores e comutadores (Materiais Elétricos - Seg. 12)"),
    ("Anexo II", "01", "0105500", "853650", "Interruptores e comutadores de uso automotivo (Autopeças - Seg. 01)"),
    ("Anexo XIV", "13", "1300100", "3004", "Medicamentos de uso humano"),
    ("Anexo XVII", "16", "1600100", "4011", "Pneumáticos novos de borracha (Seg. 16)"),
    ("Anexo XVII", "16", "1600100", "401110", "Pneumáticos novos para automóveis de passageiros"),
    ("Anexo XVII", "16", "1600200", "401120", "Pneumáticos novos para ônibus ou caminhões"),
    ("Anexo XVIII", "17", "1705300", "19053100", "Biscoitos e bolachas derivados de farinha de trigo (waffles/wafers)"),
    ("Anexo XVIII", "17", "1705900", "19054000", "Torradas, pão torrado e produtos semelhantes torrados"),
    ("Anexo XXII", "21", "2105301", "85171300", "Telefones inteligentes (Smartphones) e terminais portáteis"),
    ("Anexo XXII", "21", "2103000", "84715010", "Unidades de processamento digital"),
    ("Anexo XXVI", "25", "2500100", "8703", "Veículos automotores novos"),
    ("Anexo XXVIII", "28", "2800100", "22083020", "Uísque (Bebidas Quentes - Anexo XXVIII)"),
)

_SEED_ACORDOS_ST: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    # (uf_origem, uf_destino, segmento_cest, ncm_prefixo, numero_acordo, tipo_acordo, observacao)
    ("*", "SP", "16", "4011", "Convênio ICMS 102/2017", "CONVENIO_NACIONAL", "Pneumáticos, câmaras de ar e protetores — Abrangência Nacional"),
    ("*", "*", "16", "4011", "Convênio ICMS 102/2017", "CONVENIO_NACIONAL", "Pneumáticos — Abrangência Nacional todas as UFs"),
    ("*", "*", "25", "8703", "Convênio ICMS 199/2017", "CONVENIO_NACIONAL", "Veículos Automotores Novos — Abrangência Nacional"),
    ("*", "*", "06", "2710", "Convênio ICMS 110/2007", "CONVENIO_NACIONAL", "Lubrificantes e Combustíveis — Abrangência Nacional"),
    ("*", "*", "13", "3004", "Convênio ICMS 234/2017", "CONVENIO_NACIONAL", "Medicamentos e Produtos Farmacêuticos — Abrangência Nacional"),
    ("*", "*", "04", "2402", "Convênio ICMS 76/1994", "CONVENIO_NACIONAL", "Cigarros e Derivados do Fumo — Abrangência Nacional"),
    ("MG", "SP", "17", "1905", "Protocolo ICMS 28/2009", "PROTOCOLO_BILATERAL", "Produtos Alimentícios MG -> SP"),
    ("MG", "SP", "01", "8507", "Protocolo ICMS 41/2008", "PROTOCOLO_BILATERAL", "Autopeças MG -> SP"),
    ("PR", "SP", "10", "3917", "Protocolo ICMS 32/2014", "PROTOCOLO_BILATERAL", "Materiais de Construção PR -> SP"),
)


def explodir_codigos_ncm(texto_ncm: str) -> list[str]:
    """Explode células com múltiplos NCMs (vírgula, ponto-e-vírgula, barra, quebra de linha) em dígitos limpos."""
    partes = re.split(r"[,;/\n\r]+", str(texto_ncm or ""))
    codigos: list[str] = []
    for parte in partes:
        encontrados = re.findall(r"\b(\d{4}(?:\.\d{2}(?:\.\d{2})?)?|\d{6}|\d{8}|\d{2})\b", parte.strip())
        for raw in encontrados:
            limpo = re.sub(r"\D", "", raw)
            if len(limpo) in {2, 4, 6, 8} and limpo not in codigos:
                codigos.append(limpo)
    return codigos


def parsear_convenio_142_texto(texto_ou_html: str) -> list[dict[str, Any]]:
    """Parseia Anexos II a XXVIII do Convênio ICMS 142/2018 explodindo múltiplos NCMs por linha."""
    texto_limpo = re.sub(r"<[^>]+>", " ", texto_ou_html)
    anexo_atual = "Anexo II"
    registros: list[dict[str, Any]] = []

    for raw_ln in texto_limpo.splitlines():
        ln = " ".join(raw_ln.split())
        if not ln:
            continue
        m_anexo = re.match(r"^(ANEXO\s+[IVXLCDM]+)\b", ln, re.I)
        if m_anexo:
            anexo_atual = m_anexo.group(1).title()
            continue

        m_cest = re.search(r"\b(\d{2}\.\d{3}\.\d{2})\b", ln)
        if not m_cest:
            continue
        cest_7 = re.sub(r"\D", "", m_cest.group(1))
        seg_cod = cest_7[:2]
        ln_sem_cest = ln[: m_cest.start()] + " " + ln[m_cest.end() :]
        ncms_brutos = re.findall(r"\b(\d{4}(?:\.\d{2}(?:\.\d{2})?)?|\d{6}|\d{8})\b", ln_sem_cest)
        ncms_explodidos: list[str] = []
        for n in ncms_brutos:
            n_d = re.sub(r"\D", "", n)
            if len(n_d) in {2, 4, 6, 8} and n_d not in ncms_explodidos:
                ncms_explodidos.append(n_d)
        for ncm_d in ncms_explodidos:
            registros.append(
                {
                    "anexo": anexo_atual,
                    "segmento_codigo": seg_cod,
                    "cest": cest_7,
                    "ncm_limpo": ncm_d,
                    "ncm_raw": ", ".join(ncms_brutos),
                    "tamanho_prefixo": len(ncm_d),
                    "descricao_item": ln[:240],
                    "bens_relacionados": "",
                    "fonte_url": URL_CONVENIO_142,
                }
            )
    return registros


def higienizar_convenio_142_sqlite(conn: sqlite3.Connection) -> dict[str, int]:
    """Saneia de forma idempotente registros já gravados em convenio_142_anexos (explode + normalização)."""
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(convenio_142_anexos)").fetchall()}
    if "tamanho_prefixo" not in cols:
        conn.execute("ALTER TABLE convenio_142_anexos ADD COLUMN tamanho_prefixo INTEGER NOT NULL DEFAULT 0")

    rows = conn.execute(
        "SELECT id, anexo, segmento_codigo, cest, ncm_limpo, ncm_raw, tamanho_prefixo, descricao_item, bens_relacionados, fonte_url FROM convenio_142_anexos"
    ).fetchall()
    atualizados = 0
    explodidos = 0
    for r in rows:
        row_id = r[0]
        anexo = str(r[1] or "")
        cest_7 = re.sub(r"\D", "", str(r[3] or ""))
        seg_cod = str(r[2] or cest_7[:2] or "")
        ncm_atual = str(r[4] or "")
        ncm_raw = str(r[5] or ncm_atual)
        tam_atual = int(r[6] or 0)
        desc = str(r[7] or "")
        bens = str(r[8] or "")
        fonte = str(r[9] or URL_CONVENIO_142)

        codigos = explodir_codigos_ncm(ncm_atual) or explodir_codigos_ncm(ncm_raw)
        if not codigos:
            cod_unico = re.sub(r"\D", "", ncm_atual)
            codigos = [cod_unico] if cod_unico else []
        if not codigos:
            continue

        primeiro = codigos[0]
        if ncm_atual != primeiro or str(r[3] or "") != cest_7 or tam_atual != len(primeiro):
            try:
                conn.execute(
                    """
                    UPDATE convenio_142_anexos
                    SET cest = ?, ncm_limpo = ?, tamanho_prefixo = ?, segmento_codigo = ?
                    WHERE id = ?
                    """,
                    (cest_7, primeiro, len(primeiro), seg_cod, row_id),
                )
                atualizados += 1
            except sqlite3.IntegrityError:
                pass

        for extra in codigos[1:]:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO convenio_142_anexos (
                    anexo, segmento_codigo, cest, ncm_limpo, ncm_raw, tamanho_prefixo,
                    descricao_item, bens_relacionados, fonte_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (anexo, seg_cod, cest_7, extra, ncm_raw, len(extra), desc, bens, fonte),
            )
            explodidos += int(cur.rowcount or 0)

    return {"atualizados": atualizados, "explodidos": explodidos}


def garantir_base_confaz_142_e_acordos(
    conn: sqlite3.Connection,
    *,
    texto_cv142: str | None = None,
) -> dict[str, int]:
    """Popula de forma idempotente convenio_142_anexos e acordos_interestaduais_st."""
    url_ok = validar_url_oficial(URL_CONVENIO_142)
    ins_142 = 0
    ins_ac = 0

    with conn:
        hig_stats = higienizar_convenio_142_sqlite(conn)
        for anexo, seg, cest, ncm_l, desc in _SEED_CONVENIO_142:
            ncm_d = re.sub(r"\D", "", ncm_l)
            cest_d = re.sub(r"\D", "", cest)
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO convenio_142_anexos (
                    anexo, segmento_codigo, cest, ncm_limpo, ncm_raw, tamanho_prefixo, descricao_item, fonte_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (anexo, seg, cest_d, ncm_d, ncm_l, len(ncm_d), desc, url_ok),
            )
            ins_142 += int(cur.rowcount or 0)

        if texto_cv142:
            for item in parsear_convenio_142_texto(texto_cv142):
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO convenio_142_anexos (
                        anexo, segmento_codigo, cest, ncm_limpo, ncm_raw, tamanho_prefixo, descricao_item, bens_relacionados, fonte_url
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["anexo"],
                        item["segmento_codigo"],
                        item["cest"],
                        item["ncm_limpo"],
                        item["ncm_raw"],
                        item["tamanho_prefixo"],
                        item["descricao_item"],
                        item["bens_relacionados"],
                        url_ok,
                    ),
                )
                ins_142 += int(cur.rowcount or 0)

        for uf_o, uf_d, seg, ncm_p, num_ac, tipo_ac, obs in _SEED_ACORDOS_ST:
            cur_a = conn.execute(
                """
                INSERT OR IGNORE INTO acordos_interestaduais_st (
                    uf_origem, uf_destino, segmento_cest, ncm_prefixo, numero_acordo,
                    tipo_acordo, observacao, fonte_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (uf_o, uf_d, seg, ncm_p, num_ac, tipo_ac, obs, url_ok),
            )
            ins_ac += int(cur_a.rowcount or 0)

    return {
        "convenio_142_inseridos": ins_142,
        "acordos_st_inseridos": ins_ac,
        "higienizados": hig_stats["atualizados"],
        "explodidos": hig_stats["explodidos"],
    }
