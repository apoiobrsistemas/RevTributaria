"""Conectores de integração Linx Microvix, matriz tributária ERP e XML NF-e."""

from src.integrations.cnpj_regime import consultar_regime_cnpj
from src.integrations.linx_microvix import (
    METODOS_SUPORTADOS,
    MICROVIX_ENDPOINT,
    MicrovixClient,
    MicrovixError,
    montar_envelope_microvix,
    obter_chave_microvix,
    parsear_resposta_microvix,
    sincronizar_metodo,
)
from src.integrations.matriz_parser import (
    identificar_perna_operacao,
    importar_planilha_matriz_erp,
    parsear_config_tributaria_linx,
    separar_origem_cst,
)
from src.integrations.nfe_collector import (
    extrair_metadados_emitente_xml,
    ingerir_nfe_idempotente,
    parsear_nfe_xml,
    registrar_evento_nfe,
)

__all__ = [
    "METODOS_SUPORTADOS",
    "MICROVIX_ENDPOINT",
    "MicrovixClient",
    "MicrovixError",
    "consultar_regime_cnpj",
    "extrair_metadados_emitente_xml",
    "identificar_perna_operacao",
    "importar_planilha_matriz_erp",
    "ingerir_nfe_idempotente",
    "montar_envelope_microvix",
    "obter_chave_microvix",
    "parsear_config_tributaria_linx",
    "parsear_nfe_xml",
    "parsear_resposta_microvix",
    "registrar_evento_nfe",
    "separar_origem_cst",
    "sincronizar_metodo",
]
