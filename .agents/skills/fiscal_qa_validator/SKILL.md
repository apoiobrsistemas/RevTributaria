---
name: fiscal_qa_validator
description: Suíte Pytest para validar cálculos dos 11 blocos tributários, integridade do schema SQLite WAL, whitelist de URLs oficiais e auditoria de flags do ERP.
---

# Validação e Testes Automatizados (Pytest)

## Vetores de Teste Obrigatórios (`tests/test_fiscal_math.py`)
1. **MVA Ajustado RJ**: `uf_destino='RJ', aliquota=20, fcp=2, mva_original=49, inter=12` -> `Decimal('68.10')`.
2. **Redução por Carga Fixada**:
   - SP: `carga=8.80, aliquota=18.00` -> `Decimal('51.11')`.
   - RJ (com FECP): `carga=14.00, aliquota=20.00, fcp=2.00` -> `Decimal('36.36')`; `carga=8.80` -> `Decimal('60.00')`.
3. **ST Completa**: `valor=1000, ipi=150, mva=68.10, aliquota_st=20, fcp_st=2, carga=12` -> `icms=120.00`, `base_st=1933.15`, `st=266.63`, `fcp_st=38.66`.
4. **DIFAL Base Dupla vs. Base Única**: Validar cálculo com e sem `somar_ipi_base_difal_fcp` e `considerar_reducao_icms_no_fcp`.
5. **ICMS Efetivo (CST 60)**: Validar `vBCEfet` e `vICMSEfet` com redução de base efetiva.
6. **FCI -> Origem**: Validar transição `<=40%` (orig 5), `>40% e <=70%` (orig 3) e `>70%` (orig 8) alterando interestadual para `4%`.

## Testes de Integridade (`tests/test_architecture_guards.py`)
- Verificar que o banco SQLite ativa `journal_mode == 'wal'` e `foreign_keys == 1`.
- Verificar que `regras_servicos` não possui colunas de NCM/CEST e `regras_estaduais_icms` não possui colunas de ISS/CNAE.
- Verificar que todas as URLs em `fontes_legais` passam na regex `.gov.br|.leg.br|.jus.br|.mp.br`.