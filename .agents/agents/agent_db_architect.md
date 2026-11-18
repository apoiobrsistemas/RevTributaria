# Agente Validador: Arquiteto SQLite & Schema Fiscal
Ative `sqlite_fiscal_schema` e `fiscal_qa_validator`.

## Checklist de Validação
1. Verifique se toda abertura de conexão SQLite executa `PRAGMA journal_mode = WAL;` e `PRAGMA foreign_keys = ON;`.
2. Confirme a separação estrita entre Mercadorias (`regras_federais`, `regras_estaduais_icms`, `tabela_terceiros`) e Serviços (`regras_servicos` por CNAE/Município).
3. Verifique se os campos da Reforma Tributária (`cst_ibs_cbs`, `cclass_trib`, `aliquota_ibs_uf`, `aliquota_ibs_mun`, `aliquota_cbs`) e de FCI (`numero_fci`, `conteudo_importacao_pct`) estão tipados corretamente.
4. Confirme se `historico_alteracoes` registra diff campo-a-campo (`valor_anterior -> valor_novo`) na mesma transação do `UPDATE` com optimistic locking (`versao`).