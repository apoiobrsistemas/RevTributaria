"""Motor de cálculo tributário puro (Decimal) e auditoria NF-e / ERP."""

from src.engine.auditor import (
    TOL_CARGA_ICMS_PP,
    TOL_PERCENTUAL_PP,
    TOL_VALOR_MIN,
    TOL_VALOR_PCT,
    Divergencia,
    auditar_config_erp,
    auditar_nfe_contra_lei,
    dentro_tolerancia_percentual,
    dentro_tolerancia_valor,
)
from src.engine.fiscal_engine import (
    ALIQUOTAS_INTERNAS_UF,
    DESCRICOES_CST_CSOSN,
    DIRECOES_OPERACAO,
    FINALIDADES_OPERACAO,
    ContextoOperacaoFiscal,
    avaliar_operacao_bidirecional,
    resolver_parametros_estaduais,
)
from src.engine.fiscal_math import (
    FUNDO_NA_MVA,
    ItemCalculo,
    ResultadoFiscal,
    aliquota_interestadual,
    calcular_item,
    calcular_mva_ajustado,
    calcular_reducao_por_carga,
    derivar_cst_cfop_esperados,
    origem_por_fci,
)
from src.engine.matrix_generator import gerar_matriz_ncm
from src.engine.matriz_operacoes import gerar_linhas_matriz_ncm
from src.engine.ncm_validator import AchadoValidacaoNCM, validar_matriz_ncms
from src.engine.skills_pipeline import executar_pipeline_skills
from src.engine.sp_decision_tree import (
    CASOS_CRITICOS_SP,
    REVOGACOES_ST_SP,
    TRAVA_CST_CBENEF_SRE_70_2025,
    avaliar_arvore_5_camadas,
)

__all__ = [
    "ALIQUOTAS_INTERNAS_UF",
    "AchadoValidacaoNCM",
    "CASOS_CRITICOS_SP",
    "ContextoOperacaoFiscal",
    "DESCRICOES_CST_CSOSN",
    "DIRECOES_OPERACAO",
    "Divergencia",
    "FINALIDADES_OPERACAO",
    "FUNDO_NA_MVA",
    "ItemCalculo",
    "REVOGACOES_ST_SP",
    "ResultadoFiscal",
    "TOL_CARGA_ICMS_PP",
    "TOL_PERCENTUAL_PP",
    "TOL_VALOR_MIN",
    "TOL_VALOR_PCT",
    "TRAVA_CST_CBENEF_SRE_70_2025",
    "aliquota_interestadual",
    "auditar_config_erp",
    "auditar_nfe_contra_lei",
    "avaliar_arvore_5_camadas",
    "avaliar_operacao_bidirecional",
    "calcular_item",
    "calcular_mva_ajustado",
    "calcular_reducao_por_carga",
    "dentro_tolerancia_percentual",
    "dentro_tolerancia_valor",
    "derivar_cst_cfop_esperados",
    "executar_pipeline_skills",
    "gerar_linhas_matriz_ncm",
    "gerar_matriz_ncm",
    "origem_por_fci",
    "resolver_parametros_estaduais",
    "validar_matriz_ncms",
]
