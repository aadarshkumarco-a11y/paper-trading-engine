"""Progressive Web App (PWA) integration for Streamlit.

Streamlit Community Cloud injects its **own** ``<link rel="manifest">`` and
``<meta name="theme-color">`` tags pointing at a generic "Streamlit" PWA
manifest. If we let those win, Chrome's "Add to Home Screen" / install
prompt picks up Streamlit's name and white theme instead of ours, which
defeats the whole point of a custom-branded paper trading PWA.

The fix is to **replace** any pre-existing manifest / theme-color tags with
ours every time the app reruns. We also auto-detect whether the app is on
Streamlit Cloud (which proxies static files at ``/~/+/app/static/...``) or
running locally (``/app/static/...``).

Honest constraints:
- Streamlit's UI runs over WebSocket and is highly dynamic, so the service
  worker only caches the *static shell* (manifest, icons). A real-time
  trading view cannot be made fully offline-capable without breaking
  freshness guarantees, which would be misleading for a trading app.
- The service worker is served at ``<base>/app/static/sw.js``, so by
  default its scope is ``<base>/app/static/``. That's narrower than ``/``,
  which means Chrome's automatic "Install app" prompt may not fire on
  Streamlit Cloud. We still set up everything correctly so:
    * The Chrome menu's **"Add to Home Screen"** uses *our* manifest
      (NSE Trader name + neon-green icon).
    * On installation the app opens in standalone mode (no browser chrome).
    * Theme color is correct (#0d1117).
- The ``beforeinstallprompt`` event only fires when all PWA install
  criteria are met (Chromium browsers over HTTPS, SW with fetch handler,
  manifest, user engagement). On Streamlit Cloud this often won't fire
  due to the narrow SW scope; the install button falls back to a tooltip
  pointing the user at the browser menu.
"""
from __future__ import annotations

import streamlit.components.v1 as components

# Sentinel used in the JS so we know our injection ran (handy for debugging
# in the console: ``window.__nsept_pwa_injected``).
INJECTION_SENTINEL = "__nsept_pwa_injected"

# Theme color must match ``.streamlit/config.toml`` ``backgroundColor``.
THEME_COLOR = "#0d1117"


def inject_pwa() -> None:
    """Replace any pre-existing manifest/theme tags with ours and register the SW.

    Streamlit's own ``<link rel="manifest">`` and ``<meta name="theme-color">``
    are removed first so the browser uses our paper-trading PWA manifest, not
    Streamlit's generic one.
    """
    js = f"""
    <script>
    (function () {{
      try {{
        var top = window.parent || window;
        var head = top.document.head;
        var loc = top.location;

        // Streamlit Cloud serves static files at "/~/+/app/static/...",
        // while local Streamlit serves them at "/app/static/...". Detect.
        var basePath = (loc.pathname.indexOf('/~/+') === 0) ? '/~/+' : '';
        var manifestHref = basePath + '/app/static/manifest.json';
        var swHref = basePath + '/app/static/sw.js';
        var appleHref = basePath + '/app/static/icons/icon-192.png';

        // --- Manifest: REPLACE any existing one (Streamlit injects its own) ---
        var existingManifests = head.querySelectorAll('link[rel="manifest"]');
        existingManifests.forEach(function (n) {{ n.parentNode.removeChild(n); }});
        var manifestLink = top.document.createElement('link');
        manifestLink.rel = 'manifest';
        manifestLink.href = manifestHref;
        head.appendChild(manifestLink);

        // --- theme-color: REPLACE any existing one ---
        var existingThemes = head.querySelectorAll('meta[name="theme-color"]');
        existingThemes.forEach(function (n) {{ n.parentNode.removeChild(n); }});
        var themeMeta = top.document.createElement('meta');
        themeMeta.name = 'theme-color';
        themeMeta.content = '{THEME_COLOR}';
        head.appendChild(themeMeta);

        // --- iOS / Apple meta tags (Add to Home Screen on iPhone) ---
        function setMeta(name, content) {{
          var existing = head.querySelectorAll('meta[name="' + name + '"]');
          existing.forEach(function (n) {{ n.parentNode.removeChild(n); }});
          var m = top.document.createElement('meta');
          m.name = name;
          m.content = content;
          head.appendChild(m);
        }}
        setMeta('apple-mobile-web-app-capable', 'yes');
        setMeta('apple-mobile-web-app-status-bar-style', 'black-translucent');
        setMeta('apple-mobile-web-app-title', 'NSE Trader');
        setMeta('mobile-web-app-capable', 'yes');

        var existingApple = head.querySelectorAll('link[rel="apple-touch-icon"]');
        existingApple.forEach(function (n) {{ n.parentNode.removeChild(n); }});
        var appleLink = top.document.createElement('link');
        appleLink.rel = 'apple-touch-icon';
        appleLink.href = appleHref;
        head.appendChild(appleLink);

        // --- Service worker registration (best-effort) ---
        if ('serviceWorker' in top.navigator && !top.{INJECTION_SENTINEL}) {{
          top.{INJECTION_SENTINEL} = true;
          // Try widest scope first; if Streamlit doesn't send the
          // Service-Worker-Allowed header this falls back to the default
          // scope (the directory containing sw.js).
          top.navigator.serviceWorker.register(swHref, {{ scope: '/' }})
            .catch(function () {{
              return top.navigator.serviceWorker.register(swHref);
            }})
            .then(function (reg) {{
              console.info('[PWA] Service worker registered, scope:', reg.scope);
            }})
            .catch(function (err) {{
              console.warn('[PWA] Service worker registration failed:', err);
            }});
        }}

        console.info('[PWA] Injected manifest:', manifestHref, 'theme:', '{THEME_COLOR}');
      }} catch (e) {{
        console.warn('[PWA] inject_pwa failed:', e);
      }}
    }})();
    </script>
    """
    components.html(js, height=0)


def render_install_button() -> None:
    """Render an install-app button that triggers the browser install prompt.

    The ``beforeinstallprompt`` event only fires when *all* Chromium PWA
    install criteria are met (manifest + SW with fetch handler + scope
    covering ``start_url`` + user engagement). On Streamlit Cloud the SW
    scope is narrower than ``/``, so this often won't fire. In that case the
    button falls back to opening a friendly tooltip telling the user to use
    the browser menu's **"Add to Home Screen"** option, which DOES work
    because our manifest is correctly installed.
    """
    components.html(
        """
        <div id="pwa-install-wrapper" style="margin:8px 0;">
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
          <div id="pwa-install-hint"
               style="font-size:0.72rem;color:#8b949e;margin-top:6px;text-align:center">
            Adds an icon to your home screen / desktop.
          </div>
        </div>
        <script>
          (function () {
            let deferredPrompt = null;
            const top = window.parent || window;
            const btn = document.getElementById('pwa-install-btn');
            const hint = document.getElementById('pwa-install-hint');

            // Listen on the parent window since beforeinstallprompt fires there.
            top.addEventListener('beforeinstallprompt', (e) => {
              e.preventDefault();
              deferredPrompt = e;
              hint.textContent = 'Click to install \u2014 opens like a native app.';
            });

            top.addEventListener('appinstalled', () => {
              hint.textContent = 'Installed! Open from your home screen.';
              btn.disabled = true;
              btn.style.opacity = '0.5';
              deferredPrompt = null;
            });

            btn.addEventListener('click', async () => {
              if (deferredPrompt) {
                deferredPrompt.prompt();
                const { outcome } = await deferredPrompt.userChoice;
                if (outcome === 'accepted') {
                  hint.textContent = 'Installing\u2026';
                }
                deferredPrompt = null;
              } else {
                // Detect platform for a useful instruction.
                const ua = top.navigator.userAgent || '';
                const isIOS = /iPad|iPhone|iPod/.test(ua);
                const isAndroid = /Android/.test(ua);
                let msg;
                if (isAndroid) {
                  msg = "Android Chrome:\\n" +
                        "1. Tap the \u22EE menu (top-right of the browser).\\n" +
                        "2. Choose 'Install app' or 'Add to Home screen'.\\n" +
                        "3. Confirm \u2014 a 'NSE Trader' icon will appear on your home screen.";
                } else if (isIOS) {
                  msg = "iPhone Safari:\\n" +
                        "1. Tap the Share button (square + arrow up).\\n" +
                        "2. Scroll down and choose 'Add to Home Screen'.\\n" +
                        "3. Confirm \u2014 a 'NSE Trader' icon will appear on your home screen.";
                } else {
                  msg = "Desktop Chrome / Edge:\\n" +
                        "1. Look in the address bar for the install icon (small monitor + \u2193).\\n" +
                        "2. Or open the \u22EE menu \u2192 'Install NSE Paper Trading Terminal\u2026'.";
                }
                alert(msg);
              }
            });
          })();
        </script>
        """,
        height=110,
    )
