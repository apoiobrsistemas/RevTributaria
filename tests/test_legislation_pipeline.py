"""Testes do extrator por recortes, cliente IA sem web search, parsers e Vigia Noturno."""

from __future__ import annotations

import io
import json
from datetime import date

import openpyxl
import pytest

from src.database import init_db
from src.legislation import (
    ClienteLeituraIA,
    ConfiguracaoLLM,
    RecorteMarcadorNaoEncontradoError,
    citacao_existe_literalmente,
    formatar_cest,
    formatar_ncm,
    gerar_codigo_alerta,
    hash_conteudo_limpo,
    recortar_texto_vigente,
    verificar_fontes,
)
from src.legislation.parsers import extrair_linhas_tipi_xlsx, extrair_texto_html


def test_recorte_vigente_e_falha_segura():
    texto_lei = (
        "DISPOSIÇÕES REVOGADAS (1998) Art. 1º Antigo texto...\n"
        "REDAÇÃO VIGENTE Art. 52. Fica reduzida a base de cálculo para 8,80%.\n"
        "FIM ANEXO II\n"
        "ANEXO III REVOGADO..."
    )
    recorte = recortar_texto_vigente(texto_lei, "REDAÇÃO VIGENTE", "FIM ANEXO II")
    assert "Art. 52" in recorte
    assert "REVOGADAS" not in recorte
    assert "ANEXO III" not in recorte

    # Falha segura se marcador inicial não existir
    with pytest.raises(RecorteMarcadorNaoEncontradoError):
        recortar_texto_vigente(texto_lei, "MARCADOR INEXISTENTE")

    # Falha segura se marcador final informado não existir após o início
    with pytest.raises(RecorteMarcadorNaoEncontradoError):
        recortar_texto_vigente(texto_lei, "REDAÇÃO VIGENTE", "FIM INEXISTENTE")


def test_formatacao_ncm_cest_e_citacao_literal():
    assert formatar_ncm("85171300") == "8517.13.00"
    assert formatar_cest("2105301") == "21.053.01"

    texto_oficial = "Art. 313-W. Na saída de aparelhos telefônicos, NCM 8517.13.00, aplica-se MVA de 40%."
    # Normalização ignora acentos, pontuação e caixa
    assert citacao_existe_literalmente(
        "na saida de aparelhos telefonicos ncm 8517 13 00 aplica se mva de 40",
        texto_oficial,
    )
    assert not citacao_existe_literalmente(
        "aplica-se MVA de 75% conforme portaria inventada",
        texto_oficial,
    )


def test_cliente_ia_proibe_web_search_e_descarta_alucinacoes():
    with pytest.raises(ValueError):
        ConfiguracaoLLM(web_search=True)

    chamadas: list[tuple[str, dict, bool]] = []

    def fake_transport(prompt: str, schema: dict, web_search: bool) -> str:
        chamadas.append((prompt, schema, web_search))
        return json.dumps(
            {
                "ncm_formatado": "8517.13.00",
                "cest_formatado": "21.053.01",
                "regras": [
                    {
                        "dispositivo_legal": "Art. 313-W do RICMS/SP",
                        "trecho_citado": "Aplica-se MVA original de 40% para o NCM 8517.13.00",
                        "aliquota_icms": 18.0,
                        "margem_st": 40.0,
                        "confianca_ia": "ALTA",
                    },
                    {
                        "dispositivo_legal": "Art. 999 Inventado",
                        "trecho_citado": "Texto alucinado que não está na norma oficial",
                        "aliquota_icms": 12.0,
                        "confianca_ia": "BAIXA",
                    },
                ],
            }
        )

    cliente = ClienteLeituraIA(transport=fake_transport)
    resultado = cliente.analisar_norma(
        texto_recortado="RICMS/SP Art. 313-W: Aplica-se MVA original de 40% para o NCM 8517.13.00.",
        ncm="85171300",
        cest="2105301",
        url_oficial="https://legislacao.fazenda.sp.gov.br/ricms",
    )

    assert len(chamadas) == 1
    prompt_enviado, schema_enviado, web_search_flag = chamadas[0]
    assert web_search_flag is False
    assert "8517.13.00" in prompt_enviado
    assert "21.053.01" in prompt_enviado
    assert schema_enviado["type"] == "object"

    assert len(resultado["regras_validas"]) == 1
    assert resultado["citacoes_descartadas"] == 1
    assert resultado["regras_validas"][0]["dispositivo_legal"] == "Art. 313-W do RICMS/SP"


def test_parsers_html_e_tipi_xlsx():
    html = "<html><nav>Menu</nav><script>var x=1;</script><body><p>Art. 1º Alíquota 18%</p></body></html>"
    texto = extrair_texto_html(html)
    assert "Art. 1º Alíquota 18%" in texto
    assert "Menu" not in texto
    assert "var x=1" not in texto

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["NCM", "EX", "ALIQUOTA"])
    ws.append(["8517.13.00", "", "0"])
    buf = io.BytesIO()
    wb.save(buf)

    linhas = extrair_linhas_tipi_xlsx(buf.getvalue())
    assert linhas == [{"NCM": "8517.13.00", "EX": "", "ALIQUOTA": "0"}]


def test_vigia_noturno_detecta_mudanca_citacao_quebrada_e_queda_2_dias():
    conn = init_db(":memory:")
    try:
        texto_antigo = "Art. 10. Alíquota interna de 18%."
        hash_antigo = hash_conteudo_limpo(texto_antigo)

        # Fonte 1: vai mudar de conteúdo e quebrar citação
        conn.execute(
            """
            INSERT INTO fontes_legais (uf, esfera, tipo_norma, numero_norma, titulo, url_oficial, hash_conteudo, ultima_verificacao)
            VALUES ('SP', 'ESTADUAL', 'RICMS', '45490/00', 'RICMS SP', 'https://legislacao.fazenda.sp.gov.br/ricms', ?, '2026-11-16T00:00:00Z')
            """,
            (hash_antigo,),
        )
        # Fonte 2: fora do ar há 3 dias (>= 2 dias)
        conn.execute(
            """
            INSERT INTO fontes_legais (uf, esfera, tipo_norma, numero_norma, titulo, url_oficial, hash_conteudo, ultima_verificacao)
            VALUES ('RJ', 'ESTADUAL', 'DECRETO', '27427/00', 'RICMS RJ', 'https://portal.fazenda.rj.gov.br/ricms', ?, '2026-11-14T00:00:00Z')
            """,
            (hash_antigo,),
        )
        conn.execute(
            """
            INSERT INTO regras_estaduais_icms (
                uf_origem, uf_destino, ncm, cest, natureza_operacao,
                operacao_com_contribuinte, origem_mercadoria, vigencia_inicio,
                cfop, cst_icms, aliquota_icms, fonte_legal_id, dispositivo_legal,
                trecho_citado, status_validacao
            ) VALUES (
                'SP', 'SP', '85171300', '', 'VENDA', 1, '*', '2026-01-01',
                '5102', '00', 18.0, 1, 'Art. 10', 'Alíquota interna de 18%', 'ACEITO'
            )
            """
        )
        conn.commit()

        def fake_fetcher(url: str, usar_playwright: bool):
            if "rj.gov.br" in url:
                assert usar_playwright is True
                raise ConnectionError("Timeout SEFAZ-RJ")
            return b"<html><body>Art. 10. Aliquota interna alterada para 20%.</body></html>", "text/html"

        data_teste = date(2026, 11, 17)
        alertas = verificar_fontes(conn, fetcher=fake_fetcher, data_ref=data_teste)

        tipos = {a.tipo for a in alertas}
        assert "MUDANCA_CONTEUDO" in tipos
        assert "CITACAO_QUEBRADA" in tipos
        assert "URL_INDISPONIVEL" in tipos

        codigos = {a.codigo for a in alertas}
        assert gerar_codigo_alerta("SP", "RICMS", data_teste) in codigos
        assert gerar_codigo_alerta("RJ", "DECRETO", data_teste) in codigos
    finally:
        conn.close()
