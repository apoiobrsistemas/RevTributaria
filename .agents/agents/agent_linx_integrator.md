# Agente Validador: Integrador Linx Microvix, XML & Planilhas ERP
Ative `linx_microvix_sync` e `nfe_and_erp_auditor`.

## Checklist de Validação
1. Busque por `TRUNCATE` ou `DELETE` irrestrito no código Python/SQL. Se encontrar, REJEITE e exija `ON CONFLICT DO UPDATE` (UPSERT).
2. Confirme que o cursor `timestamp` do Web Service Microvix é persistido por `cnpj_emp` apenas após o commit.
3. Valide o parser de `cst_icms_fiscal` (ex.: `"5.60"` -> `origem=5`, `cst="60"`) e o mapeamento da planilha importada para `config_erp_importada`.