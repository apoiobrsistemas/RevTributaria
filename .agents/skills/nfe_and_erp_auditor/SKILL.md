---
name: nfe_and_erp_auditor
description: Pipeline de auditoria em duas frentes: (A) conferência item a item de XML NF-e/NFS-e contra a lei e (B) auditoria completa da matriz tributária importada do ERP (flags de custo, crédito, escrituração, ST em guia e cBenef).
---

# Auditoria de Documentos Fiscais (XML) e Matriz ERP

## Frente A: Auditoria de XML NF-e (13 Etapas Sequenciais)
1. **Filtro de Status**: Ignorar canceladas (`eventos 110111/110112`) e complementares (`finNFe == 2`, apenas referenciá-las na nota original).
2. **Match de Regra Vigente**: Buscar em `regras_estaduais_icms` e `regras_federais` pela chave da operação vigente na `dhEmi`.
3. **NCM & TIPI**: NCM ausente ou fora da TIPI = `Erro`; divergente do cadastro = `Atenção`.
4. **Origem & FCI**: Converter origem do fornecedor para loja (`1->2`, `6->7`) e validar contra percentual de FCI.
5. **CFOP Conferível**: Venda (`x.101/102/401/403`, ZFM `x.109/110`) e bonificação (`x.910`). Comodato/demonstração = `Sem regra`.
6. **CEST**: Ausente em produto sujeito a ST ou divergente = `Erro`; exceção semântica no Convênio 142 (`cest_confere=False`) = `Atenção`.
7. **ICMS Próprio, Desoneração & Diferimento**: Validar carga, valor, `cBenef`, motivo de desoneração e dedução no total da nota (`vNF`).
8. **Responsável pela ST**: Validar retenção na nota vs. recolhimento pela empresa em guia (`icms_st_pago_empresa_guia`).
9. **CST/CSOSN e CFOP**: `Erro` se divergir. **Anti-Ruído**: Não repetir texto de motivo se a causa raiz foi apontada nos passos 7 ou 8.
10. **Uso/Consumo com ST e Acordo**: Exigir retenção apenas de DIFAL (sem MVA). MVA cobrada = `Atenção`.
11. **MVA, ST, Estimativa, FCP-ST e ICMS Efetivo**: Validar `vBCST`, `vICMSST`, `vFCPST` e tags `vBCEfet`/`vICMSEfet` (quando CST 60/CSOSN 500).
12. **IPI, PIS/COFINS e IBS/CBS**: Validar `cEnq`, alíquota TIPI (com Ex), monofásico/alíquota zero de PIS/COFINS e tags de transição `IBS/CBS` + `cClassTrib`.
13. **Auditoria de Matriz ERP (Frente B)**: Comparar linha da tabela `config_erp_importada` contra a lei esperada.

## Frente B: Auditoria Específica de Campos Internos do ERP
Ao auditar `config_erp_importada`, apontar divergência exata de configuração quando o ERP diferir da regra legal nas flags operacionais:
- **Custo Médio**: `deduz_icms_fcp_custo_medio` e `somar_st_fcp_custo_medio` (se ST não recupera crédito, deve somar no custo; se ICMS é recuperável, deve deduzir).
- **Escrituração Fiscal**: `gera_credito_debito` (S/N), `ipi_gera_credito_debito` (S/N) e `escriturar_sem_tributacao` (Isentas vs. Outras).
- **Base pelo Lucro**: `base_icms_obtida_lucro` e `base_pis_cofins_obtida_lucro`.
- **Recolhimento ST**: `icms_st_pago_empresa_guia` vs. retenção na fonte (`recolhe_st`).
- **Config Placeholder**: Qualquer produto vinculado à configuração genérica inicial do ERP = `Erro`.

## Tolerâncias
- Percentuais: `± 0.01 p.p.` | Carga ICMS Próprio: `± 0.02 p.p.` | Valores R$: `max(0.05, esperado * 0.001)`.