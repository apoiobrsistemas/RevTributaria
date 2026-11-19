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
from src.integrations.microvix_conciliador import (
    conciliar_lote_com_microvix,
    exportar_relatorio_auditoria_lote_xlsx,
    sanitizar_celula_planilha,
)
from src.integrations.nfe_collector import (
    extrair_metadados_emitente_xml,
    ingerir_nfe_idempotente,
    parsear_nfe_xml,
    registrar_evento_nfe,
)
from src.integrations.xml_entrada_parser import (
    XMLSegurancaError,
    parsear_arquivos_entrada,
    parsear_nfe_entrada_xml,
)

__all__ = [
    "METODOS_SUPORTADOS",
    "MICROVIX_ENDPOINT",
    "MicrovixClient",
    "MicrovixError",
    "XMLSegurancaError",
    "conciliar_lote_com_microvix",
    "consultar_regime_cnpj",
    "exportar_relatorio_auditoria_lote_xlsx",
    "extrair_metadados_emitente_xml",
    "identificar_perna_operacao",
    "importar_planilha_matriz_erp",
    "ingerir_nfe_idempotente",
    "montar_envelope_microvix",
    "obter_chave_microvix",
    "parsear_arquivos_entrada",
    "parsear_config_tributaria_linx",
    "parsear_nfe_entrada_xml",
    "parsear_nfe_xml",
    "parsear_resposta_microvix",
    "registrar_evento_nfe",
    "sanitizar_celula_planilha",
    "separar_origem_cst",
    "sincronizar_metodo",
]
