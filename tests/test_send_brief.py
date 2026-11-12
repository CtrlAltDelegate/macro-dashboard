import email

import pandas as pd
import pytest

import send_brief


@pytest.mark.parametrize("today,expected", [
    ("2026-11-16", "2026-11-13"),  # Mon → Fri
    ("2026-11-18", "2026-11-16"),  # Wed → Mon
    ("2026-11-20", "2026-11-18"),  # Fri → Wed
    ("2026-11-21", "2026-11-20"),  # Sat → Fri
])
def test_last_brief_date(today, expected):
    assert send_brief.last_brief_date(pd.Timestamp(today)) == pd.Timestamp(expected)


def _brief(ai=True, changes=True):
    return {
        "date": "2026-11-16",
        "since": pd.Timestamp("2026-11-13"),
        "snapshot": {"score": 41.2, "zone": "Moderate Risk",
                     "rows": [("Macro Risk", "41/100 (Moderate Risk)"), ("Sahm Rule", "0.27 (recession signal at 0.50)")]},
        "changes": [{"signal": "HY OAS", "now": "4.25%", "change": "+12bp",
                     "size_vs_typical": "large", "direction": "riskier"}] if changes else [],
        "headlines": [{"title": "Fed holds <rates>", "source": "Reuters", "date": "2026-11-15",
                       "link": "https://example.com/a", "summary": "Steady."}],
        "ai": {"executive_summary": "- Risk moderate\n- Credit widening", "what_to_watch": "Jobs data."} if ai else None,
        "ai_error": None,
        "pdf": b"%PDF-1.4 fake",
    }


def test_message_has_text_html_and_pdf():
    msg = send_brief.build_message(_brief(), "me@example.com", "me@example.com")
    assert msg["Subject"] == "[Macro Brief] 2026-11-16 - Macro Risk 41/100 vs. past year (Moderate Risk)"
    assert email.message_from_bytes(bytes(msg)).is_multipart()   # serializes cleanly
    msg_text = msg.get_body(("plain",)).get_content()
    msg_html = msg.get_body(("html",)).get_content()
    for body in (msg_text, msg_html):
        assert "HY OAS" in body and "+12bp" in body and "Credit widening" in body
        assert "relative, not absolute" in body and "past 12 months" in body
        assert "Sat" not in body
    assert "WHAT CHANGED SINCE FRI NOV 13" in msg_text
    assert "&lt;rates&gt;" in msg_html                      # headlines are escaped
    atts = list(msg.iter_attachments())
    assert [a.get_filename() for a in atts] == ["macro-brief-2026-11-16.pdf"]


def test_message_without_ai_or_changes():
    b = _brief(ai=False, changes=False)
    b["pdf"] = None
    msg = send_brief.build_message(b, "a@example.com", "b@example.com")
    body = msg.get_body(("plain",)).get_content()
    assert "No signals have new data since then." in body
    assert "AI INTERPRETATION" in body and "Unavailable" in body
    assert list(msg.iter_attachments()) == []


def test_gather_offline(fake_fred, no_ai, monkeypatch):
    import news
    monkeypatch.setattr(news, "fetch_recent_macro_news", lambda **k: [])
    brief = send_brief.gather("5y", with_pdf=False)
    rows = dict(brief["snapshot"]["rows"])
    assert "Macro Risk" in rows and "Yield Curve (10Y-3M)" in rows
    assert rows["Macro Risk"].endswith("of the past 12 months)")
    assert brief["ai"] is None and brief["pdf"] is None
    text = send_brief.render_text(brief)
    assert text.startswith("MACRO BRIEF") and "SNAPSHOT" in text


def test_dry_run_needs_no_smtp(fake_fred, no_ai, monkeypatch, tmp_path):
    import config
    import news
    monkeypatch.setattr(news, "fetch_recent_macro_news", lambda **k: [])
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path)
    monkeypatch.delenv("SMTP_USER", raising=False)
    assert send_brief.main(["--dry-run", "--no-pdf"]) == 0
    assert list((tmp_path / "brief").glob("*.eml"))


def test_dry_run_output_has_no_real_addresses(fake_fred, no_ai, monkeypatch, tmp_path):
    """Dry-run files become public workflow artifacts, so they must not contain the real addresses."""
    import config
    import news
    monkeypatch.setattr(news, "fetch_recent_macro_news", lambda **k: [])
    monkeypatch.setattr(config, "EXPORTS_DIR", tmp_path)
    monkeypatch.setenv("SMTP_USER", "real.sender@gmail.com")
    monkeypatch.setenv("BRIEF_TO", "real.inbox@gmail.com")
    assert send_brief.main(["--dry-run", "--no-pdf"]) == 0
    for f in (tmp_path / "brief").iterdir():
        text = f.read_bytes().decode("utf-8", "replace")
        assert "real.sender" not in text and "real.inbox" not in text, f.name
    sent = []
    monkeypatch.setattr(send_brief, "send", sent.append)
    assert send_brief.main(["--no-pdf"]) == 0                 # a real send still uses the real addresses
    assert sent[0]["From"] == "real.sender@gmail.com" and sent[0]["To"] == "real.inbox@gmail.com"
