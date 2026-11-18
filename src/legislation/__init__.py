"""Módulo de coleta oficial, recorte de vigência, leitura estruturada e Vigia Noturno."""

from src.legislation.acervo import (
    ACERVO_INICIAL,
    buscar_acervo,
    garantir_acervo_documental,
    indexar_nts_portal_nfe,
    parsear_notas_tecnicas_portal_nfe,
)
from src.legislation.ai_reader import (
    SCHEMA_SAIDA_REGRA_FISCAL,
    ClienteLeituraIA,
    ConfiguracaoLLM,
    citacao_existe_literalmente,
    formatar_cest,
    formatar_ncm,
    normalizar_texto_literal,
)
from src.legislation.extractor import (
    RecorteMarcadorNaoEncontradoError,
    hash_conteudo_limpo,
    recortar_texto_vigente,
)
from src.legislation.official_catalog import (
    CATALOGO_FONTES_OFICIAIS,
    MAPA_8_PORTAIS_SP,
    garantir_fontes_oficiais,
)
from src.legislation.url_guard import (
    URL_OFICIAL_REGEX,
    DominioNaoOficialError,
    OfficialURL,
    validar_url_oficial,
)
from src.legislation.vigia import AlertaVigia, gerar_codigo_alerta, verificar_fontes

__all__ = [
    "ACERVO_INICIAL",
    "AlertaVigia",
    "CATALOGO_FONTES_OFICIAIS",
    "ClienteLeituraIA",
    "ConfiguracaoLLM",
    "DominioNaoOficialError",
    "MAPA_8_PORTAIS_SP",
    "OfficialURL",
    "RecorteMarcadorNaoEncontradoError",
    "SCHEMA_SAIDA_REGRA_FISCAL",
    "URL_OFICIAL_REGEX",
    "buscar_acervo",
    "citacao_existe_literalmente",
    "formatar_cest",
    "formatar_ncm",
    "garantir_acervo_documental",
    "garantir_fontes_oficiais",
    "gerar_codigo_alerta",
    "hash_conteudo_limpo",
    "indexar_nts_portal_nfe",
    "normalizar_texto_literal",
    "parsear_notas_tecnicas_portal_nfe",
    "recortar_texto_vigente",
    "validar_url_oficial",
    "verificar_fontes",
]
