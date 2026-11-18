---
name: streamlit_fiscal_ui
description: Padrões de arquitetura e UX para a interface visual local em Streamlit (src/ui/app.py), conectada exclusivamente à camada de serviço (src/app/service.py) e aos robôs de sincronização oficial.
---

# Interface Visual Local (Streamlit + Service Layer)

## Regras Arquiteturais da UI
1. **Zero SQL na Interface**: O arquivo `src/ui/app.py` (e seus subcomponentes em `src/ui/tabs/`) NUNCA deve importar `sqlite3` nem executar queries SQL diretamente. Toda leitura, escrita, simulação ou disparo de robô passa exclusivamente pelos métodos de `src/app/service.py`.
2. **Estado e Cache**: Usar `@st.cache_data(ttl=60)` apenas para listagens de leitura (catálogos de UF, fontes oficiais), invalidando o cache (`st.cache_data.clear()`) imediatamente após qualquer aprovação (`ACEITO`), edição com optimistic locking (`versao`) ou execução dos robôs de sincronização.
3. **Feedback Visual de Automação**: Todo disparo de busca automática (`sincronizar_bases_oficiais()`, `sincronizar_linx()`, `executar_vigia()`) deve exibir `st.status(..., expanded=True)` mostrando cada etapa em tempo real (ex.: *Baixando TIPI Receita Federal -> Cruzando CEST CONFAZ 142/18 -> Validando URLs .gov.br*).

## Estrutura Obrigatória das 5 Abas (`src/ui/app.py`)
- **Barra Lateral (Sidebar) — Central de Robôs & Insumos Oficiais**:
  - Indicadores rápidos: data/hora da última sincronização TIPI/Siscomex, CONFAZ, Linx Microvix e última rodada do Vigia.
  - Botões de ação imediata:
    - `🔄 Sincronizar Bases Oficiais (TIPI + Siscomex + CONFAZ + NF-e)` -> chama `service.sincronizar_bases_oficiais()`.
    - `🔌 Sincronizar Linx Microvix (Incremental)` -> chama `service.sincronizar_linx()`.
    - `🛡️ Rodar Vigia da Legislação Agora` -> chama `service.executar_vigia()`.
- **Aba 1: Painel de NCMs & Regras (Matriz Legal)**:
  - Filtros: UF Origem, UF Destino, NCM, CEST, Vigência e Status (`A_CONFERIR`, `ACEITO`, `REJEITADO`).
  - Exibição da origem da linha (`Automático: TIPI/CONFAZ`, `Automático: Linx + IA Oficial`, `Manual`) e link clicável para a fonte `.gov.br`/`.leg.br` com o trecho literal da lei em destaque.
  - Formulário de edição/inclusão exibindo `versao` atual, botão **"Aceitar Regra"** (ou **"Aceitar Marcadas em Lote"**) e painel expansível com o diff campo-a-campo de `historico_alteracoes`.
- **Aba 2: Simulador de Cálculo (11 Blocos)**:
  - Inputs: NCM, CEST, UF Origem, UF Destino, Valor Produto, IPI, FCI (%), Contribuinte (S/N) e Data da Operação.
  - Saída organizada em cards/expanders por bloco: (1) Chave & Origem FCI, (2) ICMS Próprio, (3) FCP & DIFAL (Base Única vs. Dupla), (4) Desoneração/Diferimento/`cBenef`, (5) ICMS-ST / Estimativa Simplificada / MVA Ajustado, (6) ICMS Efetivo, (7) PIS/COFINS, (8) IPI + Ex, (9) Reforma Tributária (`IBS/CBS` + `cClassTrib`), (10) Flags ERP esperadas.
- **Aba 3: Auditor de XML NF-e (Frente A)**:
  - Upload múltiplo (`accept_multiple_files=True`) de `.xml`.
  - Tabela de notas mostrando situação dinâmica da `vw_nfe_status` (`AUTORIZADA`, `CANCELADA`, `COMPLEMENTAR`) e grid item a item destacando células divergentes (`DIVERGENTE` em vermelho, `ATENCAO` em âmbar, `SEM_REGRA` em cinza) com o valor da nota em cima e o da lei embaixo, sem repetir erros em cascata.
- **Aba 4: Comparativo Matriz ERP (Frente B)**:
  - Upload de `.xlsx`/`.csv` da matriz tributária do ERP (`config_erp_importada`) ou comparação direta com a matriz sincronizada do Linx.
  - Destaque visual exclusivo para divergências nas flags internas do ERP (`deduz_icms_fcp_custo_medio`, `somar_st_fcp_custo_medio`, `gera_credito_debito`, `escriturar_sem_tributacao`, `icms_st_pago_empresa_guia`, configurações placeholder).
- **Aba 5: Vigia & Fontes Oficiais**:
  - Catálogo de normas em `fontes_legais` com badge de domínio validado (`.gov.br` / `.leg.br` / `.jus.br` / `.mp.br`) e hash SHA-256.
  - Lista de alertas abertos `VIGIA-AAAAMMDD-UF-GRUPO` exibindo `Antes × Agora`, botão para disparar releitura oficial da UF e campo para registrar motivo de conferência.
