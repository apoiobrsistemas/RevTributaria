"""Árvore de decisão hierárquica de 5 camadas para validação NCM/Exceções em SP."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from typing import Any


def _so_digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _d(valor: Any) -> Decimal:
    if valor is None or valor == "":
        return Decimal("0")
    return Decimal(str(valor))


# Portaria SRE 70/2025 — Trava CST x prefixos cBenef permitidos em SP
TRAVA_CST_CBENEF_SRE_70_2025: dict[str, tuple[str, ...]] = {
    "00": (),  # Sem benefício fiscal
    "10": (),
    "20": ("SP02", "SP09"),
    "30": ("SP01", "SP03", "SP09"),
    "40": ("SP01", "SP03", "SP09"),
    "41": ("SP01", "SP03", "SP09"),
    "50": ("SP03", "SP09"),
    "51": ("SP04", "SP09"),
    "60": (),
    "70": ("SP02", "SP09"),
    "90": ("SP05", "SP09"),
}

# Revogações e exclusões recentes de ST em SP (Camada 3)
REVOGACOES_ST_SP: dict[str, dict[str, str]] = {
    "15091000": {
        "norma": "Portaria SRE 74/2025",
        "vigencia_revogacao": "2025-10-01",
        "produto": "Azeite de oliva",
        "efeito": "Excluído da Substituição Tributária em SP; não aplicar CST 10/60/70.",
    },
    "85171300": {
        "norma": "Portaria SRE SP (Fim ST Eletrônicos)",
        "vigencia_revogacao": "2026-10-01",
        "produto": "Smartphones e telefones celulares",
        "efeito": "Excluído da ST interna em SP; tributar ICMS próprio (CST 00/20).",
    },
    "85176277": {
        "norma": "Portaria SRE SP (Fim ST Eletrônicos)",
        "vigencia_revogacao": "2026-10-01",
        "produto": "Roteadores e transceptores",
        "efeito": "Excluído da ST interna em SP; tributar ICMS próprio.",
    },
    "85183000": {
        "norma": "Portaria SRE SP (Fim ST Eletrônicos)",
        "vigencia_revogacao": "2026-10-01",
        "produto": "Fones de ouvido e headsets",
        "efeito": "Excluído da ST interna em SP; tributar ICMS próprio.",
    },
    "85044010": {
        "norma": "Portaria SRE SP (Fim ST Eletrônicos)",
        "vigencia_revogacao": "2026-10-01",
        "produto": "Carregadores e fontes",
        "efeito": "Excluído da ST interna em SP; tributar ICMS próprio.",
    },
}

# 10 Casos Críticos Pré-Mapeados de São Paulo
CASOS_CRITICOS_SP: list[dict[str, Any]] = [
    {
        "ncm": "04051000",
        "titulo": "0405.10.00 — Manteiga (Embalagem <= 1kg vs > 1kg)",
        "descricao_item": "Manteiga de leite (CEST 17.028.00 <= 1kg / 17.028.01 > 1kg)",
        "ex_tipi": "",
        "embalagem": "<= 1 kg",
        "cst_icms": "20",
        "cbenef": "SP020003",
        "tem_st": 0,
        "cest": "1702800",
        "reducao_bc": 61.11,
        "aliquota_icms": 18.0,
        "norma_chave": "RICMS/SP Art. 313-W, Port. CAT 68/2019, Port. SRE 12/2026 & 52/2026, Anexo II Art. 3º",
        "rc_sefaz_sp": "RC 24891/2022 & RC 29110/2024: Embalagem <= 1kg (CEST 17.028.00) vs > 1kg (17.028.01).",
        "lc_214_2025": "Cesta Básica Nacional de Alimentos — Alíquota Zero IBS/CBS (LC 214/2025).",
    },
    {
        "ncm": "15091000",
        "titulo": "1509.10.00 — Azeite de Oliva (Revogação ST — Portaria SRE 74/2025)",
        "descricao_item": "Azeite de oliva virgem / extra virgem",
        "ex_tipi": "",
        "embalagem": "Recipiente <= 2L",
        "cst_icms": "00",
        "cbenef": "",
        "tem_st": 0,
        "cest": "",
        "reducao_bc": 0.0,
        "aliquota_icms": 18.0,
        "norma_chave": "Portaria SRE 74/2025 (Excluiu azeites da ST em SP) + RICMS/SP Art. 52",
        "rc_sefaz_sp": "Atenção ao estoque na data de exclusão da ST conforme Art. 272-A do RICMS/SP.",
        "lc_214_2025": "Redução de 60% nas alíquotas de IBS/CBS (Alimentos — LC 214/2025).",
    },
    {
        "ncm": "15171000",
        "titulo": "1517.10.00 — Margarina (Embalagem + Cesta Básica 7%)",
        "descricao_item": "Margarina, exceto a margarina líquida (CEST 17.029.00 / 17.029.01)",
        "ex_tipi": "",
        "embalagem": "<= 1 kg",
        "cst_icms": "70",
        "cbenef": "SP020003",
        "tem_st": 1,
        "cest": "1702900",
        "reducao_bc": 61.11,
        "aliquota_icms": 18.0,
        "norma_chave": "RICMS/SP Art. 313-W, Anexo II Art. 3º XIX, Portaria SRE 70/2025 (cBenef SP020003)",
        "rc_sefaz_sp": "RC 26304/2022: Ajustar IVA-ST quando carga interna efetiva (7%) for inferior à interestadual.",
        "lc_214_2025": "Redução de 60% na alíquota padrão de IBS/CBS (LC 214/2025).",
    },
    {
        "ncm": "21032010",
        "titulo": "2103.20.10 — Catchup e Molhos de Tomate (Limite <= 1 kg)",
        "descricao_item": "Catchup e outros molhos de tomate em embalagens imediatas <= 1 kg",
        "ex_tipi": "",
        "embalagem": "<= 1 kg",
        "cst_icms": "10",
        "cbenef": "",
        "tem_st": 1,
        "cest": "1704000",
        "reducao_bc": 0.0,
        "aliquota_icms": 18.0,
        "norma_chave": "RICMS/SP Art. 313-W, Port. CAT 68/2019 Anexo XVI item 40.0, Port. SRE 12/2026",
        "rc_sefaz_sp": "RC 21988/2020: Somente <= 1 kg sofre ST; galões > 1 kg (food service) são CST 00.",
        "lc_214_2025": "Tributação regular de IBS/CBS sem regime favorecido específico.",
    },
    {
        "ncm": "30049099",
        "titulo": "3004.90.99 — Medicamentos (Lista Positiva/Negativa/Neutra + PMC)",
        "descricao_item": "Outros medicamentos para fins terapêuticos/profiláticos",
        "ex_tipi": "01",
        "embalagem": "Caixa fracionada",
        "cst_icms": "10",
        "cbenef": "",
        "tem_st": 1,
        "cest": "1300100",
        "reducao_bc": 0.0,
        "aliquota_icms": 18.0,
        "norma_chave": "RICMS/SP Art. 313-A, Art. 54 XVI (Genéricos 12%), Port. CAT 68/2019, Lei 10.147/00",
        "rc_sefaz_sp": "RC 28412/2023: Venda direta a hospitais/clínicas pode afastar a ST conforme operação.",
        "lc_214_2025": "Medicamentos ANVISA com redução de 60% ou Alíquota Zero IBS/CBS (LC 214/2025).",
    },
    {
        "ncm": "84713012",
        "titulo": "8471.30.12 — Notebooks/Tablets (PPB Decreto 51.624/07 vs Importado)",
        "descricao_item": "Máquinas automáticas de processamento de dados portáteis",
        "ex_tipi": "",
        "embalagem": "Unitária",
        "cst_icms": "70",
        "cbenef": "SP020027",
        "tem_st": 1,
        "cest": "2102900",
        "reducao_bc": 33.33,
        "aliquota_icms": 18.0,
        "norma_chave": "RICMS/SP Art. 313-Z19, Decreto 51.624/2007, Anexo II Art. 27, Port. SRE 70/2025",
        "rc_sefaz_sp": "RC 27519/2023: Exige indicação da Portaria Interministerial do PPB na NF-e.",
        "lc_214_2025": "Manutenção de incentivos específicos ZFM/Informática na transição LC 214/2025.",
    },
    {
        "ncm": "02013000",
        "titulo": "0201.30.00 — Carnes Bovinas (Decreto 62.647/17 + Anexo II Art. 74)",
        "descricao_item": "Carnes desossadas de bovino, frescas ou refrigeradas",
        "ex_tipi": "",
        "embalagem": "Corte varejo/atacado",
        "cst_icms": "20",
        "cbenef": "SP020074",
        "tem_st": 0,
        "cest": "",
        "reducao_bc": 61.11,
        "aliquota_icms": 18.0,
        "norma_chave": "RICMS/SP Anexo II Art. 74, Decreto 62.647/2017, Portaria SRE 70/2025 (SP020074)",
        "rc_sefaz_sp": "RC 29004/2024: Redução exige estorno proporcional do crédito, salvo opção pelo outorgado.",
        "lc_214_2025": "Cesta Básica Nacional de Alimentos — Alíquota Zero IBS/CBS (LC 214/2025).",
    },
    {
        "ncm": "39241000",
        "titulo": "3924.10.00 — Utensílios Plásticos (Duráveis vs Descartáveis + Ex-TIPI)",
        "descricao_item": "Serviços de mesa e utensílios plásticos (CEST 14.006.00 / 14.006.01)",
        "ex_tipi": "01",
        "embalagem": "Pacote / Unitário",
        "cst_icms": "10",
        "cbenef": "",
        "tem_st": 1,
        "cest": "1400600",
        "reducao_bc": 0.0,
        "aliquota_icms": 18.0,
        "norma_chave": "RICMS/SP Art. 313-Z15, Convênio 142/2018 Anexo XIV, Decreto 12.665/2025 (TIPI)",
        "rc_sefaz_sp": "RC 25112/2022: Potes plásticos exclusivos para indústria de alimentos não sofrem ST.",
        "lc_214_2025": "Tributação integral padrão de IBS/CBS (LC 214/2025).",
    },
    {
        "ncm": "87082999",
        "titulo": "8708.29.99 — Autopeças (Uso Automotivo Exclusivo Art. 313-O)",
        "descricao_item": "Outras partes e acessórios de carroçarias de veículos automóveis",
        "ex_tipi": "",
        "embalagem": "Peça unitária",
        "cst_icms": "10",
        "cbenef": "",
        "tem_st": 1,
        "cest": "0103100",
        "reducao_bc": 0.0,
        "aliquota_icms": 18.0,
        "norma_chave": "RICMS/SP Art. 313-O, Portaria CAT 68/2019 Anexo XIV, DN CAT 05/2009",
        "rc_sefaz_sp": "DN CAT 05/2009: Uso especificamente automotivo; remessa a montadora afasta ST.",
        "lc_214_2025": "Regime específico de transição para o setor automotivo (LC 214/2025).",
    },
    {
        "ncm": "22021000",
        "titulo": "2202.10.00 — Águas e Refrigerantes (PMPF vs IVA-ST + Imposto Seletivo)",
        "descricao_item": "Águas minerais e gaseificadas adicionadas de açúcar/aromatizadas",
        "ex_tipi": "01",
        "embalagem": "Garrafa PET / Lata",
        "cst_icms": "10",
        "cbenef": "",
        "tem_st": 1,
        "cest": "0300700",
        "reducao_bc": 0.0,
        "aliquota_icms": 18.0,
        "norma_chave": "RICMS/SP Art. 293, Portaria SRE de PMPF Bebidas Frias",
        "rc_sefaz_sp": "Gatilho de trava: se operação própria > 80%/90% do PMPF, aplica-se IVA-ST.",
        "lc_214_2025": "Bebidas açucaradas sujeitas ao Imposto Seletivo (IS) na LC 214/2025.",
    },
]


@dataclass(frozen=True)
class CamadaResultado:
    """Resultado de uma camada da árvore de decisão hierárquica."""

    camada: int
    nome: str
    status: str  # OK | ALERTA | BLOQUEIO
    detalhe: str
    norma_referencia: str


def avaliar_arvore_5_camadas(
    *,
    ncm: str,
    cst_icms: str,
    cbenef: str = "",
    tem_st: int = 0,
    cest: str = "",
    reducao_bc: float | Decimal = 0,
    descricao_item: str = "",
    ex_tipi: str = "",
    embalagem: str = "",
    data_referencia: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Executa a árvore hierárquica de 5 camadas para um NCM em SP."""
    ncm_limpo = _so_digitos(ncm)
    cest_limpo = _so_digitos(cest)
    cst = str(cst_icms or "").strip()
    cbenef_limpo = str(cbenef or "").strip().upper()
    red = _d(reducao_bc)
    ref = data_referencia or date.today().isoformat()
    camadas: list[CamadaResultado] = []

    # --- CAMADA 1: Vigência Siscomex / Regra Federal ---
    if len(ncm_limpo) != 8 or ncm_limpo == "00000000":
        camadas.append(
            CamadaResultado(
                camada=1,
                nome="1. Vigência Siscomex",
                status="BLOQUEIO",
                detalhe=f"NCM '{ncm}' inválido (deve ter 8 dígitos).",
                norma_referencia="Portal Único Siscomex Classif",
            )
        )
    else:
        fed_row = None
        if conn is not None:
            fed_row = conn.execute(
                """
                SELECT * FROM regras_federais
                WHERE ncm = ? AND status_registro = 'ATIVA'
                  AND vigencia_inicio <= ? AND (vigencia_fim IS NULL OR vigencia_fim >= ?)
                ORDER BY vigencia_inicio DESC LIMIT 1
                """,
                (ncm_limpo, ref, ref),
            ).fetchone()
        if conn is not None and fed_row is None:
            camadas.append(
                CamadaResultado(
                    camada=1,
                    nome="1. Vigência Siscomex",
                    status="ALERTA",
                    detalhe=f"NCM {ncm_limpo} válido no formato, porém sem vigência ativa em regras_federais.",
                    norma_referencia="Portal Único Siscomex / TIPI",
                )
            )
        else:
            desc_fed = fed_row["descricao_ncm"] if fed_row and fed_row["descricao_ncm"] else "NCM vigente"
            camadas.append(
                CamadaResultado(
                    camada=1,
                    nome="1. Vigência Siscomex",
                    status="OK",
                    detalhe=f"NCM {ncm_limpo} vigente ({desc_fed}).",
                    norma_referencia="Portal Único Siscomex Classif",
                )
            )

    # --- CAMADA 2: Filtro de Descrição / "Ex" / Embalagem ---
    detalhes_c2: list[str] = []
    if ex_tipi.strip():
        detalhes_c2.append(f"Ex-TIPI '{ex_tipi.strip()}' informado")
    if embalagem.strip():
        detalhes_c2.append(f"Embalagem '{embalagem.strip()}'")
    if descricao_item.strip():
        detalhes_c2.append(f"Descrição: {descricao_item.strip()[:60]}")
    if detalhes_c2:
        camadas.append(
            CamadaResultado(
                camada=2,
                nome='2. Filtro Descrição / "Ex" / Embalagem',
                status="OK",
                detalhe=" | ".join(detalhes_c2),
                norma_referencia="TIPI Decreto 11.158/2022 & Portaria CAT 68/2019",
            )
        )
    else:
        camadas.append(
            CamadaResultado(
                camada=2,
                nome='2. Filtro Descrição / "Ex" / Embalagem',
                status="ALERTA",
                detalhe="Sem descrição/Ex/embalagem informados para validar exceções de peso ou destinação.",
                norma_referencia="TIPI / Notas Explicativas NCM",
            )
        )

    # --- CAMADA 3: Matriz ST & Revogações (SP) ---
    revogacao = REVOGACOES_ST_SP.get(ncm_limpo)
    if revogacao and ref >= revogacao["vigencia_revogacao"]:
        if tem_st == 1 or cst in {"10", "30", "60", "70"}:
            camadas.append(
                CamadaResultado(
                    camada=3,
                    nome="3. Matriz ST & Revogações",
                    status="BLOQUEIO",
                    detalhe=(
                        f"ST REVOGADA para {ncm_limpo} ({revogacao['produto']}) desde "
                        f"{revogacao['vigencia_revogacao']}! {revogacao['efeito']}"
                    ),
                    norma_referencia=revogacao["norma"],
                )
            )
        else:
            camadas.append(
                CamadaResultado(
                    camada=3,
                    nome="3. Matriz ST & Revogações",
                    status="OK",
                    detalhe=f"Revogação de ST respeitada ({revogacao['norma']}).",
                    norma_referencia=revogacao["norma"],
                )
            )
    elif tem_st == 1 or cst in {"10", "30", "60", "70"}:
        if len(cest_limpo) != 7:
            camadas.append(
                CamadaResultado(
                    camada=3,
                    nome="3. Matriz ST & Revogações",
                    status="BLOQUEIO",
                    detalhe=f"Operação com ST (CST {cst}) exige CEST válido de 7 dígitos.",
                    norma_referencia="Convênio ICMS 142/2018 & Portaria CAT 68/2019",
                )
            )
        else:
            camadas.append(
                CamadaResultado(
                    camada=3,
                    nome="3. Matriz ST & Revogações",
                    status="OK",
                    detalhe=f"ST ativa com CEST {cest_limpo} e sem revogação cadastrada.",
                    norma_referencia="Portaria CAT 68/2019",
                )
            )
    else:
        camadas.append(
            CamadaResultado(
                camada=3,
                nome="3. Matriz ST & Revogações",
                status="OK",
                detalhe="Operação sem Substituição Tributária (ICMS próprio).",
                norma_referencia="Portaria CAT 68/2019",
            )
        )

    # --- CAMADA 4: Benefícios Fiscais & Trava CST x cBenef (Portaria SRE 70/2025) ---
    prefixos = TRAVA_CST_CBENEF_SRE_70_2025.get(cst)
    if prefixos is None:
        camadas.append(
            CamadaResultado(
                camada=4,
                nome="4. Benefícios & Trava CST x cBenef (SRE 70/2025)",
                status="ALERTA",
                detalhe=f"CST '{cst}' não mapeado na trava da Portaria SRE 70/2025.",
                norma_referencia="Portaria SRE 70/2025",
            )
        )
    elif prefixos == ():
        if cbenef_limpo:
            camadas.append(
                CamadaResultado(
                    camada=4,
                    nome="4. Benefícios & Trava CST x cBenef (SRE 70/2025)",
                    status="BLOQUEIO",
                    detalhe=f"Trava SRE 70/2025: CST {cst} proíbe cBenef '{cbenef_limpo}'.",
                    norma_referencia="Portaria SRE 70/2025",
                )
            )
        else:
            camadas.append(
                CamadaResultado(
                    camada=4,
                    nome="4. Benefícios & Trava CST x cBenef (SRE 70/2025)",
                    status="OK",
                    detalhe=f"CST {cst} compatível com ausência de cBenef.",
                    norma_referencia="Portaria SRE 70/2025",
                )
            )
    else:
        if not cbenef_limpo:
            camadas.append(
                CamadaResultado(
                    camada=4,
                    nome="4. Benefícios & Trava CST x cBenef (SRE 70/2025)",
                    status="BLOQUEIO",
                    detalhe=f"Trava SRE 70/2025: CST {cst} exige cBenef ({'/'.join(prefixos)}xxxx).",
                    norma_referencia="Portaria SRE 70/2025",
                )
            )
        elif not cbenef_limpo.startswith(prefixos):
            camadas.append(
                CamadaResultado(
                    camada=4,
                    nome="4. Benefícios & Trava CST x cBenef (SRE 70/2025)",
                    status="BLOQUEIO",
                    detalhe=(
                        f"Trava SRE 70/2025: cBenef '{cbenef_limpo}' incompatível com CST {cst} "
                        f"(esperado {'/'.join(prefixos)})."
                    ),
                    norma_referencia="Portaria SRE 70/2025",
                )
            )
        elif cst in {"20", "70"} and red <= 0:
            camadas.append(
                CamadaResultado(
                    camada=4,
                    nome="4. Benefícios & Trava CST x cBenef (SRE 70/2025)",
                    status="BLOQUEIO",
                    detalhe=f"CST {cst} com cBenef '{cbenef_limpo}' exige reducao_bc > 0.",
                    norma_referencia="RICMS/SP Anexo II & Portaria SRE 70/2025",
                )
            )
        else:
            camadas.append(
                CamadaResultado(
                    camada=4,
                    nome="4. Benefícios & Trava CST x cBenef (SRE 70/2025)",
                    status="OK",
                    detalhe=f"Trava CST {cst} x cBenef '{cbenef_limpo}' válida.",
                    norma_referencia="Portaria SRE 70/2025",
                )
            )

    # --- CAMADA 5: Respostas à Consulta SEFAZ-SP & LC 214/2025 ---
    caso_ref = next((c for c in CASOS_CRITICOS_SP if c["ncm"] == ncm_limpo), None)
    if caso_ref:
        camadas.append(
            CamadaResultado(
                camada=5,
                nome="5. Respostas à Consulta SEFAZ-SP & LC 214/2025",
                status="OK",
                detalhe=f"{caso_ref['rc_sefaz_sp']} | {caso_ref['lc_214_2025']}",
                norma_referencia="SEFAZ-SP RC & LC 214/2025",
            )
        )
    else:
        cclass = ""
        if conn is not None:
            fed = conn.execute(
                "SELECT cclass_trib FROM regras_federais WHERE ncm = ? AND status_registro = 'ATIVA' LIMIT 1",
                (ncm_limpo,),
            ).fetchone()
            cclass = str(fed["cclass_trib"] or "") if fed else ""
        if cclass:
            camadas.append(
                CamadaResultado(
                    camada=5,
                    nome="5. Respostas à Consulta SEFAZ-SP & LC 214/2025",
                    status="OK",
                    detalhe=f"cClassTrib '{cclass}' vinculado para transição IBS/CBS.",
                    norma_referencia="LC 214/2025",
                )
            )
        else:
            camadas.append(
                CamadaResultado(
                    camada=5,
                    nome="5. Respostas à Consulta SEFAZ-SP & LC 214/2025",
                    status="ALERTA",
                    detalhe="Sem cClassTrib (LC 214/2025) ou RC específica pré-mapeada para este NCM.",
                    norma_referencia="SEFAZ-SP RC & LC 214/2025",
                )
            )

    statuses = {c.status for c in camadas}
    if "BLOQUEIO" in statuses:
        status_geral = "BLOQUEIO"
    elif "ALERTA" in statuses:
        status_geral = "ALERTA"
    else:
        status_geral = "OK"

    return {
        "ncm": ncm_limpo,
        "status_geral": status_geral,
        "camadas": [asdict(c) for c in camadas],
    }
