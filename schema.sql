-- ============================================================================
-- RevTributaria - Schema Inicial (SQLite WAL)
-- Motor de Regras Tributárias, Consulta em Tempo Real e Auditoria de NF-e/ERP
-- ============================================================================
-- Diretrizes aplicadas:
--   1. PRAGMA journal_mode = WAL, synchronous = NORMAL, foreign_keys = ON, busy_timeout = 5000.
--   2. Códigos fiscais (NCM, CEST, CFOP, CST, cBenef, cClassTrib) em TEXT
--      para preservar zeros à esquerda.
--   3. Separação estrita entre Mercadorias (NCM/CEST) e Serviços (CNAE/LC 116/Município).
--   4. Nenhuma coluna calculada persistida nas tabelas de regras.
--   5. Optimistic locking (versao) + soft delete (status_registro) + historico_alteracoes.
-- ============================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;

-- ----------------------------------------------------------------------------
-- 1. FONTES LEGAIS E CONTROLE DE VIGÊNCIA / VALIDAÇÃO
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fontes_legais (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    uf                  TEXT NOT NULL,                -- 'BR' para federal/CONFAZ, ou 'SP', 'MG', etc.
    esfera              TEXT NOT NULL CHECK (esfera IN ('FEDERAL', 'CONFAZ', 'ESTADUAL', 'MUNICIPAL')),
    tipo_norma          TEXT NOT NULL,                -- Lei, Decreto, RICMS, Convênio, Protocolo, NT, TIPI
    numero_norma        TEXT NOT NULL,
    titulo              TEXT NOT NULL,
    url_oficial         TEXT NOT NULL,                -- Apenas domínios .gov.br, .leg.br, .jus.br, .mp.br
    hash_conteudo       TEXT,                         -- SHA-256 do corpo da norma para o vigia
    ultima_verificacao  TEXT,
    status_fonte        TEXT NOT NULL DEFAULT 'ATIVA' CHECK (status_fonte IN ('ATIVA', 'FALHA', 'REVOGADA')),
    criado_em           TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- 2. REGRAS FEDERAIS POR NCM / CEST (IPI, PIS/COFINS, IBS/CBS)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS regras_federais (
    id                                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ncm                                 TEXT NOT NULL,    -- 8 dígitos (ex: '85171300')
    ex_tipi                             TEXT NOT NULL DEFAULT '',
    cest                                TEXT NOT NULL DEFAULT '',
    descricao_ncm                       TEXT,
    vigencia_inicio                     TEXT NOT NULL,    -- 'YYYY-MM-DD'
    vigencia_fim                        TEXT,             -- NULL = vigente

    -- Bloco 8: IPI
    cst_ipi_entrada                     TEXT,
    cst_ipi_saida                       TEXT,
    aliquota_ipi                        NUMERIC DEFAULT 0,
    codigo_enquadramento_ipi            TEXT,             -- cEnq (ex: '999', '301')
    ipi_gera_credito_debito             INTEGER DEFAULT 0 CHECK (ipi_gera_credito_debito IN (0, 1)),
    ipi_escriturar_sem_tributacao       TEXT,

    -- Bloco 7: PIS / COFINS (Mercadoria)
    cst_pis_entrada                     TEXT,
    cst_pis_saida                       TEXT,
    aliquota_pis                        NUMERIC DEFAULT 0,
    cst_cofins_entrada                  TEXT,
    cst_cofins_saida                    TEXT,
    aliquota_cofins                     NUMERIC DEFAULT 0,
    operacao_receita                    INTEGER DEFAULT 1 CHECK (operacao_receita IN (0, 1)),
    codigo_tipo_base_credito_pis_cofins TEXT,
    base_pis_cofins_por_lucro           INTEGER DEFAULT 0 CHECK (base_pis_cofins_por_lucro IN (0, 1)),

    -- Bloco 9: Reforma Tributária (IBS / CBS)
    cst_ibs_cbs                         TEXT,
    cclass_trib                         TEXT,
    aliquota_cbs                        NUMERIC DEFAULT 0,
    aliquota_ibs_uf                     NUMERIC DEFAULT 0,
    aliquota_ibs_mun                    NUMERIC DEFAULT 0,
    reducao_ibs_cbs                     NUMERIC DEFAULT 0,
    diferimento_isencao_ibs_cbs         TEXT,

    -- Governança, Optimistic Locking e Fonte
    versao                              INTEGER NOT NULL DEFAULT 1,
    status_registro                     TEXT NOT NULL DEFAULT 'ATIVA'
                                        CHECK (status_registro IN ('ATIVA', 'EXCLUIDA')),
    fonte_legal_id                      INTEGER REFERENCES fontes_legais(id),
    dispositivo_legal                   TEXT,
    trecho_citado                       TEXT,
    status_validacao                    TEXT NOT NULL DEFAULT 'A_CONFERIR'
                                        CHECK (status_validacao IN ('A_CONFERIR', 'ACEITO', 'REJEITADO')),
    aceito_por                          TEXT,
    aceito_em                           TEXT,
    criado_em                           TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em                       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_fed_ncm_cest_vig
    ON regras_federais (ncm, cest, vigencia_inicio, vigencia_fim, status_registro);

-- ----------------------------------------------------------------------------
-- 3. REGRAS ESTADUAIS DE ICMS (BLOCOS 1 A 6 - MERCADORIAS)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS regras_estaduais_icms (
    id                                  INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Bloco 1: Chave da Operação
    uf_origem                           TEXT NOT NULL,
    uf_destino                          TEXT NOT NULL,
    ncm                                 TEXT NOT NULL DEFAULT '', -- '' = regra geral da UF
    cest                                TEXT NOT NULL DEFAULT '',
    natureza_operacao                   TEXT NOT NULL, -- 'VENDA', 'COMPRA_REVENDA', 'USO_CONSUMO', 'BONIFICACAO'
    operacao_com_contribuinte           INTEGER NOT NULL CHECK (operacao_com_contribuinte IN (0, 1)),
    origem_mercadoria                   TEXT NOT NULL DEFAULT '*', -- '*', '0'..'8'
    vigencia_inicio                     TEXT NOT NULL,
    vigencia_fim                        TEXT,

    -- Classificação fiscal da norma (não derivada)
    cfop                                TEXT NOT NULL,
    cst_icms                            TEXT,
    csosn                               TEXT,
    observacao_padrao                   TEXT,

    -- Bloco 2: ICMS Próprio e Parâmetros Contábeis/Custo do ERP
    aliquota_icms                       NUMERIC DEFAULT 0,
    reducao_base_icms                   NUMERIC DEFAULT 0,
    gera_credito_debito                 INTEGER DEFAULT 1 CHECK (gera_credito_debito IN (0, 1)),
    escriturar_sem_tributacao_como      TEXT,
    valor_tributavel_icms               NUMERIC,
    deduz_icms_fcp_custo_medio          INTEGER DEFAULT 0 CHECK (deduz_icms_fcp_custo_medio IN (0, 1)),
    base_icms_obtida_pelo_lucro         INTEGER DEFAULT 0 CHECK (base_icms_obtida_pelo_lucro IN (0, 1)),

    -- Bloco 3: FCP & DIFAL
    aliquota_fcp                        NUMERIC DEFAULT 0,
    somar_ipi_base_difal_fcp            INTEGER DEFAULT 0 CHECK (somar_ipi_base_difal_fcp IN (0, 1)),
    considerar_red_bc_icms_no_fcp       INTEGER DEFAULT 1 CHECK (considerar_red_bc_icms_no_fcp IN (0, 1)),
    aliquota_interna_uf_destino_difal   NUMERIC DEFAULT 0,
    aliquota_interestadual_difal        NUMERIC DEFAULT 0,
    utiliza_bc_dupla_difal              INTEGER DEFAULT 0 CHECK (utiliza_bc_dupla_difal IN (0, 1)),

    -- Bloco 4: Desoneração, Crédito Presumido e Diferimento
    aliquota_icms_desonerado            NUMERIC DEFAULT 0,
    aliquota_fcp_desonerado             NUMERIC DEFAULT 0,
    motivo_desoneracao                  TEXT,
    codigo_beneficio_fiscal             TEXT,          -- cBenef
    percentual_credito_presumido        NUMERIC DEFAULT 0,
    deduz_icms_desonerado_total_nota    INTEGER DEFAULT 0 CHECK (deduz_icms_desonerado_total_nota IN (0, 1)),
    aliquota_diferimento                NUMERIC DEFAULT 0,
    percentual_fcp_diferimento          NUMERIC DEFAULT 0,
    observacao_complementar_diferimento TEXT,

    -- Bloco 5: ICMS-ST e Estimativa Simplificada
    tem_st                              INTEGER DEFAULT 0 CHECK (tem_st IN (0, 1)),
    recolhe_st                          TEXT CHECK (recolhe_st IN ('NAO', 'RETIDA_FORNECEDOR', 'ANTECIPADA_DESTINO')),
    tem_acordo_st                       INTEGER DEFAULT 0 CHECK (tem_acordo_st IN (0, 1)),
    aliquota_icms_st                    NUMERIC DEFAULT 0,
    margem_st                           NUMERIC DEFAULT 0, -- MVA Original (%)
    nao_ajusta_mva                      INTEGER DEFAULT 0 CHECK (nao_ajusta_mva IN (0, 1)),
    aliquota_mva_especial               NUMERIC DEFAULT 0,
    reducao_icms_st                     NUMERIC DEFAULT 0,
    fcp_entra_no_mva_ajustado           INTEGER DEFAULT 0 CHECK (fcp_entra_no_mva_ajustado IN (0, 1)),
    utiliza_base_icms_para_st           INTEGER DEFAULT 0 CHECK (utiliza_base_icms_para_st IN (0, 1)),
    icms_st_pago_em_guia                INTEGER DEFAULT 0 CHECK (icms_st_pago_em_guia IN (0, 1)),
    nao_deduzir_icms_calculo_st         INTEGER DEFAULT 0 CHECK (nao_deduzir_icms_calculo_st IN (0, 1)),
    regime_estimativa_simplificado_st   INTEGER DEFAULT 0 CHECK (regime_estimativa_simplificado_st IN (0, 1)),
    percentual_carga_tributaria_media   NUMERIC DEFAULT 0,
    encerra_st                          INTEGER DEFAULT 0 CHECK (encerra_st IN (0, 1)),
    antecipacao_parcial                 INTEGER DEFAULT 0 CHECK (antecipacao_parcial IN (0, 1)),
    somar_icms_st_fcp_st_custo_medio    INTEGER DEFAULT 0 CHECK (somar_icms_st_fcp_st_custo_medio IN (0, 1)),

    -- Bloco 6: ICMS Efetivo
    aliquota_icms_efetivo               NUMERIC DEFAULT 0,
    reducao_base_icms_efetivo           NUMERIC DEFAULT 0,

    -- Governança, Optimistic Locking e Fonte
    versao                              INTEGER NOT NULL DEFAULT 1,
    status_registro                     TEXT NOT NULL DEFAULT 'ATIVA'
                                        CHECK (status_registro IN ('ATIVA', 'EXCLUIDA')),
    fonte_legal_id                      INTEGER REFERENCES fontes_legais(id),
    dispositivo_legal                   TEXT,
    trecho_citado                       TEXT,
    confianca_ia                        TEXT CHECK (confianca_ia IN ('ALTA', 'MEDIA', 'BAIXA')),
    status_validacao                    TEXT NOT NULL DEFAULT 'A_CONFERIR'
                                        CHECK (status_validacao IN ('A_CONFERIR', 'ACEITO', 'REJEITADO')),
    aceito_por                          TEXT,
    aceito_em                           TEXT,
    criado_em                           TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em                       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_est_busca
    ON regras_estaduais_icms (
        uf_origem, uf_destino, ncm, cest, natureza_operacao,
        vigencia_inicio, vigencia_fim, status_registro
    );

-- ----------------------------------------------------------------------------
-- 4. TABELA TERCEIROS (BLOCO 10 - ENTRADAS / FORNECEDORES / IMPORTADOS / FCI)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tabela_terceiros (
    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj_terceiro                   TEXT NOT NULL DEFAULT '*',
    uf_terceiro                     TEXT NOT NULL,
    ncm                             TEXT NOT NULL,
    cest                            TEXT NOT NULL DEFAULT '',
    tipo_entrada                    TEXT NOT NULL DEFAULT 'REVENDA',
    origem_mercadoria               TEXT NOT NULL DEFAULT '*',
    vigencia_inicio                 TEXT NOT NULL,
    vigencia_fim                    TEXT,

    -- Regras de entrada / Importação / FCI (sem colunas calculadas)
    exige_fci                       INTEGER DEFAULT 0 CHECK (exige_fci IN (0, 1)),
    aliquota_interestadual_aplicavel NUMERIC,
    beneficio_convenio_52_91        INTEGER DEFAULT 0 CHECK (beneficio_convenio_52_91 IN (0, 1)),
    beneficio_zfm_conv_65_88        INTEGER DEFAULT 0 CHECK (beneficio_zfm_conv_65_88 IN (0, 1)),
    observacao_fiscal               TEXT,

    -- Dados de referência FCI do produto/terceiro
    numero_fci                      TEXT,
    conteudo_importacao_pct         NUMERIC,
    valor_parcela_importada_ext     NUMERIC,
    valor_total_saida_interestadual NUMERIC,

    versao                          INTEGER NOT NULL DEFAULT 1,
    status_registro                 TEXT NOT NULL DEFAULT 'ATIVA'
                                    CHECK (status_registro IN ('ATIVA', 'EXCLUIDA')),
    fonte_legal_id                  INTEGER REFERENCES fontes_legais(id),
    dispositivo_legal               TEXT,
    status_validacao                TEXT NOT NULL DEFAULT 'A_CONFERIR'
                                    CHECK (status_validacao IN ('A_CONFERIR', 'ACEITO', 'REJEITADO')),
    aceito_por                      TEXT,
    aceito_em                       TEXT,
    criado_em                       TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em                   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_terceiros_busca
    ON tabela_terceiros (uf_terceiro, ncm, cest, tipo_entrada, vigencia_inicio, vigencia_fim, status_registro);

-- ----------------------------------------------------------------------------
-- 5. REGRAS DE SERVIÇOS (BLOCO 11 - DOMÍNIO ISOLADO: ISS + PIS/COFINS + CSRF)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS regras_servicos (
    id                                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cnae                                TEXT NOT NULL,
    codigo_servico_lc116                TEXT,
    natureza_operacao_servico           TEXT NOT NULL,
    municipio_prestacao_ibge            TEXT NOT NULL,
    municipio_recolhimento_ibge         TEXT NOT NULL,
    vigencia_inicio                     TEXT NOT NULL,
    vigencia_fim                        TEXT,

    -- ISS
    quem_pagara_iss                     TEXT NOT NULL CHECK (quem_pagara_iss IN ('PRESTADOR', 'TOMADOR')),
    identificador_iss_retido            INTEGER NOT NULL DEFAULT 0 CHECK (identificador_iss_retido IN (0, 1)),
    aliquota_iss                        NUMERIC DEFAULT 0,

    -- PIS / COFINS Serviço e Retenções (CSRF)
    cst_pis_servico                     TEXT,
    aliquota_pis_servico                NUMERIC DEFAULT 0,
    cst_cofins_servico                  TEXT,
    aliquota_cofins_servico             NUMERIC DEFAULT 0,
    codigo_tipo_base_credito_servico    TEXT,
    codigo_retencao_csrf                TEXT,
    aliquota_pis_retido                 NUMERIC DEFAULT 0,
    aliquota_cofins_retido              NUMERIC DEFAULT 0,
    aliquota_csll_retido                NUMERIC DEFAULT 0,

    versao                              INTEGER NOT NULL DEFAULT 1,
    status_registro                     TEXT NOT NULL DEFAULT 'ATIVA'
                                        CHECK (status_registro IN ('ATIVA', 'EXCLUIDA')),
    fonte_legal_id                      INTEGER REFERENCES fontes_legais(id),
    dispositivo_legal                   TEXT,
    status_validacao                    TEXT NOT NULL DEFAULT 'A_CONFERIR'
                                        CHECK (status_validacao IN ('A_CONFERIR', 'ACEITO', 'REJEITADO')),
    criado_em                           TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em                       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_servicos_busca
    ON regras_servicos (cnae, codigo_servico_lc116, municipio_prestacao_ibge, vigencia_inicio, vigencia_fim, status_registro);

-- ----------------------------------------------------------------------------
-- 6. HISTÓRICO APPEND-ONLY (AUDITORIA DE ALTERAÇÕES NAS REGRAS)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historico_alteracoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tabela_origem   TEXT NOT NULL,
    registro_id     INTEGER NOT NULL,
    acao            TEXT NOT NULL CHECK (acao IN ('CRIACAO', 'EDICAO', 'ACEITE', 'EXCLUSAO')),
    campo           TEXT,
    valor_anterior  TEXT,
    valor_novo      TEXT,
    motivo          TEXT,
    usuario         TEXT NOT NULL,
    ocorrido_em     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_historico_origem
    ON historico_alteracoes (tabela_origem, registro_id, ocorrido_em);

-- ----------------------------------------------------------------------------
-- 7. IMPORTAÇÃO DE CONFIGURAÇÃO TRIBUTÁRIA DO ERP (FLAGS ERP / COMPARADOR)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS config_erp_importada (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_importacao     TEXT NOT NULL,
    codigo_produto_erp  TEXT,
    ncm                 TEXT NOT NULL,
    cest                TEXT NOT NULL DEFAULT '',
    uf_origem           TEXT NOT NULL,
    uf_destino          TEXT NOT NULL,
    natureza_operacao   TEXT NOT NULL,
    payload_json        TEXT NOT NULL, -- Todos os ~70 campos originais do ERP em JSON
    importado_em        TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ----------------------------------------------------------------------------
-- 8. NOTAS FISCAIS (XML) E RESULTADO DA AUDITORIA / COMPARATIVO
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nfe_documentos (
    chave_acesso        TEXT PRIMARY KEY,
    numero_nf           TEXT NOT NULL,
    serie               TEXT NOT NULL,
    modelo              TEXT NOT NULL,                -- '55' (NF-e) ou '65' (NFC-e)
    finalidade          TEXT NOT NULL DEFAULT '1',    -- '1'=Normal, '2'=Complementar
    data_emissao        TEXT NOT NULL,
    cnpj_emitente       TEXT NOT NULL,
    uf_emitente         TEXT NOT NULL,
    cnpj_destinatario   TEXT NOT NULL,
    uf_destinatario     TEXT NOT NULL,
    eh_xml_completo     INTEGER NOT NULL DEFAULT 1 CHECK (eh_xml_completo IN (0, 1)),
    xml_completo        TEXT NOT NULL,
    importado_em        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS nfe_eventos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    chave_acesso        TEXT NOT NULL REFERENCES nfe_documentos(chave_acesso) ON DELETE CASCADE,
    tipo_evento         TEXT NOT NULL,                -- '110111'=Cancelamento, '110112'=Cancelamento Substituição
    sequencia           INTEGER NOT NULL DEFAULT 1,
    data_evento         TEXT NOT NULL,
    protocolo           TEXT,
    UNIQUE (chave_acesso, tipo_evento, sequencia)
);

CREATE TABLE IF NOT EXISTS nfe_sync_cursor (
    cnpj_emp            TEXT PRIMARY KEY,
    ultimo_nsu          TEXT NOT NULL DEFAULT '000000000000000',
    ultimo_timestamp    INTEGER NOT NULL DEFAULT 0,
    atualizado_em       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE VIEW IF NOT EXISTS vw_nfe_status AS
SELECT
    d.chave_acesso,
    d.numero_nf,
    d.serie,
    d.modelo,
    d.finalidade,
    d.data_emissao,
    d.cnpj_emitente,
    d.uf_emitente,
    d.cnpj_destinatario,
    d.uf_destinatario,
    d.eh_xml_completo,
    CASE
        WHEN d.eh_xml_completo = 1 THEN 'XML_COMPLETO'
        ELSE 'RESUMO_RESNFE'
    END AS nivel_documento,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM nfe_eventos e
            WHERE e.chave_acesso = d.chave_acesso
              AND e.tipo_evento IN ('110111', '110112')
        ) THEN 'CANCELADA'
        ELSE 'AUTORIZADA'
    END AS status_sefaz
FROM nfe_documentos d;

CREATE TABLE IF NOT EXISTS nfe_itens (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    chave_acesso        TEXT NOT NULL REFERENCES nfe_documentos(chave_acesso) ON DELETE CASCADE,
    numero_item         INTEGER NOT NULL,
    codigo_produto      TEXT,
    descricao           TEXT,
    ncm                 TEXT NOT NULL,
    cest                TEXT NOT NULL DEFAULT '',
    origem_mercadoria   TEXT NOT NULL,
    cfop                TEXT NOT NULL,
    cst_icms            TEXT,
    valor_produto       NUMERIC NOT NULL,
    valor_ipi           NUMERIC DEFAULT 0,
    bc_icms             NUMERIC DEFAULT 0,
    aliq_icms           NUMERIC DEFAULT 0,
    valor_icms          NUMERIC DEFAULT 0,
    mod_bc_st           TEXT,
    mva_st              NUMERIC DEFAULT 0,
    red_bc_st           NUMERIC DEFAULT 0,
    bc_st               NUMERIC DEFAULT 0,
    aliq_st             NUMERIC DEFAULT 0,
    valor_st            NUMERIC DEFAULT 0,
    valor_fcp_st        NUMERIC DEFAULT 0,
    cst_pis             TEXT,
    aliq_pis            NUMERIC DEFAULT 0,
    cst_cofins          TEXT,
    aliq_cofins         NUMERIC DEFAULT 0,
    numero_fci          TEXT,
    UNIQUE (chave_acesso, numero_item)
);

CREATE TABLE IF NOT EXISTS auditoria_divergencias (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_auditoria      TEXT NOT NULL CHECK (tipo_auditoria IN ('XML_NFE', 'CONFIG_ERP')),
    referencia_id       TEXT NOT NULL,                -- chave_acesso ou id da config_erp_importada
    numero_item         INTEGER,
    campo_divergente    TEXT NOT NULL,
    valor_praticado     TEXT,
    valor_esperado_lei  TEXT,
    severidade          TEXT NOT NULL CHECK (severidade IN ('DIVERGENTE', 'ATENCAO', 'SEM_REGRA')),
    mensagem_ajuste     TEXT NOT NULL,
    regra_aplicada_ref  TEXT,                         -- Ex: 'regras_estaduais_icms:42'
    situacao_analise    TEXT NOT NULL DEFAULT 'ABERTA' CHECK (situacao_analise IN ('ABERTA', 'ARQUIVADA', 'CORRIGIDA')),
    criado_em           TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ----------------------------------------------------------------------------
-- 9. INTEGRAÇÃO INCREMENTAL LINX MICROVIX (UPSERT + CURSOR POR CNPJ)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS linx_sync_cursor (
    cnpj_emp            TEXT NOT NULL,
    metodo              TEXT NOT NULL,
    ultimo_timestamp    INTEGER NOT NULL DEFAULT 0,
    atualizado_em       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (cnpj_emp, metodo)
);

CREATE TABLE IF NOT EXISTS linx_lojas (
    empresa             TEXT PRIMARY KEY,
    cnpj_emp            TEXT NOT NULL,
    nome_emp            TEXT,
    uf                  TEXT,
    payload_json        TEXT NOT NULL,
    timestamp_linx      INTEGER NOT NULL DEFAULT 0,
    atualizado_em       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS linx_produtos (
    empresa             TEXT NOT NULL,
    cod_produto         TEXT NOT NULL,
    nome_produto        TEXT,
    ncm                 TEXT,
    cest                TEXT DEFAULT '',
    origem_mercadoria   TEXT,
    payload_json        TEXT NOT NULL,
    timestamp_linx      INTEGER NOT NULL DEFAULT 0,
    atualizado_em       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (empresa, cod_produto)
);

CREATE TABLE IF NOT EXISTS linx_produtos_detalhes (
    empresa             TEXT NOT NULL,
    cod_produto         TEXT NOT NULL,
    cnpj_emp            TEXT NOT NULL,
    saldo               NUMERIC DEFAULT 0,
    preco_custo         NUMERIC DEFAULT 0,
    preco_venda         NUMERIC DEFAULT 0,
    payload_json        TEXT NOT NULL,
    timestamp_linx      INTEGER NOT NULL DEFAULT 0,
    atualizado_em       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (empresa, cod_produto, cnpj_emp)
);

CREATE TABLE IF NOT EXISTS linx_config_tributarias (
    empresa                 TEXT NOT NULL,
    id_config_tributaria    TEXT NOT NULL,
    cfop                    TEXT NOT NULL DEFAULT '',
    uf_operacao             TEXT NOT NULL DEFAULT '',
    cst_icms_fiscal         TEXT,
    origem_separada         TEXT,
    cst_separado            TEXT,
    tipo_operacao_perna     TEXT,
    payload_json            TEXT NOT NULL,
    timestamp_linx          INTEGER NOT NULL DEFAULT 0,
    atualizado_em           TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (empresa, id_config_tributaria, cfop, uf_operacao)
);

-- ----------------------------------------------------------------------------
-- 10. ALERTAS PERSISTENTES DO VIGIA NOTURNO E VALIDADOR DE EXCEÇÕES POR NCM
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vigia_alertas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo          TEXT NOT NULL,
    fonte_id        INTEGER REFERENCES fontes_legais(id),
    uf              TEXT NOT NULL,
    grupo           TEXT NOT NULL,
    tipo            TEXT NOT NULL,
    mensagem        TEXT NOT NULL,
    status_alerta   TEXT NOT NULL DEFAULT 'ABERTO' CHECK (status_alerta IN ('ABERTO', 'CONFERIDO', 'IGNORADO')),
    justificativa   TEXT,
    conferido_por   TEXT,
    conferido_em    TEXT,
    criado_em       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (codigo, fonte_id, tipo)
);

CREATE TABLE IF NOT EXISTS validacoes_ncm (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_execucao       TEXT NOT NULL,
    ncm                 TEXT NOT NULL,
    uf_origem           TEXT NOT NULL DEFAULT 'SP',
    uf_destino          TEXT NOT NULL DEFAULT 'SP',
    regra_estadual_id   INTEGER REFERENCES regras_estaduais_icms(id),
    regra_federal_id    INTEGER REFERENCES regras_federais(id),
    codigo_regra        TEXT NOT NULL,
    categoria           TEXT NOT NULL,
    severidade          TEXT NOT NULL CHECK (severidade IN ('ERRO', 'ALERTA', 'INFO')),
    mensagem            TEXT NOT NULL,
    sugestao_correcao   TEXT,
    executado_em        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_validacoes_ncm_busca
    ON validacoes_ncm (ncm, severidade, categoria);

CREATE TABLE IF NOT EXISTS controle_execucao_diaria (
    chave           TEXT PRIMARY KEY,
    ultima_data     TEXT NOT NULL,
    resumo_json     TEXT,
    atualizado_em   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cnpj_regimes (
    cnpj            TEXT PRIMARY KEY,
    razao_social    TEXT,
    uf              TEXT,
    crt             TEXT,
    regime_apuracao TEXT NOT NULL,
    fonte_consulta  TEXT NOT NULL DEFAULT 'XML_NFE',
    atualizado_em   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS acervo_documental (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_ato          TEXT NOT NULL UNIQUE,
    titulo              TEXT NOT NULL,
    esfera              TEXT NOT NULL CHECK (esfera IN ('FEDERAL', 'ESTADUAL_SP', 'CONFAZ', 'ENCAT')),
    tipo_documento      TEXT NOT NULL,
    status_norma        TEXT NOT NULL DEFAULT 'VIGENTE' CHECK (status_norma IN ('VIGENTE', 'ALTERADA', 'REVOGADA')),
    vigencia_inicio     TEXT NOT NULL,
    vigencia_fim        TEXT,
    url_oficial         TEXT NOT NULL,
    hash_sha256         TEXT NOT NULL,
    artigos_chave       TEXT,
    ncms_impactados     TEXT,
    regras_xml          TEXT,
    codigos_erro_sefaz  TEXT,
    texto_literal       TEXT NOT NULL,
    ultima_sincronizacao TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_acervo_busca
    ON acervo_documental (esfera, tipo_documento, status_norma, codigo_ato);

CREATE TABLE IF NOT EXISTS naturezas_operacao_ids (
    natureza_operacao TEXT PRIMARY KEY,
    id_natureza       INTEGER NOT NULL DEFAULT 0,
    atualizado_em     TEXT NOT NULL DEFAULT (datetime('now'))
);
