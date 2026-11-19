"""Testes de normalização canônica, busca em 5 camadas e sincronização on-demand oficial (Zero Hardcode)."""

from __future__ import annotations

from pathlib import Path

from src.app.service import RevTributariaService
from src.engine import gerar_matriz_consolidada_ncm


def test_consulta_ncm_com_pontos_ausente_sincroniza_portaria_sre_e_gera_st(tmp_path: Path) -> None:
    db_file = tmp_path / "sync_st.db"
    srv = RevTributariaService(db_file)
    try:
        # Simula texto oficial baixado de legislacao.fazenda.sp.gov.br (Portaria SRE 12/2026 - Art. 313-W)
        texto_portaria_oficial = (
            "Portaria SRE 12/2026 - Altera a Portaria CAT 68/2019 e fixa IVA-ST para produtos alimentícios.\n"
            "Art. 313-W do RICMS/SP: Biscoitos e bolachas derivados de farinha de trigo; outros (waffles e wafers).\n"
            "Item 53 | CEST 17.053.00 | NCM 1905.31.00 | IVA-ST Original 59,67% | Alíquota 18%\n"
        )
        res = srv.resolver_ou_sincronizar_regra_ncm(
            ncm="1905.31.00",
            uf_origem="SP",
            uf_destino="SP",
            data_referencia="2026-11-19",
            textos_oficiais=[
                {
                    "texto": texto_portaria_oficial,
                    "url": "https://legislacao.fazenda.sp.gov.br/Paginas/Portarias.aspx",
                    "numero_norma": "Portaria SRE 12/2026",
                }
            ],
        )

        assert res["encontrada"] is True
        assert res["ncm_normalizado"] == "19053100"
        assert res["origem_resolucao"] == "SYNC_OFICIAL_TEMPO_REAL"
        assert res["iva_st_original"] == 59.67
        assert "Portaria SRE 12/2026" in res["base_legal"]
        assert res["regra"]["cest"] == "1705300"
        assert res["regra"]["status_validacao"] == "A_CONFERIR"

        # Garante que gera linhas de ST (e NÃO Tributado Integralmente falso)
        matriz = gerar_matriz_consolidada_ncm(
            "19053100",
            "SP",
            "RJ",
            res["regra"],
            incluir_simples_nacional=False,
        )
        compras = [r for r in matriz if r["Natureza de Operação"] == "(E) Compra para Comercialização"]
        assert len(compras) >= 1
        assert all(r["Enquadramento ICMS"] == "ST" for r in compras)
        assert all(r["MVA Original (%)"] == 59.67 for r in compras)
        assert all("Portaria SRE 12/2026" in r["Observação Padrão NF-e"] for r in compras)

        # Sem regra nem texto oficial -> retorna SEM_REGRA_LEGAL (proibido presumir Tributado Integralmente)
        res_vazio = srv.resolver_ou_sincronizar_regra_ncm(
            ncm="9999.99.99",
            uf_origem="SP",
            uf_destino="SP",
            textos_oficiais=[{"texto": "Sem correspondencia", "url": "https://legislacao.fazenda.sp.gov.br/Paginas/Home.aspx"}],
        )
        assert res_vazio["encontrada"] is False
        assert res_vazio["origem_resolucao"] == "SEM_REGRA_LEGAL"
        matriz_vazia = gerar_matriz_consolidada_ncm("99999999", "SP", "SP", None)
        assert matriz_vazia[0]["Enquadramento ICMS"] == "SEM_REGRA_LEGAL"
    finally:
        srv.close()
