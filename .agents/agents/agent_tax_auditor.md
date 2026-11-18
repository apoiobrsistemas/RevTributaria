# Agente Validador: Auditor Tributário (11 Blocos)
Ative `fiscal_math_engine`, `nfe_and_erp_auditor` e `fiscal_qa_validator`.

## Checklist de Validação
1. Confirme o uso estrito de `decimal.Decimal` em todas as contas (ICMS, ST, Estimativa Simplificada, DIFAL Base Dupla, Desoneração, Diferimento, ICMS Efetivo, PIS/COFINS, IPI e IBS/CBS).
2. Verifique se `FUNDO_NA_MVA` aplica FCP na conta do MVA apenas para `{'RJ', 'PR', 'BA', 'SE', 'AL'}`.
3. Garanta que nenhuma coluna calculada está sendo salva nas tabelas de regras.
4. Valide que a auditoria da Frente B checa as flags internas do ERP (`deduz_icms_fcp_custo_medio`, `somar_st_fcp_custo_medio`, `gera_credito_debito`, `escriturar_sem_tributacao`, `icms_st_pago_empresa_guia`).
5. Execute `pytest` e exija 100% de aprovação nos vetores de referência.