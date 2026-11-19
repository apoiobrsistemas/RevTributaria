"""Catálogo completo de canais oficiais (SP, CONFAZ e Federal) para auditoria e Vigia."""

from __future__ import annotations

import sqlite3
from typing import Any

from src.legislation.url_guard import validar_url_oficial

CATALOGO_FONTES_OFICIAIS: list[dict[str, Any]] = [
    # --- SÃO PAULO (SEFAZ-SP, ALESP, DOE-SP) ---
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "RICMS",
        "numero_norma": "Decreto 45.490/2000",
        "titulo": "Regulamento do ICMS do Estado de São Paulo (Corpo Principal)",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/RICMS.aspx",
        "cobertura": "Alíquotas internas, ST (Art. 313-A a 313-Z20), DIFAL, diferimento",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "RICMS_ANEXO_I",
        "numero_norma": "RICMS/SP Anexo I",
        "titulo": "RICMS/SP Anexo I — Isenções do ICMS (cBenef SP01xxxx)",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/anexo01.aspx",
        "cobertura": "Isenções por NCM, CST 40/41 e códigos cBenef SP01xxxx",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "RICMS_ANEXO_II",
        "numero_norma": "RICMS/SP Anexo II",
        "titulo": "RICMS/SP Anexo II — Reduções de Base de Cálculo (cBenef SP02xxxx)",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/anexo02.aspx",
        "cobertura": "Reduções de BC (ex: Art. 27 Informática, Art. 12 Máquinas), CST 20",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "RICMS_ANEXO_III",
        "numero_norma": "RICMS/SP Anexo III",
        "titulo": "RICMS/SP Anexo III — Crédito Outorgado / Presumido",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/anexo03.aspx",
        "cobertura": "Créditos outorgados e presumidos por setor/NCM",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "PORTARIA_ST",
        "numero_norma": "Portaria CAT 68/2019",
        "titulo": "Relação Oficial de Mercadorias Sujeitas à Substituição Tributária em SP",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/pcat682019.aspx",
        "cobertura": "Lista taxativa NCM/CEST com ST vigente em SP e exceções",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "PORTAL_LEGISLACAO",
        "numero_norma": "Portal Legislação SEFAZ-SP",
        "titulo": "Portal de Legislação Tributária SEFAZ-SP (Portarias SRE/CAT, Decretos, Comunicados)",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/Home.aspx",
        "cobertura": "Portarias SRE de IVA-ST (MVA), pautas fiscais e novas alterações",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "RESPOSTA_CONSULTA",
        "numero_norma": "Respostas à Consulta SEFAZ-SP",
        "titulo": "Respostas à Consulta Tributária — Consultoria Tributária SEFAZ-SP",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/Respostas-Consulta.aspx",
        "cobertura": "Interpretação oficial de exceções de NCM, CEST, ST e benefícios",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "CBENEF_SP",
        "numero_norma": "Portaria CAT 42/2018 / cBenef SP",
        "titulo": "Portal NF-e SEFAZ-SP — Códigos de Benefício Fiscal (cBenef)",
        "url_oficial": "https://portal.fazenda.sp.gov.br/servicos/nfe/Paginas/cBenef.aspx",
        "cobertura": "Tabela oficial cBenef SP (SP01, SP02, SP03, SP04, SP05, SP09)",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "LEI_ESTADUAL",
        "numero_norma": "Lei Estadual 6.374/1989",
        "titulo": "ALESP — Lei Orgânica do ICMS do Estado de São Paulo",
        "url_oficial": "https://www.al.sp.gov.br/repositorio/legislacao/lei/1989/lei-6374-01.03.1989.html",
        "cobertura": "Alíquotas nominais, fato gerador e base legal do ICMS-SP",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "LEI_ESTADUAL",
        "numero_norma": "Lei Estadual 17.293/2020",
        "titulo": "ALESP — Ajuste Fiscal SP (Autorizações de redução/benefícios ICMS)",
        "url_oficial": "https://www.al.sp.gov.br/repositorio/legislacao/lei/2020/lei-17293-15.10.2020.html",
        "cobertura": "Complementos de alíquota e revisão de benefícios fiscais em SP",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "DIARIO_OFICIAL",
        "numero_norma": "DOE-SP Executivo",
        "titulo": "Diário Oficial do Estado de São Paulo — Publicações Normativas",
        "url_oficial": "https://www.doe.sp.gov.br/",
        "cobertura": "Publicação diária de novos Decretos e Portarias SRE",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "TRANSPARENCIA_SP",
        "numero_norma": "Transparência Fiscal SP",
        "titulo": "Portal da Transparência Fiscal e Benefícios Tributários — SEFAZ-SP",
        "url_oficial": "https://portal.fazenda.sp.gov.br/acessoinformacao/Paginas/default.aspx",
        "cobertura": "Renúncias fiscais, regimes especiais, concessões e benefícios vigentes em SP",
    },
    {
        "uf": "SP",
        "esfera": "ESTADUAL",
        "tipo_norma": "DECISAO_NORMATIVA",
        "numero_norma": "Decisões Normativas CAT SP",
        "titulo": "SEFAZ-SP — Decisões Normativas CAT (Critérios Vinculantes ICMS-SP)",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/Decisoes-Normativas.aspx",
        "cobertura": "Critérios vinculantes (ex: DN CAT 05/2009 autopeças, crédito e ST)",
    },
    # --- CONFAZ (NACIONAL / INTERESTADUAL) ---
    {
        "uf": "BR",
        "esfera": "CONFAZ",
        "tipo_norma": "CONVENIO",
        "numero_norma": "Convênio ICMS 142/2018",
        "titulo": "CONFAZ — Regimes de Substituição Tributária e Tabela CEST Nacional",
        "url_oficial": "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18",
        "cobertura": "Correlação oficial CEST x NCM e segmentos sujeitos à ST",
    },
    {
        "uf": "BR",
        "esfera": "CONFAZ",
        "tipo_norma": "CONVENIO",
        "numero_norma": "Convênio ICMS 52/1991",
        "titulo": "CONFAZ — Redução de Base de Cálculo para Máquinas e Implementos",
        "url_oficial": "https://www.confaz.fazenda.gov.br/legislacao/convenios/1991/CV052_91",
        "cobertura": "Anexos I e II com NCMs de máquinas industriais e agrícolas",
    },
    {
        "uf": "BR",
        "esfera": "CONFAZ",
        "tipo_norma": "CONVENIO",
        "numero_norma": "Convênio ICMS 100/1997",
        "titulo": "CONFAZ — Benefícios Fiscais para Insumos Agropecuários",
        "url_oficial": "https://www.confaz.fazenda.gov.br/legislacao/convenios/1997/CV100_97",
        "cobertura": "Isenção e redução de BC em operações com insumos agropecuários",
    },
    {
        "uf": "BR",
        "esfera": "CONFAZ",
        "tipo_norma": "CONVENIO",
        "numero_norma": "Convênio ICMS 65/1988",
        "titulo": "CONFAZ — Isenção Zona Franca de Manaus e Áreas de Livre Comércio",
        "url_oficial": "https://www.confaz.fazenda.gov.br/legislacao/convenios/1988/CV065_88",
        "cobertura": "Desoneração para remessas à ZFM/ALC",
    },
    {
        "uf": "BR",
        "esfera": "CONFAZ",
        "tipo_norma": "PROTOCOLO_ST",
        "numero_norma": "Protocolos ICMS CONFAZ",
        "titulo": "CONFAZ — Protocolos de Substituição Tributária Interestadual",
        "url_oficial": "https://www.confaz.fazenda.gov.br/legislacao/protocolos",
        "cobertura": "Acordos de ST entre SP e demais UFs (concessões e exclusões)",
    },
    # --- FEDERAL (SISCOMEX, RFB, PORTAL NF-E, SPED, PLANALTO) ---
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "NCM_SISCOMEX",
        "numero_norma": "Tabela NCM Siscomex",
        "titulo": "Portal Único Siscomex — Nomenclatura Comum do Mercosul (JSON Oficial)",
        "url_oficial": "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json",
        "cobertura": "Vigência oficial de todos os códigos NCM (inclusões e extinções)",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "TIPI",
        "numero_norma": "Decreto 11.158/2022",
        "titulo": "Receita Federal — Tabela de Incidência do IPI (TIPI e Ex-TIPI)",
        "url_oficial": "https://www.gov.br/receitafederal/pt-br/acesso-a-informacao/legislacao/documentos-e-arquivos/tipi.xlsx",
        "cobertura": "Alíquotas de IPI por NCM e exceções Ex-TIPI",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "TABELAS_NFE",
        "numero_norma": "Portal Nacional NF-e",
        "titulo": "Portal Nacional da NF-e — Tabelas CFOP, cBenef, NCM e cClassTrib (IBS/CBS)",
        "url_oficial": "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=Iy/5Qol1YbE=",
        "cobertura": "Tabelas nacionais de cBenef por UF, CFOP, NCM e IBS/CBS",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "SPED_TABELAS",
        "numero_norma": "Portal SPED RFB",
        "titulo": "Portal SPED Receita Federal — Tabelas EFD ICMS/IPI e EFD Contribuições",
        "url_oficial": "https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/sped",
        "cobertura": "Tabelas 4.3.10+ (Monofásicos e Alíquota Zero PIS/COFINS) e ajustes SPED",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "LEI",
        "numero_norma": "Lei Complementar 87/1996",
        "titulo": "Planalto — Lei Kandir (Normas Gerais do ICMS)",
        "url_oficial": "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp87.htm",
        "cobertura": "Base de cálculo, não-cumulatividade, ST e DIFAL nacional",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "LEI",
        "numero_norma": "Lei 10.485/2002",
        "titulo": "Planalto — PIS/COFINS Monofásico (Autopeças e Máquinas)",
        "url_oficial": "https://www.planalto.gov.br/ccivil_03/leis/2002/l10485.htm",
        "cobertura": "NCMs sujeitos à tributação monofásica de PIS/COFINS",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "LEI",
        "numero_norma": "Lei 10.147/2000",
        "titulo": "Planalto — PIS/COFINS Monofásico (Perfumaria, Cosméticos e Fármacos)",
        "url_oficial": "https://www.planalto.gov.br/ccivil_03/leis/2000/l10147.htm",
        "cobertura": "NCMs de perfumaria, higiene e medicamentos com CST 04/70",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "LEI",
        "numero_norma": "Lei Complementar 214/2025",
        "titulo": "Planalto — Reforma Tributária (IBS, CBS e Imposto Seletivo)",
        "url_oficial": "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214.htm",
        "cobertura": "Regimes diferenciados, reduções de alíquota e cesta básica IBS/CBS",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "API_CLASSTRIB_SVRS",
        "numero_norma": "API SVRS Conformidade Fácil (cClassTrib)",
        "titulo": "SVRS / SEFAZ — API Pública Oficial de Classificação Tributária IBS/CBS",
        "url_oficial": "https://cff.svrs.rs.gov.br/api/v1/consultas/classTrib",
        "cobertura": "JSON oficial de CST IBS/CBS, cClassTrib e reduções da LC 214/2025",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "API_TABX_SISCOMEX",
        "numero_norma": "API Siscomex TabX (Tabelas Aduaneiras)",
        "titulo": "Portal Único Siscomex — API Pública de Tabelas Aduaneiras e Atributos NCM",
        "url_oficial": "https://portalunico.siscomex.gov.br/tabx/api/publico/tabelas",
        "cobertura": "Metadados oficiais de tabelas NCM, atributos, II e exceções tarifárias",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "PORTAL_SVRS_DFE",
        "numero_norma": "Portal SVRS DF-e (Documentos & cBenef)",
        "titulo": "SVRS — Portal DF-e (Esquemas XML, Regras de Validação e cBenef)",
        "url_oficial": "https://dfe-portal.svrs.rs.gov.br/Nfe/Documentos",
        "cobertura": "Notas Técnicas NF-e, tabelas de rejeição e validações de cBenef",
    },
    {
        "uf": "BR",
        "esfera": "CONFAZ",
        "tipo_norma": "ATOS_COTEPE",
        "numero_norma": "Atos COTEPE/ICMS & Despachos CONFAZ",
        "titulo": "CONFAZ — Atos COTEPE/ICMS (PMPF, Combustíveis e Obrigações Acessórias)",
        "url_oficial": "https://www.confaz.fazenda.gov.br/legislacao/atos-cotepe",
        "cobertura": "Pautas fiscais PMPF, atos técnicos e alterações de convênios",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "CMED_ANVISA",
        "numero_norma": "Lista CMED / ANVISA (Medicamentos)",
        "titulo": "ANVISA / CMED — Preços de Medicamentos (PMC/PF) e Listas Positiva/Negativa/Neutra",
        "url_oficial": "https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos",
        "cobertura": "Base oficial para ST de medicamentos (Cap. 30) e redutores de PMC",
    },
    {
        "uf": "BR",
        "esfera": "FEDERAL",
        "tipo_norma": "SPED_EFD_CONTRIB",
        "numero_norma": "Tabelas 4.3.10–4.3.13 EFD-Contribuições",
        "titulo": "Receita Federal — Tabelas Oficiais PIS/COFINS Monofásico e Alíquota Zero",
        "url_oficial": "https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/declaracoes-e-demonstrativos/sped/tabelas-de-codigos-efd-contribuicoes",
        "cobertura": "NCMs oficiais de CST 04 (Monofásico), CST 05 (ST) e CST 06 (Alíquota Zero)",
    },
]

# Checklist 100%: Os 8 portais indispensáveis para validação fiscal em São Paulo
MAPA_8_PORTAIS_SP: list[dict[str, str]] = [
    {
        "ordem": "1",
        "portal": "Portal da Legislação Tributária SEFAZ-SP (RICMS/2000)",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/Home.aspx",
        "formato": "HTML Estruturado",
        "ciclo_captura": "Diária (06:00 BRT)",
        "criticidade": "Crítica",
        "risco_omissao": "Perda de alterações nos Anexos I/II (benefícios) e exclusões de mercadorias do regime de ST nos artigos 313.",
    },
    {
        "ordem": "2",
        "portal": "Portarias SRE / CAT (MVA / IVA-ST & Obrigações)",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/Portarias.aspx",
        "formato": "HTML / Tabelas Anexas",
        "ciclo_captura": "Diária (06:15 BRT)",
        "criticidade": "Crítica",
        "risco_omissao": "Aplicação de IVA-ST defasado ou retenção indevida de ICMS-ST em produtos recém-excluídos (ex: Portaria SRE 74/2025 Azeite de Oliva).",
    },
    {
        "ordem": "3",
        "portal": "Portal NF-e SP — Tabela Oficial CST x cBenef (SRE 70/2025)",
        "url_oficial": "https://portal.fazenda.sp.gov.br/servicos/nfe/Paginas/cBenef.aspx",
        "formato": "XLSX / CSV Oficial",
        "ciclo_captura": "Diária (06:30 BRT)",
        "criticidade": "Bloqueante (Emissão)",
        "risco_omissao": "Rejeição imediata da NF-e/NFC-e (Rejeições 930/931/932) por cBenef inexistente, expirado ou incompatível com o CST.",
    },
    {
        "ordem": "4",
        "portal": "Decretos Autônomos & Respostas à Consulta (RC)",
        "url_oficial": "https://legislacao.fazenda.sp.gov.br/Paginas/DecretosBeneficios.aspx",
        "formato": "HTML / PDF",
        "ciclo_captura": "Diária (07:00 BRT)",
        "criticidade": "Alta",
        "risco_omissao": "Interpretação equivocada sobre 'Ex' de descrição, embalagens (>1kg vs <=1kg) e aplicabilidade de reduções de BC.",
    },
    {
        "ordem": "5",
        "portal": "Diário Oficial do Estado de São Paulo (DOE-SP)",
        "url_oficial": "https://www.doe.sp.gov.br/",
        "formato": "JSON API / HTML",
        "ciclo_captura": "Diária (05:30 BRT)",
        "criticidade": "Alta",
        "risco_omissao": "Delay de 24h a 72h entre a publicação legal no DOE e a consolidação textual no Portal da Legislação.",
    },
    {
        "ordem": "6",
        "portal": "CONFAZ — Convênios e Protocolos ICMS",
        "url_oficial": "https://www.confaz.fazenda.gov.br/legislacao/convenios",
        "formato": "HTML / Tabelas CEST",
        "ciclo_captura": "Diária (07:30 BRT)",
        "criticidade": "Crítica",
        "risco_omissao": "Erro no cálculo de DIFAL-ST ou retenção interestadual sem protocolo vigente entre SP e a UF de destino/origem.",
    },
    {
        "ordem": "7",
        "portal": "Portal Único Siscomex & Receita Federal (NCM / TIPI)",
        "url_oficial": "https://portalunico.siscomex.gov.br/classif/",
        "formato": "JSON API / XLSX",
        "ciclo_captura": "Semanal + Alertas DOU",
        "criticidade": "Bloqueante (Emissão)",
        "risco_omissao": "Uso de NCM suprimida ou desmembrada pela CAMEX, invalidando toda a árvore de regras estaduais vinculadas.",
    },
    {
        "ordem": "8",
        "portal": "Portal da Transparência Fiscal SP — Benefícios Concedidos",
        "url_oficial": "https://portal.fazenda.sp.gov.br/acessoinformacao/Paginas/Beneficios-Fiscais-Concedidos.aspx",
        "formato": "XLSX / ODS",
        "ciclo_captura": "Mensal",
        "criticidade": "Média",
        "risco_omissao": "Desconhecimento de regimes especiais setoriais (TTD/RE) ou validações de contraparte na cadeia de suprimentos.",
    },
]

_SEFAZ_26_UFS: tuple[tuple[str, str, str], ...] = (
    ("AC", "SEFAZ-AC — RICMS/AC & Tabelas ST", "https://sefaznet.ac.gov.br/legislacao/"),
    ("AL", "SEFAZ-AL — RICMS/AL & Antecipação Tributária", "https://www.sefaz.al.gov.br/legislacao"),
    ("AM", "SEFAZ-AM — RICMS/AM & Substituição Tributária", "https://www.sefaz.am.gov.br/legislacao/"),
    ("AP", "SEFAZ-AP — RICMS/AP & Legislação Tributária", "https://www.sefaz.ap.gov.br/legislacao/"),
    ("BA", "SEFAZ-BA — RICMS/BA, Anexo 1 ST & Antecipação", "https://www.sefaz.ba.gov.br/legislacao/"),
    ("CE", "SEFAZ-CE — RICMS/CE & Carga Líquida ST", "https://www.sefaz.ce.gov.br/legislacao/"),
    ("DF", "SEEC-DF — RICMS/DF & Tabela cBenef DF", "https://www.receita.fazenda.df.gov.br/legislacao"),
    ("ES", "SEFAZ-ES — RICMS/ES & Anexos ST/Benefícios", "https://internet.sefaz.es.gov.br/legislacao/"),
    ("GO", "ECONOMIA-GO — RCTE/GO, Anexo VIII ST & cBenef", "https://www.economia.go.gov.br/legislacao-tributaria"),
    ("MA", "SEFAZ-MA — RICMS/MA & Anexo 4.13 ST", "https://sistemas1.sefaz.ma.gov.br/portalsefaz/legislacao"),
    ("MG", "SEF-MG — RICMS/MG (Dec. 48.589/2023) & Anexo XV ST", "https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/"),
    ("MS", "SEFAZ-MS — RICMS/MS & Anexo III ST", "https://www.sefaz.ms.gov.br/legislacao/"),
    ("MT", "SEFAZ-MT — RICMS/MT & Estimativa Simplificada", "https://www.sefaz.mt.gov.br/portal/legislacao/"),
    ("PA", "SEFA-PA — RICMS/PA & Anexo XIII ST", "https://www.sefa.pa.gov.br/legislacao/"),
    ("PB", "SEFAZ-PB — RICMS/PB & Anexos ST/cBenef", "https://www.sefaz.pb.gov.br/legislacao"),
    ("PE", "SEFAZ-PE — RICMS/PE & Decretos ST", "https://www.sefaz.pe.gov.br/Legislacao"),
    ("PI", "SEFAZ-PI — RICMS/PI & Anexo V-A ST", "https://portal.sefaz.pi.gov.br/legislacao/"),
    ("PR", "SEFA-PR — RICMS/PR, Anexo IX ST & Tabela cBenef", "https://www.fazenda.pr.gov.br/Pagina/Legislacao-Tributaria"),
    ("RJ", "SEFAZ-RJ — RICMS/RJ, FECP & Tabela cBenef RJ", "https://www.fazenda.rj.gov.br/sefaz/faces/oracle/webcenter/portalapp/pages/navigation-renderer.jspx"),
    ("RN", "SET-RN — RICMS/RN & Anexos ST", "https://www.set.rn.gov.br/legislacao"),
    ("RO", "SEFIN-RO — RICMS/RO & Anexo VI ST", "https://www.sefin.ro.gov.br/legislacao"),
    ("RR", "SEFAZ-RR — RICMS/RR & Legislação Tributária", "https://www.sefaz.rr.gov.br/legislacao"),
    ("RS", "SEFAZ-RS — RICMS/RS, Apêndice II ST & Tabela cBenef RS", "https://www.sefaz.rs.gov.br/legislacao/"),
    ("SC", "SEF-SC — RICMS/SC, Anexo 3 ST & Tabela cBenef SC", "https://legislacao.sef.sc.gov.br/"),
    ("SE", "SEFAZ-SE — RICMS/SE & Substituição Tributária", "https://www.sefaz.se.gov.br/legislacao"),
    ("TO", "SEFAZ-TO — RICMS/TO & Anexos ST", "https://www.sefaz.to.gov.br/legislacao/"),
)

CATALOGO_FONTES_OFICIAIS.extend(
    [
        {
            "uf": uf,
            "esfera": "ESTADUAL",
            "tipo_norma": "RICMS_SEFAZ",
            "numero_norma": f"RICMS-{uf}",
            "titulo": titulo,
            "url_oficial": url,
            "cobertura": f"RICMS/{uf}, Anexos de Isenção/RBC, MVA/IVA-ST, PMPF e cBenef {uf}",
        }
        for uf, titulo, url in _SEFAZ_26_UFS
    ]
)

CATALOGO_FONTES_OFICIAIS.extend(
    [
        {
            "uf": "BR",
            "esfera": "FEDERAL",
            "tipo_norma": "LEI_COMPLEMENTAR",
            "numero_norma": "LC 123/2006",
            "titulo": "Planalto — Lei Complementar 123/2006 (Simples Nacional & Art. 23 Crédito)",
            "url_oficial": "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp123.htm",
            "cobertura": "CSOSN 101-900, permissão de crédito Art. 23 e vedação de ajuste MVA",
        },
        {
            "uf": "BR",
            "esfera": "FEDERAL",
            "tipo_norma": "AJUSTE_SINIEF",
            "numero_norma": "Ajuste SINIEF 07/2005",
            "titulo": "CONFAZ — Ajuste SINIEF 07/2005 (NF-e, CST, CSOSN e Rejeições)",
            "url_oficial": "https://www.confaz.fazenda.gov.br/legislacao/ajustes/2005/AJ007_05",
            "cobertura": "Estrutura nacional da NF-e, CST/CSOSN, CFOP e regras de validação",
        },
    ]
)


def garantir_fontes_oficiais(conn: sqlite3.Connection) -> dict[str, int]:
    """Insere ou atualiza de forma idempotente todas as fontes oficiais mapeadas."""
    inseridas = 0
    existentes = 0
    with conn:
        for fonte in CATALOGO_FONTES_OFICIAIS:
            url = validar_url_oficial(str(fonte["url_oficial"]))
            row = conn.execute(
                "SELECT id FROM fontes_legais WHERE url_oficial = ?",
                (url,),
            ).fetchone()
            if row is not None:
                existentes += 1
                continue

            conn.execute(
                """
                INSERT INTO fontes_legais (
                    uf, esfera, tipo_norma, numero_norma, titulo, url_oficial, status_fonte
                ) VALUES (?, ?, ?, ?, ?, ?, 'ATIVA')
                """,
                (
                    fonte["uf"],
                    fonte["esfera"],
                    fonte["tipo_norma"],
                    fonte["numero_norma"],
                    fonte["titulo"],
                    url,
                ),
            )
            inseridas += 1

    return {
        "total_catalogo": len(CATALOGO_FONTES_OFICIAIS),
        "inseridas": inseridas,
        "ja_existentes": existentes,
    }
