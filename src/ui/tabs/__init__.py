"""Subcomponentes modulares das abas da interface Streamlit."""

from src.ui.tabs.consulta_matriz_ncm import render_consulta_matriz_ncm
from src.ui.tabs.tab_acervo import render_tab_acervo
from src.ui.tabs.tab_auditor_xml import render_aba_auditor_xml
from src.ui.tabs.tab_comparativo_erp import render_aba_comparativo_erp
from src.ui.tabs.tab_matriz import render_aba_matriz
from src.ui.tabs.tab_matriz_operacoes import render_aba_matriz_operacoes
from src.ui.tabs.tab_simulador import render_aba_simulador
from src.ui.tabs.tab_validador import render_aba_validador
from src.ui.tabs.tab_vigia import render_aba_vigia

__all__ = [
    "render_aba_auditor_xml",
    "render_aba_comparativo_erp",
    "render_aba_matriz",
    "render_aba_matriz_operacoes",
    "render_aba_simulador",
    "render_aba_validador",
    "render_aba_vigia",
    "render_consulta_matriz_ncm",
    "render_tab_acervo",
]
