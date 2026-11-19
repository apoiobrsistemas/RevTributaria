"""Orquestrador de Auditoria Preventiva de XMLs de Entrada em Lote & Guias (GNRE/DARE/DIFAL)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from src.engine.fiscal_engine import (
    ContextoOperacaoFiscal,
    avaliar_operacao_bidirecional,
    resolver_parametros_estaduais,
)
from src.engine.fiscal_math import ZERO, _dec, _r2
from src.engine.xml_reforma_validator import validar_xml_reforma_lc214

ORIGENS_IMPORTADAS = frozenset({"1", "2", "3", "8"})


def _inferir_finalidade(cfop_orig: str, finalidade_padrao: str) -> str:
    c = str(cfop_orig or "").strip()
    if c.endswith(("201", "202", "410", "411")):
        return "DEVOLUCAO"
    if c.endswith(("551", "406")):
        return "ATIVO_IMOBILIZADO"
    if c.endswith(("556", "407")):
        return "USO_CONSUMO"
    return finalidade_padrao


def auditar_lote_xml_entrada(
    notas: list[dict[str, Any]],
    *,
    conn: Any = None,
    finalidade_padrao: str = "COMERCIALIZACAO",
    finalidades_por_item: dict[tuple[str, int], str] | None = None,
) -> dict[str, Any]:
    """Audita lote de XMLs de entrada via avaliar_operacao_bidirecional(direcao='ENTRADA')."""
    itens_auditados: list[dict[str, Any]] = []
    glosas_credito: list[dict[str, Any]] = []
    guias_por_nota: list[dict[str, Any]] = []

    tot_antecipacao_st = ZERO
    tot_difal_fcp = ZERO
    tot_credito_legitimo = ZERO
    tot_credito_glosado = ZERO

    for nota in notas:
        chave = str(nota.get("chave_acesso") or "")
        n_nf = str(nota.get("nNF") or "")
        uf_o = str(nota.get("emit_uf") or "SP").upper()
        uf_d = str(nota.get("dest_uf") or uf_o).upper()
        data_op = str(nota.get("dhEmi") or date.today().isoformat())[:10]
        if len(data_op) != 10:
            data_op = date.today().isoformat()
        forn_sn = bool(nota.get("fornecedor_simples_nacional"))
        dest_cnpj = str(nota.get("dest_cnpj") or "")

        nota_st_recolher = ZERO
        nota_difal_recolher = ZERO
        nota_cred_leg = ZERO
        nota_cred_glosa = ZERO

        # Se algum item tem gIBSCBS, valida também o XML da Reforma (Fase 3)
        reforma_erros: list[str] = []
        if any(it.get("tem_gibscbs") for it in nota.get("itens", [])) and nota.get("xml_raw"):
            v_ref = validar_xml_reforma_lc214(str(nota["xml_raw"]))
            reforma_erros = list(v_ref.get("erros") or [])

        for it in nota.get("itens", []):
            n_item = int(it["nItem"])
            fin = (
                (finalidades_por_item or {}).get((chave, n_item))
                or _inferir_finalidade(str(it.get("CFOP") or ""), finalidade_padrao)
            )
            orig = str(it.get("orig") or "0")
            cst = str(it.get("cst_csosn") or "00")
            ncm = str(it.get("NCM") or "")
            cest = str(it.get("CEST") or "")

            params_est = (
                resolver_parametros_estaduais(
                    conn,
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    ncm=ncm,
                    cest=cest,
                    cst=cst,
                    direcao="ENTRADA",
                    data_operacao=data_op,
                )
                if conn is not None
                else {
                    "protocolo_encontrado": False,
                    "tem_protocolo_st": False,
                    "tem_st": False,
                    "mva_original": ZERO,
                    "aliquota_interna_destino": None,
                    "fcp_destino": None,
                    "pmpf_valor": ZERO,
                    "cbenef_validos_uf": [],
                    "ato_legal_st": "",
                }
            )

            v_st_xml = _dec(it.get("vICMSST"))
            v_fcp_st_xml = _dec(it.get("vFCPST"))
            st_destacada_xml = (v_st_xml > ZERO) or (cst in {"10", "30", "70", "201", "202", "203"})
            tem_st_item = bool(params_est["tem_st"]) or st_destacada_xml or (_dec(it.get("pMVAST")) > ZERO)
            mva_item = (
                _dec(params_est["mva_original"])
                if params_est["protocolo_encontrado"] and _dec(params_est["mva_original"]) > ZERO
                else _dec(it.get("pMVAST"))
            )

            ctx = ContextoOperacaoFiscal(
                direcao="ENTRADA",
                finalidade=fin,
                uf_origem=uf_o,
                uf_destino=uf_d,
                ncm=ncm,
                valor_produto=_dec(it.get("vProd")),
                quantidade=_dec(it.get("qCom") or "1"),
                valor_ipi=_dec(it.get("vIPI")),
                valor_frete=_dec(it.get("vFrete")),
                valor_despesas=_dec(it.get("vOutro")) + _dec(it.get("vSeg")),
                valor_desconto=_dec(it.get("vDesc")),
                origem_mercadoria=orig,
                operacao_com_contribuinte=(str(nota.get("dest_ind_ie_dest") or "1") != "9"),
                cst_ou_csosn=cst,
                cbenef=str(it.get("cBenef") or ""),
                cest=cest,
                aliquota_interna_destino=params_est["aliquota_interna_destino"] if params_est["protocolo_encontrado"] else None,
                aliquota_fcp=params_est["fcp_destino"] if params_est["protocolo_encontrado"] else None,
                reducao_bc_pct=_dec(it.get("pRedBC")),
                reducao_bc_st_pct=_dec(it.get("pRedBCST")),
                tem_st=tem_st_item,
                tem_protocolo_st=bool(params_est["tem_protocolo_st"]),
                st_retida_na_origem=(v_st_xml > ZERO),
                mva_original_pct=mva_item,
                pmpf_unitario=_dec(params_est.get("pmpf_valor")),
                fornecedor_simples_nacional=forn_sn,
            )
            res = avaliar_operacao_bidirecional(
                ctx,
                cbenef_validos=params_est.get("cbenef_validos_uf"),
                ato_legal_st=str(params_est.get("ato_legal_st") or ""),
            )

            alertas_item = list(res["alertas_preventivos"]) + reforma_erros
            risco = res["semaforo_risco"]

            # 1. Confronto de Alíquota Interestadual & Origem Importada (Res. Senado 13/2012)
            p_icms_xml = _dec(it.get("pICMS"))
            v_icms_xml = _dec(it.get("vICMS"))
            credito_motor = _dec(res["credito_admitido"])
            motivos_glosa: list[str] = []

            if uf_o != uf_d and orig in ORIGENS_IMPORTADAS and p_icms_xml > Decimal("4.00"):
                alertas_item.append(
                    f"GLOSA ORIGEM IMPORTADA (Res. Senado 13/2012): orig={orig} com alíquota {p_icms_xml}% > 4,00% no XML."
                )
                motivos_glosa.append(f"Alíquota interestadual {p_icms_xml}% acima do teto de 4% (orig={orig})")
                risco = "VERMELHO"

            # 2. Confronto ICMS-ST & Antecipação Tributária
            st_devido = _dec(res["valor_icms_st"]) + _dec(res["valor_fcp_st"])
            st_pago_xml = v_st_xml + v_fcp_st_xml
            st_a_recolher = max(ZERO, _r2(st_devido - st_pago_xml))
            if st_a_recolher > Decimal("0.02") and _dec(res["antecipacao_st_entrada"]) == ZERO:
                alertas_item.append(
                    f"COMPLEMENTO ST NA ENTRADA: XML destacou R$ {st_pago_xml}, devido R$ {st_devido} (diferença R$ {st_a_recolher})."
                )
                if risco == "VERDE":
                    risco = "AMARELO"
            elif _dec(res["antecipacao_st_entrada"]) > ZERO:
                st_a_recolher = _dec(res["antecipacao_st_entrada"])

            # 3. Apuração DIFAL Entrada + FCP
            difal_recolher = _r2(_dec(res["difal_valor"]) + _dec(res["fcp_difal"]))

            # 4. Crédito Admitido x Glosa Preventiva SPED
            credito_legitimo = min(v_icms_xml, credito_motor) if v_icms_xml > ZERO else credito_motor
            credito_glosado = max(ZERO, _r2(v_icms_xml - credito_legitimo))
            if credito_glosado > ZERO:
                if not motivos_glosa:
                    motivos_glosa.append(res["regra_credito_detalhe"])
                risco = "VERMELHO"
                glosas_credito.append(
                    {
                        "Chave NF-e": chave,
                        "NF-e": n_nf,
                        "Item": n_item,
                        "NCM": ncm,
                        "CST": cst,
                        "Orig": orig,
                        "ICMS XML (R$)": float(v_icms_xml),
                        "Crédito Legítimo (R$)": float(credito_legitimo),
                        "Crédito Glosado (R$)": float(credito_glosado),
                        "Motivo Glosa": " | ".join(motivos_glosa),
                    }
                )

            nota_st_recolher += st_a_recolher
            nota_difal_recolher += difal_recolher
            nota_cred_leg += credito_legitimo
            nota_cred_glosa += credito_glosado

            itens_auditados.append(
                {
                    "Semáforo": risco,
                    "Chave NF-e": chave,
                    "NF-e": n_nf,
                    "Emitente": f"{nota.get('emit_nome', '')} ({uf_o})",
                    "CNPJ Destinatário": dest_cnpj,
                    "Item": n_item,
                    "cProd": str(it.get("cProd") or ""),
                    "Descrição": str(it.get("xProd") or ""),
                    "NCM": ncm,
                    "CEST": cest,
                    "Orig": orig,
                    "CFOP XML": str(it.get("CFOP") or ""),
                    "CFOP Entrada Sugerido": res["cfop_esperado"],
                    "CST XML": cst,
                    "Finalidade": fin,
                    "Valor Item (R$)": float(_dec(it.get("vProd"))),
                    "ICMS XML (R$)": float(v_icms_xml),
                    "MVA Aplicada (%)": float(_dec(res["mva_aplicada_pct"])),
                    "Antecipação/Compl. ST (R$)": float(st_a_recolher),
                    "DIFAL + FCP (R$)": float(difal_recolher),
                    "Crédito Legítimo (R$)": float(credito_legitimo),
                    "Crédito Glosado (R$)": float(credito_glosado),
                    "Alertas": " | ".join(alertas_item) if alertas_item else "OK",
                }
            )

        tot_antecipacao_st += nota_st_recolher
        tot_difal_fcp += nota_difal_recolher
        tot_credito_legitimo += nota_cred_leg
        tot_credito_glosado += nota_cred_glosa

        guias_por_nota.append(
            {
                "Chave NF-e": chave,
                "NF-e": n_nf,
                "Rota": f"{uf_o} -> {uf_d}",
                "Fornecedor SN": "Sim" if forn_sn else "Não",
                "Antecipação ST (GNRE/DARE) R$": float(_r2(nota_st_recolher)),
                "DIFAL + FCP R$": float(_r2(nota_difal_recolher)),
                "Total Guias a Recolher R$": float(_r2(nota_st_recolher + nota_difal_recolher)),
                "Crédito Legítimo R$": float(_r2(nota_cred_leg)),
                "Crédito Glosado R$": float(_r2(nota_cred_glosa)),
            }
        )

    return {
        "total_notas": len(notas),
        "total_itens": len(itens_auditados),
        "antecipacao_st_total": float(_r2(tot_antecipacao_st)),
        "difal_fcp_total": float(_r2(tot_difal_fcp)),
        "credito_legitimo_total": float(_r2(tot_credito_legitimo)),
        "credito_glosado_total": float(_r2(tot_credito_glosado)),
        "guias_por_nota": guias_por_nota,
        "itens_auditados": itens_auditados,
        "glosas_credito": glosas_credito,
    }
