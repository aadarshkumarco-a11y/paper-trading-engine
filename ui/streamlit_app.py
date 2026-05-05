"""Multi-page Streamlit entry point for the NSE Paper Trading terminal.

Pages:
  📊 Dashboard — account overview, equity curve, quick stats
  📈 Trading   — full live terminal (watchlist | chart | order panel)
  🧠 Strategy  — built-in & custom Python strategies, sandboxed loader
  💼 Portfolio — positions, trade history, PnL breakdown, analytics
  ⚙️  Settings  — capital, feed, risk parameters

Also wires up Progressive Web App (PWA) support so the terminal can be
installed on mobile/desktop home screens. See ``ui/pwa.py`` for the
manifest/service-worker integration and its honest limitations.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.pages import dashboard, portfolio, settings, strategy, trading  # noqa: E402
from ui.pwa import inject_pwa, render_install_button  # noqa: E402
from ui.state import ensure_app  # noqa: E402
from ui.theme import inject_theme  # noqa: E402

st.set_page_config(
    page_title="NSE Paper Trading Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()
inject_pwa()


def _render_sidebar_brand() -> None:
    """Brand block + install button at the top of the sidebar."""
    st.sidebar.markdown(
        """
        <div style="padding:8px 4px 16px 4px">
          <div style="display:flex;align-items:center;gap:10px">
            <div style="font-size:1.6rem">📈</div>
            <div>
              <div style="font-weight:700;font-size:1.0rem;letter-spacing:-0.01em;color:#e6edf3">
                NSE Paper Trader
              </div>
              <div style="font-size:0.72rem;color:#8b949e">
                paper · zero real capital
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.sidebar:
        render_install_button()


def main() -> None:
    # Ensure the engine exists before any page tries to render it.
    ensure_app()
    _render_sidebar_brand()

    pages = [
        st.Page(dashboard.render, title="Dashboard", icon="📊", url_path="dashboard", default=True),
        st.Page(trading.render, title="Trading", icon="📈", url_path="trading"),
        st.Page(strategy.render, title="Strategy", icon="🧠", url_path="strategy"),
        st.Page(portfolio.render, title="Portfolio", icon="💼", url_path="portfolio"),
        st.Page(settings.render, title="Settings", icon="⚙️", url_path="settings"),
    ]
    nav = st.navigation(pages, position="sidebar", expanded=True)
    nav.run()


if __name__ == "__main__":
    main()
