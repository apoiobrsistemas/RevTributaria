"""Pipeline de auditoria item a item de XML NF-e (Frente A) e Matriz ERP (Frente B)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from src.database import (
    buscar_regra_estadual_icms,
    buscar_regra_federal,
    buscar_regra_terceiro,
)
from src.engine.fiscal_math import ItemCalculo, _dec, calcular_item

TOL_PERCENTUAL_PP = Decimal("0.01")
TOL_CARGA_ICMS_PP = Decimal("0.02")
TOL_VALOR_MIN = Decimal("0.05")
TOL_VALOR_PCT = Decimal("0.001")

CFOPS_NAO_CONFERIVEIS = frozenset({"5908", "6908", "5912", "6912", "5913", "6913"})
CONVERSAO_ORIGEM_ENTRADA = {"1": "2", "6": "7"}
PLACEHOLDERS_ERP = frozenset({"PLACEHOLDER", "GENERICA", "PADRAO_INICIAL", "CONFIG_PADRAO"})


def dentro_tolerancia_percentual(
    praticado: Any,
    esperado: Any,
    tolerancia: Decimal = TOL_PERCENTUAL_PP,
) -> bool:
    """Compara percentuais dentro da tolerância em pontos percentuais."""
    return abs(_dec(praticado) - _dec(esperado)) <= tolerancia


def dentro_tolerancia_valor(praticado: Any, esperado: Any) -> bool:
    """Compara valores monetários com tolerância max(R$ 0,05, 0,1% do esperado)."""
    p = _dec(praticado)
    e = _dec(esperado)
    lim = max(TOL_VALOR_MIN, abs(e) * TOL_VALOR_PCT)
    return abs(p - e) <= lim


@dataclass(frozen=True)
class Divergencia:
    """Divergência identificada pela auditoria."""

    tipo_auditoria: str
    referencia_id: str
    numero_item: int | None
    campo_divergente: str
    valor_praticado: str
    valor_esperado_lei: str
    severidade: str  # DIVERGENTE | ATENCAO | SEM_REGRA
    mensagem_ajuste: str
    regra_aplicada_ref: str | None = None


def _persistir_divergencias(conn: sqlite3.Connection, divergencias: list[Divergencia]) -> None:
    if not divergencias:
        return
    with conn:
        for d in divergencias:
            conn.execute(
                """
                INSERT INTO auditoria_divergencias (
                    tipo_auditoria, referencia_id, numero_item, campo_divergente,
                    valor_praticado, valor_esperado_lei, severidade,
                    mensagem_ajuste, regra_aplicada_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    d.tipo_auditoria,
                    d.referencia_id,
                    d.numero_item,
                    d.campo_divergente,
                    d.valor_praticado,
                    d.valor_esperado_lei,
                    d.severidade,
                    d.mensagem_ajuste,
                    d.regra_aplicada_ref,
                ),
            )


def auditar_nfe_contra_lei(
    conn: sqlite3.Connection,
    chave_acesso: str,
    *,
    natureza_operacao: str = "VENDA",
    operacao_com_contribuinte: bool = True,
    persistir: bool = True,
) -> list[Divergencia]:
    """Executa a Frente A (13 etapas sequenciais) sobre os itens de uma NF-e."""
    doc = conn.execute(
        "SELECT * FROM vw_nfe_status WHERE chave_acesso = ?",
        (chave_acesso,),
    ).fetchone()
    if doc is None:
        return []

    # Passo 1: Filtro de Status (ignora canceladas e complementares finNFe=2)
    if doc["status_sefaz"] == "CANCELADA" or str(doc["finalidade"]) == "2":
        return []

    itens = conn.execute(
        "SELECT * FROM nfe_itens WHERE chave_acesso = ? ORDER BY numero_item",
        (chave_acesso,),
    ).fetchall()

    data_emissao = str(doc["data_emissao"])[:10]
    uf_orig = str(doc["uf_emitente"])
    uf_dest = str(doc["uf_destinatario"])
    divergencias: list[Divergencia] = []

    for item in itens:
        n_item = int(item["numero_item"])
        ncm = str(item["ncm"] or "").strip()
        cest = str(item["cest"] or "").strip()
        cfop = str(item["cfop"] or "").strip()
        origem_xml = str(item["origem_mercadoria"] or "0").strip()

        # Passo 5 (antecipado se comodato/demonstração): Short-circuit CFOP não conferível
        if cfop in CFOPS_NAO_CONFERIVEIS:
            divergencias.append(
                Divergencia(
                    tipo_auditoria="XML_NFE",
                    referencia_id=chave_acesso,
                    numero_item=n_item,
                    campo_divergente="cfop",
                    valor_praticado=cfop,
                    valor_esperado_lei="",
                    severidade="SEM_REGRA",
                    mensagem_ajuste=f"CFOP {cfop} (comodato/demonstração) não conferível automaticamente.",
                )
            )
            continue

        # Passo 2: Match de Regra Vigente
        regra_est = buscar_regra_estadual_icms(
            conn,
            uf_origem=uf_orig,
            uf_destino=uf_dest,
            ncm=ncm,
            cest=cest,
            natureza_operacao=natureza_operacao,
            operacao_com_contribuinte=operacao_com_contribuinte,
            origem_mercadoria=origem_xml,
            data_referencia=data_emissao,
        )
        if regra_est is None:
            divergencias.append(
                Divergencia(
                    tipo_auditoria="XML_NFE",
                    referencia_id=chave_acesso,
                    numero_item=n_item,
                    campo_divergente="regra_estadual",
                    valor_praticado=f"{uf_orig}->{uf_dest} NCM {ncm}",
                    valor_esperado_lei="Regra cadastrada",
                    severidade="SEM_REGRA",
                    mensagem_ajuste="Sem regra estadual vigente cadastrada para esta operação.",
                )
            )
            continue

        regra_fed = buscar_regra_federal(
            conn,
            ncm=ncm,
            cest=cest,
            data_referencia=data_emissao,
        )
        regra_terc = buscar_regra_terceiro(
            conn,
            uf_terceiro=uf_orig,
            ncm=ncm,
            cest=cest,
            origem_mercadoria=origem_xml,
            data_referencia=data_emissao,
        )
        ref_regra = f"regras_estaduais_icms:{regra_est['id']}"

        # Passo 3: NCM & TIPI
        if len(ncm) != 8 or not ncm.isdigit():
            divergencias.append(
                Divergencia(
                    tipo_auditoria="XML_NFE",
                    referencia_id=chave_acesso,
                    numero_item=n_item,
                    campo_divergente="ncm",
                    valor_praticado=ncm,
                    valor_esperado_lei="8 dígitos TIPI",
                    severidade="DIVERGENTE",
                    mensagem_ajuste="NCM ausente ou fora do padrão TIPI (8 dígitos).",
                    regra_aplicada_ref=ref_regra,
                )
            )

        # Passo 4: Origem & FCI (conversão fornecedor -> loja)
        origem_esperada_loja = CONVERSAO_ORIGEM_ENTRADA.get(origem_xml, origem_xml)
        if regra_terc and regra_terc.get("exige_fci") and not item["numero_fci"]:
            divergencias.append(
                Divergencia(
                    tipo_auditoria="XML_NFE",
                    referencia_id=chave_acesso,
                    numero_item=n_item,
                    campo_divergente="numero_fci",
                    valor_praticado="",
                    valor_esperado_lei=f"FCI obrigatório (origem {origem_esperada_loja})",
                    severidade="ATENCAO",
                    mensagem_ajuste="Operação exige número de FCI na NF-e para mercadoria importada.",
                    regra_aplicada_ref=ref_regra,
                )
            )

        # Passo 6: CEST
        if regra_est["tem_st"] and not cest:
            divergencias.append(
                Divergencia(
                    tipo_auditoria="XML_NFE",
                    referencia_id=chave_acesso,
                    numero_item=n_item,
                    campo_divergente="cest",
                    valor_praticado="",
                    valor_esperado_lei=str(regra_est.get("cest") or "CEST obrigatório"),
                    severidade="DIVERGENTE",
                    mensagem_ajuste="Produto sujeito a ICMS-ST sem CEST informado no XML.",
                    regra_aplicada_ref=ref_regra,
                )
            )

        # Executa cálculo puro dos 11 blocos
        calc = calcular_item(
            ItemCalculo(
                valor_produto=_dec(item["valor_produto"]),
                uf_origem=uf_orig,
                uf_destino=uf_dest,
                ncm=ncm,
                cest=cest,
                origem_mercadoria=origem_xml,
                operacao_com_contribuinte=operacao_com_contribuinte,
                valor_ipi=_dec(item["valor_ipi"]),
            ),
            regra_est,
            regra_fed,
            regra_terc,
        )

        # Passo 7: ICMS Próprio, Desoneração & Diferimento
        causa_raiz_icms = False
        if not dentro_tolerancia_percentual(item["aliq_icms"], calc.aliquota_icms, TOL_CARGA_ICMS_PP):
            causa_raiz_icms = True
            divergencias.append(
                Divergencia(
                    tipo_auditoria="XML_NFE",
                    referencia_id=chave_acesso,
                    numero_item=n_item,
                    campo_divergente="aliq_icms",
                    valor_praticado=str(item["aliq_icms"]),
                    valor_esperado_lei=str(calc.aliquota_icms),
                    severidade="DIVERGENTE",
                    mensagem_ajuste=f"Alíquota ICMS praticada ({item['aliq_icms']}%) diverge da lei ({calc.aliquota_icms}%).",
                    regra_aplicada_ref=ref_regra,
                )
            )
        if not dentro_tolerancia_valor(item["valor_icms"], calc.valor_icms_proprio):
            causa_raiz_icms = True
            divergencias.append(
                Divergencia(
                    tipo_auditoria="XML_NFE",
                    referencia_id=chave_acesso,
                    numero_item=n_item,
                    campo_divergente="valor_icms",
                    valor_praticado=str(item["valor_icms"]),
                    valor_esperado_lei=str(calc.valor_icms_proprio),
                    severidade="DIVERGENTE",
                    mensagem_ajuste=f"Valor ICMS próprio ({item['valor_icms']}) diverge do esperado ({calc.valor_icms_proprio}).",
                    regra_aplicada_ref=ref_regra,
                )
            )

        # Passo 8: Responsável pela ST
        causa_raiz_st = False
        if regra_est["tem_st"] and regra_est.get("icms_st_pago_em_guia") and _dec(item["valor_st"]) > Decimal("0"):
            causa_raiz_st = True
            divergencias.append(
                Divergencia(
                    tipo_auditoria="XML_NFE",
                    referencia_id=chave_acesso,
                    numero_item=n_item,
                    campo_divergente="recolhe_st",
                    valor_praticado="RETIDA_FORNECEDOR",
                    valor_esperado_lei="PAGO_EM_GUIA",
                    severidade="DIVERGENTE",
                    mensagem_ajuste="ST destacada na nota, mas a regra prevê recolhimento pela empresa em guia.",
                    regra_aplicada_ref=ref_regra,
                )
            )

        # Passo 9: CST/CSOSN e CFOP (com deduplicação de erros em cascata)
        if str(item["cst_icms"] or "") != calc.cst_esperado:
            msg_cst = (
                "Reflexo da divergência de ICMS/ST já apontada."
                if (causa_raiz_icms or causa_raiz_st)
                else f"CST/CSOSN praticado ({item['cst_icms']}) diverge do esperado ({calc.cst_esperado})."
            )
            divergencias.append(
                Divergencia(
                    tipo_auditoria="XML_NFE",
                    referencia_id=chave_acesso,
                    numero_item=n_item,
                    campo_divergente="cst_icms",
                    valor_praticado=str(item["cst_icms"]),
                    valor_esperado_lei=calc.cst_esperado,
                    severidade="DIVERGENTE",
                    mensagem_ajuste=msg_cst,
                    regra_aplicada_ref=ref_regra,
                )
            )
        if cfop != calc.cfop_esperado:
            msg_cfop = (
                "Reflexo da divergência de operação/ST já apontada."
                if (causa_raiz_icms or causa_raiz_st)
                else f"CFOP praticado ({cfop}) diverge do esperado ({calc.cfop_esperado})."
            )
            divergencias.append(
                Divergencia(
                    tipo_auditoria="XML_NFE",
                    referencia_id=chave_acesso,
                    numero_item=n_item,
                    campo_divergente="cfop",
                    valor_praticado=cfop,
                    valor_esperado_lei=calc.cfop_esperado,
                    severidade="DIVERGENTE",
                    mensagem_ajuste=msg_cfop,
                    regra_aplicada_ref=ref_regra,
                )
            )

        # Passo 10: Uso/Consumo com ST e Acordo (apenas DIFAL, sem MVA)
        if natureza_operacao == "USO_CONSUMO" and regra_est.get("tem_acordo_st") and _dec(item["mva_st"]) > Decimal("0"):
            divergencias.append(
                Divergencia(
                    tipo_auditoria="XML_NFE",
                    referencia_id=chave_acesso,
                    numero_item=n_item,
                    campo_divergente="mva_st",
                    valor_praticado=str(item["mva_st"]),
                    valor_esperado_lei="0.00",
                    severidade="ATENCAO",
                    mensagem_ajuste="Uso/consumo com acordo ST exige apenas DIFAL, sem aplicação de MVA.",
                    regra_aplicada_ref=ref_regra,
                )
            )

        # Passo 11: MVA, ST, FCP-ST e ICMS Efetivo
        if regra_est["tem_st"] and not regra_est.get("icms_st_pago_em_guia"):
            if not dentro_tolerancia_valor(item["valor_st"], calc.valor_icms_st):
                divergencias.append(
                    Divergencia(
                        tipo_auditoria="XML_NFE",
                        referencia_id=chave_acesso,
                        numero_item=n_item,
                        campo_divergente="valor_st",
                        valor_praticado=str(item["valor_st"]),
                        valor_esperado_lei=str(calc.valor_icms_st),
                        severidade="DIVERGENTE",
                        mensagem_ajuste=(
                            "Reflexo da divergência na base/alíquota."
                            if causa_raiz_icms
                            else f"ICMS-ST praticado ({item['valor_st']}) diverge do esperado ({calc.valor_icms_st})."
                        ),
                        regra_aplicada_ref=ref_regra,
                    )
                )

        # Passo 12: PIS / COFINS
        if regra_fed:
            if not dentro_tolerancia_percentual(item["aliq_pis"], regra_fed["aliquota_pis"]):
                divergencias.append(
                    Divergencia(
                        tipo_auditoria="XML_NFE",
                        referencia_id=chave_acesso,
                        numero_item=n_item,
                        campo_divergente="aliq_pis",
                        valor_praticado=str(item["aliq_pis"]),
                        valor_esperado_lei=str(regra_fed["aliquota_pis"]),
                        severidade="DIVERGENTE",
                        mensagem_ajuste=f"Alíquota PIS ({item['aliq_pis']}%) diverge da regra federal ({regra_fed['aliquota_pis']}%).",
                        regra_aplicada_ref=f"regras_federais:{regra_fed['id']}",
                    )
                )
            if not dentro_tolerancia_percentual(item["aliq_cofins"], regra_fed["aliquota_cofins"]):
                divergencias.append(
                    Divergencia(
                        tipo_auditoria="XML_NFE",
                        referencia_id=chave_acesso,
                        numero_item=n_item,
                        campo_divergente="aliq_cofins",
                        valor_praticado=str(item["aliq_cofins"]),
                        valor_esperado_lei=str(regra_fed["aliquota_cofins"]),
                        severidade="DIVERGENTE",
                        mensagem_ajuste=f"Alíquota COFINS ({item['aliq_cofins']}%) diverge da regra federal ({regra_fed['aliquota_cofins']}%).",
                        regra_aplicada_ref=f"regras_federais:{regra_fed['id']}",
                    )
                )

    if persistir:
        _persistir_divergencias(conn, divergencias)
    return divergencias


def _norm_flag(val: Any) -> str:
    if isinstance(val, bool):
        return "1" if val else "0"
    s = str(val if val is not None else "").strip().upper()
    if s in {"S", "SIM", "TRUE", "1"}:
        return "1"
    if s in {"N", "NAO", "NÃO", "FALSE", "0"}:
        return "0"
    return s


def auditar_config_erp(
    conn: sqlite3.Connection,
    *,
    lote_importacao: str | None = None,
    persistir: bool = True,
) -> list[Divergencia]:
    """Executa a Frente B sobre config_erp_importada auditando flags internas e placeholders."""
    sql = "SELECT * FROM config_erp_importada"
    params: tuple[Any, ...] = ()
    if lote_importacao:
        sql += " WHERE lote_importacao = ?"
        params = (lote_importacao,)

    linhas = conn.execute(sql, params).fetchall()
    divergencias: list[Divergencia] = []

    for row in linhas:
        ref_id = str(row["id"])
        payload: dict[str, Any] = json.loads(row["payload_json"])
        cod_prod = str(row["codigo_produto_erp"] or "").strip().upper()
        nome_cfg = str(payload.get("nome_configuracao") or payload.get("config_placeholder") or "").upper()

        if cod_prod in PLACEHOLDERS_ERP or any(p in nome_cfg for p in PLACEHOLDERS_ERP):
            divergencias.append(
                Divergencia(
                    tipo_auditoria="CONFIG_ERP",
                    referencia_id=ref_id,
                    numero_item=None,
                    campo_divergente="config_placeholder",
                    valor_praticado=cod_prod or nome_cfg,
                    valor_esperado_lei="Configuração fiscal específica",
                    severidade="DIVERGENTE",
                    mensagem_ajuste="Produto vinculado a configuração placeholder/genérica do ERP.",
                )
            )
            continue

        regra_est = buscar_regra_estadual_icms(
            conn,
            uf_origem=str(row["uf_origem"]),
            uf_destino=str(row["uf_destino"]),
            ncm=str(row["ncm"]),
            cest=str(row["cest"] or ""),
            natureza_operacao=str(row["natureza_operacao"]),
        )
        if regra_est is None:
            divergencias.append(
                Divergencia(
                    tipo_auditoria="CONFIG_ERP",
                    referencia_id=ref_id,
                    numero_item=None,
                    campo_divergente="regra_estadual",
                    valor_praticado=f"{row['uf_origem']}->{row['uf_destino']} NCM {row['ncm']}",
                    valor_esperado_lei="Regra vigente",
                    severidade="SEM_REGRA",
                    mensagem_ajuste="Sem regra legal cadastrada para auditar esta linha do ERP.",
                )
            )
            continue

        ref_regra = f"regras_estaduais_icms:{regra_est['id']}"
        mapeamento_flags = [
            ("deduz_icms_fcp_custo_medio", "deduz_icms_fcp_custo_medio", True),
            ("somar_st_fcp_custo_medio", "somar_icms_st_fcp_st_custo_medio", True),
            ("gera_credito_debito", "gera_credito_debito", True),
            ("escriturar_sem_tributacao", "escriturar_sem_tributacao_como", False),
            ("icms_st_pago_empresa_guia", "icms_st_pago_em_guia", True),
        ]

        for campo_erp, campo_lei, eh_booleano in mapeamento_flags:
            if campo_erp not in payload:
                continue
            val_erp = _norm_flag(payload[campo_erp]) if eh_booleano else str(payload[campo_erp] or "").strip().upper()
            val_lei = _norm_flag(regra_est.get(campo_lei)) if eh_booleano else str(regra_est.get(campo_lei) or "").strip().upper()
            if val_erp != val_lei:
                divergencias.append(
                    Divergencia(
                        tipo_auditoria="CONFIG_ERP",
                        referencia_id=ref_id,
                        numero_item=None,
                        campo_divergente=campo_erp,
                        valor_praticado=str(payload[campo_erp]),
                        valor_esperado_lei=str(regra_est.get(campo_lei)),
                        severidade="DIVERGENTE",
                        mensagem_ajuste=f"Flag ERP '{campo_erp}' ({payload[campo_erp]}) diverge da regra legal ({regra_est.get(campo_lei)}).",
                        regra_aplicada_ref=ref_regra,
                    )
                )

    if persistir:
        _persistir_divergencias(conn, divergencias)
    return divergencias
