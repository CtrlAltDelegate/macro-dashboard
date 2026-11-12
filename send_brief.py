"""
Email the Macro Brief (Mon/Wed/Fri via .github/workflows/brief.yml, or run by hand).

The email body carries the full brief as text (so an email-reading agent can use it without opening
attachments); the PDF with charts is attached as a backup for humans. Subject is always
"[Macro Brief] YYYY-MM-DD ..." so it is easy to filter on.

Env (or .env): FRED_API_KEY, CLAUDE_API_KEY (optional: no AI section without it),
SMTP_USER, SMTP_PASSWORD (Gmail App Password), BRIEF_TO; optional SMTP_HOST (smtp.gmail.com),
SMTP_PORT (465), BRIEF_FROM (defaults to SMTP_USER).

    python send_brief.py             # build and send
    python send_brief.py --dry-run   # build, write exports/brief/<date>.eml + .html, don't send
"""
from __future__ import annotations

import argparse
import html
import os
import smtplib
import ssl
import sys
from datetime import date
from email.message import EmailMessage
from typing import Any

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

import config

SUBJECT_TAG = "[Macro Brief]"
BRIEF_DAYS = (0, 2, 4)  # Mon, Wed, Fri

AI_SECTIONS = (
    ("executive_summary", "Executive summary"),
    ("what_changed", "What changed (AI read)"),
    ("what_to_watch", "What to watch"),
    ("drivers_paragraph", "Headlines in context"),
    ("chart_insights", "What the charts say"),
    ("asset_implications", "Asset implications (not investment advice)"),
)


def last_brief_date(today: pd.Timestamp | None = None) -> pd.Timestamp:
    """Most recent Mon/Wed/Fri strictly before today: the previous brief, for "what changed"."""
    d = (today or pd.Timestamp.today()).normalize() - pd.Timedelta(days=1)
    while d.weekday() not in BRIEF_DAYS:
        d -= pd.Timedelta(days=1)
    return d


def _last(s: pd.Series | None) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if not s.empty else None


def _col(df: pd.DataFrame, col: str) -> pd.Series | None:
    return df[col].dropna() if not df.empty and col in df.columns else None


def snapshot_rows(*, thermo: pd.Series, liquidity_yoy: float | None, yield_df: pd.DataFrame,
                  risk_df: pd.DataFrame, net_liquidity: float | None, sahm: float | None) -> dict[str, Any]:
    """Headline readings with the dashboard's status labels. Returns {"rows": [(label, value)], **raw}."""
    from models import risk_zone, latest_change

    rows: list[tuple[str, str]] = []
    raw: dict[str, Any] = {}
    score = _last(thermo)
    if score is not None:
        raw["score"], raw["zone"] = score, risk_zone(score)
        rows.append(("Macro Risk", f"{score:.0f}/100 ({raw['zone']})"))
    if liquidity_yoy is not None:
        raw["liquidity_status"] = "Expanding" if liquidity_yoy >= 0 else "Contracting"
        rows.append(("Liquidity (Fed balance sheet, YoY)", f"{liquidity_yoy:+.1f}% ({raw['liquidity_status']})"))
    if net_liquidity is not None:
        rows.append(("Net Liquidity", f"${net_liquidity / 1e6:.2f}T"))
    d10, d3m = _col(yield_df, "DGS10"), _col(yield_df, "DGS3MO")
    if d10 is not None and d3m is not None:
        spread = d10.sub(d3m).dropna()
        if not spread.empty:
            raw["spread"] = float(spread.iloc[-1])
            raw["yield_status"] = "Inverted" if raw["spread"] < 0 else "Normal"
            raw["spread_roc_90"] = latest_change(spread, pd.Timedelta(days=90), pct=False)
            rows.append(("Yield Curve (10Y-3M)", f"{raw['spread']:.2f}% ({raw['yield_status']})"))
    t102 = _last(_col(yield_df, "T10Y2Y"))
    if t102 is not None:
        rows.append(("Yield Curve (10Y-2Y)", f"{t102:.2f}%"))
    hy = _last(_col(risk_df, "CREDIT_STRESS"))
    if hy is not None:
        raw["hy"] = hy
        raw["credit_status"] = "Low" if hy < 4 else "Moderate" if hy < 6 else "High"
        rows.append(("Credit Stress (HY spread)", f"{hy:.2f}% ({raw['credit_status']})"))
    nfci = _last(_col(risk_df, "CREDIT_TIGHTENING"))
    if nfci is not None:
        raw["fci_status"] = "Tight" if nfci > 0 else "Easy"
        rows.append(("Financial Conditions (NFCI)", f"{nfci:.2f} ({raw['fci_status']})"))
    if sahm is not None:
        rows.append(("Sahm Rule", f"{sahm:.2f} (recession signal at 0.50)"))
    raw["rows"] = rows
    return raw


def gather(lookback: str = "5y", *, with_pdf: bool = True) -> dict[str, Any]:
    """Fetch data, compute signals and changes, headlines, AI summary and (optionally) the PDF."""
    from data import (fetch_valuation_data, fetch_macro_risk_data, fetch_yield_curve_data,
                      fetch_liquidity_data, fetch_model_input_series, fetch_recession_periods,
                      fetch_rotation_ladder_data)
    from models import (compute_risk_model, warmup_start, yoy_fetch_start, collect_signals,
                        signal_changes, change_over, compute_net_liquidity)
    from ai_summary import build_macro_signal_payload, changes_for_prompt, generate_ai_summary

    if not config.FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY not set")
    obs_start = config.lookback_to_observation_start(lookback)
    year_before = yoy_fetch_start(obs_start)
    val_full = fetch_valuation_data(observation_start=year_before)
    risk_full = fetch_macro_risk_data(observation_start=warmup_start(obs_start))
    yield_df = fetch_yield_curve_data(observation_start=obs_start)
    liquidity_full = fetch_liquidity_data(observation_start=year_before)
    model_inputs = fetch_model_input_series(observation_start=year_before) or {}

    start = pd.Timestamp(obs_start) if obs_start else None
    risk_df = risk_full[risk_full.index >= start] if start is not None else risk_full
    val_df = val_full[val_full.index >= start] if start is not None else val_full
    _, thermo = compute_risk_model(risk_full, obs_start)

    liq_yoy = None
    if not liquidity_full.empty and "WALCL" in liquidity_full.columns:
        liq_yoy = _last(change_over(liquidity_full["WALCL"]))
    net_liq = None
    try:
        net_liq = _last(compute_net_liquidity(liquidity_full))
    except Exception:
        pass
    snap = snapshot_rows(thermo=thermo, liquidity_yoy=liq_yoy, yield_df=yield_df, risk_df=risk_df,
                         net_liquidity=net_liq, sahm=_last(model_inputs.get("SAHMREALTIME")))

    today = pd.Timestamp(date.today())
    since = last_brief_date(today)
    signals = collect_signals(val_df=val_df, risk_full=risk_full, yield_df=yield_df,
                              liquidity_full=liquidity_full, model_inputs=model_inputs, thermo=thermo)
    moves = signal_changes(signals, since) if signals else []

    try:
        from news import fetch_recent_macro_news, rank_macro_relevance
        headlines = rank_macro_relevance(fetch_recent_macro_news(max_articles=12, max_age_days=7), max_return=5)
    except Exception as e:
        print(f"Headlines unavailable: {e}", file=sys.stderr)
        headlines = []

    payload = build_macro_signal_payload(
        macro_risk_score=snap.get("score"), macro_risk_zone=snap.get("zone"),
        liquidity_yoy=liq_yoy,
        liquidity_trend={"Expanding": "improving", "Contracting": "contracting"}.get(snap.get("liquidity_status")),
        yield_curve_spread=snap.get("spread"), yield_curve_state=snap.get("yield_status"),
        yield_curve_momentum=snap.get("spread_roc_90"),
        credit_spread=snap.get("hy"), credit_stress_state=snap.get("credit_status"),
        financial_conditions=snap.get("fci_status"), spx_regime_zone=snap.get("zone"),
        readings={s.label: s.fmt.format(s.series.iloc[-1]) for s in signals},
        changes=changes_for_prompt(moves), changes_since=f"{since:%Y-%m-%d}",
    )
    ai = generate_ai_summary(payload, headlines, today.date().isoformat())
    if ai and ai.get("_error"):
        print(f"AI summary failed: {ai['_error']}", file=sys.stderr)

    brief = {
        "date": today.date().isoformat(),
        "since": since,
        "snapshot": snap,
        "changes": changes_for_prompt(moves, limit=12),
        "headlines": headlines,
        "ai": ai if ai and not ai.get("_error") else None,
        "ai_error": ai.get("_error") if ai else None,
        "pdf": None,
    }
    if with_pdf:
        try:
            brief["pdf"] = _build_pdf(brief, lookback, val_full, risk_full, risk_df, yield_df, liquidity_full,
                                      thermo, model_inputs, obs_start, fetch_rotation_ladder_data,
                                      fetch_recession_periods)
        except Exception as e:  # the email still goes out without the attachment
            print(f"PDF build failed: {e}", file=sys.stderr)
    return brief


def _build_pdf(brief, lookback, val_full, risk_full, risk_df, yield_df, liquidity_full, thermo,
               model_inputs, obs_start, fetch_ladder, fetch_recessions) -> bytes:
    from charts.build import build_all_charts, add_recession_shading, build_macro_radar_chart
    from pdf_report import build_dashboard_pdf
    from plotly_export import export_plotly_to_png_or_error
    from models import compute_risk_model
    from refresh import EXPORT_NAMES

    try:
        ladder_df = fetch_ladder(start=obs_start)
    except Exception:
        ladder_df = pd.DataFrame()
    composite, _ = compute_risk_model(risk_full, obs_start)
    figs = build_all_charts(val_full, risk_df, yield_df, liquidity_full, ladder_df, show_event_markers=False,
                            composite=composite, thermo=thermo, display_start=obs_start,
                            ig_series=model_inputs.get("BAMLC0A0CM"))
    try:
        recessions = fetch_recessions(observation_start=obs_start)
        for fig in figs:
            add_recession_shading(fig, recessions)
    except Exception:
        pass

    snap = brief["snapshot"]
    summary = {
        "type": "summary",
        "report_date": brief["date"],
        "lookback_label": lookback,
        "snapshot": {"extra": snap["rows"]},
        "radar_fig": build_macro_radar_chart(risk_df, liquidity_full, yield_df, thermo),
        "ai_summary": brief["ai"],
        "macro_drivers": brief["headlines"],
        "changes_since": f"{brief['since']:%a %b} {brief['since'].day}",
        "changes": brief["changes"],
    }
    charts = [
        {"type": "chart", "title": name[3:-4].replace("_", " ").title(), "fig": fig}
        for fig, name in zip(figs, EXPORT_NAMES) if fig is not None
    ]
    export = lambda f: export_plotly_to_png_or_error(f, width=800, height=450)[0]  # noqa: E731
    return build_dashboard_pdf([summary] + charts, report_date=brief["date"], lookback_label=lookback,
                               export_fn=export)


# ---------- rendering

def subject(brief: dict) -> str:
    snap = brief["snapshot"]
    tail = f" - Macro Risk {snap['score']:.0f}/100 ({snap['zone']})" if snap.get("score") is not None else ""
    return f"{SUBJECT_TAG} {brief['date']}{tail}"


def _since_text(brief: dict) -> str:
    s = brief["since"]
    return f"{s:%a %b} {s.day}"


def render_text(brief: dict) -> str:
    out = [f"MACRO BRIEF - {brief['date']}", ""]
    out += ["SNAPSHOT"] + [f"- {k}: {v}" for k, v in brief["snapshot"]["rows"]] + [""]
    out.append(f"WHAT CHANGED SINCE {_since_text(brief).upper()}")
    if brief["changes"]:
        for c in brief["changes"]:
            extra = ", ".join(x for x in (c.get("size_vs_typical") and f"{c['size_vs_typical']} move",
                                          c.get("direction")) if x)
            out.append(f"- {c['signal']}: {c['now']} ({c['change']}{'; ' + extra if extra else ''})")
    else:
        out.append("- No signals have new data since then.")
    out.append("")
    ai = brief["ai"]
    if ai:
        for key, title in AI_SECTIONS:
            if ai.get(key):
                out += [title.upper(), ai[key].strip(), ""]
    else:
        out += ["AI INTERPRETATION", f"Unavailable{': ' + brief['ai_error'] if brief.get('ai_error') else ''}.", ""]
    if brief["headlines"]:
        out.append("HEADLINES")
        for a in brief["headlines"]:
            out.append(f"- {a.get('title', '')} ({a.get('source', '')}, {a.get('date', '')})")
            if a.get("summary"):
                out.append(f"  {a['summary']}")
            if a.get("link"):
                out.append(f"  {a['link']}")
        out.append("")
    out.append("Full brief with charts attached as PDF. Data: FRED, Yahoo Finance. Not investment advice.")
    return "\n".join(out)


def render_html(brief: dict) -> str:
    e = html.escape

    def para(text: str) -> str:
        return "<br>".join(e(line) for line in text.strip().splitlines())

    rows = "".join(f"<tr><td style='padding:2px 12px 2px 0'><b>{e(k)}</b></td><td>{e(v)}</td></tr>"
                   for k, v in brief["snapshot"]["rows"])
    parts = [f"<h2>Macro Brief - {e(brief['date'])}</h2>", "<h3>Snapshot</h3>", f"<table>{rows}</table>",
             f"<h3>What changed since {e(_since_text(brief))}</h3>"]
    if brief["changes"]:
        head = "<tr><th align='left'>Signal</th><th align='left'>Now</th><th align='left'>Change</th>" \
               "<th align='left'>vs. typical</th><th align='left'>Direction</th></tr>"
        body = "".join(
            f"<tr><td>{e(c['signal'])}</td><td>{e(c['now'])}</td><td>{e(c['change'])}</td>"
            f"<td>{e(c.get('size_vs_typical', '-'))}</td><td>{e(c.get('direction', '-'))}</td></tr>"
            for c in brief["changes"])
        parts.append(f"<table cellpadding='3'>{head}{body}</table>")
    else:
        parts.append("<p>No signals have new data since then.</p>")
    ai = brief["ai"]
    if ai:
        for key, title in AI_SECTIONS:
            if ai.get(key):
                parts += [f"<h3>{e(title)}</h3>", f"<p>{para(ai[key])}</p>"]
    else:
        parts.append("<h3>AI interpretation</h3><p>Unavailable.</p>")
    if brief["headlines"]:
        items = "".join(
            f"<li><a href='{e(a.get('link', ''))}'>{e(a.get('title', ''))}</a> ({e(a.get('source', ''))}, "
            f"{e(a.get('date', ''))})<br>{e(a.get('summary', ''))}</li>" for a in brief["headlines"])
        parts += ["<h3>Headlines</h3>", f"<ul>{items}</ul>"]
    parts.append("<p style='color:#888'>Full brief with charts attached as PDF. Data: FRED, Yahoo Finance. "
                 "Not investment advice.</p>")
    return "<html><body style='font-family:Arial,sans-serif;font-size:14px'>" + "".join(parts) + "</body></html>"


def build_message(brief: dict, sender: str, to: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject(brief)
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(render_text(brief))
    msg.add_alternative(render_html(brief), subtype="html")
    if brief.get("pdf"):
        msg.add_attachment(brief["pdf"], maintype="application", subtype="pdf",
                           filename=f"macro-brief-{brief['date']}.pdf")
    return msg


def send(msg: EmailMessage) -> None:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "465"))
    user, password = os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", "")
    if not user or not password:
        raise RuntimeError("SMTP_USER / SMTP_PASSWORD not set")
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(user, password)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=ctx)
            s.login(user, password)
            s.send_message(msg)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="write .eml/.html to exports/brief/ instead of sending")
    ap.add_argument("--no-pdf", action="store_true", help="skip the PDF attachment (faster)")
    ap.add_argument("--to", default=os.getenv("BRIEF_TO", ""), help="recipient (default: BRIEF_TO)")
    ap.add_argument("--lookback", default="5y", choices=config.LOOKBACK_OPTIONS)
    args = ap.parse_args(argv)

    sender = os.getenv("BRIEF_FROM") or os.getenv("SMTP_USER", "")
    if not args.dry_run and not (args.to and sender):
        print("Set BRIEF_TO and SMTP_USER (or BRIEF_FROM).", file=sys.stderr)
        return 1
    try:
        brief = gather(args.lookback, with_pdf=not args.no_pdf)
    except Exception as e:
        print(f"Brief failed: {e}", file=sys.stderr)
        return 1
    if args.dry_run:
        # Placeholder addresses: dry-run output is uploaded as a workflow artifact, which is public in a
        # public repo (secret masking covers logs, not artifacts).
        msg = build_message(brief, "sender@example.com", "recipient@example.com")
        out = config.EXPORTS_DIR / "brief"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{brief['date']}.eml").write_bytes(bytes(msg))
        (out / f"{brief['date']}.html").write_text(render_html(brief), encoding="utf-8")
        print(f"Dry run: wrote {out / brief['date']}.eml/.html  Subject: {msg['Subject']}")
        return 0
    msg = build_message(brief, sender, args.to)
    send(msg)
    print(f"Sent: {msg['Subject']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
