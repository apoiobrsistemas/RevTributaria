"""CLI periódica (Robô Diário) para sincronização oficial, Vigia Noturno e Validador de NCMs."""

from __future__ import annotations

import argparse

from src.app.service import RevTributariaService, baixar_bytes_oficiais
from src.database.schema_fase2 import garantir_carga_fase2
from src.legislation.vigia import verificar_fontes


def main(argv: list[str] | None = None) -> int:
    """Executa catálogo oficial, sincronização, Vigia Noturno e validação completa de NCMs."""
    parser = argparse.ArgumentParser(description="Robô diário de sincronização e validação fiscal RevTributaria")
    parser.add_argument("--db", default="revtributaria.db", help="Caminho para o banco SQLite")
    parser.add_argument("--uf-origem", default="SP", help="UF de origem padrão")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executa catálogo, descoberta e validador de NCMs sem downloads externos",
    )
    args = parser.parse_args(argv)

    service = RevTributariaService(args.db)
    try:
        cat = service.garantir_catalogo_fontes_oficiais()
        print(f"[CATALOGO] Fontes oficiais: {cat}")

        acervo = service.garantir_acervo_oficial()
        print(f"[ACERVO] Documentos oficiais: {acervo}")

        fase2 = garantir_carga_fase2(service._get_conn())
        print(f"[FASE2] cBenef & Protocolos ST: {fase2}")

        fetcher = None if args.dry_run else baixar_bytes_oficiais
        resumo = service.sincronizar_bases_oficiais(
            fetcher=fetcher,
            uf_origem=args.uf_origem,
        )
        print(f"[SYNC] Resumo: {resumo}")

        if not args.dry_run:
            try:
                url_nfe = "https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=04BIflQt1aY="
                html_nfe = baixar_bytes_oficiais(url_nfe).decode("utf-8", errors="ignore")
                qtd_nts = service.indexar_nts_html_oficial(html_nfe, url_oficial=url_nfe)
                print(f"[ACERVO_NTS] NTs indexadas do Portal NF-e: {qtd_nts}")
            except Exception as exc:
                print(f"[ACERVO_NTS] Aviso ao consultar Portal NF-e: {exc}")

            alertas = verificar_fontes(service._get_conn())
            print(f"[VIGIA] Alertas gerados: {len(alertas)}")
            for alerta in alertas:
                print(f"[{alerta.codigo}] ({alerta.tipo}) {alerta.mensagem}")

        val = service.executar_validacao_ncms(uf_origem=args.uf_origem)
        print(
            "[VALIDADOR] "
            f"ncms={val['total_ncms_mapeados']} "
            f"conformes={val['ncms_conformes']} "
            f"erros={val['ncms_com_erro']} "
            f"alertas={val['ncms_com_alerta']} "
            f"achados={val['total_achados']}"
        )
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
