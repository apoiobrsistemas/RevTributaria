"""Seed híbrido inicial de SP (20 NCMs em 5 grupos críticos) e gerador de planilha modelo."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import openpyxl

from src.automation.official_ingestor import (
    URL_CONFAZ_142_18,
    URL_CONFAZ_52_91,
    URL_SISCOMEX_NCM_JSON,
    URL_TIPI_RFB,
    ingerir_convenio_142_html,
    ingerir_convenio_52_91_html,
    ingerir_siscomex_ncm_json,
    ingerir_tipi_xlsx,
)
from src.database import DEFAULT_DB_PATH, init_db, registrar_historico
from src.legislation.parsers import baixar_url_oficial
from src.legislation.url_guard import validar_url_oficial

DEFAULT_TEMPLATE_XLSX = (
    Path(__file__).resolve().parent.parent.parent / "templates" / "modelo_carga_regras_sp.xlsx"
)

FONTES_OFICIAIS_SEED: list[dict[str, str]] = [
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "RICMS",
        "numero_norma": "Decreto 45.490/2000",
        "titulo": "Regulamento do ICMS do Estado de São Paulo",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/RICMS.aspx",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "PORTARIA",
        "numero_norma": "Portaria SRE SP",
        "titulo": "Portal SEFAZ-SP Legislação e Tributação",
        "url_oficial": "https://portal.fazenda.sp.gov.br/Paginas/default.aspx",
    },
    {
        "uf": "BR",
        "esfera": "CONFAZ",
        "tipo_norma": "CONVENIO",
        "numero_norma": "Convênio ICMS 142/2018",
        "titulo": "Regimes de Substituição Tributária e CEST",
        "url_oficial": URL_CONFAZ_142_18,
    },
    {
        "uf": "BR",
        "esfera": "CONFAZ",
        "tipo_norma": "CONVENIO",
        "numero_norma": "Convênio ICMS 52/1991",
        "titulo": "Redução de Base de Cálculo - Máquinas e Implementos",
        "url_oficial": URL_CONFAZ_52_91,
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "TIPI",
        "numero_norma": "Decreto 11.158/2022",
        "titulo": "Tabela de Incidência do IPI e NCM Siscomex",
        "url_oficial": URL_TIPI_RFB,
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "LEI",
        "numero_norma": "Lei 10.485/2002 e Lei 10.147/2000",
        "titulo": "PIS/COFINS Monofásico - Autopeças e Perfumaria",
        "url_oficial": "https://www.planalto.gov.br/ccivil_03/leis/2002/l10485.htm",
    },
]

# 20 NCMs reais cobrindo Grupos A, B, C, D e E
CENARIOS_FEDERAIS_SP: list[dict[str, Any]] = [
    # Grupo A - Eletrônicos pós-fim ST em SP (2026-10-01)
    {"ncm": "85171300", "cest": "2105301", "desc": "Smartphones e celulares", "ipi": 0.0, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "85176277", "cest": "2105600", "desc": "Roteadores e transceptores", "ipi": 0.0, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "85183000", "cest": "2105900", "desc": "Fones de ouvido e headsets", "ipi": 9.75, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "85044010", "cest": "2107700", "desc": "Carregadores e fontes", "ipi": 5.0, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    # Grupo B - Redução de Base (carga 12% e 8,80% Conv. 52/91) + cBenef
    {"ncm": "84716053", "cest": "2103600", "desc": "Mouses e periféricos de informática", "ipi": 5.0, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "85444200", "cest": "1200700", "desc": "Cabos elétricos com conectores", "ipi": 3.25, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "84321000", "cest": "", "desc": "Arados agrícolas (Conv. 52/91)", "ipi": 0.0, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "200030", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 60.0},
    {"ncm": "84248221", "cest": "", "desc": "Pulverizadores agrícolas (Conv. 52/91)", "ipi": 0.0, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "200030", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 60.0},
    # Grupo C - Importados com FCI
    {"ncm": "84713012", "cest": "2103000", "desc": "Notebooks importados (FCI 35%)", "ipi": 0.0, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "85285220", "cest": "2106800", "desc": "Monitores LED importados (FCI 55%)", "ipi": 0.0, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "85235190", "cest": "2106500", "desc": "SSDs importados (FCI 80%)", "ipi": 0.0, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "84716052", "cest": "2103500", "desc": "Teclados importados (FCI 62%)", "ipi": 5.0, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    # Grupo D - ST Vigente em SP + ICMS Efetivo
    {"ncm": "85071090", "cest": "0105300", "desc": "Acumuladores e baterias automotivas", "ipi": 10.0, "pis_e": "70", "pis_s": "04", "aliq_pis": 0.0, "cof_e": "70", "cof_s": "04", "aliq_cof": 0.0, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "85122011", "cest": "0106000", "desc": "Faróis automotivos", "ipi": 5.0, "pis_e": "70", "pis_s": "04", "aliq_pis": 0.0, "cof_e": "70", "cof_s": "04", "aliq_cof": 0.0, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "85365090", "cest": "1200400", "desc": "Interruptores elétricos", "ipi": 5.0, "pis_e": "50", "pis_s": "01", "aliq_pis": 1.65, "cof_e": "50", "cof_s": "01", "aliq_cof": 7.60, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "22021000", "cest": "0300700", "desc": "Águas minerais e refrigerantes", "ipi": 4.0, "pis_e": "70", "pis_s": "04", "aliq_pis": 0.0, "cof_e": "70", "cof_s": "04", "aliq_cof": 0.0, "cclass": "200020", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    # Grupo E - Monofásicos PIS/COFINS (CST 04 saída / 70 entrada) + IBS/CBS
    {"ncm": "33030010", "cest": "2000100", "desc": "Perfumes (extratos) - Monofásico", "ipi": 27.3, "pis_e": "70", "pis_s": "04", "aliq_pis": 0.0, "cof_e": "70", "cof_s": "04", "aliq_cof": 0.0, "cclass": "200010", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "33049990", "cest": "2001500", "desc": "Cosméticos e cremes - Monofásico", "ipi": 14.3, "pis_e": "70", "pis_s": "04", "aliq_pis": 0.0, "cof_e": "70", "cof_s": "04", "aliq_cof": 0.0, "cclass": "200010", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "33051000", "cest": "2001700", "desc": "Xampus - Monofásico", "ipi": 4.55, "pis_e": "70", "pis_s": "04", "aliq_pis": 0.0, "cof_e": "70", "cof_s": "04", "aliq_cof": 0.0, "cclass": "200010", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
    {"ncm": "84212300", "cest": "0101700", "desc": "Filtros de óleo - Monofásico Lei 10.485/02", "ipi": 5.0, "pis_e": "70", "pis_s": "04", "aliq_pis": 0.0, "cof_e": "70", "cof_s": "04", "aliq_cof": 0.0, "cclass": "000001", "cbs": 8.80, "ibs_uf": 15.0, "ibs_mun": 2.7, "red_ibs": 0.0},
]

# 15 regras ACEITO + 5 regras A_CONFERIR (com citação literal SEFAZ-SP)
CENARIOS_ESTADUAIS_SP: list[dict[str, Any]] = [
    # Grupo A (pós-fim da ST em SP a partir de 2026-10-01)
    {"uf_o": "SP", "uf_d": "SP", "ncm": "85171300", "cest": "2105301", "vig_ini": "2026-10-01", "vig_fim": None, "cfop": "5102", "cst": "00", "aliq": 18.0, "red": 0.0, "st": 0, "mva": 0.0, "aliq_st": 0.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "Portaria SRE SP (Fim ST Eletrônicos 01/10/2026)", "trecho": "Exclusão dos aparelhos telefônicos celulares do regime de substituição tributária a partir de 01/10/2026."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "85176277", "cest": "2105600", "vig_ini": "2026-10-01", "vig_fim": None, "cfop": "5102", "cst": "00", "aliq": 18.0, "red": 0.0, "st": 0, "mva": 0.0, "aliq_st": 0.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "Portaria SRE SP (Fim ST Eletrônicos 01/10/2026)", "trecho": "Tributação integral de ICMS 18% nas saídas internas de roteadores após 01/10/2026."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "85183000", "cest": "2105900", "vig_ini": "2026-10-01", "vig_fim": None, "cfop": "5102", "cst": "00", "aliq": 18.0, "red": 0.0, "st": 0, "mva": 0.0, "aliq_st": 0.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "Portaria SRE SP (Fim ST Eletrônicos 01/10/2026)", "trecho": "Fones de ouvido tributados normalmente pelo ICMS próprio em SP a partir de 01/10/2026."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "85044010", "cest": "2107700", "vig_ini": "2026-10-01", "vig_fim": None, "cfop": "5102", "cst": "00", "aliq": 18.0, "red": 0.0, "st": 0, "mva": 0.0, "aliq_st": 0.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "Portaria SRE SP (Fim ST Eletrônicos 01/10/2026)", "trecho": "Carregadores excluídos da ST interna em SP a partir de 01/10/2026."},
    # Grupo B (Redução de Base 12% -> 33,33% e 8,80% -> 51,11% + cBenef)
    {"uf_o": "SP", "uf_d": "SP", "ncm": "84716053", "cest": "2103600", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5102", "cst": "20", "aliq": 18.0, "red": 33.33, "st": 0, "mva": 0.0, "aliq_st": 0.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "SP020027", "status": "ACEITO", "disp": "RICMS/SP Anexo II Art. 27", "trecho": "Fica reduzida a base de cálculo do imposto incidente na saída interna de produtos de informática, de forma que a carga tributária resulte no percentual de 12%."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "85444200", "cest": "1200700", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5102", "cst": "20", "aliq": 18.0, "red": 33.33, "st": 0, "mva": 0.0, "aliq_st": 0.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "SP020027", "status": "ACEITO", "disp": "RICMS/SP Anexo II Art. 27", "trecho": "Carga tributária efetiva de 12% nas operações internas em SP."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "84321000", "cest": "", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5102", "cst": "20", "aliq": 18.0, "red": 51.11, "st": 0, "mva": 0.0, "aliq_st": 0.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "SP020012", "status": "ACEITO", "disp": "RICMS/SP Anexo II Art. 12 (Conv. 52/91)", "trecho": "Fica reduzida a base de cálculo do ICMS nas operações com máquinas e implementos agrícolas de forma que a carga tributária final corresponda a 8,80%."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "84248221", "cest": "", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5102", "cst": "20", "aliq": 18.0, "red": 51.11, "st": 0, "mva": 0.0, "aliq_st": 0.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "SP020012", "status": "A_CONFERIR", "disp": "RICMS/SP Anexo II Art. 12 (Conv. 52/91)", "trecho": "Redução de base de cálculo para carga final de 8,80% nas operações internas com pulverizadores."},
    # Grupo C (Importados FCI - entradas/saídas interestaduais com MVA ajustado)
    {"uf_o": "SC", "uf_d": "SP", "ncm": "84713012", "cest": "2103000", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "6403", "cst": "10", "aliq": 12.0, "red": 0.0, "st": 1, "mva": 35.0, "aliq_st": 18.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "Protocolo ICMS SC/SP", "trecho": "Entrada interestadual de notebook com FCI <= 40% (origem 5, alíquota 12%)."},
    {"uf_o": "SC", "uf_d": "SP", "ncm": "85285220", "cest": "2106800", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "6403", "cst": "10", "aliq": 4.0, "red": 0.0, "st": 1, "mva": 38.0, "aliq_st": 18.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "Resolução Senado 13/2012", "trecho": "Conteúdo de importação superior a 40% (FCI 55%): alíquota interestadual de 4% com ajuste de MVA."},
    {"uf_o": "PR", "uf_d": "SP", "ncm": "85235190", "cest": "2106500", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "6403", "cst": "10", "aliq": 4.0, "red": 0.0, "st": 1, "mva": 40.0, "aliq_st": 18.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "", "status": "A_CONFERIR", "disp": "Resolução Senado 13/2012", "trecho": "Conteúdo de importação superior a 70% (FCI 80%): origem 8 e alíquota interestadual de 4%."},
    {"uf_o": "MG", "uf_d": "SP", "ncm": "84716052", "cest": "2103500", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "6403", "cst": "10", "aliq": 4.0, "red": 0.0, "st": 1, "mva": 41.0, "aliq_st": 18.0, "efet": 0.0, "red_efet": 0.0, "cbenef": "", "status": "A_CONFERIR", "disp": "Resolução Senado 13/2012", "trecho": "Conteúdo de importação 62% (origem 3): alíquota interestadual de 4%."},
    # Grupo D (ST Vigente em SP + ICMS Efetivo)
    {"uf_o": "SP", "uf_d": "SP", "ncm": "85071090", "cest": "0105300", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5405", "cst": "60", "aliq": 18.0, "red": 0.0, "st": 1, "mva": 71.78, "aliq_st": 18.0, "efet": 18.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "RICMS/SP Art. 313-O", "trecho": "Na saída interna de autopeças com imposto retido anteriormente (CST 60), informar vBCEfet e vICMSEfet a 18%."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "85122011", "cest": "0106000", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5405", "cst": "60", "aliq": 18.0, "red": 0.0, "st": 1, "mva": 71.78, "aliq_st": 18.0, "efet": 18.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "RICMS/SP Art. 313-O", "trecho": "Faróis automotivos sujeitos à ST interna com ICMS Efetivo de 18%."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "85365090", "cest": "1200400", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5405", "cst": "60", "aliq": 18.0, "red": 0.0, "st": 1, "mva": 45.0, "aliq_st": 18.0, "efet": 18.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "RICMS/SP Art. 313-Z17", "trecho": "Materiais elétricos sujeitos ao regime de substituição tributária em SP."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "22021000", "cest": "0300700", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5405", "cst": "60", "aliq": 18.0, "red": 0.0, "st": 1, "mva": 60.0, "aliq_st": 18.0, "efet": 18.0, "red_efet": 0.0, "cbenef": "", "status": "A_CONFERIR", "disp": "RICMS/SP Art. 293", "trecho": "Bebidas sujeitas à ST interna em São Paulo com ICMS Efetivo 18%."},
    # Grupo E (Monofásicos + ST em SP)
    {"uf_o": "SP", "uf_d": "SP", "ncm": "33030010", "cest": "2000100", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5405", "cst": "60", "aliq": 25.0, "red": 0.0, "st": 1, "mva": 55.0, "aliq_st": 25.0, "efet": 25.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "RICMS/SP Art. 313-E e Art. 55", "trecho": "Perfumes sujeitos à alíquota interna de 25% e ST em SP."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "33049990", "cest": "2001500", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5405", "cst": "60", "aliq": 25.0, "red": 0.0, "st": 1, "mva": 50.0, "aliq_st": 25.0, "efet": 25.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "RICMS/SP Art. 313-E", "trecho": "Cosméticos sujeitos à ST interna em SP."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "33051000", "cest": "2001700", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5405", "cst": "60", "aliq": 18.0, "red": 0.0, "st": 1, "mva": 45.0, "aliq_st": 18.0, "efet": 18.0, "red_efet": 0.0, "cbenef": "", "status": "ACEITO", "disp": "RICMS/SP Art. 313-E", "trecho": "Xampus sujeitos à alíquota interna de 18% e ST."},
    {"uf_o": "SP", "uf_d": "SP", "ncm": "84212300", "cest": "0101700", "vig_ini": "2026-01-01", "vig_fim": None, "cfop": "5405", "cst": "60", "aliq": 18.0, "red": 0.0, "st": 1, "mva": 71.78, "aliq_st": 18.0, "efet": 18.0, "red_efet": 0.0, "cbenef": "", "status": "A_CONFERIR", "disp": "RICMS/SP Art. 313-O", "trecho": "Filtros automotivos sujeitos à ST interna e PIS/COFINS monofásico."},
]

CENARIOS_TERCEIROS_FCI: list[tuple[str, str, str, str, str, float, float, int]] = [
    # uf_terceiro, ncm, cest, origem, numero_fci, conteudo_importacao_pct, aliq_inter, conv_52_91
    ("SC", "84713012", "2103000", "5", "FCI-SP-35PCT-0001", 35.0, 12.0, 0),
    ("SC", "85285220", "2106800", "3", "FCI-SP-55PCT-0002", 55.0, 4.0, 0),
    ("PR", "85235190", "2106500", "8", "FCI-SP-80PCT-0003", 80.0, 4.0, 0),
    ("MG", "84716052", "2103500", "3", "FCI-SP-62PCT-0004", 62.0, 4.0, 0),
    ("SP", "84321000", "", "0", "", 0.0, 18.0, 1),
]


def gerar_planilha_modelo_sp(caminho: str | Path = DEFAULT_TEMPLATE_XLSX) -> Path:
    """Gera a planilha modelo .xlsx com os 20 NCMs de referência de SP."""
    destino = Path(caminho)
    destino.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Matriz_SP_20_NCMs"
    ws.append(
        [
            "uf_origem",
            "uf_destino",
            "ncm",
            "cest",
            "natureza_operacao",
            "vigencia_inicio",
            "cfop",
            "cst_icms",
            "aliquota_icms",
            "reducao_base_icms",
            "tem_st",
            "margem_st",
            "aliquota_icms_st",
            "codigo_beneficio_fiscal",
            "status_validacao",
            "dispositivo_legal",
        ]
    )
    for r in CENARIOS_ESTADUAIS_SP:
        ws.append(
            [
                r["uf_o"],
                r["uf_d"],
                r["ncm"],
                r["cest"],
                "VENDA",
                r["vig_ini"],
                r["cfop"],
                r["cst"],
                r["aliq"],
                r["red"],
                r["st"],
                r["mva"],
                r["aliq_st"],
                r["cbenef"],
                r["status"],
                r["disp"],
            ]
        )
    wb.save(destino)
    return destino


def _garantir_fontes_oficiais(conn: sqlite3.Connection) -> dict[str, int]:
    ids: dict[str, int] = {}
    with conn:
        for f in FONTES_OFICIAIS_SEED:
            validar_url_oficial(f["url_oficial"])
            row = conn.execute(
                "SELECT id FROM fontes_legais WHERE url_oficial = ?",
                (f["url_oficial"],),
            ).fetchone()
            if row:
                ids[f["tipo_norma"]] = int(row["id"])
            else:
                cur = conn.execute(
                    """
                    INSERT INTO fontes_legais (uf, esfera, tipo_norma, numero_norma, titulo, url_oficial)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (f["uf"], f["esfera"], f["tipo_norma"], f["numero_norma"], f["titulo"], f["url_oficial"]),
                )
                ids[f["tipo_norma"]] = int(cur.lastrowid)
    return ids


def executar_seed_sp(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    usar_rede: bool = True,
    gerar_template: bool = True,
) -> dict[str, Any]:
    """Executa carga inicial híbrida de SP (busca oficial primeiro + fallback 20 NCMs)."""
    conn = init_db(db_path)
    try:
        fontes_ids = _garantir_fontes_oficiais(conn)
        ncms_ref = {c["ncm"] for c in CENARIOS_FEDERAIS_SP}
        resumo: dict[str, Any] = {
            "busca_online_tentada": usar_rede,
            "online_sucesso": [],
            "online_fallback": [],
            "federais_inseridas": 0,
            "estaduais_inseridas": 0,
            "terceiros_inseridas": 0,
            "erp_importadas": 0,
        }

        if usar_rede:
            for nome, url, fn in [
                ("siscomex", URL_SISCOMEX_NCM_JSON, lambda b: ingerir_siscomex_ncm_json(conn, b, apenas_ncms=ncms_ref)),
                ("tipi", URL_TIPI_RFB, lambda b: ingerir_tipi_xlsx(conn, b, apenas_ncms=ncms_ref)),
                ("confaz_142", URL_CONFAZ_142_18, lambda b: ingerir_convenio_142_html(conn, b.decode("utf-8", errors="replace"))),
                ("confaz_52_91", URL_CONFAZ_52_91, lambda b: ingerir_convenio_52_91_html(conn, b.decode("utf-8", errors="replace"))),
            ]:
                try:
                    raw, _ = baixar_url_oficial(url, timeout=8)
                    fn(raw)
                    resumo["online_sucesso"].append(nome)
                except Exception:
                    resumo["online_fallback"].append(nome)

        fonte_tipi = fontes_ids.get("TIPI")
        fonte_ricms = fontes_ids.get("RICMS")
        fonte_conv = fontes_ids.get("CONVENIO")

        with conn:
            for item in CENARIOS_FEDERAIS_SP:
                existe = conn.execute(
                    "SELECT id FROM regras_federais WHERE ncm = ? AND ex_tipi = '' AND cest = ? AND status_registro = 'ATIVA'",
                    (item["ncm"], item["cest"]),
                ).fetchone()
                if not existe:
                    cur = conn.execute(
                        """
                        INSERT INTO regras_federais (
                            ncm, ex_tipi, cest, descricao_ncm, vigencia_inicio,
                            aliquota_ipi, cst_pis_entrada, cst_pis_saida, aliquota_pis,
                            cst_cofins_entrada, cst_cofins_saida, aliquota_cofins,
                            cst_ibs_cbs, cclass_trib, aliquota_cbs, aliquota_ibs_uf, aliquota_ibs_mun,
                            reducao_ibs_cbs, fonte_legal_id, dispositivo_legal, status_validacao, aceito_por
                        ) VALUES (?, '', ?, ?, '2026-01-01', ?, ?, ?, ?, ?, ?, ?, '000', ?, ?, ?, ?, ?, ?, 'TIPI / LC 214/2025', 'ACEITO', 'seed_sp')
                        """,
                        (
                            item["ncm"],
                            item["cest"],
                            item["desc"],
                            item["ipi"],
                            item["pis_e"],
                            item["pis_s"],
                            item["aliq_pis"],
                            item["cof_e"],
                            item["cof_s"],
                            item["aliq_cof"],
                            item["cclass"],
                            item["cbs"],
                            item["ibs_uf"],
                            item["ibs_mun"],
                            item["red_ibs"],
                            fonte_tipi,
                        ),
                    )
                    registrar_historico(
                        conn,
                        tabela_origem="regras_federais",
                        registro_id=int(cur.lastrowid),
                        acao="CRIACAO",
                        usuario="seed_sp",
                        campo="ncm",
                        valor_novo=item["ncm"],
                        motivo="Carga inicial curada SP",
                        auto_commit=False,
                    )
                    resumo["federais_inseridas"] += 1

            for reg in CENARIOS_ESTADUAIS_SP:
                existe = conn.execute(
                    """
                    SELECT id FROM regras_estaduais_icms
                    WHERE uf_origem = ? AND uf_destino = ? AND ncm = ? AND cest = ?
                      AND vigencia_inicio = ? AND status_registro = 'ATIVA'
                    """,
                    (reg["uf_o"], reg["uf_d"], reg["ncm"], reg["cest"], reg["vig_ini"]),
                ).fetchone()
                if not existe:
                    cur = conn.execute(
                        """
                        INSERT INTO regras_estaduais_icms (
                            uf_origem, uf_destino, ncm, cest, natureza_operacao,
                            operacao_com_contribuinte, origem_mercadoria, vigencia_inicio, vigencia_fim,
                            cfop, cst_icms, aliquota_icms, reducao_base_icms,
                            tem_st, margem_st, aliquota_icms_st,
                            aliquota_icms_efetivo, reducao_base_icms_efetivo,
                            codigo_beneficio_fiscal, fonte_legal_id, dispositivo_legal, trecho_citado,
                            status_validacao, aceito_por
                        ) VALUES (?, ?, ?, ?, 'VENDA', 1, '*', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            reg["uf_o"],
                            reg["uf_d"],
                            reg["ncm"],
                            reg["cest"],
                            reg["vig_ini"],
                            reg["vig_fim"],
                            reg["cfop"],
                            reg["cst"],
                            reg["aliq"],
                            reg["red"],
                            reg["st"],
                            reg["mva"],
                            reg["aliq_st"],
                            reg["efet"],
                            reg["red_efet"],
                            reg["cbenef"],
                            fonte_ricms,
                            reg["disp"],
                            reg["trecho"],
                            reg["status"],
                            "seed_sp" if reg["status"] == "ACEITO" else None,
                        ),
                    )
                    registrar_historico(
                        conn,
                        tabela_origem="regras_estaduais_icms",
                        registro_id=int(cur.lastrowid),
                        acao="CRIACAO",
                        usuario="seed_sp",
                        campo="ncm",
                        valor_novo=reg["ncm"],
                        motivo=reg["disp"],
                        auto_commit=False,
                    )
                    resumo["estaduais_inseridas"] += 1

            for uf_t, ncm_t, cest_t, orig_t, num_fci, ci_pct, aliq_int, conv52 in CENARIOS_TERCEIROS_FCI:
                existe = conn.execute(
                    """
                    SELECT id FROM tabela_terceiros
                    WHERE uf_terceiro = ? AND ncm = ? AND cest = ? AND origem_mercadoria = ? AND status_registro = 'ATIVA'
                    """,
                    (uf_t, ncm_t, cest_t, orig_t),
                ).fetchone()
                if not existe:
                    cur = conn.execute(
                        """
                        INSERT INTO tabela_terceiros (
                            uf_terceiro, ncm, cest, origem_mercadoria, vigencia_inicio,
                            exige_fci, aliquota_interestadual_aplicavel, beneficio_convenio_52_91,
                            numero_fci, conteudo_importacao_pct,
                            fonte_legal_id, dispositivo_legal, status_validacao, aceito_por
                        ) VALUES (?, ?, ?, ?, '2026-01-01', ?, ?, ?, ?, ?, ?, ?, 'ACEITO', 'seed_sp')
                        """,
                        (
                            uf_t,
                            ncm_t,
                            cest_t,
                            orig_t,
                            1 if num_fci else 0,
                            aliq_int,
                            conv52,
                            num_fci or None,
                            ci_pct if num_fci else None,
                            fonte_conv,
                            "Resolução Senado 13/2012" if num_fci else "Convênio ICMS 52/1991",
                        ),
                    )
                    registrar_historico(
                        conn,
                        tabela_origem="tabela_terceiros",
                        registro_id=int(cur.lastrowid),
                        acao="CRIACAO",
                        usuario="seed_sp",
                        campo="ncm",
                        valor_novo=ncm_t,
                        motivo="Carga inicial tabela_terceiros",
                        auto_commit=False,
                    )
                    resumo["terceiros_inseridas"] += 1

            # Popula config_erp_importada com erros propositais para testar Frente B
            existe_erp = conn.execute(
                "SELECT COUNT(*) FROM config_erp_importada WHERE lote_importacao = 'SEED-SP-ERP'"
            ).fetchone()[0]
            if not existe_erp:
                erros_erp = [
                    (
                        "SEED-SP-ERP",
                        "PROD-85071090",
                        "85071090",
                        "0105300",
                        "SP",
                        "SP",
                        "VENDA",
                        json.dumps(
                            {
                                "deduz_icms_fcp_custo_medio": "S",
                                "somar_st_fcp_custo_medio": "S",
                                "gera_credito_debito": "N",
                                "escriturar_sem_tributacao": "ISENTAS",
                                "icms_st_pago_empresa_guia": "S",
                            }
                        ),
                    ),
                    (
                        "SEED-SP-ERP",
                        "PLACEHOLDER",
                        "85171300",
                        "2105301",
                        "SP",
                        "SP",
                        "VENDA",
                        json.dumps({"config_placeholder": "829"}),
                    ),
                ]
                for row_erp in erros_erp:
                    conn.execute(
                        """
                        INSERT INTO config_erp_importada (
                            lote_importacao, codigo_produto_erp, ncm, cest,
                            uf_origem, uf_destino, natureza_operacao, payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        row_erp,
                    )
                    resumo["erp_importadas"] += 1

        if gerar_template:
            gerar_planilha_modelo_sp()

        return resumo
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed inicial híbrido de SP (RevTributaria)")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Caminho para o banco SQLite")
    parser.add_argument("--offline", action="store_true", help="Usa apenas dataset curado local sem rede")
    args = parser.parse_args(argv)

    resumo = executar_seed_sp(args.db, usar_rede=not args.offline)
    print(f"[SEED SP] Concluído: {resumo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
