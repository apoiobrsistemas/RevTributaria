---
name: START
description: Esteira operacional do projeto RevTributaria (Python + SQLite WAL) orquestrando os 4 agentes (@agent_db_architect, @agent_tax_auditor, @agent_law_guard, @agent_linx_integrator) e suas respectivas skills fiscais.
---

# RevTributaria - Esteira Operacional de Execução

> **Regra Primordial de Execução:** Nenhum código, schema ou regra fiscal deve ser criado ou alterado sem consultar as skills obrigatórias da respectiva etapa. A lei oficial (`.gov.br`, `.leg.br`, `.jus.br`, `.mp.br`) prevalece sempre sobre o XML do fornecedor e sobre o cadastro do ERP.

---

## Matriz de Atribuição: Agentes vs. Skills

| Etapa / Domínio | Agente Responsável | Skills Obrigatórias |
| :--- | :--- | :--- |
| **1. Schema SQLite, Migração & Integridade** | `@agent_db_architect` | `sqlite_fiscal_schema`, `fiscal_qa_validator` |
| **2. Motor Matemático (11 Blocos)** | `@agent_tax_auditor` | `fiscal_math_engine`, `fiscal_qa_validator` |
| **3. Auditoria NF-e (XML) & Matriz ERP** | `@agent_tax_auditor` + `@agent_linx_integrator` | `nfe_and_erp_auditor`, `fiscal_qa_validator` |
| **4. Integração Linx Microvix** | `@agent_linx_integrator` | `linx_microvix_sync`, `nfe_and_erp_auditor` |
| **5. Coleta Oficial & Vigia Noturno** | `@agent_law_guard` | `official_law_scraper`, `fiscal_qa_validator` |
| **6. Interface Visual Local (Streamlit) & Orquestração** | `@agent_tax_auditor` / `@agent_linx_integrator` | `streamlit_fiscal_ui` |

---

## Fluxo de Desenvolvimento em 5 Passos

### Passo 1: Arquitetura SQLite & Governança (`@agent_db_architect`)
1. Carregar `sqlite_fiscal_schema` e `fiscal_qa_validator`.
2. Garantir `PRAGMA journal_mode = WAL;`, `PRAGMA synchronous = NORMAL;`, `PRAGMA foreign_keys = ON;` e `PRAGMA busy_timeout = 5000;`.
3. Manter separação estrita entre Mercadorias (`NCM/CEST`) e Serviços (`regras_servicos` por `CNAE/LC 116/Município`).
4. Proibir colunas calculadas persistidas nas tabelas de regras e exigir optimistic locking (`versao`) + histórico append-only (`historico_alteracoes`) na mesma transação.

### Passo 2: Motor de Cálculo Puro (`@agent_tax_auditor`)
1. Carregar `fiscal_math_engine` e `fiscal_qa_validator`.
2. Usar exclusivamente `decimal.Decimal` (`ROUND_HALF_UP`), sem I/O de banco ou rede nas funções matemáticas.
3. Cobrir: FCI -> Origem (`5`/`3`/`8`) e `4%`, redução por carga (inclusive exceção FECP RJ), MVA ajustado / estimativa simplificada, DIFAL (base única e dupla), desoneração/diferimento, ICMS Efetivo e IBS/CBS.

### Passo 3: Auditoria NF-e & Matriz ERP (`@agent_tax_auditor` + `@agent_linx_integrator`)
1. Carregar `nfe_and_erp_auditor` e `fiscal_qa_validator`.
2. Executar a Frente A (13 etapas sequenciais no XML) e Frente B (flags internas do ERP em `config_erp_importada`), evitando ruído duplicado de alertas.

### Passo 4: Integração Linx Microvix (`@agent_linx_integrator`)
1. Carregar `linx_microvix_sync` e `nfe_and_erp_auditor`.
2. Proibir `TRUNCATE`; usar apenas `UPSERT` (`ON CONFLICT DO UPDATE`), salvar cursor `timestamp` por CNPJ somente após commit e derivar status NF-e via SQL `VIEW` (`110111`/`110112`).

### Passo 5: Coleta Oficial, Vigia Noturno & Gatekeeper QA (`@agent_law_guard` + Todos)
1. Carregar `official_law_scraper` e `fiscal_qa_validator`.
2. Bloquear URLs fora de `.gov.br`, `.leg.br`, `.jus.br`, `.mp.br`, abortar recortes inválidos e validar citações literalmente.
3. Rodar `python -m pytest -v` e `.\.agents\workflow.bat` garantindo **exit code 0**.


### Passo 6: Interface Visual Local (`@agent_tax_auditor` / `@agent_linx_integrator`)
1. Carregar `streamlit_fiscal_ui`.
2. Garantir zero `sqlite3` e zero SQL em `src/ui/app.py`: toda operação passa por `src/app/service.py`.
3. Manter as 5 abas obrigatórias + barra lateral com botões de sincronização (`st.status`) e invalidação de cache após mutações.
