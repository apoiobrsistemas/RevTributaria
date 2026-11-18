---
name: fiscal_math_engine
description: Motor matemático puro em Python (Decimal) cobrindo ICMS, ST, MVA Ajustado, Estimativa Simplificada, DIFAL Base Única e Dupla, Desoneração, Diferimento, ICMS Efetivo, FCI e Reforma Tributária (IBS/CBS).
---

# Motor de Cálculo Tributário (Python Purista)

## Regras Gerais de Implementação
- Usar `decimal.Decimal` com `ROUND_HALF_UP` (2 casas para valores R$, 2 ou 4 casas para percentuais) para evitar imprecisões de `float`.
- Todas as funções devem ser puras (sem acesso a SQLite ou rede) para testes instantâneos com `pytest`.

## 1. Origem, FCI e Alíquota Interestadual
- Se `conteudo_importacao_pct` (FCI) > 70% -> Origem `8`; entre > 40% e <= 70% -> Origem `3`; <= 40% -> Origem `5`.
- Origem `1, 2, 3, 8` -> Alíquota Interestadual = `4.00%` (Res. Senado 13/2012).
- Demais origens: `12.00%` se `uf_destino` in `{'SP', 'RJ', 'PR', 'RS', 'SC'}`, senão `7.00%` (inclusive `ES`).
- Se `uf_origem == uf_destino`: operação interna.
- Se `tabela_terceiros.reducao_saida_conv52_91 == True`: `inter = min(inter, carga_52_91)` (`8.80%` S/SE/MG ou `5.14%` N/NE/CO/ES).

## 2. Alíquota Interna Efetiva e Redução por Carga
- Quando a lei fixa carga final:
  - Padrão: `reducao_bc = 1 - (carga / aliquota_icms)`.
  - Exceção RJ (carga inclui FECP): `reducao_bc = 1 - (carga / (aliquota_icms + aliquota_fcp))`.
- `fundo_mva = aliquota_fcp` APENAS se `uf_destino` in `{'RJ', 'PR', 'BA', 'SE', 'AL'}`, senão `0`.
- `interna_efetiva`: usa `aliquota_mva_especial` se preenchida (ex.: RS perfumaria 12%); senão `(aliquota_icms + fundo_mva) * (1 - reducao_bc / 100)`.

## 3. ICMS-ST (Padrão MVA vs. Estimativa Simplificada)
- **Regime Estimativa Simplificada / Carga Média** (`regime_estimativa_simplificado == True`, ex.: MT/CE):
  - `valor_st = base_operacao * (perc_carga_tributaria_media / 100)` (não aplica MVA convencional).
- **Regime MVA**:
  - `mva_ajustado = ((1 + mva_original/100) * (1 - inter/100) / (1 - interna_efetiva/100) - 1) * 100` (exceto se operação interna, `nao_ajusta_mva=True`, ou `inter >= interna_efetiva`).
  - `base_st = (operacao + ipi) * (1 + mva_ajustado/100) * (1 - reducao_bc_st/100)`.
  - Se `utiliza_base_icms_para_st == True`: `base_st = base_icms * (1 + mva_ajustado/100)`.
  - `deducao_icms = 0` se `nao_deduzir_icms_do_st == True`, senão `icms_proprio`.
  - `valor_st = max(0, base_st * (aliquota_icms_st / 100) - deducao_icms)`.
  - `valor_fcp_st = base_st * (aliquota_fcp / 100)`.

## 4. DIFAL & FCP (Base Única vs. Base Dupla)
- `base_difal = operacao + (ipi if somar_ipi_base_difal_fcp else 0)`.
- **Base Única**: `difal = base_difal * ((aliquota_interna_destino_difal - aliquota_inter_difal) / 100)`.
- **Base Dupla** (`utiliza_base_dupla_difal == True`):
  - `base_ajustada = (base_difal - icms_origem) / (1 - (aliquota_interna_destino_difal + aliquota_fcp) / 100)`.
  - `difal = (base_ajustada * aliquota_interna_destino_difal / 100) - icms_origem`.
- **FCP**: Se `considerar_reducao_icms_no_fcp == True`, aplicar `reducao_bc_icms` antes de multiplicar por `aliquota_fcp`.

## 5. Desoneração, Diferimento, ICMS Efetivo e IBS/CBS
- **ICMS Desonerado**: Calcular conforme motivo (`cBenef` / `motivo_desoneracao`) e sinalizar se `deduz_icms_desonerado_total_nota == True` impacta `vNF`.
- **ICMS Efetivo** (CST 60 / CSOSN 500): `vBCEfet = operacao * (1 - reducao_bc_icms_efetivo / 100)`; `vICMSEfet = vBCEfet * (aliquota_icms_efetivo / 100)`.
- **Reforma Tributária (IBS/CBS)**: `base_ibs_cbs = operacao` (excluindo ICMS/PIS/COFINS conforme regra de transição); aplicar `reducao_ibs_cbs` antes de `aliquota_ibs_uf`, `aliquota_ibs_mun` e `aliquota_cbs`.