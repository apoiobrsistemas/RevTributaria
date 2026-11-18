---
name: sqlite_fiscal_schema
description: Arquitetura de banco de dados SQLite (WAL mode) para matriz tributária completa de 11 blocos, separação entre Mercadorias (NCM) e Serviços (CNAE), FCI, Reforma Tributária (IBS/CBS) e auditoria append-only.
---

# Arquitetura de Banco de Dados (SQLite + Python)

## Configurações Obrigatórias de Conexão SQLite
Toda conexão Python (`sqlite3` ou SQLAlchemy) deve inicializar imediatamente:
- `PRAGMA journal_mode = WAL;` (leitura concorrente sem travar escrita)
- `PRAGMA synchronous = NORMAL;`
- `PRAGMA foreign_keys = ON;`
- `PRAGMA busy_timeout = 5000;`

## Separação Estrutural das Tabelas (11 Blocos)
1. **`fontes_legais`**: Catálogo de normas oficiais (`.gov.br`, `.leg.br`, `.jus.br`, `.mp.br`), marcadores de recorte e hash SHA-256 do corpo limpo para o Vigia Noturno.
2. **`regras_federais`**: Indexada por `ncm + ex_tipi + cest + vigencia_inicio`.
   - **IPI**: `cst_ipi`, `aliquota_ipi`, `cenq` (Código Enquadramento), `ipi_gera_credito_debito`, `escriturar_sem_tributacao`.
   - **PIS/COFINS**: `cst_pis`, `aliquota_pis`, `cst_cofins`, `aliquota_cofins`, `operacao_receita`, `cod_tipo_base_credito`, `base_obtida_lucro`.
   - **Reforma Tributária (2026+)**: `cst_ibs_cbs`, `cclass_trib`, `aliquota_ibs_uf`, `aliquota_ibs_mun`, `aliquota_cbs`, `reducao_ibs_cbs`, `diferimento_isencao_ibs_cbs`.
3. **`regras_estaduais_icms`**: Indexada por `uf_origem + uf_destino + ncm + cest + natureza_operacao + contribuinte + origem_mercadoria + vigencia_inicio`.
   - **ICMS Próprio & Flags ERP**: `cfop`, `cst_icms`, `csosn`, `aliquota_icms`, `reducao_bc_icms`, `valor_tributavel_icms`, `gera_credito_debito`, `escriturar_sem_tributacao`, `deduz_icms_fcp_custo_medio`, `base_icms_obtida_lucro`, `obs_padrao`.
   - **FCP & DIFAL**: `aliquota_fcp`, `somar_ipi_base_difal_fcp`, `considerar_reducao_icms_no_fcp`, `aliquota_interna_destino_difal`, `aliquota_inter_difal`, `utiliza_base_dupla_difal`.
   - **Desoneração, Crédito Presumido & Diferimento**: `aliquota_icms_desonerado`, `aliquota_fcp_desonerado`, `motivo_desoneracao`, `cbenef`, `perc_credito_presumido`, `deduz_icms_desonerado_total_nota`, `aliquota_diferimento`, `perc_fcp_diferimento`, `obs_diferimento`.
   - **ICMS-ST & Estimativa**: `tem_st`, `recolhe_st` (`fornecedor` | `empresa_guia`), `acordo_st`, `aliquota_icms_st`, `mva_original`, `nao_ajusta_mva`, `aliquota_mva_especial`, `reducao_bc_st`, `utiliza_base_icms_para_st`, `nao_deduzir_icms_do_st`, `regime_estimativa_simplificado`, `perc_carga_tributaria_media`, `encerra_st`, `antecipacao_parcial`, `somar_st_fcp_custo_medio`.
   - **ICMS Efetivo**: `aliquota_icms_efetivo`, `reducao_bc_icms_efetivo` (obrigatório quando CST 60 / CSOSN 500).
4. **`tabela_terceiros`** (evolução da Tabela DL): Regras de entrada/fornecedores/importação: `ncm + cest + uf_fornecedor`, `cest_confere`, `ncm_em_vigor`, `reducao_saida_conv52_91`, `zona_franca_conv65_88`, e dados de **FCI** do produto (`numero_fci`, `conteudo_importacao_pct`, `valor_parcela_importada`, `valor_total_saida_inter`).
5. **`regras_servicos`** (Domínio Isolado — NUNCA misturar com NCM): Indexada por `cnae + item_lc116 + municipio_prestacao + municipio_incidencia`: `quem_paga_iss`, `iss_retido`, `natureza_operacao_servico`, `cst_pis_cofins_servico`, `aliquotas_pis_cofins`, `cod_retencao_csrf`, `aliquotas_pis_cofins_csll_retido`.
6. **`config_erp_importada`**: Espelho da matriz tributária exportada do ERP / Linx para auditoria de flags e alíquotas.
7. **`historico_alteracoes`**: Tabela append-only (`tabela`, `registro_id`, `acao`, `campo`, `valor_anterior`, `valor_novo`, `motivo`, `usuario`, `criado_em`).

## Regras de Integridade
- **Optimistic Locking**: Toda linha editável possui `versao` (`INTEGER`). Updates exigem `WHERE id = ? AND versao = ?`.
- **Soft Delete**: Nenhuma regra é apagada (`DELETE`); usa-se `status = 'excluida'` e `vigencia_fim`.
- **Colunas Calculadas**: MVA ajustado, redução derivada de carga, CST/CFOP esperados e valores de impostos são calculados em Python, NUNCA persistidos nas tabelas de regras.