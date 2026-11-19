"""Gerador puro da matriz tributária completa por NCM (expansão linha a linha)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from src.engine.fiscal_engine import ALIQUOTAS_INTERNAS_UF
from src.engine.fiscal_math import _dec, aliquota_interestadual, calcular_mva_ajustado

REGIMES_TRIBUTARIOS_EMPRESA: tuple[str, ...] = (
    "Lucro Real",
    "Lucro Presumido",
    "Simples Nacional",
    "Simples Nacional — Excesso de Sublimite",
    "MEI",
)

ATIVIDADES_EMPRESA: tuple[str, ...] = (
    "Varejo (Padrão)",
    "Indústria / Atacado Têxtil & Calçados (SP)",
)

_CRT_POR_REGIME: dict[str, str] = {
    "Simples Nacional": "1",
    "Simples Nacional — Excesso de Sublimite": "2",
    "Lucro Presumido": "3",
    "Lucro Real": "3",
    "MEI": "4",
}

# Alíquota modal interna de ICMS por UF de destino (vigência 2024/2025/2026)
ALIQUOTA_INTERNA_MODAL_UF: dict[str, float] = {
    "AC": 19.0, "AL": 19.0, "AM": 20.0, "AP": 18.0, "BA": 20.5,
    "CE": 20.0, "DF": 20.0, "ES": 17.0, "GO": 19.0, "MA": 22.0,
    "MG": 18.0, "MS": 17.0, "MT": 17.0, "PA": 19.0, "PB": 20.0,
    "PE": 20.5, "PI": 21.0, "PR": 19.5, "RJ": 20.0, "RN": 18.0,
    "RO": 19.5, "RR": 20.0, "RS": 17.0, "SC": 17.0, "SE": 19.0,
    "SP": 18.0, "TO": 20.0,
}

# FCP modal/geral por UF de destino (itens gerais; supérfluos específicos variam por NCM)
ALIQUOTA_FCP_PADRAO_UF: dict[str, float] = {
    "AC": 0.0, "AL": 1.0, "AM": 0.0, "AP": 0.0, "BA": 0.0,
    "CE": 2.0, "DF": 0.0, "ES": 0.0, "GO": 0.0, "MA": 2.0,
    "MG": 0.0, "MS": 0.0, "MT": 0.0, "PA": 0.0, "PB": 2.0,
    "PE": 0.0, "PI": 2.0, "PR": 0.0, "RJ": 2.0, "RN": 0.0,
    "RO": 2.0, "RR": 0.0, "RS": 0.0, "SC": 0.0, "SE": 1.0,
    "SP": 0.0, "TO": 0.0,
}


def _fmt_cst(origem_num: str, cst: str) -> str:
    return f"{origem_num}.{str(cst or '00').strip().zfill(2)}"


def _fmt_csosn(origem_num: str, csosn: str) -> str:
    return f"{origem_num}.{str(csosn or '101').strip().zfill(3)}"


def _sn(val: Any, default: bool = False) -> str:
    if val is None or val == "":
        return "S" if default else "N"
    if isinstance(val, bool):
        return "S" if val else "N"
    s = str(val).strip().upper()
    if s in {"1", "S", "SIM", "TRUE", "Y", "YES"}:
        return "S"
    if s in {"0", "N", "NAO", "NÃO", "FALSE"}:
        return "N"
    return "S" if default else "N"


def _dados_federais(
    regra_federal: Mapping[str, Any] | None,
    eh_entrada: bool,
    regime_tributario: str = "Lucro Real",
    eh_receita_venda: bool = False,
) -> dict[str, Any]:
    monofasico = bool(
        regra_federal
        and str(regra_federal.get("cst_pis_saida") or "").strip() in {"04", "05", "06"}
    )

    if regime_tributario in {
        "Simples Nacional",
        "Simples Nacional — Excesso de Sublimite",
        "MEI",
    }:
        pis_cst = "98" if eh_entrada else "49"
        cof_cst = "98" if eh_entrada else "49"
        pis_aliq = 0.0
        cof_aliq = 0.0
        pis_cof_cred_deb = "Unificado no DAS / MEI (Sem Crédito/Débito por item)"
    elif regime_tributario == "Lucro Presumido":
        if monofasico:
            pis_cst = str(regra_federal.get("cst_pis_entrada") if eh_entrada else regra_federal.get("cst_pis_saida"))
            cof_cst = str(regra_federal.get("cst_cofins_entrada") if eh_entrada else regra_federal.get("cst_cofins_saida"))
            pis_aliq = 0.0
            cof_aliq = 0.0
            pis_cof_cred_deb = "Monofásico/Alíq. Zero (Sem Crédito/Débito)"
        elif eh_entrada:
            pis_cst = "70"
            cof_cst = "70"
            pis_aliq = 0.0
            cof_aliq = 0.0
            pis_cof_cred_deb = "Cumulativo (Entrada Sem Crédito)"
        else:
            pis_cst = "01"
            cof_cst = "01"
            pis_aliq = 0.65
            cof_aliq = 3.00
            pis_cof_cred_deb = "Cumulativo (Gera Débito 0,65% / 3,00%)"
    else:
        # Lucro Real (Não-Cumulativo)
        if not regra_federal:
            pis_cst = "50" if eh_entrada else "01"
            cof_cst = "50" if eh_entrada else "01"
            pis_aliq = 1.65
            cof_aliq = 7.60
            pis_cof_cred_deb = "Não-Cumulativo (Gera Crédito)" if eh_entrada else "Não-Cumulativo (Gera Débito)"
        else:
            pis_cst = str(
                (regra_federal.get("cst_pis_entrada") if eh_entrada else regra_federal.get("cst_pis_saida"))
                or ("50" if eh_entrada else "01")
            )
            cof_cst = str(
                (regra_federal.get("cst_cofins_entrada") if eh_entrada else regra_federal.get("cst_cofins_saida"))
                or ("50" if eh_entrada else "01")
            )
            pis_aliq = float(_dec(regra_federal.get("aliquota_pis")))
            cof_aliq = float(_dec(regra_federal.get("aliquota_cofins")))
            if monofasico or (pis_aliq == 0.0 and cof_aliq == 0.0):
                pis_cof_cred_deb = "Monofásico/Alíq. Zero (Sem Crédito/Débito)"
            else:
                pis_cof_cred_deb = "Não-Cumulativo (Gera Crédito)" if eh_entrada else "Não-Cumulativo (Gera Débito)"

    op_receita_sn = (
        _sn(regra_federal.get("operacao_receita"), default=eh_receita_venda)
        if (regra_federal and eh_receita_venda)
        else ("S" if eh_receita_venda else "N")
    )
    cod_base_cred = (
        str(regra_federal.get("codigo_tipo_base_credito_pis_cofins") or "").strip()
        if regra_federal
        else ""
    )
    if not cod_base_cred and eh_entrada and regime_tributario == "Lucro Real" and not monofasico:
        cod_base_cred = "01"
    base_pis_lucro_sn = _sn(regra_federal.get("base_pis_cofins_por_lucro"), default=False) if regra_federal else "N"
    cenq_ipi = str(regra_federal.get("codigo_enquadramento_ipi") or "").strip() if regra_federal else ""
    if not cenq_ipi:
        cenq_ipi = "999"
    ipi_cred_deb_sn = _sn(regra_federal.get("ipi_gera_credito_debito"), default=False) if regra_federal else "N"
    ipi_sem_trib = (
        str(regra_federal.get("ipi_escriturar_sem_tributacao") or "").strip()
        if regra_federal
        else ""
    ) or "Outras"

    if not regra_federal:
        return {
            "ipi_cst": "49" if eh_entrada else ("53" if regime_tributario in {"Simples Nacional", "MEI"} else "99"),
            "ipi_aliq": 0.0,
            "cenq_ipi": cenq_ipi,
            "ipi_cred_deb_sn": ipi_cred_deb_sn,
            "ipi_sem_trib": ipi_sem_trib,
            "pis_cst": pis_cst,
            "pis_aliq": pis_aliq,
            "cofins_cst": cof_cst,
            "cofins_aliq": cof_aliq,
            "op_receita_sn": op_receita_sn,
            "cod_base_cred": cod_base_cred,
            "base_pis_lucro_sn": base_pis_lucro_sn,
            "pis_cof_cred_deb": pis_cof_cred_deb,
            "cclass": "-",
            "cbs_aliq": 0.0,
            "ibs_aliq": 0.0,
        }

    cclass = str(regra_federal.get("cclass_trib") or "").strip() or "-"
    cbs = float(_dec(regra_federal.get("aliquota_cbs")))
    ibs = float(_dec(regra_federal.get("aliquota_ibs_uf")) + _dec(regra_federal.get("aliquota_ibs_mun")))

    return {
        "ipi_cst": str(
            (regra_federal.get("cst_ipi_entrada") if eh_entrada else regra_federal.get("cst_ipi_saida"))
            or ("49" if eh_entrada else "99")
        ),
        "ipi_aliq": float(_dec(regra_federal.get("aliquota_ipi"))),
        "cenq_ipi": cenq_ipi,
        "ipi_cred_deb_sn": ipi_cred_deb_sn,
        "ipi_sem_trib": ipi_sem_trib,
        "pis_cst": pis_cst,
        "pis_aliq": pis_aliq,
        "cofins_cst": cof_cst,
        "cofins_aliq": cof_aliq,
        "op_receita_sn": op_receita_sn,
        "cod_base_cred": cod_base_cred,
        "base_pis_lucro_sn": base_pis_lucro_sn,
        "pis_cof_cred_deb": pis_cof_cred_deb,
        "cclass": cclass,
        "cbs_aliq": cbs,
        "ibs_aliq": ibs,
    }


def gerar_matriz_ncm(
    ncm: str,
    uf_origem: str,
    uf_destino: str,
    regra_estadual: Mapping[str, Any],
    regra_federal: Mapping[str, Any] | None = None,
    tabela_terceiros: Mapping[str, Any] | None = None,
    regime_tributario: str = "Lucro Real",
    atividade_empresa: str = "Varejo (Padrão)",
) -> list[dict[str, Any]]:
    """Expande linha a linha todas as variações operacionais aplicáveis ao NCM."""
    uf_o = uf_origem.upper()
    uf_d = uf_destino.upper()
    cest = str(regra_estadual.get("cest") or "")
    tem_st = bool(regra_estadual.get("tem_st"))
    tem_acordo = bool(regra_estadual.get("tem_acordo_st", 1))
    aliq_interna = float(_dec(regra_estadual.get("aliquota_icms"), "18"))
    red_bc = float(_dec(regra_estadual.get("reducao_base_icms"), "0"))
    aliq_st = float(_dec(regra_estadual.get("aliquota_icms_st"), "0")) or ALIQUOTA_INTERNA_MODAL_UF.get(uf_d, aliq_interna)
    mva_orig = float(_dec(regra_estadual.get("margem_st"), "0"))
    fcp_regra = float(_dec(regra_estadual.get("aliquota_fcp"), "0"))
    aliq_fcp = fcp_regra if fcp_regra > 0 else ALIQUOTA_FCP_PADRAO_UF.get(uf_d, 0.0)
    difal_regra = float(_dec(regra_estadual.get("aliquota_interna_uf_destino_difal"), "0"))
    aliq_dest_difal = difal_regra if difal_regra > 0 else ALIQUOTA_INTERNA_MODAL_UF.get(uf_d, aliq_interna)
    cbenef = str(regra_estadual.get("codigo_beneficio_fiscal") or "")
    disp_legal = str(regra_estadual.get("dispositivo_legal") or "")
    obs_padrao = str(regra_estadual.get("observacao_padrao") or disp_legal)
    conv_52_91 = bool((tabela_terceiros or {}).get("beneficio_convenio_52_91", 0))

    linhas: list[dict[str, Any]] = []

    crt_atual = _CRT_POR_REGIME.get(regime_tributario, "3")
    simples_no_das = regime_tributario in {"Simples Nacional", "MEI"}

    # Flags e campos detalhados da regra estadual (Blocos 2 a 6)
    esc_sem_trib = str(regra_estadual.get("escriturar_sem_tributacao_como") or "").strip()
    val_trib_icms = float(_dec(regra_estadual.get("valor_tributavel_icms"), "0"))
    deduz_custo_medio_sn = _sn(regra_estadual.get("deduz_icms_fcp_custo_medio"), default=False)
    base_lucro_icms_sn = _sn(regra_estadual.get("base_icms_obtida_pelo_lucro"), default=False)
    somar_ipi_difal_sn = _sn(regra_estadual.get("somar_ipi_base_difal_fcp"), default=False)
    red_bc_fcp_sn = _sn(regra_estadual.get("considerar_red_bc_icms_no_fcp"), default=True)
    bc_dupla_difal_sn = _sn(
        regra_estadual.get("utiliza_bc_dupla_difal"),
        default=(uf_o != uf_d and uf_d != "ES"),
    )
    aliq_icms_deson = float(_dec(regra_estadual.get("aliquota_icms_desonerado"), "0"))
    aliq_fcp_deson = float(_dec(regra_estadual.get("aliquota_fcp_desonerado"), "0"))
    motivo_deson = str(regra_estadual.get("motivo_desoneracao") or "")
    perc_cred_pres = float(_dec(regra_estadual.get("percentual_credito_presumido"), "0"))
    deduz_deson_total_sn = _sn(regra_estadual.get("deduz_icms_desonerado_total_nota"), default=False)
    aliq_diferimento = float(_dec(regra_estadual.get("aliquota_diferimento"), "0"))
    perc_fcp_diferimento = float(_dec(regra_estadual.get("percentual_fcp_diferimento"), "0"))
    obs_diferimento = str(regra_estadual.get("observacao_complementar_diferimento") or "")
    red_icms_st = float(_dec(regra_estadual.get("reducao_icms_st"), "0"))
    util_base_icms_st_sn = _sn(regra_estadual.get("utiliza_base_icms_para_st"), default=False)
    st_pago_guia_sn = _sn(regra_estadual.get("icms_st_pago_em_guia"), default=False)
    nao_deduz_icms_st_sn = _sn(regra_estadual.get("nao_deduzir_icms_calculo_st"), default=False)
    est_simp_st_sn = _sn(regra_estadual.get("regime_estimativa_simplificado_st"), default=False)
    carga_trib_media = float(_dec(regra_estadual.get("percentual_carga_tributaria_media"), "0"))
    soma_st_custo_medio_sn = _sn(regra_estadual.get("somar_icms_st_fcp_st_custo_medio"), default=False)
    aliq_icms_efetivo = float(_dec(regra_estadual.get("aliquota_icms_efetivo"), "0"))
    red_bc_efetivo = float(_dec(regra_estadual.get("reducao_base_icms_efetivo"), "0"))
    cst_regra = str(regra_estadual.get("cst_icms") or "").strip()
    eh_isento_ou_benef_regra = cst_regra in {"40", "41", "50", "51"} and not tem_st
    regime_base_regra = (
        "Diferimento"
        if cst_regra == "51"
        else ("Isento / Benefício" if cst_regra in {"40", "41", "50"} else ("Tributado c/ Redução BC" if red_bc > 0 else "Tributado Integralmente"))
    )

    def _add_linha(
        *,
        operacao: str,
        origem_label: str,
        orig_cod: str,
        regime: str,
        destinatario: str,
        fundamentacao: str,
        cfop_int: str,
        aliq_int_val: float,
        cfop_inter: str,
        aliq_inter_val: float,
        cst_cod: str,
        csosn_cod: str,
        red_val: float,
        aliq_st_val: float,
        mva_orig_val: float,
        mva_aj_val: float,
        difal_fcp_txt: str,
        eh_entrada: bool,
        observacao: str,
    ) -> None:
        eh_receita = operacao == "Venda de Mercadorias"
        fed = _dados_federais(
            regra_federal,
            eh_entrada,
            regime_tributario=regime_tributario,
            eh_receita_venda=eh_receita,
        )
        if simples_no_das:
            icms_cred_deb = (
                "Sem Crédito/Débito ICMS (DAS/MEI)"
                if not eh_entrada
                else ("Permite Transf. Crédito (Art. 23 LC 123)" if csosn_cod == "101" else "Sem Crédito ICMS (Simples/MEI)")
            )
            gera_cred_deb_sn = "S" if (eh_entrada and csosn_cod == "101") else "N"
            cst_exib = "-"
            aliq_int_exib = 0.0
            aliq_inter_exib = 0.0
            difal_exib = "Dispensado (ADI 5464 / Simples/MEI)" if "DIFAL" in difal_fcp_txt else difal_fcp_txt
        else:
            cst_exib = _fmt_cst(orig_cod, cst_cod)
            aliq_int_exib = aliq_int_val
            aliq_inter_exib = aliq_inter_val
            difal_exib = difal_fcp_txt
            if regime == "ST" and cst_cod == "60":
                icms_cred_deb = "Substituído (Sem Crédito/Débito Próprio)"
                gera_cred_deb_sn = "N"
            elif eh_entrada:
                tem_valor = aliq_int_val > 0 or aliq_inter_val > 0
                icms_cred_deb = "Gera Crédito ICMS" if tem_valor else "Sem Crédito ICMS"
                gera_cred_deb_sn = _sn(regra_estadual.get("gera_credito_debito"), default=True) if tem_valor else "N"
            else:
                tem_valor = aliq_int_val > 0 or aliq_inter_val > 0
                icms_cred_deb = "Gera Débito ICMS" if tem_valor else "Sem Débito ICMS"
                gera_cred_deb_sn = _sn(regra_estadual.get("gera_credito_debito"), default=True) if tem_valor else "N"

        cfop_aplicado = cfop_int if uf_o == uf_d else cfop_inter
        aliq_icms_aplicada = aliq_int_exib if uf_o == uf_d else aliq_inter_exib
        contrib_sn = "N" if "Não" in destinatario else "S"
        perfil_sigla = "NC" if contrib_sn == "N" else "CO"
        esc_sem_trib_linha = esc_sem_trib or ("Outras" if gera_cred_deb_sn == "N" else "")
        eh_st_linha = regime == "ST"

        # Regra condicional: Indústria / Atacado Têxtil & Calçados em SP (Anexo II Art. 52 / Anexo III Art. 41 e 43)
        cbenef_linha = cbenef
        red_linha = red_val
        regime_icms_linha = regime
        fundamentacao_linha = fundamentacao
        obs_linha = observacao
        cap_ncm = str(ncm or "")[:2]
        eh_ind_textil_sp = (
            atividade_empresa == "Indústria / Atacado Têxtil & Calçados (SP)"
            and uf_o == "SP"
            and uf_d == "SP"
            and not simples_no_das
            and not eh_st_linha
            and operacao == "Venda de Mercadorias"
        )
        if eh_ind_textil_sp and cap_ncm in {"60", "61", "62", "63"}:
            if contrib_sn == "S" and orig_cod == "0":
                red_linha = 33.33 if red_val == 0 else red_val
                cst_exib = _fmt_cst(orig_cod, "20")
                cbenef_linha = cbenef or "SP020052"
                regime_icms_linha = "Tributado c/ Redução BC"
                fundamentacao_linha = "RICMS/SP Anexo II Art. 52 / Anexo III Art. 41 (Têxtil/Confecções SP — Carga 12%)"
                obs_linha = "Redução BC 33,33% (carga efetiva 12%) para saída interna a Contribuinte (cBenef SP020052)"
            elif contrib_sn == "S" and orig_cod == "2":
                obs_linha = "Mercadoria importada (orig. 2): não se aplica redução Art. 52 Anexo II (18% interno / 4% interestadual)"
            else:
                obs_linha = f"{observacao} | Sem redução Art. 52 Anexo II (Não Contribuinte)"
        elif eh_ind_textil_sp and cap_ncm == "64" and contrib_sn == "S":
            fundamentacao_linha = "RICMS/SP Anexo III Art. 43 (Crédito Outorgado Calçados SP)"
            obs_linha = "Opção de Crédito Outorgado (Anexo III Art. 43) para fabricante paulista de calçados"

        # Garantia Portaria SRE 70/2025 (Trava CST x cBenef SP)
        cst_2d = cst_exib.split(".")[-1] if "." in cst_exib else cst_exib
        if uf_o == "SP" and not simples_no_das:
            if cst_2d == "41" and not cbenef_linha:
                cbenef_linha = "SP030007"  # Não incidência (RICMS/SP Art. 7º / ADC 49)
            elif cst_2d == "40" and not cbenef_linha:
                cbenef_linha = "SP010000"  # Isenção (RICMS/SP Anexo I)
            elif cst_2d == "50" and not cbenef_linha:
                cbenef_linha = "SP030000"  # Suspensão
            elif cst_2d == "51" and not cbenef_linha:
                cbenef_linha = "SP040000"  # Diferimento
            elif cst_2d in {"20", "70"} and red_linha > 0 and not cbenef_linha:
                cbenef_linha = "SP020000"  # Redução de BC (RICMS/SP Anexo II)
            elif cst_2d in {"00", "10", "60"}:
                cbenef_linha = ""

        linhas.append(
            {
                # Bloco Inicial
                "Regime Tributário": regime_tributario,
                "NCM": ncm,
                "Rota": f"{uf_o} > {uf_d}",
                "UF Origem": uf_o,
                # 51 Colunas da Planilha de Terceiros (Ordem Exata)
                "Natureza de Operação": operacao,
                "UF da Operação": uf_d,
                "Operação com Contribuinte (S/N)": contrib_sn,
                "CFOP": cfop_aplicado,
                "CST ICMS": cst_exib,
                "CSOSN": _fmt_csosn(orig_cod, csosn_cod),
                "Observação Padrão": fundamentacao_linha,
                "Alíquota ICMS": aliq_icms_aplicada,
                "Red. Base ICMS": red_linha,
                "Gera Crédito/Débito (S/N)": gera_cred_deb_sn,
                "Escriturar Valores sem Tributação como": esc_sem_trib_linha,
                "Valor Tributável ICMS": val_trib_icms,
                "Deduz ICMS/FCP do custo médio (S/N)": deduz_custo_medio_sn,
                "Base de cálculo ICMS Obtida pelo Lucro (S/N)": base_lucro_icms_sn,
                "Alíquota FCP": aliq_fcp,
                "Somar IPI Base DIFAL FCP (S/N)": somar_ipi_difal_sn,
                "Considerar Redução de base do ICMS no cálculo do FCP (S/N)": red_bc_fcp_sn,
                "Alíquota interna da UF Destino (DIFAL)": aliq_dest_difal,
                "Alíquota Interestadual ICMS UFs Envolvidas (DIFAL)": aliq_inter_val,
                "Utiliza base de cálculo Dupla (DIFAL)": bc_dupla_difal_sn if (uf_o != uf_d and contrib_sn == "N" and not simples_no_das) else "N",
                "Alíquota ICMS Desonerado": aliq_icms_deson,
                "Alíquota FCP Desonerado": aliq_fcp_deson,
                "Motivo Desoneração": motivo_deson,
                "Código Beneficio Fiscal": cbenef_linha,
                "Percentual Crédito Presumido": perc_cred_pres,
                "Deduz ICMS Desonerado Total Nota (S/N)": deduz_deson_total_sn,
                "Alíquota Diferimento": aliq_diferimento,
                "Percentual FCP Diferimento": perc_fcp_diferimento,
                "Observação Complementar Diferimento": obs_diferimento,
                "Alíquota ICMS ST": aliq_st_val,
                "Margem ST": mva_orig_val,
                "Redução ICMS ST": red_icms_st if eh_st_linha else 0.0,
                "Utiliza Base ICMS p/ Cálculo ST (S/N)": util_base_icms_st_sn if eh_st_linha else "N",
                "ICMS ST pago pela empresa em guia (S/N)": st_pago_guia_sn if eh_st_linha else "N",
                "Não deduzir o ICMS do cálculo do ICMS ST (S/N)": nao_deduz_icms_st_sn if eh_st_linha else "N",
                "Utiliza cálculo ICMS ST através do regime de estimativa simplificado (S/N)": est_simp_st_sn if eh_st_linha else "N",
                "Percentual de carga tributária média (%)": carga_trib_media if eh_st_linha else 0.0,
                "Somar ICMS/ST FCP-ST no Custo Médio (S/N)": soma_st_custo_medio_sn if eh_st_linha else "N",
                "Alíquota ICMS Efetivo": aliq_icms_efetivo if (eh_st_linha and cst_cod == "60") else 0.0,
                "Redução de Base ICMS Efetivo": red_bc_efetivo if (eh_st_linha and cst_cod == "60") else 0.0,
                "CST PIS": fed["pis_cst"],
                "Alíquota PIS": fed["pis_aliq"],
                "CST COFINS": fed["cofins_cst"],
                "Alíquota COFINS": fed["cofins_aliq"],
                "Operação de Receita (S/N)": fed["op_receita_sn"],
                "Código Tipo Base de Crédito PIS/COFINS": fed["cod_base_cred"],
                "Base de Cálculo PIS/COFINS Obtida p/ Lucro (S/N)": fed["base_pis_lucro_sn"],
                "CST IPI": fed["ipi_cst"],
                "Código Enquadramento IPI": fed["cenq_ipi"],
                "IPI Gera Crédito/Débito (S/N)": fed["ipi_cred_deb_sn"],
                "Escriturar Valores Sem Tributação Como (base 2 ou base 3)": fed["ipi_sem_trib"],
                # Colunas Complementares (Plataforma / Reforma Tributária)
                "CEST": cest,
                "Origem": origem_label,
                "Regime ICMS": regime_icms_linha,
                "CRT": crt_atual,
                "Perfil (NC/CO)": perfil_sigla,
                "ICMS Crédito/Débito": icms_cred_deb,
                "PIS/COFINS Crédito/Débito": fed["pis_cof_cred_deb"],
                "% MVA ST Ajustada": mva_aj_val,
                "DIFAL / FCP": difal_exib,
                "IPI Alíq.": fed["ipi_aliq"],
                "cClass": fed["cclass"],
                "Alíquota CBS": fed["cbs_aliq"],
                "Alíquota IBS": fed["ibs_aliq"],
                "Observações": obs_linha,
            }
        )

    origens = [("Nacional", "0"), ("Importado", "2")]

    # 1. COMPRA PARA COMERCIALIZAÇÃO
    for orig_label, orig_cod in origens:
        aliq_inter = float(
            aliquota_interestadual(
                uf_o,
                uf_d if uf_d != uf_o else "MG",
                orig_cod,
                beneficio_convenio_52_91=conv_52_91,
            )
            or Decimal("12.00")
        )
        mva_aj = float(
            calcular_mva_ajustado(
                mva_orig,
                aliq_inter,
                aliq_st,
                uf_destino=uf_d,
                fcp_pct=aliq_fcp,
            )
        )
        if tem_st:
            # Com Protocolo/Convênio
            _add_linha(
                operacao="Compra para Comercialização",
                origem_label=orig_label,
                orig_cod=orig_cod,
                regime="ST",
                destinatario="Contribuinte",
                fundamentacao=obs_padrao or "ICMS ST DESTACADO NA NF-E (Protocolo/Convênio)",
                cfop_int="1.403",
                aliq_int_val=aliq_interna,
                cfop_inter="2.403",
                aliq_inter_val=aliq_inter,
                cst_cod="70" if red_bc > 0 else "10",
                csosn_cod="201",
                red_val=red_bc,
                aliq_st_val=aliq_st,
                mva_orig_val=mva_orig,
                mva_aj_val=mva_aj,
                difal_fcp_txt=f"FCP {aliq_fcp}%" if aliq_fcp else "-",
                eh_entrada=True,
                observacao="ICMS ST DESTACADO NA NF-E",
            )
            # Sem Protocolo/Convênio (Não Signatário)
            if not tem_acordo or True:
                _add_linha(
                    operacao="Compra para Comercialização",
                    origem_label=orig_label,
                    orig_cod=orig_cod,
                    regime="ST (Sem Protocolo)",
                    destinatario="Contribuinte",
                    fundamentacao="NÃO SIGNATÁRIO - SEM PROTOCOLO/CONVÊNIO",
                    cfop_int="1.403",
                    aliq_int_val=0.0,
                    cfop_inter="2.403",
                    aliq_inter_val=0.0,
                    cst_cod="60",
                    csosn_cod="500",
                    red_val=0.0,
                    aliq_st_val=0.0,
                    mva_orig_val=0.0,
                    mva_aj_val=0.0,
                    difal_fcp_txt="-",
                    eh_entrada=True,
                    observacao="ICMS ST NÃO DESTACADO E RECOLHIDO PELAS ENTRADAS - NÃO SIGNATÁRIO",
                )

        # Tributado Integralmente (ou com Redução BC / Isenção / Diferimento)
        _add_linha(
            operacao="Compra para Comercialização",
            origem_label=orig_label,
            orig_cod=orig_cod,
            regime=regime_base_regra if eh_isento_ou_benef_regra else ("Tributado Integralmente" if red_bc == 0 else "Tributado c/ Redução BC"),
            destinatario="Contribuinte",
            fundamentacao=obs_padrao or disp_legal,
            cfop_int="1.102",
            aliq_int_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_interna,
            cfop_inter="2.102",
            aliq_inter_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_inter,
            cst_cod=cst_regra if eh_isento_ou_benef_regra else ("20" if red_bc > 0 else "00"),
            csosn_cod="400" if cst_regra in {"40", "41", "50"} else "101",
            red_val=red_bc,
            aliq_st_val=0.0,
            mva_orig_val=0.0,
            mva_aj_val=0.0,
            difal_fcp_txt="-",
            eh_entrada=True,
            observacao=f"cBenef: {cbenef}" if cbenef else "Crédito normal de entrada",
        )

    # 2. VENDA DE MERCADORIAS (Contribuinte vs. Não Contribuinte)
    for orig_label, orig_cod in origens:
        aliq_inter = float(
            aliquota_interestadual(
                uf_o,
                uf_d if uf_d != uf_o else "MG",
                orig_cod,
                beneficio_convenio_52_91=conv_52_91,
            )
            or Decimal("12.00")
        )
        difal_pct = max(0.0, round(aliq_dest_difal - aliq_inter, 2))
        difal_txt = f"DIFAL {difal_pct}% + FCP {aliq_fcp}%"

        if tem_st:
            # Venda ST -> Contribuinte
            _add_linha(
                operacao="Venda de Mercadorias",
                origem_label=orig_label,
                orig_cod=orig_cod,
                regime="ST",
                destinatario="Contribuinte",
                fundamentacao=obs_padrao or "ICMS RECOLHIDO ANTERIORMENTE POR SUBST. TRIB.",
                cfop_int="5.405",
                aliq_int_val=0.0,
                cfop_inter="6.404",
                aliq_inter_val=0.0,
                cst_cod="60",
                csosn_cod="500",
                red_val=0.0,
                aliq_st_val=aliq_st,
                mva_orig_val=mva_orig,
                mva_aj_val=0.0,
                difal_fcp_txt="-",
                eh_entrada=False,
                observacao="Substituído (CST 60 / CFOP 5.405 / 6.404)",
            )
            # Venda ST -> Não Contribuinte (6.108 + DIFAL)
            _add_linha(
                operacao="Venda de Mercadorias",
                origem_label=orig_label,
                orig_cod=orig_cod,
                regime="ST",
                destinatario="Não Contribuinte",
                fundamentacao=obs_padrao or "EC 87/2015 - Venda Interestadual Não Contribuinte",
                cfop_int="5.405",
                aliq_int_val=0.0,
                cfop_inter="6.108",
                aliq_inter_val=aliq_inter,
                cst_cod="00" if uf_o != uf_d else "60",
                csosn_cod="500",
                red_val=0.0,
                aliq_st_val=0.0,
                mva_orig_val=0.0,
                mva_aj_val=0.0,
                difal_fcp_txt=difal_txt,
                eh_entrada=False,
                observacao="Consumidor final não contribuinte (6.108 + DIFAL)",
            )

        # Venda Tributado Integralmente -> Contribuinte (ou Redução / Isenção / Diferimento)
        _add_linha(
            operacao="Venda de Mercadorias",
            origem_label=orig_label,
            orig_cod=orig_cod,
            regime=regime_base_regra if eh_isento_ou_benef_regra else ("Tributado Integralmente" if red_bc == 0 else "Tributado c/ Redução BC"),
            destinatario="Contribuinte",
            fundamentacao=obs_padrao or disp_legal,
            cfop_int="5.102",
            aliq_int_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_interna,
            cfop_inter="6.102",
            aliq_inter_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_inter,
            cst_cod=cst_regra if eh_isento_ou_benef_regra else ("20" if red_bc > 0 else "00"),
            csosn_cod="400" if cst_regra in {"40", "41", "50"} else "101",
            red_val=red_bc,
            aliq_st_val=0.0,
            mva_orig_val=0.0,
            mva_aj_val=0.0,
            difal_fcp_txt="-" if cst_regra in {"40", "41", "50"} else (f"FCP {aliq_fcp}%" if aliq_fcp else "-"),
            eh_entrada=False,
            observacao=f"cBenef: {cbenef}" if cbenef else "Tributação normal na saída",
        )
        # Venda Tributado Integralmente -> Não Contribuinte (6.108 + DIFAL)
        _add_linha(
            operacao="Venda de Mercadorias",
            origem_label=orig_label,
            orig_cod=orig_cod,
            regime=regime_base_regra if eh_isento_ou_benef_regra else ("Tributado Integralmente" if red_bc == 0 else "Tributado c/ Redução BC"),
            destinatario="Não Contribuinte",
            fundamentacao=obs_padrao or "EC 87/2015 - Saída para Não Contribuinte",
            cfop_int="5.102",
            aliq_int_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_interna,
            cfop_inter="6.108",
            aliq_inter_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_inter,
            cst_cod=cst_regra if eh_isento_ou_benef_regra else ("20" if red_bc > 0 else "00"),
            csosn_cod="400" if cst_regra in {"40", "41", "50"} else "102",
            red_val=red_bc,
            aliq_st_val=0.0,
            mva_orig_val=0.0,
            mva_aj_val=0.0,
            difal_fcp_txt="-" if cst_regra in {"40", "41", "50"} else difal_txt,
            eh_entrada=False,
            observacao="Saída não contribuinte (6.108 + DIFAL)",
        )

    # 3. DEVOLUÇÃO DE COMPRA (Saídas de Devolução)
    for orig_label, orig_cod in origens:
        aliq_inter = float(
            aliquota_interestadual(uf_o, uf_d if uf_d != uf_o else "MG", orig_cod) or Decimal("12.00")
        )
        if tem_st:
            _add_linha(
                operacao="Devolução de Compra",
                origem_label=orig_label,
                orig_cod=orig_cod,
                regime="ST",
                destinatario="Contribuinte",
                fundamentacao="Espelhamento da tributação da NF-e de entrada (ST)",
                cfop_int="5.411",
                aliq_int_val=aliq_interna,
                cfop_inter="6.411",
                aliq_inter_val=aliq_inter,
                cst_cod="10",
                csosn_cod="201",
                red_val=0.0,
                aliq_st_val=aliq_st,
                mva_orig_val=mva_orig,
                mva_aj_val=0.0,
                difal_fcp_txt="-",
                eh_entrada=False,
                observacao="Devolução de compra com ST (5.411 / 6.411)",
            )
        _add_linha(
            operacao="Devolução de Compra",
            origem_label=orig_label,
            orig_cod=orig_cod,
            regime="Tributado Integralmente",
            destinatario="Contribuinte",
            fundamentacao="Espelhamento da tributação da NF-e de entrada",
            cfop_int="5.202",
            aliq_int_val=aliq_interna,
            cfop_inter="6.202",
            aliq_inter_val=aliq_inter,
            cst_cod="00",
            csosn_cod="102",
            red_val=0.0,
            aliq_st_val=0.0,
            mva_orig_val=0.0,
            mva_aj_val=0.0,
            difal_fcp_txt="-",
            eh_entrada=False,
            observacao="Devolução de compra tributada (5.202 / 6.202)",
        )

    # 4. DEVOLUÇÃO DE VENDA (Entradas de Devolução)
    for orig_label, orig_cod in origens:
        aliq_inter = float(
            aliquota_interestadual(uf_o, uf_d if uf_d != uf_o else "MG", orig_cod) or Decimal("12.00")
        )
        if tem_st:
            _add_linha(
                operacao="Devolução de Venda",
                origem_label=orig_label,
                orig_cod=orig_cod,
                regime="ST",
                destinatario="Contribuinte",
                fundamentacao="Retorno de mercadoria sujeita à ST (5.405/6.404)",
                cfop_int="1.411",
                aliq_int_val=0.0,
                cfop_inter="2.411",
                aliq_inter_val=0.0,
                cst_cod="60",
                csosn_cod="500",
                red_val=0.0,
                aliq_st_val=aliq_st,
                mva_orig_val=mva_orig,
                mva_aj_val=0.0,
                difal_fcp_txt="-",
                eh_entrada=True,
                observacao="Devolução de venda com ST (1.411 / 2.411)",
            )
        _add_linha(
            operacao="Devolução de Venda",
            origem_label=orig_label,
            orig_cod=orig_cod,
            regime="Tributado Integralmente",
            destinatario="Contribuinte",
            fundamentacao="DEV. PARCIAL / TOTAL REF. A NF-E DE SAÍDA",
            cfop_int="1.202",
            aliq_int_val=aliq_interna,
            cfop_inter="2.202",
            aliq_inter_val=aliq_inter,
            cst_cod="00",
            csosn_cod="102",
            red_val=0.0,
            aliq_st_val=0.0,
            mva_orig_val=0.0,
            mva_aj_val=0.0,
            difal_fcp_txt="-",
            eh_entrada=True,
            observacao="Devolução de venda tributada (1.202 / 2.202)",
        )

    # 5. ENTRADA DE TRANSFERÊNCIA ENTRE FILIAIS
    for orig_label, orig_cod in origens:
        aliq_inter = float(
            aliquota_interestadual(
                uf_o,
                uf_d if uf_d != uf_o else "MG",
                orig_cod,
                beneficio_convenio_52_91=conv_52_91,
            )
            or Decimal("12.00")
        )
        if tem_st:
            _add_linha(
                operacao="Entrada de Transferência entre Filiais",
                origem_label=orig_label,
                orig_cod=orig_cod,
                regime="ST",
                destinatario="Contribuinte",
                fundamentacao="Transferência entre filiais de mercadoria sujeita à ST (1.409 / 2.409)",
                cfop_int="1.409",
                aliq_int_val=0.0,
                cfop_inter="2.409",
                aliq_inter_val=0.0,
                cst_cod="60",
                csosn_cod="500",
                red_val=0.0,
                aliq_st_val=aliq_st,
                mva_orig_val=mva_orig,
                mva_aj_val=0.0,
                difal_fcp_txt="-",
                eh_entrada=True,
                observacao="Entrada de transferência com ST (1.409 / 2.409)",
            )
        _add_linha(
            operacao="Entrada de Transferência entre Filiais",
            origem_label=orig_label,
            orig_cod=orig_cod,
            regime="Não Tributada (ADC 49)",
            destinatario="Contribuinte",
            fundamentacao="ADC 49 STF / LC 204/2023 / Convênio ICMS 109/2024 (Transferência entre filiais — Não Incidência)",
            cfop_int="1.152",
            aliq_int_val=0.0,
            cfop_inter="2.152",
            aliq_inter_val=0.0,
            cst_cod="41",
            csosn_cod="400",
            red_val=0.0,
            aliq_st_val=0.0,
            mva_orig_val=0.0,
            mva_aj_val=0.0,
            difal_fcp_txt="-",
            eh_entrada=True,
            observacao="Entrada de transferência não tributada (CST 41 / CFOP 1.152 / 2.152)",
        )

    # 6. SAÍDA DE TRANSFERÊNCIA ENTRE FILIAIS
    for orig_label, orig_cod in origens:
        aliq_inter = float(
            aliquota_interestadual(
                uf_o,
                uf_d if uf_d != uf_o else "MG",
                orig_cod,
                beneficio_convenio_52_91=conv_52_91,
            )
            or Decimal("12.00")
        )
        if tem_st:
            _add_linha(
                operacao="Saída de Transferência entre Filiais",
                origem_label=orig_label,
                orig_cod=orig_cod,
                regime="ST",
                destinatario="Contribuinte",
                fundamentacao="Transferência entre filiais de mercadoria sujeita à ST (5.409 / 6.409)",
                cfop_int="5.409",
                aliq_int_val=0.0,
                cfop_inter="6.409",
                aliq_inter_val=0.0,
                cst_cod="60",
                csosn_cod="500",
                red_val=0.0,
                aliq_st_val=aliq_st,
                mva_orig_val=mva_orig,
                mva_aj_val=0.0,
                difal_fcp_txt="-",
                eh_entrada=False,
                observacao="Saída de transferência com ST (5.409 / 6.409)",
            )
        _add_linha(
            operacao="Saída de Transferência entre Filiais",
            origem_label=orig_label,
            orig_cod=orig_cod,
            regime="Não Tributada (ADC 49)",
            destinatario="Contribuinte",
            fundamentacao="ADC 49 STF / LC 204/2023 / Convênio ICMS 109/2024 (Transferência entre filiais — Não Incidência)",
            cfop_int="5.152",
            aliq_int_val=0.0,
            cfop_inter="6.152",
            aliq_inter_val=0.0,
            cst_cod="41",
            csosn_cod="400",
            red_val=0.0,
            aliq_st_val=0.0,
            mva_orig_val=0.0,
            mva_aj_val=0.0,
            difal_fcp_txt="-",
            eh_entrada=False,
            observacao="Saída de transferência não tributada (CST 41 / CFOP 5.152 / 6.152)",
        )

    # 7. OUTRAS ENTRADAS (1.949 / 2.949)
    for orig_label, orig_cod in origens:
        aliq_inter = float(
            aliquota_interestadual(
                uf_o,
                uf_d if uf_d != uf_o else "MG",
                orig_cod,
                beneficio_convenio_52_91=conv_52_91,
            )
            or Decimal("12.00")
        )
        if tem_st:
            _add_linha(
                operacao="Outras Entradas",
                origem_label=orig_label,
                orig_cod=orig_cod,
                regime="ST",
                destinatario="Contribuinte",
                fundamentacao=obs_padrao or "Outras entradas de mercadoria sujeita à ST (1.949 / 2.949)",
                cfop_int="1.949",
                aliq_int_val=0.0,
                cfop_inter="2.949",
                aliq_inter_val=0.0,
                cst_cod="60",
                csosn_cod="500",
                red_val=0.0,
                aliq_st_val=aliq_st,
                mva_orig_val=mva_orig,
                mva_aj_val=0.0,
                difal_fcp_txt="-",
                eh_entrada=True,
                observacao="Outras entradas com ST (1.949 / 2.949)",
            )
        _add_linha(
            operacao="Outras Entradas",
            origem_label=orig_label,
            orig_cod=orig_cod,
            regime=regime_base_regra if eh_isento_ou_benef_regra else ("Tributado Integralmente" if red_bc == 0 else "Tributado c/ Redução BC"),
            destinatario="Contribuinte",
            fundamentacao=obs_padrao or disp_legal or "Outras entradas não especificadas (1.949 / 2.949)",
            cfop_int="1.949",
            aliq_int_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_interna,
            cfop_inter="2.949",
            aliq_inter_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_inter,
            cst_cod=cst_regra if eh_isento_ou_benef_regra else ("20" if red_bc > 0 else "00"),
            csosn_cod="400" if cst_regra in {"40", "41", "50"} else "102",
            red_val=red_bc,
            aliq_st_val=0.0,
            mva_orig_val=0.0,
            mva_aj_val=0.0,
            difal_fcp_txt="-",
            eh_entrada=True,
            observacao="Outras entradas (1.949 / 2.949)",
        )

    # 8. OUTRAS SAÍDAS (5.949 / 6.949)
    for orig_label, orig_cod in origens:
        aliq_inter = float(
            aliquota_interestadual(
                uf_o,
                uf_d if uf_d != uf_o else "MG",
                orig_cod,
                beneficio_convenio_52_91=conv_52_91,
            )
            or Decimal("12.00")
        )
        difal_pct = max(0.0, round(aliq_dest_difal - aliq_inter, 2))
        difal_txt = f"DIFAL {difal_pct}% + FCP {aliq_fcp}%"
        if tem_st:
            _add_linha(
                operacao="Outras Saídas",
                origem_label=orig_label,
                orig_cod=orig_cod,
                regime="ST",
                destinatario="Contribuinte",
                fundamentacao=obs_padrao or "Outras saídas de mercadoria sujeita à ST (5.949 / 6.949)",
                cfop_int="5.949",
                aliq_int_val=0.0,
                cfop_inter="6.949",
                aliq_inter_val=0.0,
                cst_cod="60",
                csosn_cod="500",
                red_val=0.0,
                aliq_st_val=aliq_st,
                mva_orig_val=mva_orig,
                mva_aj_val=0.0,
                difal_fcp_txt="-",
                eh_entrada=False,
                observacao="Outras saídas com ST (5.949 / 6.949)",
            )
        _add_linha(
            operacao="Outras Saídas",
            origem_label=orig_label,
            orig_cod=orig_cod,
            regime=regime_base_regra if eh_isento_ou_benef_regra else ("Tributado Integralmente" if red_bc == 0 else "Tributado c/ Redução BC"),
            destinatario="Contribuinte",
            fundamentacao=obs_padrao or disp_legal or "Outras saídas não especificadas — Contribuinte (5.949 / 6.949)",
            cfop_int="5.949",
            aliq_int_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_interna,
            cfop_inter="6.949",
            aliq_inter_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_inter,
            cst_cod=cst_regra if eh_isento_ou_benef_regra else ("20" if red_bc > 0 else "00"),
            csosn_cod="400" if cst_regra in {"40", "41", "50"} else "102",
            red_val=red_bc,
            aliq_st_val=0.0,
            mva_orig_val=0.0,
            mva_aj_val=0.0,
            difal_fcp_txt="-" if cst_regra in {"40", "41", "50"} else (f"FCP {aliq_fcp}%" if aliq_fcp else "-"),
            eh_entrada=False,
            observacao="Outras saídas Contribuinte (5.949 / 6.949)",
        )
        _add_linha(
            operacao="Outras Saídas",
            origem_label=orig_label,
            orig_cod=orig_cod,
            regime=regime_base_regra if eh_isento_ou_benef_regra else ("Tributado Integralmente" if red_bc == 0 else "Tributado c/ Redução BC"),
            destinatario="Não Contribuinte",
            fundamentacao=obs_padrao or disp_legal or "Outras saídas não especificadas — Não Contribuinte (5.949 / 6.949)",
            cfop_int="5.949",
            aliq_int_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_interna,
            cfop_inter="6.949",
            aliq_inter_val=0.0 if cst_regra in {"40", "41", "50"} else aliq_inter,
            cst_cod=cst_regra if eh_isento_ou_benef_regra else ("20" if red_bc > 0 else "00"),
            csosn_cod="400" if cst_regra in {"40", "41", "50"} else "102",
            red_val=red_bc,
            aliq_st_val=0.0,
            mva_orig_val=0.0,
            mva_aj_val=0.0,
            difal_fcp_txt="-" if cst_regra in {"40", "41", "50"} else difal_txt,
            eh_entrada=False,
            observacao="Outras saídas Não Contribuinte (5.949 / 6.949)",
        )

    return validar_linhas_matriz_sre_70(linhas)


def validar_linhas_matriz_sre_70(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Garante em todas as linhas geradas que exceções tenham cBenef válido (Portaria SRE 70/2025)."""
    cbenef_default_por_cst = {
        "20": "SP020000",
        "30": "SP010000",
        "40": "SP010000",
        "41": "SP030007",
        "50": "SP030000",
        "51": "SP040000",
        "70": "SP020000",
        "90": "SP050000",
    }
    for row in linhas:
        uf_o = str(row.get("UF Origem") or "").upper()
        cst_full = str(row.get("CST ICMS") or "")
        if cst_full == "-" or uf_o != "SP":
            continue
        cst_2d = cst_full.split(".")[-1] if "." in cst_full else cst_full
        cbenef = str(row.get("Código Beneficio Fiscal") or "").strip().upper()
        if cst_2d in cbenef_default_por_cst and not cbenef:
            row["Código Beneficio Fiscal"] = cbenef_default_por_cst[cst_2d]
        elif cst_2d in {"00", "10", "60"} and cbenef:
            row["Código Beneficio Fiscal"] = ""
    return linhas


def gerar_matriz_consolidada_ncm(
    ncm: str,
    uf_origem: str,
    uf_destino: str,
    regra_estadual: Mapping[str, Any],
    regra_federal: Mapping[str, Any] | None = None,
    regime_tributario: str = "Lucro Real",
    atividade_empresa: str = "Varejo (Padrão)",
) -> list[dict[str, Any]]:
    """Gera visão técnica unificada com TODAS as Naturezas de Entrada e Saída e colunas completas de MVA/ST/DIFAL/ERP."""
    uf_o = uf_origem.upper()[:2]
    uf_d = uf_destino.upper()[:2]
    cest = str(regra_estadual.get("cest") or "")
    tem_st = bool(regra_estadual.get("tem_st"))
    aliq_uf_o, fcp_uf_o = ALIQUOTAS_INTERNAS_UF.get(uf_o, (Decimal("18.00"), Decimal("0.00")))
    aliq_uf_d, fcp_uf_d = ALIQUOTAS_INTERNAS_UF.get(uf_d, (Decimal("18.00"), Decimal("0.00")))
    aliq_interna = float(_dec(regra_estadual.get("aliquota_icms"), str(aliq_uf_d)))
    aliq_fcp = float(_dec(regra_estadual.get("aliquota_fcp"), str(fcp_uf_d)))
    red_bc = float(_dec(regra_estadual.get("reducao_base_icms"), "0"))
    aliq_st = float(_dec(regra_estadual.get("aliquota_icms_st"), str(aliq_interna)))
    mva_orig = float(_dec(regra_estadual.get("margem_st"), "0"))
    red_st = float(_dec(regra_estadual.get("reducao_icms_st"), "0"))
    carga_media = float(_dec(regra_estadual.get("percentual_carga_tributaria_media"), "0"))
    aliq_efetivo = float(_dec(regra_estadual.get("aliquota_icms_efetivo"), "0"))
    red_efetivo = float(_dec(regra_estadual.get("reducao_base_icms_efetivo"), "0"))
    cbenef = str(regra_estadual.get("codigo_beneficio_fiscal") or "")
    protocolo = str(regra_estadual.get("dispositivo_legal") or ("Convênio ICMS 142/2018" if tem_st else "-"))
    fonte_url = str(regra_estadual.get("fonte_url") or "https://www.confaz.fazenda.gov.br/")
    conv_52_91 = "52/91" in protocolo

    aliq_inter_nac = float(aliquota_interestadual(uf_o, uf_d if uf_d != uf_o else "MG", "0", beneficio_convenio_52_91=conv_52_91) or Decimal("12.00"))
    aliq_inter_imp4 = float(aliquota_interestadual(uf_o, uf_d if uf_d != uf_o else "MG", "2", beneficio_convenio_52_91=conv_52_91) or Decimal("4.00"))
    mva_aj_nac = float(calcular_mva_ajustado(mva_orig, aliq_inter_nac, aliq_st, uf_destino=uf_d, fcp_pct=aliq_fcp)) if tem_st else 0.0
    mva_aj_imp4 = float(calcular_mva_ajustado(mva_orig, aliq_inter_imp4, aliq_st, uf_destino=uf_d, fcp_pct=aliq_fcp)) if tem_st else 0.0
    mva_sn = round(mva_orig, 2) if tem_st else 0.0

    deduz_custo = _sn(regra_estadual.get("deduz_icms_fcp_custo_medio"), default=False)
    soma_st_custo = _sn(regra_estadual.get("somar_icms_st_fcp_st_custo_medio"), default=False)
    bc_dupla = _sn(regra_estadual.get("utiliza_bc_dupla_difal"), default=(uf_o != uf_d and uf_d != "ES"))
    somar_ipi_difal = _sn(regra_estadual.get("somar_ipi_base_difal_fcp"), default=False)
    cst_regra = str(regra_estadual.get("cst_icms") or "").strip()
    cst_ibs_cbs = str((regra_federal or {}).get("cst_ibs_cbs") or "000")

    naturezas_catalogo = [
        # Entradas (1.xxx / 2.xxx / 3.xxx)
        ("Entrada", "(E) Compra para Comercialização", "Contribuinte", "1.403" if tem_st else "1.102", "2.403" if tem_st else "2.102", tem_st, False),
        ("Entrada", "(E) Compra para Industrialização", "Contribuinte", "1.401" if tem_st else "1.101", "2.401" if tem_st else "2.101", tem_st, False),
        ("Entrada", "(E) Devolução de Vendas", "Contribuinte", "1.411" if tem_st else "1.202", "2.411" if tem_st else "2.202", tem_st, False),
        ("Entrada", "(E) Compra para Uso e Consumo", "Não Contribuinte", "1.407" if tem_st else "1.556", "2.407" if tem_st else "2.556", tem_st, uf_o != uf_d),
        ("Entrada", "(E) Compra para Ativo Imobilizado", "Não Contribuinte", "1.406" if tem_st else "1.551", "2.406" if tem_st else "2.551", tem_st, uf_o != uf_d),
        ("Entrada", "(E) Transferência de Mercadorias", "Contribuinte", "1.409" if tem_st else "1.152", "2.409" if tem_st else "2.152", tem_st, False),
        ("Entrada", "(E) Remessa em Bonificação", "Contribuinte", "1.910", "2.910", False, False),
        ("Entrada", "(E) Importação Direta do Exterior", "Não Contribuinte", "3.102", "3.102", tem_st, False),
        # Saídas (5.xxx / 6.xxx)
        ("Saída", "(S) Venda de Mercadorias — Contribuinte", "Contribuinte", "5.405" if tem_st else "5.102", "6.403" if tem_st else "6.102", tem_st, False),
        ("Saída", "(S) Venda de Mercadorias — Não Contribuinte", "Não Contribuinte", "5.405" if tem_st else "5.102", "6.108", tem_st, uf_o != uf_d),
        ("Saída", "(S) Devolução de Compras", "Contribuinte", "5.411" if tem_st else "5.202", "6.411" if tem_st else "6.202", tem_st, False),
        ("Saída", "(S) Devolução de Uso e Consumo / Ativo Imobilizado", "Contribuinte", "5.413" if tem_st else "5.556", "6.413" if tem_st else "6.556", tem_st, False),
        ("Saída", "(S) Transferência de Mercadorias", "Contribuinte", "5.409" if tem_st else "5.152", "6.409" if tem_st else "6.152", tem_st, False),
        ("Saída", "(S) Remessa em Bonificação", "Contribuinte", "5.910", "6.910", False, False),
    ]

    origens_cfg = [
        ("Nacional", "0", aliq_inter_nac, mva_aj_nac),
        ("Importado 4%", "2", aliq_inter_imp4, mva_aj_imp4),
        ("Importado s/ Similar CAMEX", "6", aliq_inter_nac, mva_aj_nac),
    ]
    regimes_cfg = ["Regime Normal", "Simples Nacional"]

    saida: list[dict[str, Any]] = []
    for sentido, nat_nome, perfil, cfop_int, cfop_inter, usa_st, tem_difal in naturezas_catalogo:
        eh_ent = sentido == "Entrada"
        eh_imp_dir = "Importação Direta" in nat_nome
        for reg_nome in regimes_cfg:
            if eh_imp_dir and reg_nome == "Simples Nacional":
                continue
            for orig_lbl, orig_dig, aliq_inter_orig, mva_aj_orig in origens_cfg:
                if eh_imp_dir and orig_dig == "0":
                    continue
                orig_ef = ("1" if orig_dig == "2" else "6") if eh_imp_dir else orig_dig
                simples = reg_nome == "Simples Nacional"
                fed = _dados_federais(
                    regra_federal,
                    eh_ent,
                    regime_tributario="Simples Nacional" if simples else regime_tributario,
                    eh_receita_venda=("Venda de Mercadorias" in nat_nome),
                )
                if usa_st:
                    enq = "ST Retida/Destacada" if (eh_ent or cfop_inter in {"6.403", "6.411", "6.409"}) else "Substituído CST 60/500"
                    cst_2 = "70" if red_bc > 0 else ("60" if (not eh_ent and cfop_int == "5.405") else "10")
                    csosn_3 = "500" if cst_2 == "60" else "201"
                elif cst_regra in {"40", "41", "50"}:
                    enq = "Isenção/Imunidade"
                    cst_2 = cst_regra
                    csosn_3 = "400"
                elif red_bc > 0:
                    enq = "Redução de Base"
                    cst_2 = "20"
                    csosn_3 = "102"
                else:
                    enq = "Tributado Integralmente"
                    cst_2 = "00"
                    csosn_3 = "102"

                aliq_int_ef = round(aliq_interna * (1.0 - red_bc / 100.0) + aliq_fcp, 2)
                difal_pct = round(max(0.0, aliq_interna + aliq_fcp - aliq_inter_orig), 2) if (tem_difal and not simples) else 0.0
                met_difal = "Base Dupla" if bc_dupla == "S" else ("Soma IPI na Base" if somar_ipi_difal == "S" else "Base Única")
                cenario = (
                    f"[{sentido.upper()} - {nat_nome.split(' ', 1)[-1].upper()}] NCM {ncm} | {enq} ({orig_lbl})"
                    + (f" — MVA Ajust. {mva_aj_orig:.2f}%" if usa_st else "")
                )

                saida.append(
                    {
                        "Cenário / Nomenclatura Fiscal": cenario,
                        "Sentido": sentido,
                        "Natureza de Operação": nat_nome,
                        "Perfil Destinatário/Remetente": perfil,
                        "NCM": ncm,
                        "CEST": cest,
                        "Origem": orig_lbl,
                        "Regime Tributário": reg_nome,
                        "Enquadramento ICMS": enq,
                        "CFOP Interno": cfop_int,
                        "CFOP Interestadual": cfop_inter,
                        "CST (Orig.CST)": "-" if simples else f"{orig_ef}.{cst_2}",
                        "CSOSN (Orig.CSOSN)": f"{orig_ef}.{csosn_3}" if simples else f"{orig_ef}.102",
                        "Código cBenef": cbenef,
                        "Tem ST?": "Sim" if usa_st else "Não",
                        "Responsável ST": "Substituído CST 60/500" if cst_2 == "60" else ("Retida pelo Remetente" if usa_st else "-"),
                        "Protocolo / Convênio ICMS": protocolo if usa_st else "-",
                        "MVA Original (%)": round(mva_orig, 2) if usa_st else 0.0,
                        "MVA Ajustada Nacional (%)": round(mva_aj_nac, 2) if usa_st else 0.0,
                        "MVA Ajustada Importado 4% (%)": round(mva_aj_imp4, 2) if usa_st else 0.0,
                        "MVA Simples Nacional (%)": mva_sn if usa_st else 0.0,
                        "Alíq. ST (%)": round(aliq_st, 2) if usa_st else 0.0,
                        "Redução BC ST (%)": round(red_st, 2) if usa_st else 0.0,
                        "FCP-ST (%)": round(aliq_fcp, 2) if usa_st else 0.0,
                        "Carga Média / Estimativa Simplificada (%)": round(carga_media, 2) if usa_st else 0.0,
                        "Alíq. ICMS Efetivo (%)": round(aliq_efetivo, 2) if (usa_st and cst_2 == "60") else 0.0,
                        "Redução BC Efetivo (%)": round(red_efetivo, 2) if (usa_st and cst_2 == "60") else 0.0,
                        "Alíq. ICMS Interna (%)": round(aliq_interna, 2),
                        "FCP (%)": round(aliq_fcp, 2),
                        "Alíq. Interna Efetiva (%)": aliq_int_ef,
                        "Alíq. ICMS Interestadual (%)": 0.0 if simples else round(aliq_inter_orig, 2),
                        "Redução BC ICMS (%)": round(red_bc, 2),
                        "Carga Tributária Final (%)": round(aliq_int_ef, 2),
                        "DIFAL (%)": difal_pct,
                        "Metodologia DIFAL": met_difal,
                        "CST IPI": fed["ipi_cst"],
                        "cEnq": fed["cenq_ipi"],
                        "Alíq. IPI (%)": fed["ipi_aliq"],
                        "CST PIS": fed["pis_cst"],
                        "Alíq. PIS (%)": fed["pis_aliq"],
                        "CST COFINS": fed["cofins_cst"],
                        "Alíq. COFINS (%)": fed["cofins_aliq"],
                        "Regime Receita": fed["op_receita_sn"],
                        "CST IBS/CBS": cst_ibs_cbs,
                        "cClassTrib": fed["cclass"],
                        "Alíq. IBS (%)": fed["ibs_aliq"],
                        "Alíq. CBS (%)": fed["cbs_aliq"],
                        "Deduz ICMS/FCP Custo Médio?": deduz_custo,
                        "Soma ST/FCP-ST Custo Médio?": soma_st_custo if usa_st else "N",
                        "Gera Crédito/Débito?": "N" if cst_2 in {"40", "41", "50", "60"} or simples else "S",
                        "Fonte Oficial (.gov.br)": fonte_url,
                        "Observação Padrão NF-e": protocolo or f"Operação {sentido} NCM {ncm} conforme RICMS/{uf_d}",
                    }
                )
    return saida
