"""Camada de serviço orquestrando banco SQLite, ingestores oficiais, motor e auditoria."""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import threading
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import openpyxl

from src.automation.official_ingestor import (
    URL_CONFAZ_142_18,
    URL_CONFAZ_52_91,
    URL_SISCOMEX_NCM_JSON,
    URL_TIPI_RFB,
    descobrir_pares_ncm_cest,
    ingerir_cbenef_xlsx,
    ingerir_cclasstrib_xlsx,
    ingerir_convenio_142_html,
    ingerir_convenio_52_91_html,
    ingerir_siscomex_ncm_json,
    ingerir_tipi_xlsx,
)
from src.database import (
    DEFAULT_DB_PATH,
    atualizar_regra_com_lock,
    buscar_regra_estadual_icms,
    buscar_regra_federal,
    buscar_regra_terceiro,
    init_db,
    registrar_historico,
)
from src.database.naturezas import (
    NATUREZAS_OPERACAO_PADRAO,
    aplicar_ids_natureza_nas_linhas as _aplicar_ids_natureza_nas_linhas,
    listar_ids_naturezas_operacao_db,
    salvar_ids_naturezas_operacao_db,
)
from src.database.snapshot import restaurar_snapshot_se_necessario
from src.engine import (
    CASOS_CRITICOS_SP,
    ContextoOperacaoFiscal,
    ContextoReformaLC214,
    ItemCalculo,
    REVOGACOES_ST_SP,
    auditar_config_erp,
    auditar_lote_xml_entrada,
    auditar_nfe_contra_lei,
    avaliar_arvore_5_camadas,
    avaliar_operacao_bidirecional,
    calcular_item,
    calcular_transicao_lc214,
    executar_pipeline_skills,
    gerar_linhas_matriz_ncm,
    gerar_matriz_ncm,
    resolver_parametros_estaduais,
    validar_matriz_ncms,
    validar_xml_reforma_lc214,
)
from src.engine.fiscal_math import aliquota_interestadual
from src.engine.matrix_generator import ALIQUOTA_FCP_PADRAO_UF, ALIQUOTA_INTERNA_MODAL_UF
from src.integrations import (
    METODOS_SUPORTADOS,
    MicrovixClient,
    conciliar_lote_com_microvix,
    consultar_regime_cnpj,
    exportar_relatorio_auditoria_lote_xlsx,
    extrair_metadados_emitente_xml,
    importar_planilha_matriz_erp,
    ingerir_nfe_idempotente,
    parsear_arquivos_entrada,
    sincronizar_metodo,
)
from src.legislation.acervo import (
    buscar_acervo,
    garantir_acervo_documental,
    indexar_nts_portal_nfe,
)
from src.legislation.extractor import hash_conteudo_limpo
from src.legislation.official_catalog import MAPA_8_PORTAIS_SP, garantir_fontes_oficiais
from src.legislation.parsers import baixar_url_oficial
from src.legislation.url_guard import validar_url_oficial
from src.legislation.vigia import verificar_fontes

FetcherBytesFn = Callable[[str], bytes]
_ROTINA_DIARIA_LOCK = threading.Lock()


class RevTributariaService:
    """Orquestrador principal da aplicação para UI, CLI e automações."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = init_db(self.db_path)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def sincronizar_bases_oficiais(
        self,
        *,
        fontes: dict[str, bytes | str] | None = None,
        fetcher: FetcherBytesFn | None = None,
        urls: dict[str, str] | None = None,
        uf_origem: str = "SP",
        ufs_destino: tuple[str, ...] = ("SP",),
    ) -> dict[str, Any]:
        """Orquestra descoberta de pares + ingestores oficiais + fila A_CONFERIR estadual."""
        conn = self._get_conn()
        pares = descobrir_pares_ncm_cest(conn)
        ncms_ativos = {ncm for ncm, _ in pares}

        urls_uso = {
            "siscomex": URL_SISCOMEX_NCM_JSON,
            "tipi": URL_TIPI_RFB,
            "confaz_142": URL_CONFAZ_142_18,
            "confaz_52_91": URL_CONFAZ_52_91,
        }
        if urls:
            for k, u in urls.items():
                validar_url_oficial(u)
                urls_uso[k] = u

        resumo: dict[str, Any] = {
            "pares_descobertos": len(pares),
            "siscomex_atualizados": 0,
            "tipi_atualizados": 0,
            "confaz_142_atualizados": 0,
            "confaz_52_91_atualizados": 0,
            "cbenef_inseridos": 0,
            "cclasstrib_atualizados": 0,
            "fila_estadual_criada": 0,
            "avisos_fontes": {},
        }

        def _obter(chave: str) -> bytes | str | None:
            if fontes and chave in fontes:
                return fontes[chave]
            if fetcher is not None and chave in urls_uso:
                validar_url_oficial(urls_uso[chave])
                try:
                    return fetcher(urls_uso[chave])
                except Exception as exc:
                    if exc.__class__.__name__ == "DominioNaoOficialError":
                        raise
                    resumo["avisos_fontes"][chave] = str(exc)
                    return None
            return None

        dados_siscomex = _obter("siscomex")
        if dados_siscomex is not None:
            try:
                raw = dados_siscomex.encode("utf-8") if isinstance(dados_siscomex, str) else dados_siscomex
                resumo["siscomex_atualizados"] = ingerir_siscomex_ncm_json(
                    conn,
                    raw,
                    url_oficial=urls_uso["siscomex"],
                    apenas_ncms=ncms_ativos or None,
                )
            except Exception as exc:
                if exc.__class__.__name__ == "DominioNaoOficialError":
                    raise
                resumo["avisos_fontes"]["parse_siscomex"] = str(exc)

        dados_tipi = _obter("tipi")
        if dados_tipi is not None and isinstance(dados_tipi, (bytes, bytearray)):
            try:
                resumo["tipi_atualizados"] = ingerir_tipi_xlsx(
                    conn,
                    bytes(dados_tipi),
                    url_oficial=urls_uso["tipi"],
                    apenas_ncms=ncms_ativos or None,
                )
            except Exception as exc:
                if exc.__class__.__name__ == "DominioNaoOficialError":
                    raise
                resumo["avisos_fontes"]["parse_tipi"] = str(exc)

        dados_142 = _obter("confaz_142")
        if dados_142 is not None:
            try:
                html_142 = dados_142.decode("utf-8", errors="replace") if isinstance(dados_142, (bytes, bytearray)) else dados_142
                resumo["confaz_142_atualizados"] = ingerir_convenio_142_html(
                    conn, html_142, url_oficial=urls_uso["confaz_142"], uf_terceiro=uf_origem
                )
            except Exception as exc:
                if exc.__class__.__name__ == "DominioNaoOficialError":
                    raise
                resumo["avisos_fontes"]["parse_confaz_142"] = str(exc)

        dados_52 = _obter("confaz_52_91")
        if dados_52 is not None:
            try:
                html_52 = dados_52.decode("utf-8", errors="replace") if isinstance(dados_52, (bytes, bytearray)) else dados_52
                resumo["confaz_52_91_atualizados"] = ingerir_convenio_52_91_html(
                    conn, html_52, url_oficial=urls_uso["confaz_52_91"], uf_terceiro=uf_origem
                )
            except Exception as exc:
                if exc.__class__.__name__ == "DominioNaoOficialError":
                    raise
                resumo["avisos_fontes"]["parse_confaz_52_91"] = str(exc)

        if fontes and "cbenef" in fontes and isinstance(fontes["cbenef"], (bytes, bytearray)):
            resumo["cbenef_inseridos"] = ingerir_cbenef_xlsx(conn, bytes(fontes["cbenef"]))

        if fontes and "cclasstrib" in fontes and isinstance(fontes["cclasstrib"], (bytes, bytearray)):
            resumo["cclasstrib_atualizados"] = ingerir_cclasstrib_xlsx(conn, bytes(fontes["cclasstrib"]))

        if fetcher is baixar_bytes_oficiais and not fontes:
            self.garantir_catalogo_fontes_oficiais()
            self.garantir_acervo_oficial()
            qtd_regras = conn.execute(
                "SELECT COUNT(*) FROM regras_estaduais_icms WHERE status_registro = 'ATIVA'"
            ).fetchone()[0]
            if qtd_regras < 1000 and str(self.db_path) != ":memory:":
                snap = self.restaurar_snapshot_cloud()
                resumo["snapshot_restaurado"] = snap
                conn = self._get_conn()
                qtd_regras = conn.execute(
                    "SELECT COUNT(*) FROM regras_estaduais_icms WHERE status_registro = 'ATIVA'"
                ).fetchone()[0]
            if qtd_regras < 20 and str(self.db_path) != ":memory:":
                self.executar_seed_sp(usar_rede=False)
                from src.app.seed_moda import DEFAULT_MODA_XLSX

                if DEFAULT_MODA_XLSX.exists():
                    self.importar_regras_lote(
                        DEFAULT_MODA_XLSX.read_bytes(),
                        extensao=".xlsx",
                        usuario="sync_cloud_fallback",
                    )
                self.consolidar_regras_todos_ncms_base(uf_origem=uf_origem)

        # Enfileira pares descobertos sem regra estadual vigente como A_CONFERIR
        hoje = date.today().isoformat()
        with conn:
            for ncm, cest in pares:
                for uf_dest in ufs_destino:
                    regra = buscar_regra_estadual_icms(
                        conn,
                        uf_origem=uf_origem,
                        uf_destino=uf_dest,
                        ncm=ncm,
                        cest=cest,
                        data_referencia=hoje,
                    )
                    if regra is None or regra["ncm"] == "":
                        cfop = "5102" if uf_origem.upper() == uf_dest.upper() else "6102"
                        conn.execute(
                            """
                            INSERT INTO regras_estaduais_icms (
                                uf_origem, uf_destino, ncm, cest, natureza_operacao,
                                operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                                cfop, cst_icms, status_validacao
                            ) VALUES (?, ?, ?, ?, 'VENDA', 1, '*', ?, ?, '00', 'A_CONFERIR')
                            """,
                            (uf_origem.upper(), uf_dest.upper(), ncm, cest, hoje, cfop),
                        )
                        resumo["fila_estadual_criada"] += 1

        return resumo

    def importar_regras_lote_csv(
        self,
        conteudo_bytes: bytes,
        *,
        usuario: str = "sistema",
    ) -> int:
        """Fallback de importação em lote CSV para regras_estaduais_icms."""
        conn = self._get_conn()
        texto = conteudo_bytes.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(texto), delimiter=";")
        inseridas = 0
        with conn:
            for row in reader:
                ncm = str(row.get("ncm") or "").strip()
                if not ncm:
                    continue
                conn.execute(
                    """
                    INSERT INTO regras_estaduais_icms (
                        uf_origem, uf_destino, ncm, cest, natureza_operacao,
                        operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                        cfop, cst_icms, aliquota_icms, status_validacao, aceito_por
                    ) VALUES (?, ?, ?, ?, ?, ?, '*', ?, ?, ?, ?, 'A_CONFERIR', ?)
                    """,
                    (
                        str(row.get("uf_origem") or "SP").upper(),
                        str(row.get("uf_destino") or "SP").upper(),
                        ncm,
                        str(row.get("cest") or "").strip(),
                        str(row.get("natureza_operacao") or "VENDA").upper(),
                        int(row.get("operacao_com_contribuinte") or 1),
                        str(row.get("vigencia_inicio") or date.today().isoformat()),
                        str(row.get("cfop") or "5102"),
                        str(row.get("cst_icms") or "00"),
                        float(str(row.get("aliquota_icms") or 18).replace(",", ".")),
                        usuario,
                    ),
                )
                inseridas += 1
        return inseridas

    def aprovar_ou_editar_regra(
        self,
        *,
        tabela: str,
        registro_id: int,
        versao_atual: int,
        alteracoes: dict[str, Any],
        usuario: str,
        motivo: str | None = None,
        aprovar: bool = False,
    ) -> int:
        """Edita e/ou aprova regra com optimistic locking e diff em historico_alteracoes."""
        conn = self._get_conn()
        payload = dict(alteracoes)
        if aprovar:
            payload["status_validacao"] = "ACEITO"
            payload["aceito_por"] = usuario
            payload["aceito_em"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return atualizar_regra_com_lock(
            conn,
            tabela=tabela,
            registro_id=registro_id,
            versao_atual=versao_atual,
            alteracoes=payload,
            usuario=usuario,
            motivo=motivo,
        )

    def simular_calculo_item(
        self,
        *,
        uf_origem: str,
        uf_destino: str,
        ncm: str,
        cest: str = "",
        valor: Decimal | float | str,
        ipi: Decimal | float | str | None = None,
        fci: Decimal | float | str | None = None,
        contribuinte: bool = True,
        origem_mercadoria: str = "0",
        data_referencia: str | None = None,
        regime_tributario: str = "Lucro Real",
        atividade_empresa: str = "Varejo (Padrão)",
    ) -> dict[str, Any]:
        """Consulta regra vigente no SQLite (com fallback UF origem), executa calcular_item e gera espelho XML."""
        conn = self._get_conn()
        ref = data_referencia or date.today().isoformat()
        ncm_limpo = re.sub(r"\D", "", str(ncm or ""))
        uf_o = uf_origem.upper()
        uf_d = uf_destino.upper()

        regra_est = buscar_regra_estadual_icms(
            conn,
            uf_origem=uf_o,
            uf_destino=uf_d,
            ncm=ncm_limpo,
            cest=cest,
            operacao_com_contribuinte=contribuinte,
            origem_mercadoria=origem_mercadoria,
            data_referencia=ref,
        )
        if regra_est is None or (regra_est.get("ncm") == "" and ncm_limpo):
            row_fb = conn.execute(
                """
                SELECT * FROM regras_estaduais_icms
                WHERE status_registro = 'ATIVA'
                  AND status_validacao != 'REJEITADO'
                  AND ncm = ?
                  AND vigencia_inicio <= ?
                  AND (vigencia_fim IS NULL OR vigencia_fim >= ?)
                ORDER BY
                    CASE WHEN uf_origem = ? AND uf_destino = ? THEN 0
                         WHEN uf_origem = ? AND uf_destino = ? THEN 1
                         ELSE 2 END,
                    vigencia_inicio DESC, id DESC
                LIMIT 1
                """,
                (ncm_limpo, ref, ref, uf_o, uf_d, uf_o, uf_o),
            ).fetchone()
            if row_fb is not None:
                regra_est = dict(row_fb)

        if regra_est is None:
            raise LookupError(f"Nenhuma regra estadual vigente encontrada para {uf_o}->{uf_d} NCM {ncm_limpo}.")

        regra_uso = dict(regra_est)
        if uf_o != uf_d:
            from src.engine.fiscal_math import aliquota_interestadual as _aliq_inter_fn

            inter_calc = _aliq_inter_fn(uf_o, uf_d, origem_mercadoria)
            if inter_calc is not None:
                regra_uso["aliquota_icms"] = float(inter_calc)
            if not float(regra_uso.get("aliquota_interna_uf_destino_difal") or 0):
                regra_uso["aliquota_interna_uf_destino_difal"] = ALIQUOTA_INTERNA_MODAL_UF.get(uf_d, 18.0)
            if not float(regra_uso.get("aliquota_fcp") or 0):
                regra_uso["aliquota_fcp"] = ALIQUOTA_FCP_PADRAO_UF.get(uf_d, 0.0)
            regra_uso["cfop"] = "6404" if regra_uso.get("tem_st") else ("6102" if contribuinte else "6108")

        if (
            atividade_empresa == "Indústria / Atacado Têxtil & Calçados (SP)"
            and uf_o == "SP"
            and uf_d == "SP"
            and contribuinte
            and origem_mercadoria == "0"
            and ncm_limpo[:2] in {"60", "61", "62", "63"}
            and not regra_uso.get("tem_st")
        ):
            regra_uso["cst_icms"] = "20"
            regra_uso["reducao_base_icms"] = 33.33
            regra_uso["codigo_beneficio_fiscal"] = regra_uso.get("codigo_beneficio_fiscal") or "SP020052"

        regra_fed = buscar_regra_federal(conn, ncm=ncm_limpo, cest=cest, data_referencia=ref)
        regra_fed_uso = dict(regra_fed) if regra_fed else None
        if regra_fed_uso is not None:
            if regime_tributario in {"Simples Nacional", "Simples Nacional — Excesso de Sublimite", "MEI"}:
                regra_fed_uso["cst_pis_saida"] = "49"
                regra_fed_uso["aliquota_pis"] = 0.0
                regra_fed_uso["cst_cofins_saida"] = "49"
                regra_fed_uso["aliquota_cofins"] = 0.0
            elif regime_tributario == "Lucro Presumido" and str(regra_fed_uso.get("cst_pis_saida") or "") not in {"04", "05", "06"}:
                regra_fed_uso["cst_pis_saida"] = "01"
                regra_fed_uso["aliquota_pis"] = 0.65
                regra_fed_uso["cst_cofins_saida"] = "01"
                regra_fed_uso["aliquota_cofins"] = 3.00

        regra_terc = buscar_regra_terceiro(
            conn, uf_terceiro=uf_o, ncm=ncm_limpo, cest=cest, data_referencia=ref
        )

        resultado = calcular_item(
            ItemCalculo(
                valor_produto=Decimal(str(valor)),
                uf_origem=uf_o,
                uf_destino=uf_d,
                ncm=ncm_limpo,
                cest=cest or str(regra_uso.get("cest") or ""),
                origem_mercadoria=origem_mercadoria,
                operacao_com_contribuinte=contribuinte,
                valor_ipi=Decimal(str(ipi)) if ipi is not None else None,
                conteudo_importacao_pct=Decimal(str(fci)) if fci is not None else None,
            ),
            regra_uso,
            regra_fed_uso,
            regra_terc,
        )
        res_dict = {k: (str(v) if isinstance(v, Decimal) else v) for k, v in asdict(resultado).items()}

        # Espelho de XML NF-e pronto para conferência de emissão real
        espelho_xml = [
            {"Grupo XML": "<prod>", "Tag / Campo": "NCM / CEST", "Parâmetro / Alíquota": f"NCM {ncm_limpo} | CEST {regra_uso.get('cest') or '-'}", "Base de Cálculo (R$)": res_dict["valor_operacao"], "Valor Calculado (R$)": res_dict["valor_operacao"], "Regra / Fundamentação": f"CFOP {res_dict['cfop_esperado']}"},
            {"Grupo XML": "<IPI>", "Tag / Campo": "vIPI", "Parâmetro / Alíquota": f"Alíq {(regra_fed_uso or {}).get('aliquota_ipi', 0)}%", "Base de Cálculo (R$)": res_dict["valor_operacao"], "Valor Calculado (R$)": res_dict["valor_ipi"], "Regra / Fundamentação": f"CST IPI {(regra_fed_uso or {}).get('cst_ipi_saida', '99')} | cEnq {(regra_fed_uso or {}).get('codigo_enquadramento_ipi', '999')}"},
            {"Grupo XML": "<ICMS>", "Tag / Campo": "vBC / pICMS / vICMS", "Parâmetro / Alíquota": f"Alíq {res_dict['aliquota_icms']}% | Red BC {res_dict['reducao_bc_aplicada']}%", "Base de Cálculo (R$)": res_dict["bc_icms"], "Valor Calculado (R$)": res_dict["valor_icms_proprio"], "Regra / Fundamentação": f"Orig {res_dict['origem_efetiva']} | CST {res_dict['cst_esperado']} | cBenef {regra_uso.get('codigo_beneficio_fiscal') or '-'}"},
            {"Grupo XML": "<ICMS>", "Tag / Campo": "vBCST / pMVAST / vICMSST", "Parâmetro / Alíquota": f"MVA {res_dict['mva_aplicada']}% | Alíq ST {regra_uso.get('aliquota_icms_st', 0)}%", "Base de Cálculo (R$)": res_dict["bc_st"], "Valor Calculado (R$)": res_dict["valor_icms_st"], "Regra / Fundamentação": f"FCP-ST R$ {res_dict['valor_fcp_st']}"},
            {"Grupo XML": "<ICMSUFDest>", "Tag / Campo": "vICMSUFDest / vFCPUFDest", "Parâmetro / Alíquota": f"Dest {regra_uso.get('aliquota_interna_uf_destino_difal', 0)}% | Inter {res_dict['aliquota_inter_aplicada'] or 0}% | FCP {regra_uso.get('aliquota_fcp', 0)}%", "Base de Cálculo (R$)": res_dict["bc_icms"], "Valor Calculado (R$)": res_dict["valor_difal"], "Regra / Fundamentação": "EC 87/2015 (DIFAL Não Contribuinte)"},
            {"Grupo XML": "<ICMS>", "Tag / Campo": "vBCEfet / vICMSEfet", "Parâmetro / Alíquota": f"Alíq Efetiva {regra_uso.get('aliquota_icms_efetivo', 0)}%", "Base de Cálculo (R$)": res_dict["bc_icms_efetivo"], "Valor Calculado (R$)": res_dict["valor_icms_efetivo"], "Regra / Fundamentação": "Obrigatório para CST 60 / CSOSN 500"},
            {"Grupo XML": "<PIS>", "Tag / Campo": "vBC / pPIS / vPIS", "Parâmetro / Alíquota": f"CST {(regra_fed_uso or {}).get('cst_pis_saida', '01')} | {(regra_fed_uso or {}).get('aliquota_pis', 0)}%", "Base de Cálculo (R$)": res_dict["valor_operacao"], "Valor Calculado (R$)": res_dict["valor_pis"], "Regra / Fundamentação": regime_tributario},
            {"Grupo XML": "<COFINS>", "Tag / Campo": "vBC / pCOFINS / vCOFINS", "Parâmetro / Alíquota": f"CST {(regra_fed_uso or {}).get('cst_cofins_saida', '01')} | {(regra_fed_uso or {}).get('aliquota_cofins', 0)}%", "Base de Cálculo (R$)": res_dict["valor_operacao"], "Valor Calculado (R$)": res_dict["valor_cofins"], "Regra / Fundamentação": regime_tributario},
            {"Grupo XML": "<IBSCBS>", "Tag / Campo": "vCBS / vIBSUF / vIBSMun", "Parâmetro / Alíquota": f"cClassTrib {res_dict['cclass_trib'] or '-'}", "Base de Cálculo (R$)": res_dict["valor_operacao"], "Valor Calculado (R$)": f"CBS {res_dict['valor_cbs']} | IBS {res_dict['valor_ibs_total']}", "Regra / Fundamentação": "Reforma Tributária LC 214/2025"},
        ]
        res_dict["espelho_xml"] = espelho_xml
        return res_dict

    def registrar_ncms_ausentes_da_nfe(
        self,
        chave_acesso: str,
        *,
        natureza_operacao: str = "VENDA",
        operacao_com_contribuinte: bool = True,
        usuario: str = "auto_xml_nfe",
    ) -> dict[str, int]:
        """Cadastra automaticamente NCMs do XML ainda ausentes na base (federal + estadual) antes da auditoria."""
        conn = self._get_conn()
        doc = conn.execute(
            "SELECT * FROM nfe_documentos WHERE chave_acesso = ?",
            (chave_acesso,),
        ).fetchone()
        if doc is None:
            return {"ncms_federais_adicionados": 0, "ncms_estaduais_adicionados": 0}

        self.garantir_catalogo_fontes_oficiais()
        uf_o = str(doc["uf_emitente"] or "SP").upper()
        uf_d = str(doc["uf_destinatario"] or uf_o).upper()
        data_emissao = str(doc["data_emissao"] or date.today().isoformat())[:10]
        vig_ini = min(data_emissao, date.today().isoformat())
        contrib_int = 1 if operacao_com_contribuinte else 0

        r_ricms = conn.execute(
            "SELECT id FROM fontes_legais WHERE numero_norma LIKE '%45.490/2000%' ORDER BY id LIMIT 1"
        ).fetchone()
        r_tipi = conn.execute(
            "SELECT id FROM fontes_legais WHERE tipo_norma = 'TIPI' ORDER BY id LIMIT 1"
        ).fetchone()
        fid_ricms = int(r_ricms["id"]) if r_ricms else None
        fid_tipi = int(r_tipi["id"]) if r_tipi else fid_ricms

        itens = conn.execute(
            "SELECT DISTINCT ncm, cest, descricao, origem_mercadoria, cfop FROM nfe_itens WHERE chave_acesso = ?",
            (chave_acesso,),
        ).fetchall()

        fed_add = 0
        est_add = 0
        with conn:
            for it in itens:
                ncm = re.sub(r"\D", "", str(it["ncm"] or ""))
                cest_xml = re.sub(r"\D", "", str(it["cest"] or ""))
                desc = str(it["descricao"] or "Produto NF-e")[:80]
                if len(ncm) != 8 or ncm == "00000000":
                    continue

                # 1. Regra Federal ausente
                fed_ex = conn.execute(
                    "SELECT id FROM regras_federais WHERE ncm = ? AND status_registro = 'ATIVA' LIMIT 1",
                    (ncm,),
                ).fetchone()
                if fed_ex is None:
                    conn.execute(
                        """
                        INSERT INTO regras_federais (
                            ncm, ex_tipi, cest, descricao_ncm, vigencia_inicio,
                            cst_ipi_entrada, cst_ipi_saida, aliquota_ipi,
                            cst_pis_entrada, cst_pis_saida, aliquota_pis,
                            cst_cofins_entrada, cst_cofins_saida, aliquota_cofins,
                            cst_ibs_cbs, cclass_trib, fonte_legal_id,
                            dispositivo_legal, trecho_citado, status_validacao, aceito_por
                        ) VALUES (?, '', ?, ?, ?, '49', '99', 0, '50', '01', 1.65, '50', '01', 7.60, '000', '000001', ?, 'Auto-inclusão XML NF-e (TIPI/Siscomex)', 'NCM incluído automaticamente a partir de XML NF-e para validação.', 'A_CONFERIR', ?)
                        """,
                        (ncm, cest_xml, desc, vig_ini, fid_tipi, usuario),
                    )
                    fed_add += 1

                # 2. Regra Estadual ausente para a rota da NF-e
                est_ex = buscar_regra_estadual_icms(
                    conn,
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    ncm=ncm,
                    cest=cest_xml,
                    natureza_operacao=natureza_operacao,
                    operacao_com_contribuinte=operacao_com_contribuinte,
                    data_referencia=data_emissao,
                )
                if est_ex is None or est_ex["ncm"] == "":
                    eh_sp_interna = uf_o == "SP" and uf_d == "SP"
                    caso = next((c for c in CASOS_CRITICOS_SP if c["ncm"] == ncm), None) if eh_sp_interna else None
                    rev = REVOGACOES_ST_SP.get(ncm) if eh_sp_interna else None
                    orig_item = str(it["origem_mercadoria"] or "0")
                    cfop_xml = str(it["cfop"] or "")
                    if uf_o == uf_d:
                        aliq_uf = float(ALIQUOTA_INTERNA_MODAL_UF.get(uf_o, 18.0))
                    else:
                        aliq_uf = float(aliquota_interestadual(uf_o, uf_d, orig_item) or Decimal("12.00"))
                    cfop_dev = cfop_xml in {"1202", "2202", "5202", "6202", "1411", "2411", "5411", "6411"}
                    cfop_st = cfop_xml in {"1403", "2403", "5405", "6404", "1411", "2411", "5411", "6411"}
                    cfop_def = (
                        cfop_xml
                        if cfop_dev
                        else ("5102" if uf_o == uf_d else ("6102" if operacao_com_contribuinte else "6108"))
                    )
                    cst_def = str(caso["cst_icms"][-2:] if caso else ("90" if cfop_xml == "6411" else "00"))
                    cbenef_def = str(caso["cbenef"] if caso else "")
                    red_def = float(caso["reducao_bc"] if caso else 0.0)
                    if rev and data_emissao >= rev["vigencia_revogacao"]:
                        tem_st_def = 0
                    elif caso is not None:
                        tem_st_def = int(caso["tem_st"])
                    elif not eh_sp_interna and cest_xml and cfop_st:
                        tem_st_def = 1
                    else:
                        tem_st_def = 0
                    cest_def = str((caso["cest"] if caso else "") or cest_xml)
                    disp_def = str((caso["norma_chave"] if caso else "") or f"Auto-inclusão XML NF-e ({uf_o}->{uf_d}) — Conferir RICMS")
                    trecho_def = "Regra preliminar criada automaticamente na ingestão de XML NF-e para conferência."

                    cur_est = conn.execute(
                        """
                        INSERT INTO regras_estaduais_icms (
                            uf_origem, uf_destino, ncm, cest, natureza_operacao,
                            operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                            cfop, cst_icms, aliquota_icms, reducao_base_icms,
                            codigo_beneficio_fiscal, tem_st, fonte_legal_id,
                            dispositivo_legal, trecho_citado, status_validacao, aceito_por
                        ) VALUES (?, ?, ?, ?, ?, ?, '*', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'A_CONFERIR', ?)
                        """,
                        (
                            uf_o,
                            uf_d,
                            ncm,
                            cest_def,
                            natureza_operacao,
                            contrib_int,
                            vig_ini,
                            cfop_def,
                            cst_def,
                            aliq_uf,
                            red_def,
                            cbenef_def,
                            tem_st_def,
                            fid_ricms,
                            disp_def,
                            trecho_def,
                            usuario,
                        ),
                    )
                    registrar_historico(
                        conn,
                        tabela_origem="regras_estaduais_icms",
                        registro_id=int(cur_est.lastrowid),
                        acao="CRIACAO",
                        campo="ncm",
                        valor_anterior="",
                        valor_novo=ncm,
                        motivo=f"Auto-inclusão XML NF-e {chave_acesso}",
                        usuario=usuario,
                        auto_commit=False,
                    )
                    est_add += 1

        return {
            "ncms_federais_adicionados": fed_add,
            "ncms_estaduais_adicionados": est_add,
        }

    def executar_auditoria_nfe(
        self,
        xml_content: str,
        *,
        natureza_operacao: str = "VENDA",
        operacao_com_contribuinte: bool = True,
        auto_cadastrar_ncms: bool = True,
    ) -> dict[str, Any]:
        """Ingere XML NF-e de forma idempotente, cadastra NCMs ausentes e executa auditoria Frente A."""
        conn = self._get_conn()
        chave = ingerir_nfe_idempotente(conn, xml_str=xml_content)
        auto_res = {"ncms_federais_adicionados": 0, "ncms_estaduais_adicionados": 0}
        if auto_cadastrar_ncms:
            auto_res = self.registrar_ncms_ausentes_da_nfe(
                chave,
                natureza_operacao=natureza_operacao,
                operacao_com_contribuinte=operacao_com_contribuinte,
            )
        divs = auditar_nfe_contra_lei(
            conn,
            chave,
            natureza_operacao=natureza_operacao,
            operacao_com_contribuinte=operacao_com_contribuinte,
        )
        return {
            "chave_acesso": chave,
            "total_divergencias": len(divs),
            "divergencias": [asdict(d) for d in divs],
            **auto_res,
        }

    def executar_auditoria_erp(
        self,
        arquivo_planilha: str | Path | bytes,
        *,
        lote_importacao: str,
        extensao: str = ".xlsx",
    ) -> dict[str, Any]:
        """Importa planilha da matriz ERP e executa auditoria Frente B."""
        conn = self._get_conn()
        importadas = importar_planilha_matriz_erp(
            conn,
            arquivo_planilha,
            lote_importacao=lote_importacao,
            extensao=extensao,
        )
        divs = auditar_config_erp(conn, lote_importacao=lote_importacao)
        return {
            "lote_importacao": lote_importacao,
            "linhas_importadas": importadas,
            "total_divergencias": len(divs),
            "divergencias": [asdict(d) for d in divs],
        }

    # ------------------------------------------------------------------
    # Métodos de leitura e operação para a UI (Zero SQL na camada UI)
    # ------------------------------------------------------------------
    def obter_resumo_sidebar(self) -> dict[str, Any]:
        """Retorna indicadores de status para a barra lateral da UI."""
        conn = self._get_conn()
        a_conferir = conn.execute(
            "SELECT COUNT(*) FROM regras_estaduais_icms WHERE status_registro = 'ATIVA' AND status_validacao = 'A_CONFERIR'"
        ).fetchone()[0]
        aceitas = conn.execute(
            "SELECT COUNT(*) FROM regras_estaduais_icms WHERE status_registro = 'ATIVA' AND status_validacao = 'ACEITO'"
        ).fetchone()[0]
        fontes = conn.execute("SELECT COUNT(*) FROM fontes_legais").fetchone()[0]
        nfes = conn.execute("SELECT COUNT(*) FROM nfe_documentos").fetchone()[0]
        ult_vigia = conn.execute("SELECT MAX(ultima_verificacao) FROM fontes_legais").fetchone()[0]
        ult_linx = conn.execute("SELECT MAX(atualizado_em) FROM linx_sync_cursor").fetchone()[0]
        return {
            "regras_a_conferir": int(a_conferir),
            "regras_aceitas": int(aceitas),
            "fontes_cadastradas": int(fontes),
            "nfes_importadas": int(nfes),
            "ultima_verificacao_vigia": ult_vigia or "Nunca executado",
            "ultima_sincronizacao_linx": ult_linx or "Nunca sincronizado",
        }

    def listar_regras_estaduais(
        self,
        *,
        uf_origem: str = "",
        uf_destino: str = "",
        ncm: str = "",
        cest: str = "",
        status_validacao: str = "",
        limite: int = 1000,
    ) -> list[dict[str, Any]]:
        """Lista regras estaduais com filtros opcionais e dados da fonte legal."""
        conn = self._get_conn()
        sql = """
            SELECT r.*, f.url_oficial AS fonte_url_oficial, f.tipo_norma AS fonte_tipo_norma
            FROM regras_estaduais_icms r
            LEFT JOIN fontes_legais f ON f.id = r.fonte_legal_id
            WHERE r.status_registro = 'ATIVA'
        """
        params: list[Any] = []
        if uf_origem.strip():
            sql += " AND r.uf_origem = ?"
            params.append(uf_origem.strip().upper())
        if uf_destino.strip():
            sql += " AND r.uf_destino = ?"
            params.append(uf_destino.strip().upper())
        if ncm.strip():
            sql += " AND r.ncm LIKE ?"
            params.append(f"%{ncm.strip()}%")
        if cest.strip():
            sql += " AND r.cest LIKE ?"
            params.append(f"%{cest.strip()}%")
        if status_validacao.strip():
            sql += " AND r.status_validacao = ?"
            params.append(status_validacao.strip().upper())

        sql += " ORDER BY r.id DESC LIMIT ?"
        params.append(limite)
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def listar_historico_regra(self, tabela: str, registro_id: int) -> list[dict[str, Any]]:
        """Lista o histórico append-only de alterações de uma regra."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT * FROM historico_alteracoes
            WHERE tabela_origem = ? AND registro_id = ?
            ORDER BY id DESC
            """,
            (tabela, registro_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def criar_regra_estadual_manual(
        self,
        *,
        uf_origem: str,
        uf_destino: str,
        ncm: str,
        cest: str = "",
        natureza_operacao: str = "VENDA",
        operacao_com_contribuinte: bool = True,
        cfop: str = "5102",
        cst_icms: str = "00",
        aliquota_icms: float = 18.0,
        reducao_base_icms: float = 0.0,
        tem_st: bool = False,
        margem_st: float = 0.0,
        aliquota_icms_st: float = 0.0,
        aliquota_fcp: float = 0.0,
        dispositivo_legal: str = "Cadastro Manual",
        usuario: str = "usuario_ui",
    ) -> int:
        """Cria uma nova regra estadual e registra criação no histórico."""
        conn = self._get_conn()
        hoje = date.today().isoformat()
        with conn:
            cur = conn.execute(
                """
                INSERT INTO regras_estaduais_icms (
                    uf_origem, uf_destino, ncm, cest, natureza_operacao,
                    operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                    cfop, cst_icms, aliquota_icms, reducao_base_icms,
                    tem_st, margem_st, aliquota_icms_st, aliquota_fcp,
                    dispositivo_legal, status_validacao
                ) VALUES (?, ?, ?, ?, ?, ?, '*', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'A_CONFERIR')
                """,
                (
                    uf_origem.upper(),
                    uf_destino.upper(),
                    ncm.strip(),
                    cest.strip(),
                    natureza_operacao.upper(),
                    1 if operacao_com_contribuinte else 0,
                    hoje,
                    cfop.strip(),
                    cst_icms.strip(),
                    aliquota_icms,
                    reducao_base_icms,
                    1 if tem_st else 0,
                    margem_st,
                    aliquota_icms_st,
                    aliquota_fcp,
                    dispositivo_legal,
                ),
            )
            reg_id = int(cur.lastrowid)
            registrar_historico(
                conn,
                tabela_origem="regras_estaduais_icms",
                registro_id=reg_id,
                acao="CRIACAO",
                usuario=usuario,
                campo="ncm",
                valor_anterior=None,
                valor_novo=ncm.strip(),
                motivo=dispositivo_legal,
                auto_commit=False,
            )
            return reg_id

    def aprovar_em_lote(self, ids_versoes: list[tuple[int, int]], usuario: str) -> int:
        """Aprova em lote regras estaduais usando optimistic locking."""
        aprovadas = 0
        for reg_id, versao in ids_versoes:
            self.aprovar_ou_editar_regra(
                tabela="regras_estaduais_icms",
                registro_id=reg_id,
                versao_atual=versao,
                alteracoes={},
                usuario=usuario,
                motivo="Aprovação em lote pela interface",
                aprovar=True,
            )
            aprovadas += 1
        return aprovadas

    def listar_fontes_legais(self) -> list[dict[str, Any]]:
        """Retorna todas as fontes oficiais cadastradas."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM fontes_legais ORDER BY uf, id DESC").fetchall()
        return [dict(r) for r in rows]

    def listar_nfe_documentos(self) -> list[dict[str, Any]]:
        """Retorna documentos NF-e com status dinâmico da vw_nfe_status."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM vw_nfe_status ORDER BY data_emissao DESC").fetchall()
        return [dict(r) for r in rows]

    def listar_divergencias(
        self,
        *,
        tipo_auditoria: str | None = None,
        referencia_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista divergências registradas em auditoria_divergencias."""
        conn = self._get_conn()
        sql = "SELECT * FROM auditoria_divergencias WHERE 1=1"
        params: list[Any] = []
        if tipo_auditoria:
            sql += " AND tipo_auditoria = ?"
            params.append(tipo_auditoria)
        if referencia_id:
            sql += " AND referencia_id = ?"
            params.append(referencia_id)
        sql += " ORDER BY id DESC LIMIT 500"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def sincronizar_linx(self, cnpj_emp: str, client: MicrovixClient | None = None) -> dict[str, int]:
        """Executa sincronização incremental dos 4 métodos Linx Microvix."""
        conn = self._get_conn()
        cli = client or MicrovixClient()
        resumo: dict[str, int] = {}
        for metodo in sorted(METODOS_SUPORTADOS):
            resumo[metodo] = sincronizar_metodo(conn, cli, metodo=metodo, cnpj_emp=cnpj_emp)
        return resumo

    def executar_vigia(self) -> list[dict[str, Any]]:
        """Executa o Vigia Noturno (Zero IA) sobre fontes_legais."""
        conn = self._get_conn()
        alertas = verificar_fontes(conn)
        return [asdict(a) for a in alertas]

    def listar_linx_config_tributarias(self) -> list[dict[str, Any]]:
        """Lista as configurações tributárias sincronizadas do Linx Microvix."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM linx_config_tributarias ORDER BY empresa, id_config_tributaria"
        ).fetchall()
        return [dict(r) for r in rows]

    def executar_seed_sp(self, *, usar_rede: bool = False) -> dict[str, Any]:
        """Executa o Seed Inicial de SP (20 NCMs) e gera a planilha modelo."""
        from src.app.seed_sp import executar_seed_sp

        return executar_seed_sp(self.db_path, usar_rede=usar_rede)

    def gerar_template_carga_ncms_bytes(self) -> bytes:
        """Gera um template padrão .xlsx em memória para carga de NCMs/regras."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Carga_NCMs"
        ws.append(
            [
                "uf_origem",
                "uf_destino",
                "ncm",
                "cest",
                "natureza_operacao",
                "operacao_com_contribuinte",
                "vigencia_inicio",
                "cfop",
                "cst_icms",
                "aliquota_icms",
                "reducao_base_icms",
                "tem_st",
                "margem_st",
                "aliquota_icms_st",
                "codigo_beneficio_fiscal",
                "dispositivo_legal",
            ]
        )
        ws.append(["SP", "SP", "85171300", "2105301", "VENDA", 1, "2026-10-01", "5102", "00", 18.0, 0.0, 0, 0.0, 0.0, "", "Portaria SRE SP"])
        ws.append(["SP", "SP", "84321000", "", "VENDA", 1, "2026-01-01", "5102", "20", 18.0, 51.11, 0, 0.0, 0.0, "SP020012", "RICMS/SP Anexo II Art. 12"])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def importar_regras_lote(
        self,
        conteudo_bytes: bytes,
        *,
        extensao: str = ".xlsx",
        usuario: str = "usuario_ui",
    ) -> dict[str, int]:
        """Importa planilha .xlsx ou .csv de NCMs para regras_estaduais_icms como A_CONFERIR."""
        ext = extensao.lower()
        linhas: list[dict[str, Any]] = []

        if ext == ".csv":
            texto = conteudo_bytes.decode("utf-8-sig", errors="replace")
            reader = csv.DictReader(io.StringIO(texto), delimiter=";")
            linhas = [dict(r) for r in reader]
            if linhas and len(linhas[0]) == 1 and "," in next(iter(linhas[0].keys())):
                reader = csv.DictReader(io.StringIO(texto), delimiter=",")
                linhas = [dict(r) for r in reader]
        else:
            wb = openpyxl.load_workbook(io.BytesIO(conteudo_bytes), read_only=True, data_only=True)
            try:
                ws = wb.active
                it = ws.iter_rows(values_only=True)
                header_raw = next(it, None)
                if header_raw:
                    headers = [
                        str(h).strip() if h is not None else f"col_{i}"
                        for i, h in enumerate(header_raw)
                    ]
                    for row in it:
                        if not any(v is not None and str(v).strip() for v in row):
                            continue
                        linhas.append(
                            {
                                headers[i]: ("" if i >= len(row) or row[i] is None else row[i])
                                for i in range(len(headers))
                            }
                        )
            finally:
                wb.close()

        conn = self._get_conn()
        inseridas = 0
        ignoradas = 0

        def _num(v: Any, default: float = 0.0) -> float:
            s = str(v if v is not None else "").replace(",", ".").replace("%", "").strip()
            if not s:
                return default
            try:
                return float(s)
            except ValueError:
                return default

        def _flag(v: Any, default: int = 0) -> int:
            s = str(v if v is not None else "").strip().upper()
            if s in {"1", "S", "SIM", "TRUE"}:
                return 1
            if s in {"0", "N", "NAO", "NÃO", "FALSE"}:
                return 0
            return default

        with conn:
            for raw in linhas:
                row = {str(k).strip().lower(): v for k, v in raw.items()}
                ncm = re.sub(r"\D", "", str(row.get("ncm") or ""))
                if len(ncm) != 8:
                    ignoradas += 1
                    continue
                cest = re.sub(r"\D", "", str(row.get("cest") or ""))
                uf_o = str(row.get("uf_origem") or "SP").strip().upper()[:2] or "SP"
                uf_d = str(row.get("uf_destino") or uf_o).strip().upper()[:2] or uf_o
                nat = str(row.get("natureza_operacao") or "VENDA").strip().upper()
                contrib = _flag(row.get("operacao_com_contribuinte"), 1)
                vig_ini = str(row.get("vigencia_inicio") or date.today().isoformat()).strip()[:10]
                cfop = re.sub(r"\D", "", str(row.get("cfop") or "5102")) or "5102"
                cst = str(row.get("cst_icms") or "00").strip()
                aliq = _num(row.get("aliquota_icms"), 18.0)
                red = _num(row.get("reducao_base_icms"), 0.0)
                tem_st = _flag(row.get("tem_st"), 0)
                mva = _num(row.get("margem_st"), 0.0)
                aliq_st = _num(row.get("aliquota_icms_st"), 0.0)
                cbenef = str(row.get("codigo_beneficio_fiscal") or "").strip()
                disp = str(row.get("dispositivo_legal") or "Importação Planilha Lote").strip()

                cur = conn.execute(
                    """
                    INSERT INTO regras_estaduais_icms (
                        uf_origem, uf_destino, ncm, cest, natureza_operacao,
                        operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                        cfop, cst_icms, aliquota_icms, reducao_base_icms,
                        tem_st, margem_st, aliquota_icms_st, codigo_beneficio_fiscal,
                        dispositivo_legal, status_validacao
                    ) VALUES (?, ?, ?, ?, ?, ?, '*', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'A_CONFERIR')
                    """,
                    (
                        uf_o, uf_d, ncm, cest, nat, contrib, vig_ini,
                        cfop, cst, aliq, red, tem_st, mva, aliq_st, cbenef, disp,
                    ),
                )
                registrar_historico(
                    conn,
                    tabela_origem="regras_estaduais_icms",
                    registro_id=int(cur.lastrowid),
                    acao="CRIACAO",
                    usuario=usuario,
                    campo="ncm",
                    valor_novo=ncm,
                    motivo=disp,
                    auto_commit=False,
                )
                inseridas += 1

        return {"inseridas": inseridas, "ignoradas": ignoradas}

    def consultar_matriz_completa_ncm(
        self,
        *,
        ncm: str,
        uf_origem: str,
        uf_destino: str,
        cest: str = "",
        data_referencia: str | None = None,
        incluir_tributado_se_st: bool = True,
    ) -> list[dict[str, Any]]:
        """Retorna todas as linhas de operações (Compra, Venda, Dev. Compra, Dev. Venda) para o NCM."""
        conn = self._get_conn()
        ref = data_referencia or date.today().isoformat()
        ncm_limpo = re.sub(r"\D", "", ncm or "")
        if len(ncm_limpo) != 8:
            return []

        # Busca todas as variações vigentes para o NCM (e fallback geral da UF se não houver específica)
        regras = conn.execute(
            """
            SELECT * FROM regras_estaduais_icms
            WHERE status_registro = 'ATIVA'
              AND status_validacao != 'REJEITADO'
              AND uf_origem = ?
              AND uf_destino = ?
              AND ncm = ?
              AND vigencia_inicio <= ?
              AND (vigencia_fim IS NULL OR vigencia_fim >= ?)
            ORDER BY vigencia_inicio DESC, id DESC
            """,
            (uf_origem.upper(), uf_destino.upper(), ncm_limpo, ref, ref),
        ).fetchall()

        regras_list = [dict(r) for r in regras]
        if not regras_list:
            # Fallback 1: regra interna da UF de destino ou origem para o mesmo NCM
            regra_uf_ncm = conn.execute(
                """
                SELECT * FROM regras_estaduais_icms
                WHERE status_registro = 'ATIVA'
                  AND status_validacao != 'REJEITADO'
                  AND ncm = ?
                  AND uf_origem IN (?, ?)
                  AND vigencia_inicio <= ?
                  AND (vigencia_fim IS NULL OR vigencia_fim >= ?)
                ORDER BY
                    CASE WHEN uf_destino = ? THEN 1 ELSE 0 END DESC,
                    vigencia_inicio DESC,
                    id DESC
                LIMIT 1
                """,
                (ncm_limpo, uf_origem.upper(), uf_destino.upper(), ref, ref, uf_destino.upper()),
            ).fetchone()
            if regra_uf_ncm is not None:
                regras_list = [dict(regra_uf_ncm)]
            else:
                regra_fallback = buscar_regra_estadual_icms(
                    conn,
                    uf_origem=uf_origem,
                    uf_destino=uf_destino,
                    ncm=ncm_limpo,
                    cest=cest,
                    data_referencia=ref,
                )
                if regra_fallback is not None:
                    regras_list = [regra_fallback]

        if not regras_list:
            return []

        regra_fed = buscar_regra_federal(conn, ncm=ncm_limpo, cest=cest, data_referencia=ref)
        todas_linhas: list[dict[str, Any]] = []
        for regra_est in regras_list:
            todas_linhas.extend(
                gerar_linhas_matriz_ncm(
                    ncm=ncm_limpo,
                    uf_origem=uf_origem,
                    uf_destino=uf_destino,
                    regra_est=regra_est,
                    regra_fed=regra_fed,
                    incluir_tributado_se_st=incluir_tributado_se_st,
                )
            )
        return todas_linhas

    def exportar_matriz_ncm_xlsx(self, linhas: list[dict[str, Any]]) -> bytes:
        """Exporta as linhas da matriz por operação para arquivo Excel (.xlsx)."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Matriz_Operacoes_NCM"
        if not linhas:
            buf = io.BytesIO()
            wb.save(buf)
            return buf.getvalue()

        colunas = list(linhas[0].keys())
        ws.append(colunas)
        for linha in linhas:
            ws.append([linha.get(c, "") for c in colunas])

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def listar_ncms_disponiveis(self) -> list[str]:
        """Lista NCMs distintos disponíveis nas regras estaduais e federais."""
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT DISTINCT ncm FROM regras_estaduais_icms WHERE status_registro = 'ATIVA' AND ncm != ''
            UNION
            SELECT DISTINCT ncm FROM regras_federais WHERE status_registro = 'ATIVA' AND ncm != ''
            ORDER BY ncm
            """
        ).fetchall()
        return [str(r[0]) for r in rows]

    def consultar_matriz_operacional(
        self,
        ncm: str,
        uf_origem: str,
        uf_destino: str,
        *,
        cest: str = "",
        data_referencia: str | None = None,
        regime_tributario: str = "Lucro Real",
        atividade_empresa: str = "Varejo (Padrão)",
    ) -> list[dict[str, Any]]:
        """Consulta regras vigentes e expande a matriz operacional completa por NCM."""
        conn = self._get_conn()
        ref = data_referencia or date.today().isoformat()
        ncm_limpo = re.sub(r"\D", "", ncm or "")
        if len(ncm_limpo) != 8:
            return []

        regras = conn.execute(
            """
            SELECT * FROM regras_estaduais_icms
            WHERE status_registro = 'ATIVA'
              AND status_validacao != 'REJEITADO'
              AND uf_origem = ?
              AND uf_destino = ?
              AND ncm = ?
              AND vigencia_inicio <= ?
              AND (vigencia_fim IS NULL OR vigencia_fim >= ?)
            ORDER BY vigencia_inicio DESC, id DESC
            """,
            (uf_origem.upper(), uf_destino.upper(), ncm_limpo, ref, ref),
        ).fetchall()

        regras_list = [dict(r) for r in regras]
        if not regras_list:
            regra_uf_ncm = conn.execute(
                """
                SELECT * FROM regras_estaduais_icms
                WHERE status_registro = 'ATIVA'
                  AND status_validacao != 'REJEITADO'
                  AND ncm = ?
                  AND uf_origem IN (?, ?)
                  AND vigencia_inicio <= ?
                  AND (vigencia_fim IS NULL OR vigencia_fim >= ?)
                ORDER BY
                    CASE WHEN uf_destino = ? THEN 1 ELSE 0 END DESC,
                    vigencia_inicio DESC,
                    id DESC
                LIMIT 1
                """,
                (ncm_limpo, uf_origem.upper(), uf_destino.upper(), ref, ref, uf_destino.upper()),
            ).fetchone()
            if regra_uf_ncm is not None:
                regras_list = [dict(regra_uf_ncm)]
            else:
                regra_fallback = buscar_regra_estadual_icms(
                    conn,
                    uf_origem=uf_origem,
                    uf_destino=uf_destino,
                    ncm=ncm_limpo,
                    cest=cest,
                    data_referencia=ref,
                )
                if regra_fallback is not None:
                    regras_list = [regra_fallback]

        if not regras_list:
            return []

        regra_fed = buscar_regra_federal(conn, ncm=ncm_limpo, cest=cest, data_referencia=ref)
        regra_terc = buscar_regra_terceiro(
            conn, uf_terceiro=uf_origem, ncm=ncm_limpo, cest=cest, data_referencia=ref
        )

        linhas: list[dict[str, Any]] = []
        for regra_est in regras_list:
            linhas.extend(
                gerar_matriz_ncm(
                    ncm=ncm_limpo,
                    uf_origem=uf_origem,
                    uf_destino=uf_destino,
                    regra_estadual=regra_est,
                    regra_federal=regra_fed,
                    tabela_terceiros=regra_terc,
                    regime_tributario=regime_tributario,
                    atividade_empresa=atividade_empresa,
                )
            )
        return linhas

    def consultar_matriz_operacional_todas_ufs(
        self,
        ncm: str,
        uf_origem: str,
        *,
        ufs_destino: tuple[str, ...] | list[str] | None = None,
        cest: str = "",
        data_referencia: str | None = None,
        regime_tributario: str = "Lucro Real",
        atividade_empresa: str = "Varejo (Padrão)",
    ) -> list[dict[str, Any]]:
        """Expande a matriz para todos os destinos (27 UFs), ordenando:
        UF Origem > Origem (Nacional/Importado) > Perfil (NC primeiro, depois CO) > Natureza/CFOP > Destino.
        """
        todas_ufs = (
            "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO",
            "MA", "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR",
            "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
        )
        destinos = sorted({u.upper() for u in (ufs_destino or todas_ufs)})
        uf_o = uf_origem.upper()
        linhas_totais: list[dict[str, Any]] = []

        for uf_d in destinos:
            linhas_uf = self.consultar_matriz_operacional(
                ncm=ncm,
                uf_origem=uf_o,
                uf_destino=uf_d,
                cest=cest,
                data_referencia=data_referencia,
                regime_tributario=regime_tributario,
                atividade_empresa=atividade_empresa,
            )
            linhas_totais.extend(linhas_uf)

        def _sort_key(row: dict[str, Any]) -> tuple[str, int, int, str, int, str, str]:
            orig_rank = 0 if row.get("Origem") == "Nacional" else 1
            perfil_rank = 0 if row.get("Perfil (NC/CO)") == "NC" else 1
            regime = str(row.get("Regime ICMS") or "")
            regime_rank = 1 if regime == "ST" else 0
            return (
                str(row.get("UF Origem") or ""),
                orig_rank,
                perfil_rank,
                str(row.get("Natureza de Operação") or ""),
                regime_rank,
                str(row.get("CFOP") or ""),
                str(row.get("UF da Operação") or ""),
            )

        linhas_totais.sort(key=_sort_key)
        return linhas_totais

    def extrair_ncms_de_arquivo(self, filename: str, conteudo_bytes: bytes) -> list[str]:
        """Extrai lista única e ordenada de NCMs (8 dígitos) de .xlsx, .csv ou .txt."""
        nome = (filename or "").lower()
        ncms: list[str] = []

        if nome.endswith(".xlsx"):
            wb = openpyxl.load_workbook(io.BytesIO(conteudo_bytes), read_only=True, data_only=True)
            try:
                ws = wb.active
                rows = ws.iter_rows(values_only=True)
                first = next(rows, None)
                if first is not None:
                    headers = [str(h or "").strip().lower() for h in first]
                    col_idx = next((i for i, h in enumerate(headers) if "ncm" in h), None)
                    if col_idx is None:
                        col_idx = 0
                        # Primeira linha pode já ser um NCM sem cabeçalho
                        dig = re.sub(r"\D", "", str(first[col_idx] or ""))
                        if len(dig) == 8 and dig != "00000000":
                            ncms.append(dig)
                    for row in rows:
                        if col_idx < len(row):
                            dig = re.sub(r"\D", "", str(row[col_idx] or ""))
                            if len(dig) == 8 and dig != "00000000":
                                ncms.append(dig)
            finally:
                wb.close()
        else:
            texto = conteudo_bytes.decode("utf-8-sig", errors="replace")
            if nome.endswith(".csv"):
                delim = ";" if ";" in texto.splitlines()[0] else "," if texto.splitlines() else ";"
                reader = csv.reader(io.StringIO(texto), delimiter=delim)
                rows_csv = list(reader)
                if rows_csv:
                    headers = [str(h or "").strip().lower() for h in rows_csv[0]]
                    col_idx = next((i for i, h in enumerate(headers) if "ncm" in h), None)
                    start_row = 1 if col_idx is not None else 0
                    idx_uso = col_idx if col_idx is not None else 0
                    for row in rows_csv[start_row:]:
                        if idx_uso < len(row):
                            dig = re.sub(r"\D", "", str(row[idx_uso] or ""))
                            if len(dig) == 8 and dig != "00000000":
                                ncms.append(dig)
            else:
                # .txt ou fallback genérico: captura sequências de NCM com ou sem pontos
                for match in re.findall(r"\b\d{4}\.?\d{2}\.?\d{2}\b", texto):
                    dig = re.sub(r"\D", "", match)
                    if len(dig) == 8 and dig != "00000000":
                        ncms.append(dig)

        return list(dict.fromkeys(ncms))

    def consultar_matriz_operacional_lote(
        self,
        ncms: list[str],
        uf_origem: str,
        *,
        ufs_destino: tuple[str, ...] | list[str] | None = None,
        data_referencia: str | None = None,
        regime_tributario: str = "Lucro Real",
        atividade_empresa: str = "Varejo (Padrão)",
    ) -> dict[str, Any]:
        """Consolida a matriz operacional (todas as naturezas e destinos) para uma lista de NCMs."""
        ncms_limpos = list(
            dict.fromkeys(
                re.sub(r"\D", "", str(n or ""))
                for n in ncms
                if len(re.sub(r"\D", "", str(n or ""))) == 8
            )
        )
        linhas_consolidadas: list[dict[str, Any]] = []
        ncms_sem_regra: list[str] = []

        for ncm in ncms_limpos:
            linhas_ncm = self.consultar_matriz_operacional_todas_ufs(
                ncm=ncm,
                uf_origem=uf_origem,
                ufs_destino=ufs_destino,
                data_referencia=data_referencia,
                regime_tributario=regime_tributario,
                atividade_empresa=atividade_empresa,
            )
            if not linhas_ncm:
                ncms_sem_regra.append(ncm)
            else:
                linhas_consolidadas.extend(linhas_ncm)

        return {
            "ncms_solicitados": len(ncms_limpos),
            "ncms_encontrados": len(ncms_limpos) - len(ncms_sem_regra),
            "ncms_sem_regra": ncms_sem_regra,
            "linhas": linhas_consolidadas,
        }

    def exportar_matriz_padrao_xlsx(self, linhas: list[dict[str, Any]]) -> bytes:
        """Gera Excel multi-abas no padrão oficial da planilha de configuração."""
        wb = openpyxl.Workbook()
        ws_compras = wb.active
        ws_compras.title = "Compras Comercialização"
        ws_vendas = wb.create_sheet("Venda de Mercadorias")
        ws_dev = wb.create_sheet("Devoluções & Outras")
        ws_transf = wb.create_sheet("Transferências Filiais")

        if not linhas:
            buf = io.BytesIO()
            wb.save(buf)
            return buf.getvalue()

        colunas = list(linhas[0].keys())
        for ws in (ws_compras, ws_vendas, ws_dev, ws_transf):
            ws.append(colunas)

        for linha in linhas:
            op = str(linha.get("Natureza de Operação") or linha.get("Operação") or "")
            valores = [linha.get(c, "") for c in colunas]
            if "Compra para Comercialização" in op:
                ws_compras.append(valores)
            elif "Venda de Mercadorias" in op:
                ws_vendas.append(valores)
            elif "Transferência" in op:
                ws_transf.append(valores)
            else:
                ws_dev.append(valores)

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def exportar_matriz_erp_unica_xlsx(self, linhas: list[dict[str, Any]]) -> bytes:
        """Gera Excel em aba única na ordem exata do layout de importação de terceiros."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Layout Importacao ERP"
        if linhas:
            colunas = list(linhas[0].keys())
            ws.append(colunas)
            for linha in linhas:
                ws.append([linha.get(c, "") for c in colunas])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def validar_pre_consulta_ncms(
        self,
        ncms: list[str],
        *,
        uf_origem: str = "SP",
        data_referencia: str | None = None,
    ) -> dict[str, Any]:
        """Gatekeeper pré-consulta: valida fontes oficiais, alertas do Vigia e Árvore 5 Camadas."""
        conn = self._get_conn()
        garantir_fontes_oficiais(conn)
        fontes_ativas = int(
            conn.execute("SELECT COUNT(*) FROM fontes_legais WHERE status_fonte = 'ATIVA'").fetchone()[0]
        )
        fontes_falha = int(
            conn.execute("SELECT COUNT(*) FROM fontes_legais WHERE status_fonte = 'FALHA'").fetchone()[0]
        )
        alertas_vigia = int(
            conn.execute("SELECT COUNT(*) FROM vigia_alertas WHERE status_alerta = 'ABERTO'").fetchone()[0]
        )

        ncms_limpos = list(dict.fromkeys(re.sub(r"\D", "", str(n or "")) for n in ncms if n))
        detalhes: list[dict[str, Any]] = []
        ok_cnt = 0
        alerta_cnt = 0
        bloqueio_cnt = 0

        for ncm in ncms_limpos:
            regra_est = buscar_regra_estadual_icms(
                conn,
                uf_origem=uf_origem.upper(),
                uf_destino=uf_origem.upper(),
                ncm=ncm,
                data_referencia=data_referencia,
            )
            cst = str((regra_est or {}).get("cst_icms") or "00")
            cbenef = str((regra_est or {}).get("codigo_beneficio_fiscal") or "")
            tem_st = int((regra_est or {}).get("tem_st") or 0)
            cest = str((regra_est or {}).get("cest") or "")
            red_bc = float((regra_est or {}).get("reducao_base_icms") or 0.0)
            desc = str((regra_est or {}).get("dispositivo_legal") or "")

            res_5 = avaliar_arvore_5_camadas(
                ncm=ncm,
                cst_icms=cst,
                cbenef=cbenef,
                tem_st=tem_st,
                cest=cest,
                reducao_bc=red_bc,
                descricao_item=desc,
                data_referencia=data_referencia,
                conn=conn,
            )
            st_g = res_5["status_geral"]
            if st_g == "OK":
                ok_cnt += 1
            elif st_g == "ALERTA":
                alerta_cnt += 1
            else:
                bloqueio_cnt += 1
            detalhes.append(res_5)

        return {
            "fontes_ativas": fontes_ativas,
            "fontes_falha": fontes_falha,
            "alertas_vigia_abertos": alertas_vigia,
            "ncms_validados": len(ncms_limpos),
            "ncms_ok": ok_cnt,
            "ncms_alerta": alerta_cnt,
            "ncms_bloqueio": bloqueio_cnt,
            "detalhes": detalhes,
        }

    def executar_rotina_diaria_ao_abrir(
        self,
        *,
        uf_origem: str = "SP",
        forcar: bool = False,
        data_hoje: str | None = None,
        fetcher_sync: FetcherBytesFn | None = None,
        fetcher_vigia: Callable[[str, bool], tuple[bytes, str]] | None = None,
    ) -> dict[str, Any]:
        """Executa automaticamente 1x por dia ao abrir o sistema: catálogo + sync + Vigia SHA-256 + validador."""
        with _ROTINA_DIARIA_LOCK:
            conn = self._get_conn()
            hoje = data_hoje or date.today().isoformat()
            row = conn.execute(
                "SELECT ultima_data, resumo_json FROM controle_execucao_diaria WHERE chave = 'rotina_diaria_abertura'"
            ).fetchone()

            if row is not None and row["ultima_data"] == hoje and not forcar:
                resumo_prev = json.loads(row["resumo_json"]) if row["resumo_json"] else {}
                return {
                    "executado_agora": False,
                    "ultima_data": hoje,
                    "resumo": resumo_prev,
                }

            cat = self.garantir_catalogo_fontes_oficiais()

            sync_res: dict[str, Any] = {"erro": None}
            try:
                sync_res = self.sincronizar_bases_oficiais(
                    fetcher=fetcher_sync or baixar_bytes_oficiais,
                    uf_origem=uf_origem,
                )
            except Exception as exc:
                sync_res = {"erro": str(exc)}

            alertas_vigia: list[dict[str, Any]] = []
            vigia_erro: str | None = None
            try:
                alertas_obj = verificar_fontes(conn, fetcher=fetcher_vigia)
                alertas_vigia = [asdict(a) for a in alertas_obj]
            except Exception as exc:
                vigia_erro = str(exc)

            try:
                val_res = self.executar_validacao_ncms(uf_origem=uf_origem, persistir=True)
                validacao_resumo = {
                    "total_ncms_mapeados": val_res["total_ncms_mapeados"],
                    "ncms_conformes": val_res["ncms_conformes"],
                    "ncms_com_erro": val_res["ncms_com_erro"],
                    "ncms_com_alerta": val_res["ncms_com_alerta"],
                }
            except sqlite3.OperationalError as exc:
                validacao_resumo = {"erro": str(exc)}

            resumo = {
                "ultima_data": hoje,
                "catalogo": cat,
                "sync": sync_res,
                "alertas_vigia_novos": len(alertas_vigia),
                "vigia_erro": vigia_erro,
                "validacao": validacao_resumo,
            }
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT INTO controle_execucao_diaria (chave, ultima_data, resumo_json, atualizado_em)
                        VALUES ('rotina_diaria_abertura', ?, ?, datetime('now'))
                        ON CONFLICT(chave) DO UPDATE SET
                            ultima_data = excluded.ultima_data,
                            resumo_json = excluded.resumo_json,
                            atualizado_em = datetime('now')
                        """,
                        (hoje, json.dumps(resumo, ensure_ascii=False)),
                    )
            except sqlite3.OperationalError:
                pass

            return {
                "executado_agora": True,
                "ultima_data": hoje,
                "resumo": resumo,
            }

    def consolidar_regras_todos_ncms_base(
        self,
        *,
        uf_origem: str = "SP",
        data_referencia: str | None = None,
    ) -> dict[str, int]:
        """Garante que todos os NCMs da base federal possuam regra estadual e lastro em fontes_legais."""
        conn = self._get_conn()
        uf_o = uf_origem.upper()
        ref = data_referencia or date.today().isoformat()
        self.garantir_catalogo_fontes_oficiais()

        def _fonte_id_por_norma(termo: str) -> int | None:
            r = conn.execute(
                "SELECT id FROM fontes_legais WHERE numero_norma LIKE ? OR tipo_norma LIKE ? ORDER BY id LIMIT 1",
                (f"%{termo}%", f"%{termo}%"),
            ).fetchone()
            return int(r["id"]) if r else None

        id_ricms = _fonte_id_por_norma("45.490/2000")
        id_cat68 = _fonte_id_por_norma("68/2019") or id_ricms
        id_anexo1 = _fonte_id_por_norma("Anexo I") or id_ricms
        id_anexo2 = _fonte_id_por_norma("Anexo II") or id_ricms
        id_confaz142 = _fonte_id_por_norma("142/2018") or id_ricms

        regras_vinculadas = 0
        ncms_inseridos = 0
        fed_cclass_atualizados = 0

        with conn:
            # 1. Preenche cClassTrib padrão (000001) em regras_federais sem cClassTrib
            cur_fed = conn.execute(
                """
                UPDATE regras_federais
                SET cclass_trib = '000001',
                    cst_ibs_cbs = COALESCE(NULLIF(cst_ibs_cbs, ''), '000'),
                    atualizado_em = datetime('now')
                WHERE status_registro = 'ATIVA'
                  AND (cclass_trib IS NULL OR cclass_trib = '')
                """
            )
            fed_cclass_atualizados = int(cur_fed.rowcount)

            # 2. Associa fonte_legal_id e trecho_citado nas regras estaduais sem lastro
            sem_fonte = conn.execute(
                """
                SELECT id, cst_icms, tem_st, reducao_base_icms, dispositivo_legal, trecho_citado
                FROM regras_estaduais_icms
                WHERE status_registro = 'ATIVA'
                  AND (fonte_legal_id IS NULL OR trecho_citado IS NULL OR trecho_citado = '')
                """
            ).fetchall()
            for r in sem_fonte:
                tem_st = int(r["tem_st"] or 0)
                red = float(r["reducao_base_icms"] or 0)
                cst = str(r["cst_icms"] or "00")
                if tem_st == 1:
                    fid = id_cat68
                    disp_def = "Portaria CAT 68/2019 / RICMS/SP Art. 313"
                    trecho_def = "Mercadoria enquadrada no regime de substituição tributária em São Paulo."
                elif red > 0 or cst == "20":
                    fid = id_anexo2
                    disp_def = "RICMS/SP Anexo II"
                    trecho_def = "Redução de base de cálculo do ICMS conforme Anexo II do RICMS/SP."
                elif cst in {"40", "41", "50"}:
                    fid = id_anexo1
                    disp_def = "RICMS/SP Anexo I / Art. 7º"
                    trecho_def = "Operação com isenção ou não incidência prevista no RICMS/SP."
                else:
                    fid = id_ricms
                    disp_def = "RICMS/SP Decreto 45.490/2000 Art. 52"
                    trecho_def = "Alíquota interna de 18% nas operações internas em São Paulo (RICMS/SP Art. 52)."

                conn.execute(
                    """
                    UPDATE regras_estaduais_icms
                    SET fonte_legal_id = COALESCE(fonte_legal_id, ?),
                        dispositivo_legal = CASE WHEN dispositivo_legal IS NULL OR dispositivo_legal = '' THEN ? ELSE dispositivo_legal END,
                        trecho_citado = CASE WHEN trecho_citado IS NULL OR trecho_citado = '' THEN ? ELSE trecho_citado END,
                        atualizado_em = datetime('now')
                    WHERE id = ?
                    """,
                    (fid, disp_def, trecho_def, int(r["id"])),
                )
                regras_vinculadas += 1

            # 3. Garante que todo NCM de regras_federais possua ao menos 1 regra estadual vigente em SP
            cest_por_ncm: dict[str, str] = {}
            for tr in conn.execute(
                "SELECT ncm, cest FROM tabela_terceiros WHERE status_registro = 'ATIVA' AND cest != ''"
            ).fetchall():
                cest_por_ncm.setdefault(str(tr["ncm"]), str(tr["cest"]))

            existentes_est = {
                str(r["ncm"])
                for r in conn.execute(
                    "SELECT DISTINCT ncm FROM regras_estaduais_icms WHERE status_registro = 'ATIVA' AND uf_origem = ?",
                    (uf_o,),
                ).fetchall()
            }

            feds = conn.execute(
                """
                SELECT DISTINCT ncm, descricao_ncm
                FROM regras_federais
                WHERE status_registro = 'ATIVA' AND length(ncm) = 8 AND ncm != '00000000'
                """
            ).fetchall()

            novos_registros: list[tuple[Any, ...]] = []
            for f in feds:
                ncm = str(f["ncm"])
                if ncm in existentes_est:
                    continue
                cest = cest_por_ncm.get(ncm, "")
                desc = str(f["descricao_ncm"] or "NCM TIPI/Siscomex")
                fid = id_confaz142 if cest else id_ricms
                disp = (
                    f"RICMS/SP Art. 52 + Conv. 142/2018 (CEST {cest}) — {desc[:60]}"
                    if cest
                    else f"RICMS/SP Decreto 45.490/2000 Art. 52 — {desc[:60]}"
                )
                trecho = "Tributação padrão de ICMS 18% nas operações internas em São Paulo (RICMS/SP Art. 52)."
                novos_registros.append(
                    (
                        uf_o,
                        uf_o,
                        ncm,
                        cest,
                        "VENDA",
                        1,
                        "*",
                        ref,
                        "5102",
                        "00",
                        18.0,
                        0.0,
                        fid,
                        disp,
                        trecho,
                        "ACEITO",
                        "consolidacao_oficial",
                    )
                )
                ncms_inseridos += 1

            if novos_registros:
                conn.executemany(
                    """
                    INSERT INTO regras_estaduais_icms (
                        uf_origem, uf_destino, ncm, cest, natureza_operacao,
                        operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                        cfop, cst_icms, aliquota_icms, reducao_base_icms,
                        fonte_legal_id, dispositivo_legal, trecho_citado,
                        status_validacao, aceito_por
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    novos_registros,
                )

        return {
            "ncms_inseridos_sp": ncms_inseridos,
            "regras_vinculadas_fonte": regras_vinculadas,
            "federais_cclasstrib_atualizados": fed_cclass_atualizados,
        }

    def consultar_regime_emitente_nfe(
        self,
        chave_acesso: str,
        *,
        regime_manual: str = "",
    ) -> dict[str, Any]:
        """Consulta/atualiza o regime tributário do CNPJ emitente a partir do XML + cache/RFB."""
        conn = self._get_conn()
        doc = conn.execute(
            "SELECT * FROM nfe_documentos WHERE chave_acesso = ?",
            (chave_acesso,),
        ).fetchone()
        if doc is None:
            raise ValueError(f"NF-e {chave_acesso} não encontrada.")
        meta = extrair_metadados_emitente_xml(str(doc["xml_completo"] or "")) if doc["xml_completo"] else {}
        reg = consultar_regime_cnpj(
            conn,
            str(doc["cnpj_emitente"] or ""),
            razao_social=meta.get("razao_emitente", ""),
            uf=str(doc["uf_emitente"] or ""),
            crt_xml=meta.get("crt_emitente", "3"),
            regime_manual=regime_manual,
        )
        return {**meta, **reg}

    def gerar_comparativo_nfe_item_a_item(
        self,
        chave_acesso: str,
        *,
        natureza_operacao: str = "VENDA",
        operacao_com_contribuinte: bool = True,
        regime_emitente: str = "",
    ) -> dict[str, Any]:
        """Gera comparativo item a item (2 linhas por produto: Nota x Lei) com Check e mapa de células."""
        conn = self._get_conn()
        doc = conn.execute(
            "SELECT * FROM nfe_documentos WHERE chave_acesso = ?",
            (chave_acesso,),
        ).fetchone()
        if doc is None:
            raise ValueError(f"NF-e {chave_acesso} não encontrada.")

        meta_emit = self.consultar_regime_emitente_nfe(chave_acesso, regime_manual=regime_emitente)
        regime_uso = str(meta_emit.get("regime_apuracao") or "Lucro Real")
        uf_o = str(doc["uf_emitente"] or "SP").upper()
        uf_d = str(doc["uf_destinatario"] or uf_o).upper()
        data_ref = str(doc["data_emissao"] or date.today().isoformat())[:10]

        itens = conn.execute(
            "SELECT * FROM nfe_itens WHERE chave_acesso = ? ORDER BY numero_item ASC",
            (chave_acesso,),
        ).fetchall()

        divs_rows = conn.execute(
            """
            SELECT * FROM auditoria_divergencias
            WHERE tipo_auditoria = 'XML_NFE' AND referencia_id = ?
            ORDER BY numero_item ASC, id ASC
            """,
            (chave_acesso,),
        ).fetchall()
        divs_por_item: dict[int, list[dict[str, Any]]] = {}
        for d in divs_rows:
            if d["numero_item"] is not None:
                divs_por_item.setdefault(int(d["numero_item"]), []).append(dict(d))

        mapa_campo_col = {
            "ncm": "NCM",
            "cest": "CEST",
            "cfop": "CFOP",
            "cst_icms": "CST/CSOSN",
            "aliq_icms": "Alíq. ICMS",
            "valor_icms": "Vlr ICMS",
            "mva_st": "MVA ST",
            "bc_st": "BC ST",
            "aliq_st": "Alíq. ST",
            "valor_st": "Vlr ST",
            "valor_fcp_st": "Vlr FCP ST",
            "cst_pis": "CST PIS",
            "aliq_pis": "Alíq. PIS",
            "cst_cofins": "CST COFINS",
            "aliq_cofins": "Alíq. COFINS",
            "numero_fci": "FCI",
            "origem_mercadoria": "Orig",
        }

        linhas: list[dict[str, Any]] = []
        celulas_divergentes: dict[tuple[int, str], str] = {}
        itens_ok = 0
        itens_erro = 0
        itens_sem_regra = 0

        for it in itens:
            n_item = int(it["numero_item"])
            ncm = str(it["ncm"] or "")
            cest = str(it["cest"] or "")
            orig_nota = str(it["origem_mercadoria"] or "0")
            divs_item = divs_por_item.get(n_item, [])
            sevs = {d["severidade"] for d in divs_item}

            if "DIVERGENTE" in sevs:
                check_icon = "❌"
                itens_erro += 1
            elif "SEM_REGRA" in sevs or "ATENCAO" in sevs:
                check_icon = "⚠️"
                itens_sem_regra += 1
            else:
                check_icon = "✅"
                itens_ok += 1

            regra_est = buscar_regra_estadual_icms(
                conn,
                uf_origem=uf_o,
                uf_destino=uf_d,
                ncm=ncm,
                cest=cest,
                natureza_operacao=natureza_operacao,
                operacao_com_contribuinte=1 if operacao_com_contribuinte else 0,
                origem_mercadoria=orig_nota,
                data_referencia=data_ref,
            )
            regra_fed = buscar_regra_federal(conn, ncm=ncm, cest=cest, data_referencia=data_ref)
            regra_terc = buscar_regra_terceiro(conn, uf_terceiro=uf_o, ncm=ncm, cest=cest, data_referencia=data_ref)

            # Valores esperados pela lei + motor puro
            esp_cest = str((regra_est or {}).get("cest") or cest)
            esp_cfop = str((regra_est or {}).get("cfop") or it["cfop"] or "")
            esp_cst = str((regra_est or {}).get("cst_icms") or it["cst_icms"] or "")
            esp_aliq_icms = float((regra_est or {}).get("aliquota_icms") or 0.0)
            esp_vlr_icms = float(it["valor_icms"] or 0.0)
            esp_mva = float((regra_est or {}).get("margem_st") or 0.0)
            esp_bc_st = float(it["bc_st"] or 0.0)
            esp_aliq_st = float((regra_est or {}).get("aliquota_icms_st") or 0.0)
            esp_vlr_st = float(it["valor_st"] or 0.0)
            esp_vlr_fcp_st = float(it["valor_fcp_st"] or 0.0)
            esp_pis_cst = str((regra_fed or {}).get("cst_pis_saida") or it["cst_pis"] or "")
            esp_pis_aliq = float((regra_fed or {}).get("aliquota_pis") or 0.0)
            esp_cof_cst = str((regra_fed or {}).get("cst_cofins_saida") or it["cst_cofins"] or "")
            esp_cof_aliq = float((regra_fed or {}).get("aliquota_cofins") or 0.0)
            esp_cbenef = str((regra_est or {}).get("codigo_beneficio_fiscal") or "")

            if "Simples Nacional" in regime_uso and "Excesso" not in regime_uso or "MEI" in regime_uso:
                esp_pis_aliq = 0.0
                esp_cof_aliq = 0.0
            elif "Presumido" in regime_uso and esp_pis_cst not in {"04", "05", "06"}:
                esp_pis_aliq = 0.65
                esp_cof_aliq = 3.00

            if regra_est is not None:
                regra_calc = dict(regra_est)
                if uf_o != uf_d:
                    aliq_inter_lei = aliquota_interestadual(uf_o, uf_d, orig_nota)
                    if aliq_inter_lei is not None:
                        regra_calc["aliquota_icms"] = float(aliq_inter_lei)
                        esp_aliq_icms = float(aliq_inter_lei)
                calc = calcular_item(
                    ItemCalculo(
                        valor_produto=Decimal(str(it["valor_produto"] or 0)),
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        ncm=ncm,
                        cest=cest,
                        origem_mercadoria=orig_nota,
                        operacao_com_contribuinte=operacao_com_contribuinte,
                        valor_ipi=Decimal(str(it["valor_ipi"] or 0)),
                        conteudo_importacao_pct=(
                            Decimal(str(regra_terc["conteudo_importacao_pct"]))
                            if regra_terc and regra_terc.get("conteudo_importacao_pct") is not None
                            else None
                        ),
                    ),
                    regra_icms=regra_calc,
                    regra_federal=regra_fed,
                    regra_terceiro=regra_terc,
                )
                esp_vlr_icms = float(calc.valor_icms_proprio)
                esp_mva = float(calc.mva_aplicada)
                esp_bc_st = float(calc.bc_st)
                esp_vlr_st = float(calc.valor_icms_st)
                esp_vlr_fcp_st = float(calc.valor_fcp_st)

            # Sobrescreve com o valor_esperado_lei exato registrado pela auditoria de 13 etapas
            msgs_item: list[str] = []
            for d in divs_item:
                campo = str(d["campo_divergente"] or "")
                col = mapa_campo_col.get(campo)
                if col:
                    celulas_divergentes[(n_item, col)] = str(d["severidade"])
                msgs_item.append(f"{campo}: {d['valor_praticado']} -> {d['valor_esperado_lei']}")
                val_esp = str(d["valor_esperado_lei"] or "")
                if campo == "cfop":
                    esp_cfop = val_esp
                elif campo == "cst_icms":
                    esp_cst = val_esp
                elif campo == "cest":
                    esp_cest = val_esp

            resumo_divs = " | ".join(msgs_item) if msgs_item else "Conforme legislação"

            # Linha 1: O que está na Nota (XML)
            linhas.append(
                {
                    "Check": check_icon,
                    "Item": n_item,
                    "Registro": "NF-e (Nota)",
                    "Código": str(it["codigo_produto"] or ""),
                    "Descrição": str(it["descricao"] or "")[:45],
                    "NCM": ncm,
                    "CEST": cest,
                    "Orig": orig_nota,
                    "CFOP": str(it["cfop"] or ""),
                    "CST/CSOSN": str(it["cst_icms"] or ""),
                    "cBenef": "",
                    "Vlr Prod": round(float(it["valor_produto"] or 0), 2),
                    "Alíq. ICMS": round(float(it["aliq_icms"] or 0), 2),
                    "Vlr ICMS": round(float(it["valor_icms"] or 0), 2),
                    "MVA ST": round(float(it["mva_st"] or 0), 2),
                    "BC ST": round(float(it["bc_st"] or 0), 2),
                    "Alíq. ST": round(float(it["aliq_st"] or 0), 2),
                    "Vlr ST": round(float(it["valor_st"] or 0), 2),
                    "Vlr FCP ST": round(float(it["valor_fcp_st"] or 0), 2),
                    "CST PIS": str(it["cst_pis"] or ""),
                    "Alíq. PIS": round(float(it["aliq_pis"] or 0), 2),
                    "CST COFINS": str(it["cst_cofins"] or ""),
                    "Alíq. COFINS": round(float(it["aliq_cofins"] or 0), 2),
                    "FCI": str(it["numero_fci"] or ""),
                    "Diagnóstico": resumo_divs,
                }
            )
            # Linha 2: Como deveria ser (Lei)
            linhas.append(
                {
                    "Check": "",
                    "Item": n_item,
                    "Registro": "Lei (Esperado)",
                    "Código": str(it["codigo_produto"] or ""),
                    "Descrição": str(it["descricao"] or "")[:45],
                    "NCM": ncm,
                    "CEST": esp_cest,
                    "Orig": orig_nota,
                    "CFOP": esp_cfop,
                    "CST/CSOSN": esp_cst,
                    "cBenef": esp_cbenef,
                    "Vlr Prod": round(float(it["valor_produto"] or 0), 2),
                    "Alíq. ICMS": round(esp_aliq_icms, 2),
                    "Vlr ICMS": round(esp_vlr_icms, 2),
                    "MVA ST": round(esp_mva, 2),
                    "BC ST": round(esp_bc_st, 2),
                    "Alíq. ST": round(esp_aliq_st, 2),
                    "Vlr ST": round(esp_vlr_st, 2),
                    "Vlr FCP ST": round(esp_vlr_fcp_st, 2),
                    "CST PIS": esp_pis_cst,
                    "Alíq. PIS": round(esp_pis_aliq, 2),
                    "CST COFINS": esp_cof_cst,
                    "Alíq. COFINS": round(esp_cof_aliq, 2),
                    "FCI": str(it["numero_fci"] or ""),
                    "Diagnóstico": str((regra_est or {}).get("dispositivo_legal") or "Sem regra estadual cadastrada"),
                }
            )

        return {
            "chave_acesso": chave_acesso,
            "emitente": meta_emit,
            "total_itens": len(itens),
            "itens_ok": itens_ok,
            "itens_divergentes": itens_erro,
            "itens_sem_regra": itens_sem_regra,
            "linhas": linhas,
            "celulas_divergentes": celulas_divergentes,
        }

    def garantir_catalogo_fontes_oficiais(self) -> dict[str, int]:
        """Garante que todas as fontes oficiais mapeadas (SP/CONFAZ/Federal) estejam cadastradas."""
        conn = self._get_conn()
        return garantir_fontes_oficiais(conn)

    def executar_validacao_ncms(
        self,
        *,
        uf_origem: str | None = None,
        data_referencia: str | None = None,
        persistir: bool = True,
    ) -> dict[str, Any]:
        """Mapeia todos os NCMs e executa o validador de exceções (cBenef, ST, isenções, vigência)."""
        conn = self._get_conn()
        res = validar_matriz_ncms(
            conn,
            uf_origem=uf_origem,
            data_referencia=data_referencia,
            persistir=persistir,
        )
        return {
            **res,
            "achados": [asdict(a) for a in res["achados"]],
        }

    def listar_validacoes_ncm(
        self,
        *,
        severidade: str = "",
        categoria: str = "",
        ncm: str = "",
        limite: int = 500,
    ) -> list[dict[str, Any]]:
        """Lista os achados mais recentes da validação de NCMs persistidos no banco."""
        conn = self._get_conn()
        sql = "SELECT * FROM validacoes_ncm WHERE 1=1"
        params: list[Any] = []
        if severidade:
            sql += " AND severidade = ?"
            params.append(severidade.upper())
        if categoria:
            sql += " AND categoria = ?"
            params.append(categoria.upper())
        if ncm:
            ncm_limpo = re.sub(r"\D", "", ncm)
            sql += " AND ncm LIKE ?"
            params.append(f"{ncm_limpo}%")
        sql += " ORDER BY CASE severidade WHEN 'ERRO' THEN 1 WHEN 'ALERTA' THEN 2 ELSE 3 END, ncm LIMIT ?"
        params.append(limite)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def obter_resumo_mapeamento_ncms(self) -> dict[str, Any]:
        """Retorna cobertura de NCMs, exceções (cBenef, ST, isenções, redução) e última validação."""
        conn = self._get_conn()
        total_est = int(
            conn.execute(
                "SELECT COUNT(DISTINCT ncm) FROM regras_estaduais_icms WHERE status_registro = 'ATIVA' AND ncm != ''"
            ).fetchone()[0]
        )
        total_fed = int(
            conn.execute(
                "SELECT COUNT(DISTINCT ncm) FROM regras_federais WHERE status_registro = 'ATIVA' AND ncm != ''"
            ).fetchone()[0]
        )
        com_cbenef = int(
            conn.execute(
                "SELECT COUNT(DISTINCT ncm) FROM regras_estaduais_icms WHERE status_registro = 'ATIVA' AND codigo_beneficio_fiscal IS NOT NULL AND codigo_beneficio_fiscal != ''"
            ).fetchone()[0]
        )
        com_st = int(
            conn.execute(
                "SELECT COUNT(DISTINCT ncm) FROM regras_estaduais_icms WHERE status_registro = 'ATIVA' AND tem_st = 1"
            ).fetchone()[0]
        )
        com_reducao = int(
            conn.execute(
                "SELECT COUNT(DISTINCT ncm) FROM regras_estaduais_icms WHERE status_registro = 'ATIVA' AND reducao_base_icms > 0"
            ).fetchone()[0]
        )
        com_isencao = int(
            conn.execute(
                "SELECT COUNT(DISTINCT ncm) FROM regras_estaduais_icms WHERE status_registro = 'ATIVA' AND cst_icms IN ('40', '41', '50')"
            ).fetchone()[0]
        )
        erros = int(
            conn.execute("SELECT COUNT(*) FROM validacoes_ncm WHERE severidade = 'ERRO'").fetchone()[0]
        )
        alertas = int(
            conn.execute("SELECT COUNT(*) FROM validacoes_ncm WHERE severidade = 'ALERTA'").fetchone()[0]
        )
        infos = int(
            conn.execute("SELECT COUNT(*) FROM validacoes_ncm WHERE severidade = 'INFO'").fetchone()[0]
        )
        ultima = conn.execute("SELECT MAX(executado_em) FROM validacoes_ncm").fetchone()[0]
        return {
            "ncms_estaduais_distintos": total_est,
            "ncms_federais_distintos": total_fed,
            "ncms_com_cbenef": com_cbenef,
            "ncms_com_st": com_st,
            "ncms_com_reducao": com_reducao,
            "ncms_com_isencao": com_isencao,
            "validacao_erros": erros,
            "validacao_alertas": alertas,
            "validacao_infos": infos,
            "ultima_validacao": ultima or "Nunca",
        }

    def listar_alertas_vigia(self, *, status_alerta: str = "") -> list[dict[str, Any]]:
        """Lista alertas persistentes do Vigia Noturno."""
        conn = self._get_conn()
        sql = "SELECT * FROM vigia_alertas WHERE 1=1"
        params: list[Any] = []
        if status_alerta:
            sql += " AND status_alerta = ?"
            params.append(status_alerta.upper())
        sql += " ORDER BY criado_em DESC, id DESC"
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def encerrar_alerta_vigia(
        self,
        *,
        alerta_id: int,
        justificativa: str,
        usuario: str = "auditor_fiscal",
        status_alerta: str = "CONFERIDO",
    ) -> None:
        """Marca um alerta do Vigia como CONFERIDO/IGNORADO com justificativa."""
        conn = self._get_conn()
        with conn:
            conn.execute(
                """
                UPDATE vigia_alertas
                SET status_alerta = ?,
                    justificativa = ?,
                    conferido_por = ?,
                    conferido_em = datetime('now')
                WHERE id = ?
                """,
                (status_alerta.upper(), justificativa.strip(), usuario, alerta_id),
            )

    def listar_casos_criticos_sp(self) -> list[dict[str, Any]]:
        """Retorna os 10 casos críticos pré-mapeados de São Paulo."""
        return [dict(c) for c in CASOS_CRITICOS_SP]

    def obter_mapa_8_portais_sp(self) -> list[dict[str, str]]:
        """Retorna o checklist 100% dos 8 portais indispensáveis de SP."""
        return [dict(p) for p in MAPA_8_PORTAIS_SP]

    def avaliar_arvore_5_camadas_individual(
        self,
        *,
        ncm: str,
        cst_icms: str,
        cbenef: str = "",
        tem_st: int = 0,
        cest: str = "",
        reducao_bc: float = 0.0,
        descricao_item: str = "",
        ex_tipi: str = "",
        embalagem: str = "",
        data_referencia: str | None = None,
    ) -> dict[str, Any]:
        """Executa a árvore hierárquica de 5 camadas conectada ao banco."""
        conn = self._get_conn()
        return avaliar_arvore_5_camadas(
            ncm=ncm,
            cst_icms=cst_icms,
            cbenef=cbenef,
            tem_st=tem_st,
            cest=cest,
            reducao_bc=reducao_bc,
            descricao_item=descricao_item,
            ex_tipi=ex_tipi,
            embalagem=embalagem,
            data_referencia=data_referencia,
            conn=conn,
        )

    def simular_monitor_diario_sha256(
        self,
        *,
        simular_alteracao_portal: str = "Portarias SRE / CAT",
    ) -> list[dict[str, str]]:
        """Simula execução diária com detecção de alterações via hash SHA-256 nos 8 portais SP."""
        resultados: list[dict[str, str]] = []
        for p in MAPA_8_PORTAIS_SP:
            validar_url_oficial(p["url_oficial"])
            base_texto = f"{p['portal']}|{p['url_oficial']}|{p['formato']}"
            hash_anterior = hash_conteudo_limpo(base_texto)
            alterado = simular_alteracao_portal.lower() in p["portal"].lower()
            novo_texto = (
                f"{base_texto}|ATUALIZACAO_PORTARIA_DIARIA_{date.today().isoformat()}"
                if alterado
                else base_texto
            )
            hash_atual = hash_conteudo_limpo(novo_texto)
            resultados.append(
                {
                    "ordem": p["ordem"],
                    "portal": p["portal"],
                    "url_oficial": p["url_oficial"],
                    "hash_anterior": hash_anterior[:16] + "...",
                    "hash_atual": hash_atual[:16] + "...",
                    "status": "MUDANCA_DETECTADA" if hash_anterior != hash_atual else "SEM_ALTERACAO",
                }
            )
        return resultados

    def garantir_acervo_oficial(self) -> dict[str, int]:
        """Garante carga e atualização do acervo documental oficial no SQLite."""
        conn = self._get_conn()
        res = garantir_acervo_documental(conn)
        conn.commit()
        return res

    def buscar_acervo_documental(
        self,
        *,
        esfera: str = "",
        tipo_documento: str = "",
        status_norma: str = "",
        termo: str = "",
    ) -> list[dict[str, Any]]:
        """Consulta o acervo técnico e normativo indexado no banco."""
        conn = self._get_conn()
        garantir_acervo_documental(conn)
        conn.commit()
        return buscar_acervo(
            conn,
            esfera=esfera,
            tipo_documento=tipo_documento,
            status_norma=status_norma,
            termo=termo,
        )

    def indexar_nts_html_oficial(
        self,
        html: str,
        *,
        url_oficial: str = "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=04BIflQt1aY=",
    ) -> int:
        """Indexa Notas Técnicas extraídas do Portal NF-e no acervo com hash SHA-256."""
        conn = self._get_conn()
        qtd = indexar_nts_portal_nfe(conn, html, url_oficial=url_oficial)
        conn.commit()
        return qtd

    def simular_operacao_bidirecional(
        self,
        *,
        direcao: str,
        finalidade: str,
        uf_origem: str,
        uf_destino: str,
        ncm: str,
        valor_produto: Decimal | float | str,
        quantidade: Decimal | float | str = Decimal("1"),
        valor_ipi: Decimal | float | str = Decimal("0"),
        origem_mercadoria: str = "0",
        operacao_com_contribuinte: bool = True,
        cst_ou_csosn: str = "",
        cbenef: str = "",
        mva_original_pct: Decimal | float | str | None = None,
        reducao_bc_pct: Decimal | float | str | None = None,
        tem_st: bool | None = None,
        tem_protocolo_st: bool | None = None,
        st_retida_na_origem: bool = False,
        fornecedor_simples_nacional: bool = False,
        aliquota_credito_sn_pct: Decimal | float | str = Decimal("0"),
        pmpf_unitario: Decimal | float | str = Decimal("0"),
        data_referencia: str | None = None,
    ) -> dict[str, Any]:
        """Executa o roteador fiscal bidirecional (Saída vs Entrada Inversa) usando regras do banco."""
        conn = self._get_conn()
        ref = data_referencia or date.today().isoformat()
        ncm_limpo = re.sub(r"\D", "", str(ncm or ""))
        uf_o = uf_origem.strip().upper()
        uf_d = uf_destino.strip().upper()
        uf_regra = uf_d if direcao.strip().upper() == "ENTRADA" else uf_o

        regra_est = buscar_regra_estadual_icms(
            conn,
            uf_origem=uf_regra,
            uf_destino=uf_d,
            ncm=ncm_limpo,
            operacao_com_contribuinte=operacao_com_contribuinte,
            origem_mercadoria=origem_mercadoria,
            data_referencia=ref,
        ) or buscar_regra_estadual_icms(
            conn,
            uf_origem=uf_regra,
            uf_destino=uf_regra,
            ncm=ncm_limpo,
            operacao_com_contribuinte=operacao_com_contribuinte,
            origem_mercadoria=origem_mercadoria,
            data_referencia=ref,
        )
        regra_fed = buscar_regra_federal(conn, ncm=ncm_limpo, data_referencia=ref)

        cst_uso = cst_ou_csosn.strip() or str((regra_est or {}).get("cst_icms") or "00")
        params_est = resolver_parametros_estaduais(
            conn,
            uf_origem=uf_o,
            uf_destino=uf_d,
            ncm=ncm_limpo,
            cest=str((regra_est or {}).get("cest") or ""),
            cst=cst_uso,
            direcao=direcao,
            data_operacao=ref,
        )

        cbenef_uso = cbenef.strip() or str((regra_est or {}).get("codigo_beneficio_fiscal") or "")
        mva_uso = Decimal(
            str(
                mva_original_pct
                if mva_original_pct is not None
                else (params_est["mva_original"] if params_est["protocolo_encontrado"] else ((regra_est or {}).get("margem_st") or 0))
            )
        )
        red_uso = Decimal(str(reducao_bc_pct if reducao_bc_pct is not None else ((regra_est or {}).get("reducao_base_icms") or 0)))
        st_uso = bool(
            tem_st
            if tem_st is not None
            else (params_est["tem_st"] or bool((regra_est or {}).get("tem_st") or 0))
        )
        proto_uso = bool(
            tem_protocolo_st
            if tem_protocolo_st is not None
            else (params_est["tem_protocolo_st"] if params_est["protocolo_encontrado"] else bool((regra_est or {}).get("tem_acordo_st") or 0))
        )

        ctx = ContextoOperacaoFiscal(
            direcao=direcao,
            finalidade=finalidade,
            uf_origem=uf_o,
            uf_destino=uf_d,
            ncm=ncm_limpo,
            valor_produto=Decimal(str(valor_produto)),
            quantidade=Decimal(str(quantidade)),
            valor_ipi=Decimal(str(valor_ipi)),
            origem_mercadoria=origem_mercadoria,
            operacao_com_contribuinte=operacao_com_contribuinte,
            cst_ou_csosn=cst_uso,
            cbenef=cbenef_uso,
            cest=str(params_est.get("cest_resolvido") or (regra_est or {}).get("cest") or ""),
            aliquota_interna_destino=params_est["aliquota_interna_destino"] if params_est["protocolo_encontrado"] else None,
            aliquota_fcp=params_est["fcp_destino"] if params_est["protocolo_encontrado"] else None,
            reducao_bc_pct=red_uso,
            tem_st=st_uso,
            tem_protocolo_st=proto_uso,
            st_retida_na_origem=st_retida_na_origem,
            mva_original_pct=mva_uso,
            pmpf_unitario=Decimal(str(pmpf_unitario or params_est.get("pmpf_valor") or 0)),
            fornecedor_simples_nacional=fornecedor_simples_nacional,
            aliquota_credito_sn_pct=Decimal(str(aliquota_credito_sn_pct)),
        )
        return avaliar_operacao_bidirecional(
            ctx,
            regra_est=regra_est,
            regra_fed=regra_fed,
            cbenef_validos=params_est["cbenef_validos_uf"],
            ato_legal_st=params_est["ato_legal_st"],
        )

    def resolver_parametros_estaduais_ncm(
        self,
        *,
        uf_origem: str,
        uf_destino: str,
        ncm: str,
        cest: str = "",
        cst: str = "00",
        direcao: str = "SAIDA",
        data_operacao: str | None = None,
    ) -> dict[str, Any]:
        """Resolve automaticamente Protocolo ST e códigos cBenef vigentes por UF/data."""
        return resolver_parametros_estaduais(
            self._get_conn(),
            uf_origem=uf_origem,
            uf_destino=uf_destino,
            ncm=ncm,
            cest=cest,
            cst=cst,
            direcao=direcao,
            data_operacao=data_operacao,
        )

    def simular_reforma_lc214(
        self,
        *,
        ano_calendario: int,
        ncm: str,
        valor_operacao_bruto: Decimal | float | str,
        direcao: str = "SAIDA",
        icms_atual: Decimal | float | str = Decimal("0"),
        pis_atual: Decimal | float | str = Decimal("0"),
        cofins_atual: Decimal | float | str = Decimal("0"),
        ipi_atual: Decimal | float | str = Decimal("0"),
        iss_atual: Decimal | float | str = Decimal("0"),
        concorrente_zfm: bool = False,
        fornecedor_simples_nacional: bool = False,
        simples_regime_hibrido: bool = False,
        split_payment_liquidado: bool = True,
        xml_contem_gibscbs: bool = True,
    ) -> dict[str, Any]:
        """Simula a transição dual (Sistema Atual x Reforma LC 214/2025) de 2026 a 2033+."""
        ctx = ContextoReformaLC214(
            ano_calendario=ano_calendario,
            ncm=ncm,
            valor_operacao_bruto=Decimal(str(valor_operacao_bruto)),
            direcao=direcao,
            icms_atual=Decimal(str(icms_atual)),
            pis_atual=Decimal(str(pis_atual)),
            cofins_atual=Decimal(str(cofins_atual)),
            ipi_atual=Decimal(str(ipi_atual)),
            iss_atual=Decimal(str(iss_atual)),
            concorrente_zfm=concorrente_zfm,
            fornecedor_simples_nacional=fornecedor_simples_nacional,
            simples_regime_hibrido=simples_regime_hibrido,
            split_payment_liquidado=split_payment_liquidado,
            xml_contem_gibscbs=xml_contem_gibscbs,
        )
        return calcular_transicao_lc214(ctx)

    @staticmethod
    def validar_xml_reforma(xml_str: str) -> dict[str, Any]:
        """Valida grupos XML gIBSCBS e gIS conforme NT SVRS e Art. 12 § 2º da LC 214/2025."""
        return validar_xml_reforma_lc214(xml_str)

    def auditar_lote_entradas_xml(
        self,
        arquivos: list[tuple[str, bytes]],
        *,
        finalidade_padrao: str = "COMERCIALIZACAO",
        finalidades_por_item: dict[tuple[str, int], str] | None = None,
        erp_registros: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Executa parser seguro, auditoria bidirecional de entradas em lote e conciliação Linx Microvix."""
        conn = self._get_conn()
        parsed = parsear_arquivos_entrada(arquivos)
        res_lote = auditar_lote_xml_entrada(
            parsed["notas"],
            conn=conn,
            finalidade_padrao=finalidade_padrao,
            finalidades_por_item=finalidades_por_item,
        )
        divergencias_erp = conciliar_lote_com_microvix(
            conn,
            res_lote["itens_auditados"],
            erp_registros=erp_registros,
        )
        return {
            **res_lote,
            "erros_parse": parsed["erros"],
            "divergencias_erp": divergencias_erp,
        }

    @staticmethod
    def exportar_auditoria_lote_xlsx(
        resultado_lote: dict[str, Any],
        divergencias_erp: list[dict[str, Any]],
    ) -> bytes:
        """Exporta relatório executivo (.xlsx) em 4 abas com sanitização anti-Formula Injection."""
        return exportar_relatorio_auditoria_lote_xlsx(resultado_lote, divergencias_erp)

    def restaurar_snapshot_cloud(self) -> dict[str, Any]:
        """Restaura o snapshot versionado (10.580+ regras) se a base local estiver incompleta."""
        self.close()
        return restaurar_snapshot_se_necessario(self.db_path)

    NATUREZAS_OPERACAO_PADRAO = NATUREZAS_OPERACAO_PADRAO

    def listar_ids_naturezas_operacao(self) -> dict[str, int]:
        """Retorna os IDs externos configurados para cada Natureza de Operação (persistidos no SQLite)."""
        return listar_ids_naturezas_operacao_db(self._get_conn())

    def salvar_ids_naturezas_operacao(self, mapa_ids: dict[str, int]) -> dict[str, int]:
        """Salva/atualiza os IDs externos das Naturezas de Operação no SQLite."""
        return salvar_ids_naturezas_operacao_db(self._get_conn(), mapa_ids)

    @staticmethod
    def aplicar_ids_natureza_nas_linhas(
        linhas: list[dict[str, Any]],
        mapa_ids: dict[str, int],
    ) -> list[dict[str, Any]]:
        """Insere a coluna 'ID Natureza' imediatamente à esquerda de 'Natureza de Operação'."""
        return _aplicar_ids_natureza_nas_linhas(linhas, mapa_ids)

    def executar_pipeline_skills_ncm(
        self,
        *,
        ncm: str,
        cst_icms: str = "00",
        cbenef: str = "",
        tem_st: int = 0,
        cest: str = "",
        reducao_bc: float = 0.0,
        descricao_item: str = "",
        ex_tipi: str = "",
        embalagem: str = "",
        data_referencia: str | None = None,
    ) -> dict[str, Any]:
        """Executa o pipeline completo de 5 Skills Fiscais com Auditor Anti-Alucinação."""
        conn = self._get_conn()
        return executar_pipeline_skills(
            conn=conn,
            ncm=ncm,
            cst_icms=cst_icms,
            cbenef=cbenef,
            tem_st=tem_st,
            cest=cest,
            reducao_bc=reducao_bc,
            descricao_item=descricao_item,
            ex_tipi=ex_tipi,
            embalagem=embalagem,
            data_referencia=data_referencia,
        )


def baixar_bytes_oficiais(url: str) -> bytes:
    """Helper de download oficial usando a whitelist obrigatória."""
    conteudo, _ = baixar_url_oficial(url, timeout=8)
    return conteudo
