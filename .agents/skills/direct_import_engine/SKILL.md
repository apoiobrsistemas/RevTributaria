---
name: direct_import_engine
description: Motor de Importação Direta do Exterior (DI, DUIMP, NF-e Entrada CFOP 3.xxx), governança TEC/CAMEX/TIPI/Siscomex e cálculo "por dentro" do ICMS-Importação com reflexo na saída subsequente.
---

# Direct Import Engine (`direct_import_engine`)

Skill oficial do módulo de **Importação Direta do Exterior e Auditoria de NF-e de Entrada (CFOP 3.xxx)** do RevTributária.

## 1. Fontes Oficiais Obrigatórias (Whitelist `.gov.br` / `.leg.br`)
- **TEC / CAMEX (`gov.br/mdic`)**: Alíquota do Imposto de Importação (`II`) por NCM e lista de bens sem similar nacional (Resolução CAMEX/Gecex) — define **Origem `6`** vs. **Origem `1`**.
- **Portal Único Siscomex (`portalunico.siscomex.gov.br/classif` e `duimp`)**: Vigência NCM, atributos DUIMP e taxas aduaneiras (Siscomex / AFRMM).
- **TIPI (`gov.br/receitafederal`) & Lei 10.865/2004 (`planalto.gov.br`)**: Alíquota de `IPI` no desembaraço e `PIS/COFINS-Importação` (2,10% / 9,65% + adicional de 1% da COFINS-Importação quando aplicável).
- **MOC NF-e (`nfe.fazenda.gov.br`) & LC 87/96 art. 13, V (`planalto.gov.br`)**: Regras dos grupos `<DI>` e `<adi>` e cálculo "por dentro" do ICMS-Importação.

## 2. Fórmulas Determinísticas (`decimal.Decimal`, `ROUND_HALF_UP`)
1. `Valor Aduaneiro (CIF) = Valor FOB + Frete Internacional + Seguro Internacional`
2. `II = CIF * (Aliq_II / 100)`
3. `Base IPI = CIF + II`; `IPI = Base IPI * (Aliq_IPI / 100)`
4. `PIS_Imp = CIF * (Aliq_PIS_Imp / 100)`; `COFINS_Imp = CIF * ((Aliq_COFINS_Imp + Adicional_COFINS_Imp) / 100)`
5. `Base ICMS "Por Dentro" = (CIF + II + IPI + PIS_Imp + COFINS_Imp + Taxa_Siscomex + AFRMM + Outras_Despesas) / (1 - (Aliq_ICMS_Efetiva + Aliq_FCP) / 100)`
6. `ICMS_Importacao = Base_ICMS * (Aliq_ICMS_Efetiva / 100)` e `FCP = Base_ICMS * (Aliq_FCP / 100)`
7. **Origem & Saída Subsequente:**
   - **Origem `1`** (com similar nacional): na revenda interestadual subsequente converte para **Origem `2`** com alíquota interestadual de **4%** (Res. Senado 13/2012).
   - **Origem `6`** (sem similar nacional — lista CAMEX): na revenda interestadual subsequente converte para **Origem `7`**, mantendo alíquota interestadual de **7% ou 12%** (não sujeita aos 4%).
   - Importador é equiparado a industrial pelo RIPI (Decreto 7.212/2010), mantendo destaque de IPI na saída subsequente quando tributado.

## 3. Regras de Persistência & Auditoria
- Tabelas: `regras_importacao_ncm` (com `versao`, `status IN ('A_CONFERIR', 'ACEITO')`, sem colunas calculadas), `importacao_documentos` e `importacao_itens` (append-only / idempotente).
- Parsers multi-documento: `DUIMP (JSON/XML)`, `DI (XML/PDF)` e `NF-e Entrada 3.xxx (XML)`.
