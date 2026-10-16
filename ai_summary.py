"""
Lightweight LLM interpretation layer for the Macro Dashboard.
Uses compact signal payload + news headlines only. Strict token limits and caching.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

import config

# Token guardrails
MAX_INPUT_TOKENS = 1800
MAX_OUTPUT_TOKENS = 800

# Anthropic retires dated model IDs; alias + fallbacks avoid 404 not_found_error
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5"
_MODEL_FALLBACKS = (
    "claude-3-5-haiku-latest",
    "claude-sonnet-4-20250514",
)


def claude_api_key() -> str:
    """Anthropic key from env/.env/Streamlit Secrets: CLAUDE_API_KEY, else ANTHROPIC_API_KEY ('' if unset)."""
    return config.get_secret("CLAUDE_API_KEY") or config.get_secret("ANTHROPIC_API_KEY")


def _is_model_not_found(err: Exception) -> bool:
    s = str(err).lower()
    return "404" in str(err) or "not_found" in s or "not found" in s

# Cache: key by (report_date, hash(signals + headlines))
def _cache_key(signals: dict, news: list) -> str:
    raw = json.dumps({"s": signals, "n": [a.get("title", "") for a in news]}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_macro_signal_payload(
    *,
    macro_risk_score: float | None = None,
    macro_risk_zone: str | None = None,
    liquidity_yoy: float | None = None,
    liquidity_trend: str | None = None,
    yield_curve_spread: float | None = None,
    yield_curve_state: str | None = None,
    yield_curve_momentum: float | None = None,
    credit_spread: float | None = None,
    credit_stress_state: str | None = None,
    financial_conditions: str | None = None,
    spx_regime_zone: str | None = None,
    btc_price: float | None = None,
    btc_zone: str | None = None,
    oil_price: float | None = None,
    oil_roc_1y: float | None = None,
    deficit_pct_gdp: float | None = None,
    debt_to_gdp: float | None = None,
    interest_burden_pct: float | None = None,
    readings: dict[str, str] | None = None,
    changes: list[dict[str, Any]] | None = None,
    changes_since: str | None = None,
) -> dict[str, Any]:
    """Build a compact payload for the LLM. Only numbers and short labels.

    readings: extra current values already formatted for display, e.g. {"Sahm Rule": "0.27", "VIX": "17.0"}.
    changes / changes_since: output of changes_for_prompt() — what actually moved since a reference date.
    """
    payload: dict[str, Any] = {}
    if macro_risk_score is not None:
        payload["macro_risk_score"] = round(macro_risk_score, 0)
    if macro_risk_zone:
        payload["macro_risk_zone"] = macro_risk_zone
    if liquidity_yoy is not None:
        payload["liquidity_yoy"] = round(liquidity_yoy, 1)
    if liquidity_trend:
        payload["liquidity_trend"] = liquidity_trend
    if yield_curve_spread is not None:
        payload["yield_curve_spread"] = round(yield_curve_spread, 2)
    if yield_curve_state:
        payload["yield_curve_state"] = yield_curve_state
    if yield_curve_momentum is not None:
        payload["yield_curve_momentum"] = round(yield_curve_momentum, 2)
    if credit_spread is not None:
        payload["credit_spread"] = round(credit_spread, 1)
    if credit_stress_state:
        payload["credit_stress_state"] = credit_stress_state
    if financial_conditions:
        payload["financial_conditions"] = financial_conditions
    if spx_regime_zone:
        payload["spx_regime_zone"] = spx_regime_zone
    if btc_price is not None:
        payload["btc_price"] = round(btc_price, 0)
    if btc_zone:
        payload["btc_zone"] = btc_zone
    if oil_price is not None:
        payload["oil_price"] = round(oil_price, 1)
    if oil_roc_1y is not None:
        payload["oil_roc_1y"] = round(oil_roc_1y, 1)
    if deficit_pct_gdp is not None:
        payload["deficit_pct_gdp"] = round(deficit_pct_gdp, 1)
    if debt_to_gdp is not None:
        payload["debt_to_gdp"] = round(debt_to_gdp, 1)
    if interest_burden_pct is not None:
        payload["interest_burden_pct"] = round(interest_burden_pct, 1)
    if readings:
        payload["readings"] = readings
    if changes_since:
        payload["changes_since"] = changes_since
        payload["changes"] = changes or []
    return payload


def changes_for_prompt(changes: list, limit: int = 8) -> list[dict[str, Any]]:
    """Compact form of models.signals.SignalChange list (largest unusual moves first) for the LLM."""
    out = []
    for c in changes[:limit]:
        item = {"signal": c.label, "now": c.now_text, "change": c.delta_text}
        if c.zscore is not None:
            item["size_vs_typical"] = "large" if abs(c.zscore) >= 2 else "notable" if abs(c.zscore) >= 1 else "normal"
        if c.worse is not None:
            item["direction"] = "riskier" if c.worse else "safer"
        out.append(item)
    return out


def _read_cache(report_date: str, key: str) -> dict | None:
    path = config.CACHE_DIR / "ai_summary" / f"{report_date}_{key}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_cache(report_date: str, key: str, data: dict) -> None:
    out_dir = config.CACHE_DIR / "ai_summary"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{report_date}_{key}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=0)
    except Exception:
        pass


def generate_ai_summary(
    signals: dict[str, Any],
    news_items: list[dict[str, str]],
    report_date: str | None = None,
    *,
    force_refresh: bool = False,
) -> dict[str, str] | None:
    """
    Generate executive summary, what changed, what to watch, and optional drivers paragraph.
    Uses a single low-cost LLM call. Cached by (report_date, content hash).
    Returns None if no API key or on error.
    """
    report_date = report_date or date.today().isoformat()
    key = _cache_key(signals, news_items)
    if not force_refresh:
        cached = _read_cache(report_date, key)
        if cached:
            return cached

    api_key = claude_api_key()
    if not api_key:
        return None

    # Build compact prompt; changes get their own section so "what changed" is grounded in real moves
    current = {k: v for k, v in signals.items() if k not in ("changes", "changes_since")}
    signals_str = json.dumps(current, indent=0)
    if signals.get("changes_since"):
        changes_str = (f"Since {signals['changes_since']} (largest moves relative to normal first):\n"
                       + json.dumps(signals.get("changes") or [], indent=0))
    else:
        changes_str = "Not provided."
    news_str = ""
    for i, a in enumerate(news_items[:5], 1):
        news_str += f"{i}. [{a.get('source','')}] {a.get('title','')}\n   {a.get('summary','')}\n"
    prompt = f"""You are a calm macro research assistant. Based ONLY on the following compact macro signals and headlines, write a brief interpretation. No hype, no dramatic certainty, plain English (10th-grade level). Do not make up numbers.

MACRO SIGNALS (current readings):
{signals_str}

CHANGES (computed from the data):
{changes_str}

RECENT HEADLINES:
{news_str}

Respond with exactly this JSON (no other text):
{{
  "executive_summary": "3-6 bullet points, max 120 words total. One line per point.",
  "what_changed": "2-4 sentences on what moved, using ONLY the CHANGES section (say the reference date; lead with 'large' moves). If CHANGES is empty or not provided, say that no major signals moved. Max 80 words.",
  "what_to_watch": "2-3 sentences on what to watch next, max 60 words.",
  "drivers_paragraph": "One short paragraph linking headlines to chart signals when relevant, or empty string if not useful.",
  "chart_insights": "3-5 short bullet points: what the key charts (liquidity and net liquidity, macro risk, yield curve 10Y-3M and 10Y-2Y, credit spreads, financial conditions, labor incl. the Sahm rule, rotation) say about today's economy. Reference specific signals from the payload. Max 150 words total.",
  "asset_implications": "One short paragraph (2-4 sentences): Given current conditions, what asset class tilts or pivots might be worth considering? Phrase as thoughtful interpretation, e.g. 'Due to [X], one might consider tilting toward [Y].' Reference specific signals. Not investment advice. Max 100 words."
}}"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        primary = (config.get_secret("CLAUDE_MODEL") or DEFAULT_CLAUDE_MODEL).strip()
        models_to_try = [primary]
        for m in _MODEL_FALLBACKS:
            if m not in models_to_try:
                models_to_try.append(m)

        content = ""
        last_err: Exception | None = None
        for model in models_to_try:
            try:
                msg = client.messages.create(
                    model=model,
                    max_tokens=MAX_OUTPUT_TOKENS,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}],
                )
                block = msg.content[0]
                content = (getattr(block, "text", "") or "").strip()
                break
            except Exception as e:
                if _is_model_not_found(e):
                    last_err = e
                    continue
                return {"_error": str(e)}
        if not content:
            return {"_error": str(last_err) if last_err else "No response from Claude"}

        # Extract JSON (handle optional markdown code block)
        if "```" in content:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                content = content[start:end]
        data = json.loads(content)

        def _to_str(v: Any) -> str:
            if v is None:
                return ""
            if isinstance(v, str):
                return v.strip()
            if isinstance(v, list):
                return "\n".join(str(x).strip() for x in v if str(x).strip()).strip()
            return str(v).strip()

        out = {
            "executive_summary": _to_str(data.get("executive_summary")),
            "what_changed": _to_str(data.get("what_changed")),
            "what_to_watch": _to_str(data.get("what_to_watch")),
            "drivers_paragraph": _to_str(data.get("drivers_paragraph")),
            "chart_insights": _to_str(data.get("chart_insights")),
            "asset_implications": _to_str(data.get("asset_implications")),
        }
        _write_cache(report_date, key, out)
        return out
    except Exception as e:
        return {"_error": str(e)}


def ai_summary_available() -> bool:
    """True if CLAUDE_API_KEY (or ANTHROPIC_API_KEY) is set."""
    return bool(claude_api_key())
