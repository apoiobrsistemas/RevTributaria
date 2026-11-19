"""Exportador Oficial de Configuração Tributária para Linx Microvix (71 colunas A-BS)."""

from __future__ import annotations

import io
import re
from decimal import Decimal
from typing import Any

import openpyxl

from src.engine.fiscal_engine import (
    ALIQUOTAS_INTERNAS_UF,
    ContextoOperacaoFiscal,
    avaliar_operacao_bidirecional,
    resolver_parametros_estaduais,
)
from src.integrations.microvix_conciliador import sanitizar_celula_planilha

SHEET_NAME_MICROVIX = "Configurações Tributárias"

COLUNAS_MICROVIX_71: tuple[str, ...] = (
    "ID Config",
    "Natureza de Operação",
    "UF da Operação",
    "Operação com Contribuinte (S/N)",
    "CFOP",
    "CST ICMS",
    "CSOSN",
    "Observação Padrão",
    "Alíquota ICMS",
    "Red. Base ICMS",
    "Gera Crédito/Débito (S/N)",
    "Escriturar Valores sem Tributação como",
    "Valor Tributável ICMS",
    "Deduz ICMS/FCP do custo médio (S/N)",
    "Base de cálculo ICMS Obtida pelo Lucro (S/N)",
    "Alíquota FCP",
    "Somar IPI Base DIFAL FCP (S/N)",
    "Considerar Redução de base do ICMS no cálculo do FCP (S/N)",
    "Alíquota interna da UF Destino (DIFAL)",
    "Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)",
    "Utiliza base de cálculo Dupla (DIFAL)",
    "Alíquota ICMS Desonerado",
    "Alíquota FCP Desonerado",
    "Motivo Desoneração",
    "Código Beneficio Fiscal",
    "Percentual Crédito Presumido",
    "Deduz ICMS Desonerado Total Nota (S/N)",
    "Alíquota Diferimento",
    "Percentual FCP Diferimento",
    "Observação Complementar Diferimento",
    "Alíquota ICMS ST",
    "Margem ST",
    "Redução ICMS ST",
    "Utiliza Base ICMS p/ Cálculo ST (S/N)",
    "ICMS ST pago pela empresa em guia (S/N)",
    "Não deduzir o ICMS do cálculo do ICMS ST (S/N)",
    "Utiliza cálculo ICMS ST através do regime de estimativa simplificado (S/N)",
    "Percentual de carga tributária média (%)",
    "Somar ICMS/ST FCP-ST no Custo Médio (S/N)",
    "Alíquota ICMS Efetivo",
    "Redução de Base ICMS Efetivo",
    "CST PIS",
    "Alíquota PIS",
    "CST COFINS",
    "Alíquota COFINS",
    "Operação de Receita (S/N)",
    "Código Tipo Base de Crédito PIS/COFINS",
    "Base de Cálculo PIS/COFINS Obtida p/ Lucro (S/N)",
    "CST IPI",
    "Código Enquadramento IPI",
    "IPI Gera Crédito/Débito (S/N)",
    "Escriturar Valores Sem Tributação Como",
    "CNAE",
    "Quem Pagará ISS",
    "Em que Município será Prestado",
    "Qual Município será Pago/Recolhido",
    "Identificador ISS Retido",
    "Natureza de Operação do Serviço Prestado",
    "CST PIS - Serviço",
    "Alíquota PIS - Serviço",
    "CST COFINS - Serviço",
    "Alíquota COFINS - Serviço",
    "Código Tipo Base de Crédito Serviço",
    "Código de Retenção CSRF",
    "Alíquota de PIS Retido",
    "Alíquota de COFINS Retido",
    "Alíquota de CSLL Retido",
    "Número da FCI",
    "Conteúdo Importação (%)",
    "Valor Parcela Importada Exterior (R$)",
    "Valor Total Saída Interestadual",
)

_COLUNAS_TEXTO = frozenset(
    {
        "ID Config",
        "Natureza de Operação",
        "UF da Operação",
        "Operação com Contribuinte (S/N)",
        "CFOP",
        "CST ICMS",
        "CSOSN",
        "Escriturar Valores sem Tributação como",
        "Código Beneficio Fiscal",
        "CST PIS",
        "CST COFINS",
        "Código Tipo Base de Crédito PIS/COFINS",
        "CST IPI",
        "Código Enquadramento IPI",
        "Escriturar Valores Sem Tributação Como",
    }
)

_COLUNAS_DECIMAL = frozenset(
    {
        "Alíquota ICMS",
        "Red. Base ICMS",
        "Valor Tributável ICMS",
        "Alíquota FCP",
        "Alíquota interna da UF Destino (DIFAL)",
        "Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)",
        "Alíquota ICMS Desonerado",
        "Alíquota FCP Desonerado",
        "Percentual Crédito Presumido",
        "Alíquota Diferimento",
        "Percentual FCP Diferimento",
        "Alíquota ICMS ST",
        "Margem ST",
        "Redução ICMS ST",
        "Percentual de carga tributária média (%)",
        "Alíquota ICMS Efetivo",
        "Redução de Base ICMS Efetivo",
        "Alíquota PIS",
        "Alíquota COFINS",
    }
)

_COLUNAS_SERVICO = frozenset(COLUNAS_MICROVIX_71[52:67])
_COLUNAS_BOOLEANAS = tuple(c for c in COLUNAS_MICROVIX_71 if c.endswith("(S/N)")) + (
    "Utiliza base de cálculo Dupla (DIFAL)",
    "Número da FCI",
    "Conteúdo Importação (%)",
    "Valor Parcela Importada Exterior (R$)",
    "Valor Total Saída Interestadual",
)

UFS_27_ORDENADAS = tuple(sorted(ALIQUOTAS_INTERNAS_UF.keys()))


def parsear_ids_config(texto: str) -> list[str]:
    """Extrai lista ordenada de IDs de configuração (ex.: '1,2,3' -> ['1', '2', '3'])."""
    itens = [re.sub(r"\D", "", x) for x in str(texto or "1").replace(";", ",").split(",")]
    limpos = [x for x in itens if x]
    return limpos or ["1"]


def _fmt_cst(origem: str, cst: str) -> str:
    o = (re.sub(r"\D", "", str(origem or "0")) or "0")[:1]
    c = re.sub(r"\D", "", str(cst or "00"))[-2:].zfill(2)
    return f"{o}.{c}"


def _fmt_csosn(origem: str, csosn: str) -> str:
    o = (re.sub(r"\D", "", str(origem or "0")) or "0")[:1]
    c = re.sub(r"\D", "", str(csosn or "102"))[-3:].zfill(3)
    return f"{o}.{c}"


def _pis_cofins_por_regime(regime: str, direcao: str, finalidade: str) -> tuple[str, float, str, float, str, str]:
    reg_u = regime.upper()
    if "SIMPLES" in reg_u or "MEI" in reg_u:
        cst_pc = "49" if direcao == "SAIDA" else "99"
        return cst_pc, 0.0, cst_pc, 0.0, "N", "01"
    if direcao == "ENTRADA":
        if finalidade in {"USO_CONSUMO"}:
            return "70", 0.0, "70", 0.0, "N", "01"
        if "PRESUMIDO" in reg_u:
            return "70", 0.0, "70", 0.0, "N", "01"
        return "50", 1.65, "50", 7.60, "N", "01"
    # SAIDA
    op_rec = "S" if finalidade == "COMERCIALIZACAO" else "N"
    if finalidade == "DEVOLUCAO":
        return "49", 0.0, "49", 0.0, "N", "01"
    if "PRESUMIDO" in reg_u:
        return "01", 0.65, "01", 3.00, op_rec, "01"
    return "01", 1.65, "01", 7.60, op_rec, "01"


def gerar_linhas_microvix(
    *,
    conn: Any = None,
    id_configs: list[str] | str = "1",
    natureza_operacao: str = "43",
    direcao: str = "SAIDA",
    finalidade: str = "COMERCIALIZACAO",
    uf_empresa: str = "SP",
    uf_parceiro: str = "SP",
    operacao_com_contribuinte: bool = True,
    ncm: str = "85071090",
    cest: str = "",
    origem_mercadoria: str = "0",
    cst_icms: str = "00",
    csosn: str = "102",
    regime_pis_cofins: str = "Lucro Real",
    observacao_padrao: int | None = None,
    modo_nacional_27_ufs: bool = False,
    fornecedor_simples_nacional: bool = False,
    data_operacao: str | None = None,
) -> list[dict[str, Any]]:
    """Gera linhas determinísticas no layout de 71 colunas a partir do motor fiscal central."""
    ids_lista = parsear_ids_config(id_configs) if isinstance(id_configs, str) else [str(x) for x in id_configs]
    nat_str = str(re.sub(r"\D", "", str(natureza_operacao or "1")) or "1")
    dir_u = direcao.strip().upper()
    fin_u = finalidade.strip().upper()
    uf_emp = uf_empresa.strip().upper()[:2]
    orig_dig = (re.sub(r"\D", "", str(origem_mercadoria or "0")) or "0")[:1]

    pares_uf_contrib: list[tuple[str, bool]] = []
    if modo_nacional_27_ufs:
        for uf_item in UFS_27_ORDENADAS:
            pares_uf_contrib.append((uf_item, False))
            pares_uf_contrib.append((uf_item, True))
    else:
        pares_uf_contrib.append((uf_parceiro.strip().upper()[:2], bool(operacao_com_contribuinte)))

    linhas: list[dict[str, Any]] = []
    for id_cfg in ids_lista:
        for uf_op_alvo, contrib in pares_uf_contrib:
            # Regra oficial Linx: SAÍDA -> UF_Destino=parceiro; ENTRADA -> UF_Origem=parceiro
            uf_o = uf_emp if dir_u == "SAIDA" else uf_op_alvo
            uf_d = uf_op_alvo if dir_u == "SAIDA" else uf_emp
            uf_da_operacao = uf_d if dir_u == "SAIDA" else uf_o

            params = (
                resolver_parametros_estaduais(
                    conn,
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    ncm=ncm,
                    cest=cest,
                    cst=cst_icms,
                    direcao=dir_u,
                    data_operacao=data_operacao,
                )
                if conn is not None
                else {
                    "protocolo_encontrado": False,
                    "tem_protocolo_st": False,
                    "tem_st": False,
                    "mva_original": Decimal("0"),
                    "aliquota_interna_destino": None,
                    "fcp_destino": None,
                    "pmpf_valor": Decimal("0"),
                    "cbenef_validos_uf": [],
                    "cbenef_sugerido": "",
                    "ato_legal_st": "",
                }
            )

            cst_2 = cst_icms.strip().zfill(2)[-2:]
            cbenef_uso = str(params.get("cbenef_sugerido") or "") if cst_2 in {"20", "30", "40", "41", "50", "51", "70"} else ""
            tem_st_item = bool(params["tem_st"]) or cst_2 in {"10", "30", "70"}

            res = avaliar_operacao_bidirecional(
                ContextoOperacaoFiscal(
                    direcao=dir_u,
                    finalidade=fin_u,
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    ncm=ncm,
                    valor_produto=Decimal("1000.00"),
                    origem_mercadoria=orig_dig,
                    operacao_com_contribuinte=contrib,
                    cst_ou_csosn=cst_2,
                    cbenef=cbenef_uso,
                    cest=cest,
                    aliquota_interna_destino=params["aliquota_interna_destino"] if params["protocolo_encontrado"] else None,
                    aliquota_fcp=params["fcp_destino"] if params["protocolo_encontrado"] else None,
                    tem_st=tem_st_item,
                    tem_protocolo_st=bool(params["tem_protocolo_st"]),
                    mva_original_pct=params["mva_original"] if params["protocolo_encontrado"] else Decimal("0"),
                    fornecedor_simples_nacional=fornecedor_simples_nacional,
                ),
                cbenef_validos=params.get("cbenef_validos_uf"),
                ato_legal_st=str(params.get("ato_legal_st") or ""),
            )

            aliq_intra_d, fcp_d = ALIQUOTAS_INTERNAS_UF.get(uf_d, (Decimal("18.00"), Decimal("0.00")))
            aliq_fcp = float(params["fcp_destino"]) if params.get("fcp_destino") is not None else float(fcp_d)
            aliq_dest_difal = float(params["aliquota_interna_destino"]) if params.get("aliquota_interna_destino") is not None else float(aliq_intra_d)
            aliq_icms_val = float(res["aliquota_icms_proprio"]) if cst_2 not in {"30", "40", "41", "50", "51", "60"} else 0.0

            interestadual = uf_o != uf_d
            sujeito_difal = (dir_u == "SAIDA" and interestadual and not contrib) or (
                dir_u == "ENTRADA" and interestadual and fin_u in {"USO_CONSUMO", "ATIVO_IMOBILIZADO"}
            )
            bc_dupla = "S" if (dir_u == "ENTRADA" and interestadual and contrib and fin_u in {"USO_CONSUMO", "ATIVO_IMOBILIZADO"}) else "N"

            gera_cred_deb = "N" if cst_2 in {"30", "40", "41", "50", "51", "60"} else "S"
            escriturar_sem_trib = "2" if cst_2 in {"20", "30", "40", "41"} else "3"
            deduz_custo = "S" if (dir_u == "ENTRADA" and Decimal(res["credito_admitido"]) > Decimal("0")) else "N"

            mva_st_val = float(res["mva_aplicada_pct"])
            aliq_st_val = aliq_dest_difal if tem_st_item else 0.0
            st_em_guia = "S" if (Decimal(res["antecipacao_st_entrada"]) > Decimal("0") or (dir_u == "SAIDA" and tem_st_item and interestadual and not params["tem_protocolo_st"])) else "N"
            somar_st_custo = "S" if (dir_u == "ENTRADA" and cst_2 in {"10", "60", "70"}) else "N"
            aliq_efetivo = aliq_dest_difal if cst_2 == "60" else 0.0

            cst_pis, aliq_pis, cst_cof, aliq_cof, op_rec, cod_cred_pc = _pis_cofins_por_regime(
                regime_pis_cofins, dir_u, fin_u
            )
            if dir_u == "ENTRADA":
                cst_ipi, enq_ipi = ("49", "126") if fin_u != "COMERCIALIZACAO" else ("49", "999")
            else:
                cst_ipi, enq_ipi = ("99", "126") if fin_u == "DEVOLUCAO" else ("53", "999")

            exige_fci = "S" if (interestadual and orig_dig in {"3", "5", "8"}) else "N"

            row: dict[str, Any] = {
                "ID Config": str(id_cfg),
                "Natureza de Operação": nat_str,
                "UF da Operação": uf_da_operacao,
                "Operação com Contribuinte (S/N)": "S" if contrib else "N",
                "CFOP": str(res["cfop_esperado"]),
                "CST ICMS": _fmt_cst(orig_dig, cst_2),
                "CSOSN": _fmt_csosn(orig_dig, csosn),
                "Observação Padrão": int(observacao_padrao) if observacao_padrao else None,
                "Alíquota ICMS": round(aliq_icms_val, 2),
                "Red. Base ICMS": 0.00,
                "Gera Crédito/Débito (S/N)": gera_cred_deb,
                "Escriturar Valores sem Tributação como": escriturar_sem_trib,
                "Valor Tributável ICMS": round(aliq_icms_val, 2),
                "Deduz ICMS/FCP do custo médio (S/N)": deduz_custo,
                "Base de cálculo ICMS Obtida pelo Lucro (S/N)": "N",
                "Alíquota FCP": round(aliq_fcp, 2),
                "Somar IPI Base DIFAL FCP (S/N)": "S" if sujeito_difal else "N",
                "Considerar Redução de base do ICMS no cálculo do FCP (S/N)": "N",
                "Alíquota interna da UF Destino (DIFAL)": round(aliq_dest_difal, 2),
                "Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)": round(float(res["aliquota_icms_proprio"]), 2),
                "Utiliza base de cálculo Dupla (DIFAL)": bc_dupla,
                "Alíquota ICMS Desonerado": 0.00,
                "Alíquota FCP Desonerado": 0.00,
                "Motivo Desoneração": None,
                "Código Beneficio Fiscal": cbenef_uso or None,
                "Percentual Crédito Presumido": 0.00,
                "Deduz ICMS Desonerado Total Nota (S/N)": "N",
                "Alíquota Diferimento": 100.00 if cst_2 == "51" else 0.00,
                "Percentual FCP Diferimento": 0.00,
                "Observação Complementar Diferimento": "Diferimento conforme RICMS" if cst_2 == "51" else None,
                "Alíquota ICMS ST": round(aliq_st_val, 2),
                "Margem ST": round(mva_st_val, 2),
                "Redução ICMS ST": 0.00,
                "Utiliza Base ICMS p/ Cálculo ST (S/N)": "S" if cst_2 == "70" else "N",
                "ICMS ST pago pela empresa em guia (S/N)": st_em_guia,
                "Não deduzir o ICMS do cálculo do ICMS ST (S/N)": "N" if tem_st_item else "S",
                "Utiliza cálculo ICMS ST através do regime de estimativa simplificado (S/N)": "S" if uf_d == "MT" and tem_st_item else "N",
                "Percentual de carga tributária média (%)": 0.00,
                "Somar ICMS/ST FCP-ST no Custo Médio (S/N)": somar_st_custo,
                "Alíquota ICMS Efetivo": round(aliq_efetivo, 2),
                "Redução de Base ICMS Efetivo": 0.00,
                "CST PIS": cst_pis,
                "Alíquota PIS": round(aliq_pis, 2),
                "CST COFINS": cst_cof,
                "Alíquota COFINS": round(aliq_cof, 2),
                "Operação de Receita (S/N)": op_rec,
                "Código Tipo Base de Crédito PIS/COFINS": cod_cred_pc,
                "Base de Cálculo PIS/COFINS Obtida p/ Lucro (S/N)": "N",
                "CST IPI": cst_ipi,
                "Código Enquadramento IPI": enq_ipi,
                "IPI Gera Crédito/Débito (S/N)": "S" if cst_ipi in {"00", "50"} else "N",
                "Escriturar Valores Sem Tributação Como": escriturar_sem_trib,
                # Bloco Serviço e CSRF (BA-BO): vazio para mercadorias
                **{col_srv: None for col_srv in COLUNAS_MICROVIX_71[52:67]},
                # Bloco FCI (BP-BS)
                "Número da FCI": exige_fci,
                "Conteúdo Importação (%)": exige_fci,
                "Valor Parcela Importada Exterior (R$)": exige_fci,
                "Valor Total Saída Interestadual": exige_fci,
            }
            linhas.append(row)

    return linhas


def validar_planilha_microvix(
    linhas_ou_xlsx: list[dict[str, Any]] | bytes,
) -> dict[str, Any]:
    """Audita a planilha Microvix antes do download (71 colunas, aba, formatos e obrigatórios)."""
    erros: list[str] = []
    rows: list[dict[str, Any]] = []

    if isinstance(linhas_ou_xlsx, (bytes, bytearray)):
        wb = openpyxl.load_workbook(io.BytesIO(bytes(linhas_ou_xlsx)), data_only=False)
        if SHEET_NAME_MICROVIX not in wb.sheetnames:
            erros.append(f"Aba obrigatória '{SHEET_NAME_MICROVIX}' ausente (encontradas: {wb.sheetnames}).")
            return {"valido": False, "total_linhas": 0, "erros": erros}
        ws = wb[SHEET_NAME_MICROVIX]
        it = ws.iter_rows(values_only=True)
        headers = [str(h or "") for h in next(it, ())]
        if tuple(headers) != COLUNAS_MICROVIX_71:
            erros.append("Cabeçalhos das 71 colunas divergem do layout oficial Linx Microvix.")
        for r in it:
            if not any(v is not None and str(v).strip() != "" for v in r):
                continue
            rows.append({COLUNAS_MICROVIX_71[i]: (r[i] if i < len(r) else None) for i in range(len(COLUNAS_MICROVIX_71))})
    else:
        rows = list(linhas_ou_xlsx)
        if rows and tuple(rows[0].keys()) != COLUNAS_MICROVIX_71:
            erros.append("Ordem ou nomes das 71 colunas divergem do layout oficial Linx Microvix.")

    if not rows:
        erros.append("Planilha sem linhas de dados para exportação.")

    obrigatorios = (
        "ID Config",
        "Natureza de Operação",
        "UF da Operação",
        "Operação com Contribuinte (S/N)",
        "CST ICMS",
    )
    for idx, r in enumerate(rows, start=1):
        for col in obrigatorios:
            val = r.get(col)
            if val is None or str(val).strip() == "":
                erros.append(f"Linha {idx}: campo obrigatório '{col}' vazio.")
        cst = str(r.get("CST ICMS") or "")
        if not re.match(r"^\d\.\d{2}$", cst):
            erros.append(f"Linha {idx}: CST ICMS '{cst}' fora do padrão 0.XX.")
        csosn = str(r.get("CSOSN") or "")
        if not re.match(r"^\d\.\d{3}$", csosn):
            erros.append(f"Linha {idx}: CSOSN '{csosn}' fora do padrão 0.XXX.")
        cfop = str(r.get("CFOP") or "")
        if not re.match(r"^\d{4}$", cfop):
            erros.append(f"Linha {idx}: CFOP '{cfop}' deve ter 4 dígitos sem ponto.")
        for col_b in _COLUNAS_BOOLEANAS:
            bval = str(r.get(col_b) or "")
            if not re.match(r"^[SN]$", bval):
                erros.append(f"Linha {idx}: booleano '{col_b}' = '{bval}' deve ser 'S' ou 'N'.")
        for col_s in _COLUNAS_SERVICO:
            if r.get(col_s) not in (None, ""):
                erros.append(f"Linha {idx}: coluna de serviço '{col_s}' deve ficar vazia para mercadoria.")
        if len(erros) >= 20:
            break

    return {"valido": len(erros) == 0, "total_linhas": len(rows), "erros": erros}


def exportar_microvix_xlsx(linhas: list[dict[str, Any]]) -> bytes:
    """Gera o arquivo Importacao_ConfigTributaria_Microvix.xlsx com formatação @ e 0.00."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET_NAME_MICROVIX
    ws.append(list(COLUNAS_MICROVIX_71))

    for row in linhas:
        valores = [sanitizar_celula_planilha(row.get(col)) for col in COLUNAS_MICROVIX_71]
        ws.append(valores)
        row_idx = ws.max_row
        for col_idx, col_name in enumerate(COLUNAS_MICROVIX_71, start=1):
            cell = ws.cell(row=row_idx, column=col_idx)
            if col_name in _COLUNAS_TEXTO:
                cell.number_format = "@"
            elif col_name in _COLUNAS_DECIMAL and cell.value is not None:
                cell.number_format = "0.00"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


COLUNAS_MATRIZ_NCM_69: tuple[str, ...] = (
    "Regime Tributário",
    "NCM",
    "Rota",
    "UF Origem",
    "Natureza de Operação",
    "UF da Operação",
    "Operação com Contribuinte (S/N)",
    "CFOP",
    "CST ICMS",
    "CSOSN",
    "Observação Padrão",
    "Alíquota ICMS",
    "Red. Base ICMS",
    "Gera Crédito/Débito (S/N)",
    "Escriturar Valores sem Tributação como",
    "Valor Tributável ICMS",
    "Deduz ICMS/FCP do custo médio (S/N)",
    "Base de cálculo ICMS Obtida pelo Lucro (S/N)",
    "Alíquota FCP",
    "Somar IPI Base DIFAL FCP (S/N)",
    "Considerar Redução de base do ICMS no cálculo do FCP (S/N)",
    "Alíquota interna da UF Destino (DIFAL)",
    "Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)",
    "Utiliza base de cálculo Dupla (DIFAL)",
    "Alíquota ICMS Desonerado",
    "Alíquota FCP Desonerado",
    "Motivo Desoneração",
    "Código Beneficio Fiscal",
    "Percentual Crédito Presumido",
    "Deduz ICMS Desonerado Total Nota (S/N)",
    "Alíquota Diferimento",
    "Percentual FCP Diferimento",
    "Observação Complementar Diferimento",
    "Alíquota ICMS ST",
    "Margem ST",
    "Redução ICMS ST",
    "Utiliza Base ICMS p/ Cálculo ST (S/N)",
    "ICMS ST pago pela empresa em guia (S/N)",
    "Não deduzir o ICMS do cálculo do ICMS ST (S/N)",
    "Utiliza cálculo ICMS ST através do regime de estimativa simplificado (S/N)",
    "Percentual de carga tributária média (%)",
    "Somar ICMS/ST FCP-ST no Custo Médio (S/N)",
    "Alíquota ICMS Efetivo",
    "Redução de Base ICMS Efetivo",
    "CST PIS",
    "Alíquota PIS",
    "CST COFINS",
    "Alíquota COFINS",
    "Operação de Receita (S/N)",
    "Código Tipo Base de Crédito PIS/COFINS",
    "Base de Cálculo PIS/COFINS Obtida p/ Lucro (S/N)",
    "CST IPI",
    "Código Enquadramento IPI",
    "IPI Gera Crédito/Débito (S/N)",
    "Escriturar Valores Sem Tributação Como (base 2 ou base 3)",
    "CEST",
    "Origem",
    "Regime ICMS",
    "CRT",
    "Perfil (NC/CO)",
    "ICMS Crédito/Débito",
    "PIS/COFINS Crédito/Débito",
    "% MVA ST Ajustada",
    "DIFAL / FCP",
    "IPI Alíq.",
    "cClass",
    "Alíquota CBS",
    "Alíquota IBS",
    "Observações",
)

_MATRIZ_69_TEXTO = frozenset(
    {
        "Regime Tributário",
        "NCM",
        "Rota",
        "UF Origem",
        "Natureza de Operação",
        "UF da Operação",
        "Operação com Contribuinte (S/N)",
        "CFOP",
        "CST ICMS",
        "CSOSN",
        "Escriturar Valores sem Tributação como",
        "Código Beneficio Fiscal",
        "CST PIS",
        "CST COFINS",
        "Código Tipo Base de Crédito PIS/COFINS",
        "CST IPI",
        "Código Enquadramento IPI",
        "Escriturar Valores Sem Tributação Como (base 2 ou base 3)",
        "CEST",
        "CRT",
        "Perfil (NC/CO)",
        "cClass",
    }
)

_MATRIZ_69_DECIMAL = frozenset(
    {
        "Alíquota ICMS",
        "Red. Base ICMS",
        "Valor Tributável ICMS",
        "Alíquota FCP",
        "Alíquota interna da UF Destino (DIFAL)",
        "Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)",
        "Alíquota ICMS Desonerado",
        "Alíquota FCP Desonerado",
        "Percentual Crédito Presumido",
        "Alíquota Diferimento",
        "Percentual FCP Diferimento",
        "Alíquota ICMS ST",
        "Margem ST",
        "Redução ICMS ST",
        "Percentual de carga tributária média (%)",
        "Alíquota ICMS Efetivo",
        "Redução de Base ICMS Efetivo",
        "Alíquota PIS",
        "Alíquota COFINS",
        "% MVA ST Ajustada",
        "IPI Alíq.",
        "Alíquota CBS",
        "Alíquota IBS",
    }
)

_MATRIZ_69_BOOLEANAS = tuple(c for c in COLUNAS_MATRIZ_NCM_69 if c.endswith("(S/N)")) + (
    "Utiliza base de cálculo Dupla (DIFAL)",
)


def _norm_sn_69(val: Any, default: str = "N") -> str:
    s = str(val or "").strip().upper()
    if s in {"S", "SIM", "1", "TRUE"}:
        return "S"
    if s in {"N", "NAO", "NÃO", "0", "FALSE"}:
        return "N"
    return default


def _norm_float_69(val: Any) -> float:
    if val is None or str(val).strip() == "":
        return 0.0
    if isinstance(val, (int, float, Decimal)):
        return round(float(val), 2)
    s = str(val).strip().replace("%", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return 0.0


def normalizar_linhas_matriz_69(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normaliza as linhas da Consulta Matriz por NCM para todas as 69 colunas com tipos Linx."""
    saida: list[dict[str, Any]] = []
    for raw in linhas:
        row: dict[str, Any] = {}
        for col in COLUNAS_MATRIZ_NCM_69:
            val = raw.get(col)
            if col in _MATRIZ_69_BOOLEANAS:
                row[col] = _norm_sn_69(val, "N")
            elif col in _MATRIZ_69_DECIMAL:
                row[col] = _norm_float_69(val)
            elif col in {"Escriturar Valores sem Tributação como", "Escriturar Valores Sem Tributação Como (base 2 ou base 3)"}:
                dig = re.sub(r"\D", "", str(val or ""))
                row[col] = dig[:1] if dig in {"1", "2", "3"} else "3"
            elif col == "CST ICMS":
                s = str(val or "").strip()
                row[col] = s if re.match(r"^\d\.\d{2}$", s) else _fmt_cst("0", s)
            elif col == "CSOSN":
                s = str(val or "").strip()
                row[col] = s if re.match(r"^\d\.\d{3}$", s) else _fmt_csosn("0", s)
            else:
                row[col] = "" if val is None else str(val)
        saida.append(row)
    return saida


def validar_matriz_ncm_69(linhas_ou_xlsx: list[dict[str, Any]] | bytes) -> dict[str, Any]:
    """Valida as 69 colunas solicitadas da Consulta Matriz por NCM antes do download."""
    erros: list[str] = []
    rows: list[dict[str, Any]] = []

    if isinstance(linhas_ou_xlsx, (bytes, bytearray)):
        wb = openpyxl.load_workbook(io.BytesIO(bytes(linhas_ou_xlsx)), data_only=False)
        if SHEET_NAME_MICROVIX not in wb.sheetnames:
            return {"valido": False, "total_linhas": 0, "erros": [f"Aba '{SHEET_NAME_MICROVIX}' ausente."]}
        ws = wb[SHEET_NAME_MICROVIX]
        it = ws.iter_rows(values_only=True)
        headers = [str(h or "") for h in next(it, ())]
        if tuple(headers) != COLUNAS_MATRIZ_NCM_69:
            erros.append("Cabeçalhos divergem das 69 colunas da Matriz NCM.")
        for r in it:
            if not any(v is not None and str(v).strip() != "" for v in r):
                continue
            rows.append({COLUNAS_MATRIZ_NCM_69[i]: (r[i] if i < len(r) else None) for i in range(len(COLUNAS_MATRIZ_NCM_69))})
    else:
        rows = normalizar_linhas_matriz_69(linhas_ou_xlsx)

    if not rows:
        erros.append("Sem linhas na Matriz NCM para exportação.")

    for idx, r in enumerate(rows, start=1):
        for col in ("Regime Tributário", "NCM", "Natureza de Operação", "UF Origem", "UF da Operação", "CFOP", "CST ICMS"):
            if str(r.get(col) or "").strip() == "":
                erros.append(f"Linha {idx}: campo obrigatório '{col}' vazio.")
        for col_b in _MATRIZ_69_BOOLEANAS:
            if str(r.get(col_b) or "") not in {"S", "N"}:
                erros.append(f"Linha {idx}: booleano '{col_b}' deve ser 'S' ou 'N'.")
        if len(erros) >= 20:
            break

    return {"valido": len(erros) == 0, "total_linhas": len(rows), "erros": erros}


def exportar_matriz_ncm_69_xlsx(linhas: list[dict[str, Any]]) -> bytes:
    """Exporta todas as 69 colunas da Consulta Matriz por NCM para .xlsx com formatação Linx."""
    norm = normalizar_linhas_matriz_69(linhas)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET_NAME_MICROVIX
    ws.append(list(COLUNAS_MATRIZ_NCM_69))

    for row in norm:
        valores = [sanitizar_celula_planilha(row.get(col)) for col in COLUNAS_MATRIZ_NCM_69]
        ws.append(valores)
        row_idx = ws.max_row
        for col_idx, col_name in enumerate(COLUNAS_MATRIZ_NCM_69, start=1):
            cell = ws.cell(row=row_idx, column=col_idx)
            if col_name in _MATRIZ_69_TEXTO:
                cell.number_format = "@"
            elif col_name in _MATRIZ_69_DECIMAL and cell.value is not None:
                cell.number_format = "0.00"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def exportar_matriz_ncm_69_csv(linhas: list[dict[str, Any]]) -> bytes:
    """Exporta todas as 69 colunas da Consulta Matriz por NCM para .csv (UTF-8 BOM, ';')."""
    import csv

    norm = normalizar_linhas_matriz_69(linhas)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(COLUNAS_MATRIZ_NCM_69), delimiter=";", extrasaction="ignore")
    writer.writeheader()
    for row in norm:
        writer.writerow({c: sanitizar_celula_planilha(row.get(c)) for c in COLUNAS_MATRIZ_NCM_69})
    return ("\ufeff" + buf.getvalue()).encode("utf-8")
