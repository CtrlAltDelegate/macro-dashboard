"""
Netlify build: write landing page into public/ so deploy works even if landing/ wasn't pushed.
Run from repo root: python scripts/build_landing.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LANDING_SRC = REPO_ROOT / "landing"
PUBLIC_DIR = REPO_ROOT / "public"

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Macro Dashboard — Regime & rotation analytics</title>
  <meta name="description" content="Private macro dashboard: valuation pressure, risk composite, allocation thermostat, and cross-asset rotation. FRED + Yahoo Finance. Newsletter-ready charts.">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="header">
    <div class="container">
      <a href="#" class="logo">Macro Dashboard</a>
      <nav class="nav">
        <a href="#features">Features</a>
        <a href="#run">Run it</a>
        <a href="https://github.com/CtrlAltDelegate/macro-dashboard" class="btn btn-ghost" target="_blank" rel="noopener">GitHub</a>
      </nav>
    </div>
  </header>
  <main>
    <section class="hero">
      <div class="container">
        <p class="hero-tag">Private · Local-first · Newsletter-ready</p>
        <h1>Macro regime &<br>rotation analytics</h1>
        <p class="hero-desc">
          Four analytical models: valuation pressure, macro risk composite, allocation thermostat, and risk cascade curves.
          Built for portfolio exposure decisions and Substack-ready charts.
        </p>
        <div class="hero-actions">
          <a href="https://github.com/CtrlAltDelegate/macro-dashboard" class="btn btn-primary" target="_blank" rel="noopener">View on GitHub</a>
          <a href="#run" class="btn btn-secondary">How to run</a>
        </div>
      </div>
    </section>
    <section id="features" class="features">
      <div class="container">
        <h2>What it does</h2>
        <div class="grid">
          <article class="card">
            <span class="card-num">01</span>
            <h3>Valuation Pressure Index</h3>
            <p>Macro-driven valuation compression on equities. Formula: (SPX/UNRATE²)×Inflation×FedFunds / M2. Rising = tightening; falling = easing.</p>
          </article>
          <article class="card">
            <span class="card-num">02</span>
            <h3>Macro Risk Dashboard</h3>
            <p>Raw standardized composite + ROC for acceleration. Pillars: GDP, unemployment, inflation, NFCI, Fed liquidity, HY spread. Rising = deterioration.</p>
          </article>
          <article class="card">
            <span class="card-num">03</span>
            <h3>Risk Thermostat (0–100)</h3>
            <p>Allocation guide: Risk-on → Neutral → De-risk → Defensive → Capital preservation. Actionable exposure levels from macro risk.</p>
          </article>
          <article class="card">
            <span class="card-num">04</span>
            <h3>Risk Cascade Curves</h3>
            <p>Relative strength ratios (ALT/BTC, BTC/SPY, IWM/SPY, HYG/IEF, XLU/SPY). See which asset class breaks first during risk escalation.</p>
          </article>
        </div>
      </div>
    </section>
    <section id="run" class="run">
      <div class="container">
        <h2>Run it yourself</h2>
        <p class="run-desc">Local-first. No recurring cost. Data from FRED (free API key) and Yahoo Finance.</p>
        <div class="code-block">
          <code>git clone https://github.com/CtrlAltDelegate/macro-dashboard.git</code><br>
          <code>cd macro-dashboard && pip install -r requirements.txt</code><br>
          <code># Add FRED_API_KEY to .env, then:</code><br>
          <code>streamlit run app.py</code>
        </div>
        <p class="run-note">Optional: schedule Tue/Fri refresh with Windows Task Scheduler to export PNGs to <code>exports/latest/</code>.</p>
      </div>
    </section>
    <footer class="footer">
      <div class="container">
        <p>Macro Dashboard · FRED + Yahoo Finance · Export PNG for newsletter</p>
        <p><a href="https://github.com/CtrlAltDelegate/macro-dashboard" target="_blank" rel="noopener">GitHub</a></p>
      </div>
    </footer>
  </main>
</body>
</html>
"""


def main() -> int:
    if (LANDING_SRC / "index.html").exists() and (LANDING_SRC / "style.css").exists():
        # Use source files if present
        PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        (PUBLIC_DIR / "index.html").write_text((LANDING_SRC / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
        (PUBLIC_DIR / "style.css").write_text((LANDING_SRC / "style.css").read_text(encoding="utf-8"), encoding="utf-8")
        print("Copied landing/ -> public/")
        return 0

    # Fallback: write embedded HTML (no CSS file if we only have HTML; we need both for styling)
    # Embed minimal CSS in a style tag so one file works
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    (PUBLIC_DIR / "index.html").write_text(HTML, encoding="utf-8")
    # Write CSS from embedded constant (same as landing/style.css)
    css_path = REPO_ROOT / "landing" / "style.css"
    if css_path.exists():
        (PUBLIC_DIR / "style.css").write_text(css_path.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        # Embedded fallback CSS so page still looks good
        (PUBLIC_DIR / "style.css").write_text(EMBEDDED_CSS, encoding="utf-8")
    print("Wrote public/ from embedded landing (landing/ not found)")
    return 0


EMBEDDED_CSS = r""":root{--bg:#0a0e14;--surface:#0d1117;--surface2:#161b22;--border:#30363d;--text:#e6edf3;--text-muted:#8b949e;--accent:#58a6ff;--font:"DM Sans",system-ui,sans-serif;--font-mono:"JetBrains Mono",monospace}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:var(--font);font-size:1rem;line-height:1.6;-webkit-font-smoothing:antialiased}.container{max-width:720px;margin:0 auto;padding:0 1.5rem}.header{position:sticky;top:0;z-index:10;background:rgba(10,14,20,.85);backdrop-filter:saturate(180%) blur(12px);border-bottom:1px solid var(--border)}.header .container{display:flex;align-items:center;justify-content:space-between;padding:.75rem 0}.logo{font-weight:700;font-size:1.1rem;color:var(--text);text-decoration:none;letter-spacing:-.02em}.nav{display:flex;align-items:center;gap:1.5rem}.nav a{color:var(--text-muted);text-decoration:none;font-size:.9rem;font-weight:500}.nav a:hover{color:var(--accent)}.btn{display:inline-block;padding:.5rem 1rem;border-radius:8px;font-size:.9rem;font-weight:600;text-decoration:none;transition:background .2s,color .2s}.btn-primary{background:var(--accent);color:var(--bg)}.btn-primary:hover{background:#79b8ff;color:var(--bg)}.btn-secondary{background:var(--surface2);color:var(--text);border:1px solid var(--border)}.btn-secondary:hover{background:var(--border);color:var(--text)}.btn-ghost{background:transparent;color:var(--text-muted)}.btn-ghost:hover{color:var(--accent)}.hero{padding:4rem 0 5rem}.hero-tag{font-size:.8rem;text-transform:uppercase;letter-spacing:.08em;color:var(--text-muted);margin-bottom:1rem}.hero h1{font-size:clamp(2rem,5vw,3rem);font-weight:700;letter-spacing:-.03em;line-height:1.15;margin:0 0 1.25rem;color:var(--text)}.hero-desc{color:var(--text-muted);font-size:1.05rem;max-width:540px;margin-bottom:2rem}.hero-actions{display:flex;flex-wrap:wrap;gap:.75rem}.features{padding:3rem 0 4rem;border-top:1px solid var(--border)}.features h2,.run h2{font-size:1.25rem;font-weight:600;color:var(--text);margin-bottom:1.5rem}.grid{display:grid;gap:1rem}.card{background:var(--surface2);border:1px solid var(--border);border-radius:12px;padding:1.5rem}.card-num{font-family:var(--font-mono);font-size:.75rem;font-weight:500;color:var(--accent);margin-bottom:.5rem}.card h3{font-size:1rem;font-weight:600;color:var(--text);margin:0 0 .5rem}.card p{font-size:.9rem;color:var(--text-muted);margin:0;line-height:1.5}.run{padding:3rem 0 4rem;border-top:1px solid var(--border)}.run-desc{color:var(--text-muted);margin-bottom:1rem}.code-block{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.25rem 1.5rem;font-family:var(--font-mono);font-size:.85rem;line-height:1.8;color:var(--text);overflow-x:auto}.code-block code{background:0 0;padding:0}.run-note{font-size:.9rem;color:var(--text-muted);margin-top:1rem}.run-note code{background:var(--surface2);padding:.15rem .4rem;border-radius:4px;font-size:.85em}.footer{padding:2rem 0;border-top:1px solid var(--border);text-align:center;font-size:.85rem;color:var(--text-muted)}.footer a{color:var(--accent);text-decoration:none}.footer a:hover{text-decoration:underline}.footer p{margin:.25rem 0}@media (min-width:640px){.grid{grid-template-columns:repeat(2,1fr)}}"""


if __name__ == "__main__":
    sys.exit(main())
