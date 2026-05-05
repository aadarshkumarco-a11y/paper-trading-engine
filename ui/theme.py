"""Dark + glassmorphism theme injected into Streamlit via CSS."""
from __future__ import annotations

import streamlit as st

# Color tokens — keep the palette here so charts/components can stay in sync.
COLORS = {
    "bg": "#0d1117",
    "bg_alt": "#0a0e14",
    "card": "rgba(255,255,255,0.04)",
    "card_border": "rgba(255,255,255,0.08)",
    "text": "#e6edf3",
    "text_muted": "#8b949e",
    "accent": "#58a6ff",
    "profit": "#00ff9f",
    "loss": "#ff4d4d",
    "warning": "#f5a524",
    "buy": "#00c87f",
    "sell": "#ff4d6d",
}


CSS = f"""
<style>
:root {{
  --bg: {COLORS['bg']};
  --bg-alt: {COLORS['bg_alt']};
  --card: {COLORS['card']};
  --card-border: {COLORS['card_border']};
  --text: {COLORS['text']};
  --text-muted: {COLORS['text_muted']};
  --accent: {COLORS['accent']};
  --profit: {COLORS['profit']};
  --loss: {COLORS['loss']};
  --buy: {COLORS['buy']};
  --sell: {COLORS['sell']};
}}

/* Page-wide dark backdrop with a subtle radial gradient. */
.stApp {{
  background:
    radial-gradient(900px circle at 10% 0%, rgba(88,166,255,0.10), transparent 40%),
    radial-gradient(700px circle at 90% 100%, rgba(0,255,159,0.06), transparent 40%),
    var(--bg) !important;
  color: var(--text) !important;
}}

/* Header strip */
header[data-testid="stHeader"] {{
  background: transparent !important;
}}

/* Sidebar */
section[data-testid="stSidebar"] > div {{
  background: rgba(13,17,23,0.85) !important;
  backdrop-filter: blur(12px);
  border-right: 1px solid var(--card-border);
}}
section[data-testid="stSidebar"] * {{
  color: var(--text) !important;
}}

/* Headings */
h1, h2, h3, h4, h5, h6 {{
  color: var(--text) !important;
  letter-spacing: -0.01em;
}}
h1 {{ font-weight: 700 !important; }}

/* Metric cards (top bar uses these) */
[data-testid="stMetric"] {{
  background: var(--card);
  border: 1px solid var(--card-border);
  backdrop-filter: blur(10px);
  border-radius: 14px;
  padding: 14px 18px;
  transition: transform 120ms ease, border-color 120ms ease;
}}
[data-testid="stMetric"]:hover {{
  border-color: rgba(88,166,255,0.45);
  transform: translateY(-1px);
}}
[data-testid="stMetricLabel"] p {{
  color: var(--text-muted) !important;
  font-size: 0.78rem !important;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}}
[data-testid="stMetricValue"] {{
  color: var(--text) !important;
  font-weight: 700;
}}

/* Generic glass cards rendered via st.markdown(html). */
.glass-card {{
  background: var(--card);
  border: 1px solid var(--card-border);
  backdrop-filter: blur(10px);
  border-radius: 14px;
  padding: 14px 16px;
  margin-bottom: 10px;
}}
.glass-card .title {{
  color: var(--text-muted);
  font-size: 0.72rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 4px;
}}
.glass-card .value {{
  color: var(--text);
  font-size: 1.35rem;
  font-weight: 700;
}}

/* Status pills (market open/closed, engine running). */
.pill {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border: 1px solid var(--card-border);
}}
.pill-open {{
  background: rgba(0,255,159,0.10);
  color: var(--profit);
  border-color: rgba(0,255,159,0.4);
}}
.pill-closed {{
  background: rgba(255,77,77,0.10);
  color: var(--loss);
  border-color: rgba(255,77,77,0.4);
}}
.pill-running {{
  background: rgba(88,166,255,0.10);
  color: var(--accent);
  border-color: rgba(88,166,255,0.4);
}}
.pill-idle {{
  background: rgba(139,148,158,0.10);
  color: var(--text-muted);
  border-color: var(--card-border);
}}

/* Pulsing dot for "live" indicator. */
.pill .dot {{
  width: 8px; height: 8px; border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 8px currentColor;
  animation: pulse 1.6s infinite;
}}
@keyframes pulse {{
  0% {{ opacity: 1; }}
  50% {{ opacity: 0.35; }}
  100% {{ opacity: 1; }}
}}

/* Watchlist row */
.watchlist-row {{
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px; border-radius: 10px;
  border: 1px solid var(--card-border);
  background: var(--card);
  margin-bottom: 6px;
  transition: border-color 120ms ease, transform 120ms ease;
}}
.watchlist-row:hover {{
  border-color: rgba(88,166,255,0.4);
  transform: translateX(2px);
}}
.watchlist-row .sym {{ font-weight: 700; color: var(--text); }}
.watchlist-row .price {{ color: var(--text); font-variant-numeric: tabular-nums; }}
.watchlist-row .price.up {{ color: var(--profit); }}
.watchlist-row .price.down {{ color: var(--loss); }}

/* Buttons — make BUY/SELL pop */
.stButton > button[kind="primary"] {{
  background: linear-gradient(180deg, #20c98e 0%, #00a675 100%) !important;
  border: 0 !important;
  color: #00210e !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em;
  box-shadow: 0 4px 18px rgba(0,200,127,0.25);
}}
.stButton > button[kind="primary"]:hover {{
  filter: brightness(1.08);
  transform: translateY(-1px);
}}
.stButton > button[kind="secondary"] {{
  background: linear-gradient(180deg, #ff6b88 0%, #d63f5d 100%) !important;
  border: 0 !important;
  color: #2a000b !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em;
  box-shadow: 0 4px 18px rgba(214,63,93,0.25);
}}
.stButton > button[kind="secondary"]:hover {{
  filter: brightness(1.08);
  transform: translateY(-1px);
}}
/* Default-shape buttons (e.g. add-to-watchlist) */
.stButton > button {{
  border-radius: 10px;
  transition: transform 120ms ease, filter 120ms ease;
}}

/* Inputs / selects */
.stTextInput input, .stNumberInput input, .stSelectbox div[role="combobox"], textarea {{
  background: rgba(13,17,23,0.55) !important;
  border-radius: 10px !important;
  color: var(--text) !important;
}}
.stTextInput input::placeholder, .stNumberInput input::placeholder, textarea::placeholder {{
  color: var(--text-muted) !important;
}}

/* Dataframes / tables — dark zebra */
[data-testid="stDataFrame"] {{
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  overflow: hidden;
}}

/* Tabs */
[data-baseweb="tab"] {{
  color: var(--text-muted) !important;
  font-weight: 600 !important;
}}
[data-baseweb="tab"][aria-selected="true"] {{
  color: var(--accent) !important;
}}
[data-baseweb="tab-list"] {{
  border-bottom: 1px solid var(--card-border) !important;
}}

/* Toast / alerts */
.stAlert {{
  border-radius: 12px !important;
  border: 1px solid var(--card-border) !important;
}}

/* Sidebar navigation list — Zerodha-Kite style */
section[data-testid="stSidebarNav"] {{
  background: transparent !important;
}}
section[data-testid="stSidebarNav"] ul {{
  padding-top: 4px !important;
}}
section[data-testid="stSidebarNav"] a {{
  border-radius: 10px !important;
  padding: 8px 12px !important;
  margin: 2px 6px !important;
  transition: background 140ms ease, transform 140ms ease, border-color 140ms ease !important;
  border: 1px solid transparent !important;
  color: var(--text) !important;
}}
section[data-testid="stSidebarNav"] a:hover {{
  background: rgba(88,166,255,0.08) !important;
  border-color: rgba(88,166,255,0.20) !important;
  transform: translateX(2px) !important;
}}
section[data-testid="stSidebarNav"] a[aria-current="page"] {{
  background: linear-gradient(135deg, rgba(0,255,159,0.10), rgba(88,166,255,0.10)) !important;
  border-color: rgba(0,255,159,0.30) !important;
  color: var(--profit) !important;
  font-weight: 700 !important;
  box-shadow: 0 4px 16px rgba(0,255,159,0.08);
}}

/* Smooth page-fade on rerun */
[data-testid="stMain"] {{
  animation: page-fade 220ms ease;
}}
@keyframes page-fade {{
  from {{ opacity: 0; transform: translateY(4px); }}
  to {{ opacity: 1; transform: none; }}
}}

/* Subtle glow on glass cards on hover */
.glass-card {{
  transition: border-color 140ms ease, transform 140ms ease, box-shadow 140ms ease;
}}
.glass-card:hover {{
  border-color: rgba(88,166,255,0.25);
  box-shadow: 0 6px 22px rgba(0,0,0,0.35), 0 0 0 1px rgba(88,166,255,0.08) inset;
}}

/* Hide Streamlit's "Made with Streamlit" footer for a cleaner trading-terminal look. */
footer, #MainMenu {{ visibility: hidden; }}
</style>
"""


def inject_theme() -> None:
    """Apply the dark glassmorphism theme to the current Streamlit page.

    Safe to call multiple times — Streamlit deduplicates identical st.markdown blocks.
    """
    st.markdown(CSS, unsafe_allow_html=True)


def pill(label: str, kind: str = "idle", *, show_dot: bool = True) -> str:
    """Return HTML for a status pill (open/closed/running/idle)."""
    klass = {
        "open": "pill-open",
        "closed": "pill-closed",
        "running": "pill-running",
        "idle": "pill-idle",
    }.get(kind, "pill-idle")
    dot = '<span class="dot"></span>' if show_dot else ""
    return f'<span class="pill {klass}">{dot}{label}</span>'
