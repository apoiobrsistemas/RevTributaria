---
name: linx_microvix_sync
description: Sincronização Python com Web Service XML do Linx Microvix, controle incremental por timestamp por CNPJ, UPSERT seguro no SQLite e importação de planilhas de matriz tributária.
---

# Integração Linx Microvix & Importador de Matriz ERP

## Web Service Microvix (`POST https://webapi.microvix.com.br/1.0/api/integracao`)
- Autenticação pública `linx_export` + `chave` (UUID do portal lido exclusivamente de `os.environ["MICROVIX_CHAVE"]`).
- Parser XML (`xml.etree.ElementTree` ou `lxml`): mapear `ResponseData/C/D` (colunas) com `ResponseData/R/D` (linhas).
- Retry automático com backoff exponencial (3 tentativas) para timeouts.

## Regras SQLite para Carga Linx
1. **Proibido `TRUNCATE` ou `DELETE` global**: Usar `INSERT INTO ... ON CONFLICT(empresa, cod_produto) DO UPDATE SET ...` (UPSERT SQLite).
2. **Timestamp por Loja**: O filtro `timestamp` da API retorna registros com `timestamp > valor_informado`. Salvar `ultimo_timestamp` por `cnpj_emp` somente após commit da transação.
3. **Leitura das Pernas da Matriz (`LinxConfiguracoesTributariasDetalhes`)**:
   - Separar origem e CST de `cst_icms_fiscal` (ex.: `"5.60"` -> `origem = 5`, `cst = "60"`).
   - Mapear pernas configuradas para venda consumidor (`5.102` / `<UF> NC`) e compra fornecedor (`1.102` / `<UF_FORN> CO`), além de alimentar `config_erp_importada` para auditoria dos ~70 campos.