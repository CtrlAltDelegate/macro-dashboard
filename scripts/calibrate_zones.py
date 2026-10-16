"""
Check whether the Market Risk Level zones separate stock-market outcomes.

Computes the risk model over full FRED history, then the S&P 500's forward 3/6/12-month returns and worst
6-month drawdown after each week in each zone. Prints a markdown table and writes exports/zone_calibration.md.

Run from the project root (needs FRED_API_KEY; S&P 500 history comes from Yahoo Finance):

    python scripts/calibrate_zones.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import config  # noqa: E402
from data import fetch_macro_risk_data  # noqa: E402
from data.market_data import _download, _extract_closes  # noqa: E402
from models import compute_risk_model  # noqa: E402
from models.calibration import stats_markdown, zone_forward_stats  # noqa: E402


def main() -> int:
    if not config.FRED_API_KEY:
        print("FRED_API_KEY not set. Set it in .env or environment.", file=sys.stderr)
        return 1
    print("Fetching full FRED history for the risk model...")
    risk_full = fetch_macro_risk_data(observation_start=None)
    _composite, thermo = compute_risk_model(risk_full, None)
    if thermo.empty:
        print("Risk model returned no data.", file=sys.stderr)
        return 1
    print("Fetching S&P 500 history (Yahoo ^GSPC)...")
    spx = _extract_closes(_download(["^GSPC"], None), ["^GSPC"])
    if spx.empty:
        print("Could not load S&P 500 history from Yahoo Finance.", file=sys.stderr)
        return 1
    table = zone_forward_stats(thermo, spx["^GSPC"])
    title = (f"Market Risk Level zones vs. S&P 500 outcomes "
             f"({thermo.index[0]:%Y}–{thermo.index[-1]:%Y}, weekly, run {date.today().isoformat()})")
    md = stats_markdown(table, title) + (
        "\nForward returns are price-only (no dividends). FRED serves revised data, and overlapping windows "
        "make weeks non-independent — treat this as descriptive, not a backtest.\n"
    )
    print(md)
    out = config.EXPORTS_DIR / "zone_calibration.md"
    out.write_text(md, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
