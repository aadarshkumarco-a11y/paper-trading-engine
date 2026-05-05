"""Progressive Web App (PWA) integration for Streamlit.

Streamlit serves files placed in ``static/`` at ``/app/static/<file>``. We use
that to serve a manifest, icons, and a service worker, and inject the required
``<link rel="manifest">``, ``theme-color`` meta tag, and a service-worker
registration script via ``st.markdown(unsafe_allow_html=True)``.

Honest constraints:
- Streamlit's UI runs over WebSocket and is highly dynamic, so the service
  worker only caches the *static shell* (manifest, icons). A real-time
  trading view cannot be made fully offline-capable without breaking
  freshness guarantees, which would be misleading for a trading app.
- The ``beforeinstallprompt`` event only fires on Chromium-based browsers
  served over HTTPS. On Streamlit Community Cloud (HTTPS) it works.
"""
from __future__ import annotations

import streamlit.components.v1 as components

# Path is relative to the Streamlit static-file mount (`/app/static/...`).
MANIFEST_PATH = "./app/static/manifest.json"
SW_PATH = "./app/static/sw.js"
APPLE_TOUCH_ICON = "./app/static/icons/icon-192.png"


def inject_pwa() -> None:
    """Inject manifest link, theme-color meta tag, apple meta, and SW registration.

    ``st.markdown(unsafe_allow_html=True)`` strips ``<script>`` tags, so we
    use ``components.v1.html`` (an iframe) and reach back into
    ``window.parent.document.head`` to install the PWA tags. Same-origin
    iframes have full access to the parent document, which is what we need
    here. The service worker is then registered on ``window.parent`` so it
    controls the app shell, not the iframe.
    """
    js = f"""
    <script>
    (function () {{
      try {{
        var top = window.parent || window;
        var head = top.document.head;
        function ensure(selector, factory) {{
          if (head.querySelector(selector)) return;
          head.appendChild(factory());
        }}
        ensure('link[rel="manifest"]', function () {{
          var l = top.document.createElement('link');
          l.rel = 'manifest';
          l.href = '{MANIFEST_PATH}';
          return l;
        }});
        ensure('meta[name="theme-color"]', function () {{
          var m = top.document.createElement('meta');
          m.name = 'theme-color';
          m.content = '#0d1117';
          return m;
        }});
        ensure('meta[name="apple-mobile-web-app-capable"]', function () {{
          var m = top.document.createElement('meta');
          m.name = 'apple-mobile-web-app-capable';
          m.content = 'yes';
          return m;
        }});
        ensure('meta[name="apple-mobile-web-app-status-bar-style"]', function () {{
          var m = top.document.createElement('meta');
          m.name = 'apple-mobile-web-app-status-bar-style';
          m.content = 'black-translucent';
          return m;
        }});
        ensure('meta[name="apple-mobile-web-app-title"]', function () {{
          var m = top.document.createElement('meta');
          m.name = 'apple-mobile-web-app-title';
          m.content = 'NSE Paper Trading';
          return m;
        }});
        ensure('link[rel="apple-touch-icon"]', function () {{
          var l = top.document.createElement('link');
          l.rel = 'apple-touch-icon';
          l.href = '{APPLE_TOUCH_ICON}';
          return l;
        }});

        if ('serviceWorker' in top.navigator && !top.__nsept_sw_registered) {{
          top.__nsept_sw_registered = true;
          top.navigator.serviceWorker.register('{SW_PATH}').catch(function (err) {{
            console.warn('Service worker registration failed:', err);
          }});
        }}
      }} catch (e) {{
        console.warn('PWA inject failed:', e);
      }}
    }})();
    </script>
    """
    components.html(js, height=0)


def render_install_button() -> None:
    """Render an install-app button that triggers the browser install prompt.

    Lives inside an ``iframe`` (st.components.v1.html), so we forward the
    ``beforeinstallprompt`` event from the parent window via ``postMessage``.
    The button hides itself on browsers/sessions where install is not
    available (e.g. already installed, non-Chromium).
    """
    components.html(
        """
        <div id="pwa-install-wrapper" style="display:none;margin:8px 0;">
          <button id="pwa-install-btn"
            style="
              width:100%;
              padding:10px 14px;
              border:1px solid rgba(0,255,159,0.35);
              border-radius:10px;
              background:linear-gradient(135deg, rgba(0,255,159,0.10), rgba(88,166,255,0.10));
              color:#e6edf3;
              font-weight:600;
              cursor:pointer;
              transition: all 120ms ease;
            "
            onmouseover="this.style.borderColor='rgba(0,255,159,0.7)';this.style.transform='translateY(-1px)';"
            onmouseout="this.style.borderColor='rgba(0,255,159,0.35)';this.style.transform='none';"
          >
            ⬇ Install as App
          </button>
          <div style="font-size:0.72rem;color:#8b949e;margin-top:6px;text-align:center">
            Adds an icon to your home screen / desktop.
          </div>
        </div>
        <script>
          // Streamlit renders this snippet inside an iframe. Listen to the
          // parent window's beforeinstallprompt event via postMessage relay.
          let deferredPrompt = null;
          const wrapper = document.getElementById('pwa-install-wrapper');
          const btn = document.getElementById('pwa-install-btn');

          // Attempt direct listening (fires only if iframe is sameish-origin).
          window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPrompt = e;
            wrapper.style.display = 'block';
          });

          window.addEventListener('appinstalled', () => {
            wrapper.style.display = 'none';
            deferredPrompt = null;
          });

          // Always show the button as a hint — clicking will trigger the
          // prompt if we have a deferred one, else explain to the user.
          wrapper.style.display = 'block';

          btn.addEventListener('click', async () => {
            if (deferredPrompt) {
              deferredPrompt.prompt();
              const { outcome } = await deferredPrompt.userChoice;
              if (outcome === 'accepted') {
                wrapper.style.display = 'none';
              }
              deferredPrompt = null;
            } else {
              alert(
                "If you don't see an install prompt, use your browser menu:\\n" +
                "• Chrome: ⋮ menu → 'Install app' / 'Add to Home Screen'\\n" +
                "• Safari iOS: Share → 'Add to Home Screen'"
              );
            }
          });
        </script>
        """,
        height=70,
    )
