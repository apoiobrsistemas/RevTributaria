"""Validador determinístico de NCMs e exceções fiscais (cBenef, ST, isenções, vigência e lastro)."""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any


def _d(valor: Any) -> Decimal:
    if valor is None or valor == "":
        return Decimal("0")
    return Decimal(str(valor))


def _so_digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


@dataclass(frozen=True)
class AchadoValidacaoNCM:
    """Inconsistência ou exceção identificada na validação da matriz de NCMs."""

    ncm: str
    uf_origem: str
    uf_destino: str
    regra_estadual_id: int | None
    regra_federal_id: int | None
    codigo_regra: str
    categoria: str
    severidade: str  # ERRO | ALERTA | INFO
    mensagem: str
    sugestao_correcao: str


def _prefixo_cbenef_esperado(uf: str, cst: str) -> tuple[str, ...] | None:
    """Retorna prefixos esperados de cBenef para SP conforme Tabela cBenef/SEFAZ-SP."""
    if uf.upper() != "SP":
        return None
    mapa = {
        "40": ("SP01", "SP03", "SP09"),
        "41": ("SP01", "SP03", "SP09"),
        "50": ("SP03", "SP09"),
        "20": ("SP02", "SP09"),
        "70": ("SP02", "SP09"),
        "51": ("SP04", "SP09"),
        "90": ("SP05", "SP09"),
    }
    return mapa.get(cst)


def validar_matriz_ncms(
    conn: sqlite3.Connection,
    *,
    uf_origem: str | None = None,
    data_referencia: str | None = None,
    persistir: bool = True,
) -> dict[str, Any]:
    """Mapeia todos os NCMs ativos e valida exceções, cBenef, ST, isenções e lastro legal."""
    ref = data_referencia or date.today().isoformat()
    lote = f"VAL-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
    achados: list[AchadoValidacaoNCM] = []

    # 1. Carregar regras federais ativas indexadas por NCM
    fed_rows = conn.execute(
        """
        SELECT * FROM regras_federais
        WHERE status_registro = 'ATIVA'
        ORDER BY ncm, vigencia_inicio DESC
        """
    ).fetchall()
    fed_por_ncm: dict[str, list[sqlite3.Row]] = {}
    for row in fed_rows:
        ncm_limpo = _so_digitos(row["ncm"])
        fed_por_ncm.setdefault(ncm_limpo, []).append(row)

    # 2. Carregar tabela_terceiros ativa indexada por NCM (Conv. 52/91, Conv. 142/18 CEST, ZFM)
    terc_rows = conn.execute(
        """
        SELECT * FROM tabela_terceiros
        WHERE status_registro = 'ATIVA'
        """
    ).fetchall()
    terc_por_ncm: dict[str, list[sqlite3.Row]] = {}
    for row in terc_rows:
        ncm_limpo = _so_digitos(row["ncm"])
        terc_por_ncm.setdefault(ncm_limpo, []).append(row)

    # 3. Carregar regras estaduais ativas
    sql_est = "SELECT * FROM regras_estaduais_icms WHERE status_registro = 'ATIVA'"
    params_est: list[Any] = []
    if uf_origem:
        sql_est += " AND uf_origem = ?"
        params_est.append(uf_origem.upper())
    sql_est += " ORDER BY ncm, uf_origem, uf_destino, vigencia_inicio DESC"
    est_rows = conn.execute(sql_est, params_est).fetchall()

    ncms_mapeados: set[str] = set()
    chaves_vigencia: dict[tuple[str, str, str, str, str, int, str], list[sqlite3.Row]] = {}

    for row in est_rows:
        reg_id = int(row["id"])
        ncm = _so_digitos(row["ncm"])
        cest = _so_digitos(row["cest"])
        uf_o = str(row["uf_origem"]).upper()
        uf_d = str(row["uf_destino"]).upper()
        cst = str(row["cst_icms"] or "").strip()
        cbenef = str(row["codigo_beneficio_fiscal"] or "").strip().upper()
        aliq_icms = _d(row["aliquota_icms"])
        red_bc = _d(row["reducao_base_icms"])
        aliq_dif = _d(row["aliquota_diferimento"])
        aliq_deson = _d(row["aliquota_icms_desonerado"])
        motivo_deson = str(row["motivo_desoneracao"] or "").strip()
        tem_st = int(row["tem_st"] or 0)
        tem_acordo_st = int(row["tem_acordo_st"] or 0)
        margem_st = _d(row["margem_st"])
        mva_esp = _d(row["aliquota_mva_especial"])
        est_simp = int(row["regime_estimativa_simplificado_st"] or 0)
        icms_efet = _d(row["aliquota_icms_efetivo"])
        vig_ini = str(row["vigencia_inicio"] or "")
        vig_fim = str(row["vigencia_fim"] or "")

        if not ncm:
            # Regra genérica de UF (ncm == '') não entra no mapa de NCMs específicos
            continue

        ncms_mapeados.add(ncm)

        # A. Formato de NCM
        if len(ncm) != 8 or ncm == "00000000":
            achados.append(
                AchadoValidacaoNCM(
                    ncm=ncm or str(row["ncm"]),
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    regra_estadual_id=reg_id,
                    regra_federal_id=None,
                    codigo_regra="NCM_FORMATO_INVALIDO",
                    categoria="NCM_FEDERAL",
                    severidade="ERRO",
                    mensagem=f"NCM '{row['ncm']}' inválido (deve conter 8 dígitos diferentes de 00000000).",
                    sugestao_correcao="Corrigir NCM conforme Tabela Siscomex/TIPI.",
                )
            )
            continue

        # B. Cobertura Federal (TIPI / Siscomex / IBS-CBS)
        feds = fed_por_ncm.get(ncm, [])
        if not feds:
            achados.append(
                AchadoValidacaoNCM(
                    ncm=ncm,
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    regra_estadual_id=reg_id,
                    regra_federal_id=None,
                    codigo_regra="NCM_SEM_REGRA_FEDERAL",
                    categoria="NCM_FEDERAL",
                    severidade="ALERTA",
                    mensagem=f"NCM {ncm} sem correspondência ativa em regras_federais (TIPI/Siscomex/PIS-COFINS).",
                    sugestao_correcao="Sincronizar TIPI + Siscomex ou cadastrar regra federal para o NCM.",
                )
            )
        else:
            fed_vig = feds[0]
            if not str(fed_vig["cclass_trib"] or "").strip():
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=int(fed_vig["id"]),
                        codigo_regra="IBS_CBS_CCLASS_AUSENTE",
                        categoria="NCM_FEDERAL",
                        severidade="INFO",
                        mensagem=f"NCM {ncm} sem cClassTrib (IBS/CBS 2026+) preenchido na regra federal.",
                        sugestao_correcao="Importar planilha cClassTrib do Portal Nacional NF-e.",
                    )
                )

        # C. Validação de Vigência
        if vig_fim and vig_ini and vig_fim < vig_ini:
            achados.append(
                AchadoValidacaoNCM(
                    ncm=ncm,
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    regra_estadual_id=reg_id,
                    regra_federal_id=None,
                    codigo_regra="VIGENCIA_INVERTIDA",
                    categoria="VIGENCIA",
                    severidade="ERRO",
                    mensagem=f"Vigência inválida: fim ({vig_fim}) anterior ao início ({vig_ini}).",
                    sugestao_correcao="Ajustar vigencia_inicio / vigencia_fim.",
                )
            )

        chave_sobrep = (
            uf_o,
            uf_d,
            ncm,
            cest,
            str(row["natureza_operacao"]),
            int(row["operacao_com_contribuinte"]),
            str(row["origem_mercadoria"]),
        )
        chaves_vigencia.setdefault(chave_sobrep, []).append(row)

        # D. Consistência de Benefícios Fiscais (cBenef, Isenção, Redução BC, Diferimento)
        if cst == "00":
            if red_bc > 0 or aliq_dif > 0 or tem_st == 1:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="CST00_COM_EXCECAO",
                        categoria="REDUCAO_BC",
                        severidade="ERRO",
                        mensagem=(
                            f"CST 00 incompatível com redução ({red_bc}%), "
                            f"diferimento ({aliq_dif}%) ou ST (tem_st={tem_st})."
                        ),
                        sugestao_correcao="Alterar CST para 20 (redução), 51 (diferimento) ou 10/60/70 (ST).",
                    )
                )
            if cbenef:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="CST00_COM_CBENEF",
                        categoria="CBENEF",
                        severidade="ERRO",
                        mensagem=f"CST 00 (tributação integral) não deve possuir cBenef '{cbenef}'.",
                        sugestao_correcao="Remover cBenef ou ajustar CST para o benefício correspondente.",
                    )
                )

        if cst in {"20", "70"} and red_bc <= 0:
            achados.append(
                AchadoValidacaoNCM(
                    ncm=ncm,
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    regra_estadual_id=reg_id,
                    regra_federal_id=None,
                    codigo_regra="CST20_SEM_REDUCAO",
                    categoria="REDUCAO_BC",
                    severidade="ERRO",
                    mensagem=f"CST {cst} exige reducao_base_icms > 0 (atual: {red_bc}%).",
                    sugestao_correcao="Informar percentual de redução conforme RICMS/SP Anexo II ou Convênio 52/91.",
                )
            )

        if cst in {"40", "41", "50"} and (aliq_icms > 0 or red_bc > 0):
            achados.append(
                AchadoValidacaoNCM(
                    ncm=ncm,
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    regra_estadual_id=reg_id,
                    regra_federal_id=None,
                    codigo_regra="ISENCAO_COM_ALIQUOTA",
                    categoria="ISENCAO",
                    severidade="ERRO",
                    mensagem=f"CST {cst} (Isenta/Não Tributada/Suspensão) possui alíquota ({aliq_icms}%) ou redução ({red_bc}%).",
                    sugestao_correcao="Zerar alíquota e redução de BC para CST 40/41/50.",
                )
            )

        if cst == "51" and aliq_dif <= 0:
            achados.append(
                AchadoValidacaoNCM(
                    ncm=ncm,
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    regra_estadual_id=reg_id,
                    regra_federal_id=None,
                    codigo_regra="CST51_SEM_DIFERIMENTO",
                    categoria="DIFERIMENTO",
                    severidade="ERRO",
                    mensagem="CST 51 (Diferimento) exige aliquota_diferimento > 0.",
                    sugestao_correcao="Informar percentual de diferimento conforme RICMS/SP.",
                )
            )

        if aliq_deson > 0 and not motivo_deson:
            achados.append(
                AchadoValidacaoNCM(
                    ncm=ncm,
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    regra_estadual_id=reg_id,
                    regra_federal_id=None,
                    codigo_regra="DESONERACAO_SEM_MOTIVO",
                    categoria="ISENCAO",
                    severidade="ERRO",
                    mensagem="Desoneração informada sem motivo_desoneracao (tag motDesICMS obrigatória na NF-e).",
                    sugestao_correcao="Preencher motivo_desoneracao (ex: 7=SUFRAMA, 9=Outros).",
                )
            )

        prefixos = _prefixo_cbenef_esperado(uf_o, cst)
        if prefixos is not None:
            if not cbenef:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="CBENEF_AUSENTE",
                        categoria="CBENEF",
                        severidade="ALERTA",
                        mensagem=f"CST {cst} em {uf_o} sem código cBenef (esperado prefixo {'/'.join(prefixos)}).",
                        sugestao_correcao="Consultar Portaria CAT 42/2018 / Tabela cBenef SP e preencher codigo_beneficio_fiscal.",
                    )
                )
            elif not cbenef.startswith(prefixos):
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="CBENEF_PREFIXO_INCOMPATIVEL",
                        categoria="CBENEF",
                        severidade="ERRO",
                        mensagem=f"cBenef '{cbenef}' incompatível com CST {cst} em {uf_o} (esperado {'/'.join(prefixos)}).",
                        sugestao_correcao="Validar código cBenef na tabela oficial da SEFAZ-SP.",
                    )
                )

        # E. Validação de Substituição Tributária (Concessões, CEST, Acordos e ICMS Efetivo)
        if cst in {"10", "30", "70"}:
            if tem_st != 1:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="ST_FLAG_DESLIGADA",
                        categoria="ST_CONCESSAO",
                        severidade="ERRO",
                        mensagem=f"CST {cst} exige tem_st = 1.",
                        sugestao_correcao="Ativar tem_st = 1 e informar MVA/alíquota ST.",
                    )
                )
            if len(cest) != 7:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="ST_CEST_INVALIDO",
                        categoria="ST_CONCESSAO",
                        severidade="ERRO",
                        mensagem=f"Operação com ST (CST {cst}) exige CEST válido de 7 dígitos (atual: '{cest}').",
                        sugestao_correcao="Vincular CEST conforme Convênio ICMS 142/2018 e Portaria CAT 68/2019.",
                    )
                )
            if margem_st <= 0 and mva_esp <= 0 and est_simp == 0:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="ST_MVA_AUSENTE",
                        categoria="ST_CONCESSAO",
                        severidade="ERRO",
                        mensagem=f"CST {cst} sem MVA original, MVA especial ou estimativa simplificada.",
                        sugestao_correcao="Preencher margem_st conforme Portaria SRE vigente de IVA-ST.",
                    )
                )
            if uf_o != uf_d and tem_acordo_st == 0:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="ST_INTERESTADUAL_SEM_ACORDO",
                        categoria="ST_CONCESSAO",
                        severidade="ALERTA",
                        mensagem=f"ST interestadual {uf_o}->{uf_d} marcada sem tem_acordo_st = 1.",
                        sugestao_correcao="Verificar Protocolo/Convênio ICMS CONFAZ entre as UFs.",
                    )
                )

        if cst == "60":
            if len(cest) != 7:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="CST60_SEM_CEST",
                        categoria="ST_CONCESSAO",
                        severidade="ALERTA",
                        mensagem=f"CST 60 sem CEST de 7 dígitos (atual: '{cest}').",
                        sugestao_correcao="Informar CEST correspondente ao item sujeito à ST.",
                    )
                )
            if icms_efet <= 0:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="ICMS_EFETIVO_AUSENTE",
                        categoria="ICMS_EFETIVO",
                        severidade="ALERTA",
                        mensagem="CST 60 sem aliquota_icms_efetivo (> 0), exigida para consumidor final na NF-e 4.0.",
                        sugestao_correcao="Preencher aliquota_icms_efetivo (e reducao_base_icms_efetivo se aplicável).",
                    )
                )

        # F. Cruzamento com tabela_terceiros (Convênio 52/91 e Convênio 142/2018 CEST)
        tercs = terc_por_ncm.get(ncm, [])
        if any(int(t["beneficio_convenio_52_91"] or 0) == 1 for t in tercs):
            if cst == "00" or red_bc <= 0:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="CONV52_NAO_APLICADO",
                        categoria="REDUCAO_BC",
                        severidade="ALERTA",
                        mensagem=(
                            f"NCM {ncm} consta no Convênio ICMS 52/1991 (tabela_terceiros), "
                            f"mas regra {uf_o}->{uf_d} está com CST {cst} e redução {red_bc}%."
                        ),
                        sugestao_correcao="Conferir enquadramento no Convênio 52/91 e Anexo II do RICMS/SP.",
                    )
                )

        cests_terc = {_so_digitos(t["cest"]) for t in tercs if len(_so_digitos(t["cest"])) == 7}
        if cests_terc and not cest:
            achados.append(
                AchadoValidacaoNCM(
                    ncm=ncm,
                    uf_origem=uf_o,
                    uf_destino=uf_d,
                    regra_estadual_id=reg_id,
                    regra_federal_id=None,
                    codigo_regra="CEST_CONFAZ_NAO_VINCULADO",
                    categoria="ST_CONCESSAO",
                    severidade="ALERTA",
                    mensagem=(
                        f"NCM {ncm} possui CEST ({', '.join(sorted(cests_terc))}) no Convênio 142/2018, "
                        "mas a regra estadual está sem CEST."
                    ),
                    sugestao_correcao="Verificar na Portaria CAT 68/2019 (SP) se o item está sujeito à ST.",
                )
            )

        # G. Lastro Legal (Norma e Citação Literal)
        if str(row["status_validacao"]) == "ACEITO":
            disp = str(row["dispositivo_legal"] or "").strip()
            trecho = str(row["trecho_citado"] or "").strip()
            if not disp or not trecho:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem=uf_o,
                        uf_destino=uf_d,
                        regra_estadual_id=reg_id,
                        regra_federal_id=None,
                        codigo_regra="ACEITO_SEM_LASTRO_LEGAL",
                        categoria="FONTE_LEGAL",
                        severidade="ALERTA",
                        mensagem="Regra ACEITO sem dispositivo_legal ou trecho_citado oficial.",
                        sugestao_correcao="Vincular fonte .gov.br/.leg.br e citação literal da norma.",
                    )
                )

    # H. Sobreposição de vigência na mesma chave estadual
    for chave, grupo in chaves_vigencia.items():
        if len(grupo) <= 1:
            continue
        ordenado = sorted(grupo, key=lambda r: str(r["vigencia_inicio"]))
        for idx in range(len(ordenado) - 1):
            atual = ordenado[idx]
            prox = ordenado[idx + 1]
            fim_atual = str(atual["vigencia_fim"] or "9999-12-31")
            ini_prox = str(prox["vigencia_inicio"])
            if fim_atual >= ini_prox:
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=chave[2],
                        uf_origem=chave[0],
                        uf_destino=chave[1],
                        regra_estadual_id=int(atual["id"]),
                        regra_federal_id=None,
                        codigo_regra="VIGENCIA_SOBREPOSTA",
                        categoria="VIGENCIA",
                        severidade="ERRO",
                        mensagem=(
                            f"Sobreposição de vigência entre regras #{atual['id']} "
                            f"(fim {atual['vigencia_fim'] or 'aberta'}) e #{prox['id']} (início {ini_prox})."
                        ),
                        sugestao_correcao="Encerrar vigencia_fim da regra anterior na véspera da nova vigência.",
                    )
                )

    # I. Validação das regras federais (PIS/COFINS monofásico / alíquota zero)
    for ncm, feds in fed_por_ncm.items():
        if not ncm or ncm == "00000000":
            continue
        for f in feds:
            # Filtrar apenas NCMs mapeados na matriz estadual ou com exceção explícita
            if ncm not in ncms_mapeados:
                continue
            cst_pis_s = str(f["cst_pis_saida"] or "").strip()
            aliq_pis = _d(f["aliquota_pis"])
            aliq_cof = _d(f["aliquota_cofins"])
            if cst_pis_s in {"04", "06"} and (aliq_pis > 0 or aliq_cof > 0):
                achados.append(
                    AchadoValidacaoNCM(
                        ncm=ncm,
                        uf_origem="BR",
                        uf_destino="BR",
                        regra_estadual_id=None,
                        regra_federal_id=int(f["id"]),
                        codigo_regra="MONOFASICO_COM_ALIQUOTA",
                        categoria="MONOFASICO",
                        severidade="ERRO",
                        mensagem=(
                            f"NCM {ncm} com CST PIS saída {cst_pis_s} (Monofásico/Alíquota Zero) "
                            f"possui alíquota PIS={aliq_pis}% / COFINS={aliq_cof}%."
                        ),
                        sugestao_correcao="Zerar alíquota PIS/COFINS para revenda monofásica/alíquota zero (CST 04/06).",
                    )
                )

    if persistir:
        with conn:
            conn.execute("DELETE FROM validacoes_ncm WHERE lote_execucao != ?", (lote,))
            if achados:
                conn.executemany(
                    """
                    INSERT INTO validacoes_ncm (
                        lote_execucao, ncm, uf_origem, uf_destino,
                        regra_estadual_id, regra_federal_id, codigo_regra,
                        categoria, severidade, mensagem, sugestao_correcao
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            lote,
                            a.ncm,
                            a.uf_origem,
                            a.uf_destino,
                            a.regra_estadual_id,
                            a.regra_federal_id,
                            a.codigo_regra,
                            a.categoria,
                            a.severidade,
                            a.mensagem,
                            a.sugestao_correcao,
                        )
                        for a in achados
                    ],
                )

    ncms_erro = {a.ncm for a in achados if a.severidade == "ERRO"}
    ncms_alerta = {a.ncm for a in achados if a.severidade == "ALERTA"} - ncms_erro
    ncms_conformes = ncms_mapeados - ncms_erro - ncms_alerta

    por_categoria: dict[str, int] = {}
    for a in achados:
        por_categoria[a.categoria] = por_categoria.get(a.categoria, 0) + 1

    return {
        "lote_execucao": lote,
        "data_referencia": ref,
        "total_ncms_mapeados": len(ncms_mapeados),
        "ncms_conformes": len(ncms_conformes),
        "ncms_com_erro": len(ncms_erro),
        "ncms_com_alerta": len(ncms_alerta),
        "total_achados": len(achados),
        "por_categoria": por_categoria,
        "achados": achados,
    }
