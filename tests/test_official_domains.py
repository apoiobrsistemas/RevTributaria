"""Testes de bloqueio estrito de domínios não oficiais."""

from __future__ import annotations

import pytest

from src.legislation import DominioNaoOficialError, OfficialURL, validar_url_oficial


@pytest.mark.parametrize(
    "url_valida",
    [
        "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp87.htm",
        "https://legislacao.fazenda.sp.gov.br/Paginas/RICMS.aspx",
        "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18",
        "https://www.al.sp.gov.br/repositorio/legislacao/lei/2020/lei-17293.html",
        "https://www.stf.jus.br/portal/jurisprudencia/listar.asp",
        "https://www.mpf.mp.br/atuacao-tematica/parecer",
        "http://portal.fazenda.rj.gov.br/sefaz/",
    ],
)
def test_aceita_dominios_oficiais_permitidos(url_valida: str):
    assert validar_url_oficial(url_valida) == url_valida
    assert str(OfficialURL(url_valida)) == url_valida


@pytest.mark.parametrize(
    "url_invalida",
    [
        "",
        "   ",
        "https://www.econeteditora.com.br/icms",
        "https://www.iob.com.br/legislacao",
        "https://gov.br.evil.com/ricms",
        "https://evil.com/fazenda.gov.br",
        "https://fazenda.gov.br@evil.com/ricms",
        "ftp://fazenda.gov.br/arquivo.pdf",
        "file:///etc/passwd",
        "javascript:alert(1)",
    ],
)
def test_bloqueia_dominios_nao_oficiais_e_spoofing(url_invalida: str):
    with pytest.raises(DominioNaoOficialError):
        validar_url_oficial(url_invalida)
    with pytest.raises(DominioNaoOficialError):
        OfficialURL(url_invalida)
