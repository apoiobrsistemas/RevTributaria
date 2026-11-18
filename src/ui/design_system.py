"""Design System Executivo Light Mode para Streamlit (RevTributária)."""

from __future__ import annotations

from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components


def formatar_data_ptbr(valor: str | None) -> str:
    """Converte timestamp ISO (ex.: 2026-11-18T16:56:13Z) para '18/11/2026 às 16:56'."""
    bruto = str(valor or "").strip()
    if not bruto or bruto.lower() in {"nunca sincronizado", "n/a", "none", "-"}:
        return "Aguardando sincronização"
    try:
        limpo = bruto.replace("Z", "+00:00")
        dt = datetime.fromisoformat(limpo)
        return dt.strftime("%d/%m/%Y às %H:%M")
    except ValueError:
        return bruto


def formatar_milhar_ptbr(valor: int | float) -> str:
    """Formata inteiro com separador de milhar brasileiro (ex.: 10580 -> 10.580)."""
    return f"{int(valor):,}".replace(",", ".")


def formatar_ncm_mascara(ncm: str) -> str:
    """Formata NCM de 8 dígitos como XXXX.XX.XX para exibição amigável."""
    digitos = "".join(c for c in str(ncm or "") if c.isdigit())
    if len(digitos) == 8:
        return f"{digitos[:4]}.{digitos[4:6]}.{digitos[6:8]}"
    return str(ncm or "")


def apply_modern_design_system() -> None:
    """Injeta CSS global 100% Light Mode Executivo com contraste WCAG AAA."""
    st.markdown(
        '<meta name="google" content="notranslate">'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&family=Plus+Jakarta+Sans:wght@600;700&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )
    css_raw = """
<style>
  :root {
    --bg-canvas: #F8FAFC;
    --bg-surface: #FFFFFF;
    --bg-subtle: #F1F5F9;
    --border-subtle: #E2E8F0;
    --border-input: #CBD5E1;
    --text-primary: #0F172A;
    --text-secondary: #475569;
    --text-muted: #64748B;
    --accent-primary: #2563EB;
    --accent-hover: #1D4ED8;
    --accent-soft: #EFF6FF;
    --success-bg: #ECFDF5;
    --success-text: #065F46;
    --success-border: #A7F3D0;
  }

  /* Ocultar ruídos visuais nativos preservando botão de colapsar sidebar */
  #MainMenu, footer { visibility: hidden; }
  header[data-testid="stHeader"] {
    background: rgba(248, 250, 252, 0.85) !important;
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--border-subtle);
  }
  header[data-testid="stHeader"] * {
    color: var(--text-primary) !important;
  }

  /* Base Light Global */
  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background-color: var(--bg-canvas) !important;
    color: var(--text-primary) !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
  }
  h1, h2, h3, h4, .rev-title {
    font-family: 'Plus Jakarta Sans', 'Inter', sans-serif !important;
    color: var(--text-primary) !important;
  }
  p, span, label, div, li {
    color: inherit;
  }
  .stMarkdown, .stMarkdown p, .stCaption, [data-testid="stCaptionContainer"] p {
    color: var(--text-secondary) !important;
  }
  code, pre, .stCodeBlock, .rev-mono {
    font-family: 'JetBrains Mono', monospace !important;
  }

  /* Sidebar Executiva */
  section[data-testid="stSidebar"] {
    background-color: var(--bg-surface) !important;
    border-right: 1px solid var(--border-subtle) !important;
  }
  section[data-testid="stSidebar"] > div {
    background-color: var(--bg-surface) !important;
  }
  section[data-testid="stSidebar"] label,
  section[data-testid="stSidebar"] p,
  section[data-testid="stSidebar"] span {
    color: var(--text-primary) !important;
  }

  /* Cards da Sidebar (Marca, Status, KPIs 2x2, Rodapé) */
  .rev-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 0 12px 0;
  }
  .rev-brand-icon {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    background: #EFF6FF;
    color: #2563EB;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    border: 1px solid #BFDBFE;
  }
  .rev-brand-title {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-weight: 700;
    font-size: 1.2rem;
    color: #0F172A;
    line-height: 1.2;
  }
  .rev-brand-sub {
    font-size: 0.78rem;
    color: #64748B;
    font-weight: 500;
  }
  .rev-sync-banner {
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    border-radius: 12px;
    padding: 10px 12px;
    color: #1E40AF !important;
    font-size: 0.82rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
  }
  .rev-kpi-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 14px;
  }
  .rev-kpi-card {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 12px;
    transition: all 0.2s ease;
  }
  .rev-kpi-card:hover {
    border-color: #CBD5E1;
    box-shadow: 0 3px 10px rgba(15, 23, 42, 0.05);
  }
  .rev-kpi-label {
    font-size: 0.70rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748B;
    margin-bottom: 4px;
  }
  .rev-kpi-val {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 1.45rem;
    font-weight: 700;
    color: #0F172A;
    font-variant-numeric: tabular-nums;
    line-height: 1.15;
  }
  .rev-kpi-badge-ok {
    display: inline-block;
    margin-top: 4px;
    font-size: 0.68rem;
    font-weight: 600;
    background: #ECFDF5;
    color: #065F46;
    border: 1px solid #A7F3D0;
    border-radius: 999px;
    padding: 1px 7px;
  }
  .rev-date-badge {
    background: #F1F5F9;
    color: #334155 !important;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 0.76rem;
    margin-bottom: 8px;
  }
  .rev-profile-card {
    display: flex;
    align-items: center;
    gap: 10px;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 10px 12px;
    margin: 8px 0 12px 0;
  }
  .rev-avatar {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: #2563EB;
    color: #FFFFFF;
    font-weight: 700;
    font-size: 0.8rem;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }

  /* Hero Banner Principal */
  .rev-hero {
    background: linear-gradient(135deg, #FFFFFF 0%, #F1F5F9 100%);
    border: 1px solid #E2E8F0;
    border-radius: 16px;
    padding: 16px 22px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    animation: revFadeIn 0.3s ease-out;
  }
  .rev-hero-text {
    color: #0F172A !important;
    font-size: 0.96rem;
    font-weight: 600;
  }
  .rev-status-pill {
    background: #ECFDF5;
    color: #065F46 !important;
    border: 1px solid #A7F3D0;
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 0.82rem;
    font-weight: 600;
    white-space: nowrap;
    display: inline-flex;
    align-items: center;
  }
  .rev-pulse {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #059669;
    margin-right: 8px;
    animation: revPulse 2s infinite;
  }
  @keyframes revPulse {
    0% { box-shadow: 0 0 0 0 rgba(5, 150, 105, 0.55); }
    70% { box-shadow: 0 0 0 8px rgba(5, 150, 105, 0); }
    100% { box-shadow: 0 0 0 0 rgba(5, 150, 105, 0); }
  }
  @keyframes revFadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  /* Navegação de Abas (stTabs) - Limpa e sem corte escuro */
  .stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background-color: transparent;
    border-bottom: 1px solid #E2E8F0;
    padding-bottom: 4px;
    overflow-x: auto;
    scrollbar-width: thin;
  }
  .stTabs [data-baseweb="tab"] {
    background-color: transparent !important;
    color: #475569 !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    border-radius: 10px 10px 0 0 !important;
    padding: 8px 14px !important;
    border: none !important;
    transition: all 0.2s ease;
  }
  .stTabs [data-baseweb="tab"]:hover {
    color: #0F172A !important;
    background-color: #F1F5F9 !important;
  }
  .stTabs [aria-selected="true"] {
    color: #2563EB !important;
    background-color: #EFF6FF !important;
    font-weight: 600 !important;
    border-bottom: 3px solid #2563EB !important;
  }
  .stTabs [data-baseweb="tab-highlight"] {
    background-color: #2563EB !important;
  }

  /* Inputs, Selectboxes, DateInputs e Radio Buttons 100% Light */
  [data-testid="stWidgetLabel"] label,
  [data-testid="stWidgetLabel"] p {
    color: #334155 !important;
    font-size: 13px !important;
    font-weight: 600 !important;
  }
  [data-baseweb="input"],
  [data-baseweb="base-input"],
  [data-baseweb="select"] > div {
    background-color: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 10px !important;
    min-height: 42px !important;
    color: #0F172A !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
  }
  [data-baseweb="input"] input,
  [data-baseweb="base-input"] input,
  [data-baseweb="select"] span,
  [data-baseweb="select"] div {
    color: #0F172A !important;
    background-color: transparent !important;
  }
  [data-baseweb="input"]:focus-within,
  [data-baseweb="select"] > div:focus-within {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15) !important;
  }
  ul[data-baseweb="menu"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 10px !important;
  }
  ul[data-baseweb="menu"] li {
    color: #0F172A !important;
    background-color: #FFFFFF !important;
  }
  ul[data-baseweb="menu"] li:hover {
    background-color: #EFF6FF !important;
    color: #1D4ED8 !important;
  }

  /* Pílulas modernas para stRadio */
  div[data-testid="stRadio"] > div[role="radiogroup"] {
    gap: 10px;
  }
  div[data-testid="stRadio"] label[data-baseweb="radio"] {
    background: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    border-radius: 999px !important;
    padding: 6px 14px !important;
    color: #0F172A !important;
    transition: all 0.2s ease;
  }
  div[data-testid="stRadio"] label[data-baseweb="radio"]:hover {
    border-color: #2563EB !important;
    background: #EFF6FF !important;
  }
  div[data-testid="stRadio"] label[data-baseweb="radio"] p {
    color: #0F172A !important;
    font-weight: 500 !important;
  }

  /* Cards de Métricas, Expanders e Botões */
  div[data-testid="stMetric"], div[data-testid="stExpander"] {
    background-color: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 12px !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    transition: all 0.2s ease;
  }
  div[data-testid="stMetric"] label, div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #0F172A !important;
  }
  div[data-testid="stExpander"] summary, div[data-testid="stExpander"] summary p {
    color: #0F172A !important;
    font-weight: 600 !important;
  }
  button[kind="primary"] {
    background-color: #2563EB !important;
    border-color: #2563EB !important;
    color: #FFFFFF !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
  }
  button[kind="primary"]:hover {
    background-color: #1D4ED8 !important;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
  }
  button[kind="secondary"] {
    background-color: #FFFFFF !important;
    border: 1px solid #CBD5E1 !important;
    color: #0F172A !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
  }
  button[kind="secondary"]:hover {
    border-color: #2563EB !important;
    color: #2563EB !important;
    background-color: #EFF6FF !important;
  }

  /* Card Unificado de Seção */
  .rev-section-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 16px;
    padding: 20px 24px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  }
  .rev-section-header {
    display: flex;
    align-items: flex-start;
    gap: 14px;
  }
  .rev-section-badge {
    width: 42px;
    height: 42px;
    border-radius: 12px;
    background: #EFF6FF;
    color: #2563EB;
    border: 1px solid #BFDBFE;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    flex-shrink: 0;
  }
</style>
"""
    css_compact = "\n".join(line for line in css_raw.splitlines() if line.strip())
    st.markdown(css_compact, unsafe_allow_html=True)
    components.html(
        "<script>"
        "try {"
        "const d = window.parent.document;"
        "d.documentElement.setAttribute('translate', 'no');"
        "d.documentElement.classList.add('notranslate');"
        "if (d.body) { d.body.setAttribute('translate', 'no'); d.body.classList.add('notranslate'); }"
        "} catch (e) {}"
        "</script>",
        height=0,
        width=0,
    )
