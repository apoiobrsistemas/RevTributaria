"""Exportador oficial no Layout Padrão de Importação Config. Tributária Linx (71 colunas)."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import defaultdict
from typing import Any

import openpyxl
from openpyxl.cell import WriteOnlyCell

from src.integrations.microvix_conciliador import sanitizar_celula_planilha

COLUNAS_LAYOUT_LINX_TERCEIRO: tuple[str, ...] = (
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


def _sn(valor: Any, default: str = "N") -> str:
    s = str(valor or "").strip().upper()
    if s in {"S", "SIM", "1", "TRUE"}:
        return "S"
    if s in {"N", "NAO", "NÃO", "0", "FALSE"}:
        return "N"
    return default


def _num(valor: Any, default: str = "0") -> str:
    if valor is None or str(valor).strip() == "":
        return default
    s = str(valor).strip().replace("%", "").replace(",", ".")
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return f"{f:.2f}".rstrip("0").rstrip(".")
    except ValueError:
        return default


def _formatar_cst_pontuado(valor: Any, *, origem: str = "0", is_csosn: bool = False) -> str:
    s = str(valor or "").strip()
    if "." in s:
        partes = s.split(".", 1)
        orig_p = re.sub(r"\D", "", partes[0]) or origem or "0"
        cod_p = re.sub(r"\D", "", partes[1])
        return f"{orig_p}.{cod_p.zfill(3 if is_csosn else 2)}"
    dig = re.sub(r"\D", "", s)
    if not dig:
        return f"{origem}.102" if is_csosn else f"{origem}.00"
    if is_csosn:
        if len(dig) == 4:
            return f"{dig[0]}.{dig[1:]}"
        return f"{origem}.{dig.zfill(3)[-3:]}"
    if len(dig) == 3:
        return f"{dig[0]}.{dig[1:]}"
    return f"{origem}.{dig.zfill(2)[-2:]}"


def converter_linhas_para_layout_linx_terceiro(
    linhas: list[dict[str, Any]],
    *,
    id_config_inicial: int = 1,
    ids_natureza: dict[str, int] | None = None,
    usar_ncm_no_id_config: bool = True,
) -> list[dict[str, Any]]:
    """Converte linhas da Consulta Matriz por NCM para o layout exato de 71 colunas da Linx."""
    saida: list[dict[str, Any]] = []
    mapa_nat = ids_natureza or {}
    fallback_nat_idx: dict[str, int] = {}

    for idx, linha in enumerate(linhas):
        nat_nome = str(linha.get("Natureza de Operação") or "").strip()
        id_nat_val = linha.get("ID Natureza")
        if id_nat_val in (None, "", 0):
            id_nat_val = mapa_nat.get(nat_nome, 0)
        if not id_nat_val or int(id_nat_val) == 0:
            if nat_nome not in fallback_nat_idx:
                fallback_nat_idx[nat_nome] = len(fallback_nat_idx) + 1
            id_nat_val = fallback_nat_idx[nat_nome]

        cfop_limpo = re.sub(r"\D", "", str(linha.get("CFOP") or ""))
        orig_txt = str(linha.get("Origem") or "0").strip()
        orig_dig = "1" if orig_txt.lower().startswith("import") else (re.sub(r"\D", "", orig_txt) or "0")[:1]

        cst_fmt = _formatar_cst_pontuado(linha.get("CST ICMS") or "00", origem=orig_dig, is_csosn=False)
        csosn_fmt = _formatar_cst_pontuado(linha.get("CSOSN") or "102", origem=orig_dig, is_csosn=True)

        uf_op = str(linha.get("UF da Operação") or "SP").strip().upper()[:2]
        contrib = _sn(linha.get("Operação com Contribuinte (S/N)"), "S")
        gera_cred = _sn(linha.get("Gera Crédito/Débito (S/N)"), "S")
        escriturar = re.sub(r"\D", "", str(linha.get("Escriturar Valores sem Tributação como") or "3")) or "3"
        op_receita = _sn(linha.get("Operação de Receita (S/N)"), "S" if "Venda" in nat_nome else "N")

        ncm_tela = str(linha.get("NCM") or "").strip()
        id_cfg_val: str | int = ncm_tela if (usar_ncm_no_id_config and ncm_tela) else (int(id_config_inicial) + idx)

        registro: dict[str, Any] = {
            "ID Config": id_cfg_val,
            "Natureza de Operação": int(id_nat_val),
            "UF da Operação": uf_op,
            "Operação com Contribuinte (S/N)": contrib,
            "CFOP": cfop_limpo,
            "CST ICMS": cst_fmt,
            "CSOSN": csosn_fmt,
            "Observação Padrão": re.sub(r"\D", "", str(linha.get("Observação Padrão") or "")),
            "Alíquota ICMS": _num(linha.get("Alíquota ICMS"), "18"),
            "Red. Base ICMS": _num(linha.get("Red. Base ICMS"), "0"),
            "Gera Crédito/Débito (S/N)": gera_cred,
            "Escriturar Valores sem Tributação como": escriturar,
            "Valor Tributável ICMS": _num(linha.get("Valor Tributável ICMS"), "0"),
            "Deduz ICMS/FCP do custo médio (S/N)": _sn(linha.get("Deduz ICMS/FCP do custo médio (S/N)"), "N"),
            "Base de cálculo ICMS Obtida pelo Lucro (S/N)": _sn(linha.get("Base de cálculo ICMS Obtida pelo Lucro (S/N)"), "N"),
            "Alíquota FCP": _num(linha.get("Alíquota FCP"), "0"),
            "Somar IPI Base DIFAL FCP (S/N)": _sn(linha.get("Somar IPI Base DIFAL FCP (S/N)"), "N"),
            "Considerar Redução de base do ICMS no cálculo do FCP (S/N)": _sn(
                linha.get("Considerar Redução de base do ICMS no cálculo do FCP (S/N)"), "N"
            ),
            "Alíquota interna da UF Destino (DIFAL)": _num(linha.get("Alíquota interna da UF Destino (DIFAL)"), "18"),
            "Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)": _num(
                linha.get("Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)"), "12"
            ),
            "Utiliza base de cálculo Dupla (DIFAL)": _sn(linha.get("Utiliza base de cálculo Dupla (DIFAL)"), "N"),
            "Alíquota ICMS Desonerado": _num(linha.get("Alíquota ICMS Desonerado"), "0"),
            "Alíquota FCP Desonerado": _num(linha.get("Alíquota FCP Desonerado"), "0"),
            "Motivo Desoneração": re.sub(r"\D", "", str(linha.get("Motivo Desoneração") or "")),
            "Código Beneficio Fiscal": str(linha.get("Código Beneficio Fiscal") or "").strip(),
            "Percentual Crédito Presumido": _num(linha.get("Percentual Crédito Presumido"), "0"),
            "Deduz ICMS Desonerado Total Nota (S/N)": _sn(linha.get("Deduz ICMS Desonerado Total Nota (S/N)"), "N"),
            "Alíquota Diferimento": _num(linha.get("Alíquota Diferimento"), "0"),
            "Percentual FCP Diferimento": _num(linha.get("Percentual FCP Diferimento"), "0"),
            "Observação Complementar Diferimento": str(linha.get("Observação Complementar Diferimento") or "").strip(),
            "Alíquota ICMS ST": _num(linha.get("Alíquota ICMS ST"), "0"),
            "Margem ST": _num(linha.get("Margem ST"), "0"),
            "Redução ICMS ST": _num(linha.get("Redução ICMS ST"), "0"),
            "Utiliza Base ICMS p/ Cálculo ST (S/N)": _sn(linha.get("Utiliza Base ICMS p/ Cálculo ST (S/N)"), "N"),
            "ICMS ST pago pela empresa em guia (S/N)": _sn(linha.get("ICMS ST pago pela empresa em guia (S/N)"), "N"),
            "Não deduzir o ICMS do cálculo do ICMS ST (S/N)": _sn(
                linha.get("Não deduzir o ICMS do cálculo do ICMS ST (S/N)"), "N"
            ),
            "Utiliza cálculo ICMS ST através do regime de estimativa simplificado (S/N)": _sn(
                linha.get("Utiliza cálculo ICMS ST através do regime de estimativa simplificado (S/N)"), "N"
            ),
            "Percentual de carga tributária média (%)": _num(
                linha.get("Percentual de carga tributária média (%)"), "0"
            ),
            "Somar ICMS/ST FCP-ST no Custo Médio (S/N)": _sn(
                linha.get("Somar ICMS/ST FCP-ST no Custo Médio (S/N)"), "N"
            ),
            "Alíquota ICMS Efetivo": _num(linha.get("Alíquota ICMS Efetivo"), "0"),
            "Redução de Base ICMS Efetivo": _num(linha.get("Redução de Base ICMS Efetivo"), "0"),
            "CST PIS": str(linha.get("CST PIS") or "99").zfill(2),
            "Alíquota PIS": _num(linha.get("Alíquota PIS"), "0"),
            "CST COFINS": str(linha.get("CST COFINS") or "99").zfill(2),
            "Alíquota COFINS": _num(linha.get("Alíquota COFINS"), "0"),
            "Operação de Receita (S/N)": op_receita,
            "Código Tipo Base de Crédito PIS/COFINS": str(
                linha.get("Código Tipo Base de Crédito PIS/COFINS") or "01"
            ).zfill(2),
            "Base de Cálculo PIS/COFINS Obtida p/ Lucro (S/N)": _sn(
                linha.get("Base de Cálculo PIS/COFINS Obtida p/ Lucro (S/N)"), "N"
            ),
            "CST IPI": str(linha.get("CST IPI") or "49").zfill(2),
            "Código Enquadramento IPI": str(linha.get("Código Enquadramento IPI") or "999"),
            "IPI Gera Crédito/Débito (S/N)": _sn(linha.get("IPI Gera Crédito/Débito (S/N)"), "N"),
            "Escriturar Valores Sem Tributação Como": str(
                linha.get("Escriturar Valores Sem Tributação Como (base 2 ou base 3)") or ""
            ),
            "CNAE": "",
            "Quem Pagará ISS": "",
            "Em que Município será Prestado": "",
            "Qual Município será Pago/Recolhido": "",
            "Identificador ISS Retido": "",
            "Natureza de Operação do Serviço Prestado": "",
            "CST PIS - Serviço": "",
            "Alíquota PIS - Serviço": "",
            "CST COFINS - Serviço": "",
            "Alíquota COFINS - Serviço": "",
            "Código Tipo Base de Crédito Serviço": "",
            "Código de Retenção CSRF": "",
            "Alíquota de PIS Retido": "",
            "Alíquota de COFINS Retido": "",
            "Alíquota de CSLL Retido": "",
            "Número da FCI": "N",
            "Conteúdo Importação (%)": "N",
            "Valor Parcela Importada Exterior (R$)": "N",
            "Valor Total Saída Interestadual": "N",
        }
        saida.append(registro)

    return saida


def exportar_layout_linx_terceiro_xlsx(
    linhas: list[dict[str, Any]],
    *,
    id_config_inicial: int = 1,
    ids_natureza: dict[str, int] | None = None,
    usar_ncm_no_id_config: bool = True,
) -> bytes:
    """Exporta planilha .xlsx em modo streaming (write_only) no modelo Linx (71 colunas)."""
    convertidas = converter_linhas_para_layout_linx_terceiro(
        linhas,
        id_config_inicial=id_config_inicial,
        ids_natureza=ids_natureza,
        usar_ncm_no_id_config=usar_ncm_no_id_config,
    )
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(title="Config_Tributaria_Linx")
    ws.append(list(COLUNAS_LAYOUT_LINX_TERCEIRO))
    for reg in convertidas:
        row_cells: list[Any] = []
        for idx_col, col in enumerate(COLUNAS_LAYOUT_LINX_TERCEIRO):
            val = sanitizar_celula_planilha(reg.get(col, ""))
            if idx_col == 0:
                c = WriteOnlyCell(ws, value=val)
                c.number_format = "@"
                row_cells.append(c)
            else:
                row_cells.append(val)
        ws.append(row_cells)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def exportar_layout_linx_terceiro_csv(
    linhas: list[dict[str, Any]],
    *,
    id_config_inicial: int = 1,
    ids_natureza: dict[str, int] | None = None,
    usar_ncm_no_id_config: bool = True,
) -> bytes:
    """Exporta .csv (delimitado por vírgula) no modelo exato de importação Linx (71 colunas)."""
    convertidas = converter_linhas_para_layout_linx_terceiro(
        linhas,
        id_config_inicial=id_config_inicial,
        ids_natureza=ids_natureza,
        usar_ncm_no_id_config=usar_ncm_no_id_config,
    )
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=list(COLUNAS_LAYOUT_LINX_TERCEIRO),
        delimiter=",",
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for reg in convertidas:
        writer.writerow({k: sanitizar_celula_planilha(v) for k, v in reg.items()})
    return buf.getvalue().encode("utf-8-sig")


def exportar_tabela_crua_xlsx(
    linhas: list[dict[str, Any]],
    *,
    sheet_name: str = "Consulta_Matriz",
) -> bytes:
    """Exporta exatamente as colunas e valores crus exibidos em tela para .xlsx (streaming)."""
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(title=sheet_name[:31])
    if linhas:
        colunas = list(linhas[0].keys())
        ws.append(colunas)
        for row in linhas:
            ws.append([sanitizar_celula_planilha(row.get(c, "")) for c in colunas])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _extrair_digito_origem_cst(cst_val: Any) -> str:
    digs = re.sub(r"\D", "", str(cst_val or ""))
    return digs[0] if digs else "0"


def exportar_layout_linx_terceiro_por_ncm_origem_zip(
    linhas: list[dict[str, Any]],
    *,
    id_config_inicial: int = 1,
    ids_natureza: dict[str, int] | None = None,
    usar_ncm_no_id_config: bool = True,
    formato: str = "xlsx",
) -> bytes:
    """Agrupa por NCM e 1º dígito do CST ICMS (0xx, 1xx, 2xx...) e empacota em um .zip."""
    grupos: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for linha in linhas:
        ncm_raw = re.sub(r"\D", "", str(linha.get("NCM") or "")) or str(linha.get("NCM") or "SEM_NCM").strip()
        orig_dig = _extrair_digito_origem_cst(linha.get("CST ICMS"))
        grupos[(ncm_raw, orig_dig)].append(linha)

    ext = "csv" if formato.lower() == "csv" else "xlsx"
    buf_zip = io.BytesIO()
    with zipfile.ZipFile(buf_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for (ncm_key, orig_dig) in sorted(grupos.keys()):
            sub_linhas = grupos[(ncm_key, orig_dig)]
            if ext == "csv":
                payload = exportar_layout_linx_terceiro_csv(
                    sub_linhas,
                    id_config_inicial=id_config_inicial,
                    ids_natureza=ids_natureza,
                    usar_ncm_no_id_config=usar_ncm_no_id_config,
                )
            else:
                payload = exportar_layout_linx_terceiro_xlsx(
                    sub_linhas,
                    id_config_inicial=id_config_inicial,
                    ids_natureza=ids_natureza,
                    usar_ncm_no_id_config=usar_ncm_no_id_config,
                )
            nome_arq = f"{ncm_key}_CST_{orig_dig}xx.{ext}"
            zf.writestr(nome_arq, payload)
    return buf_zip.getvalue()
