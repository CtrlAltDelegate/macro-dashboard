"""
Macro Drivers: fetch and rank recent macro-relevant headlines from reputable RSS feeds.
No API key required. Used to support the AI interpretation layer and PDF report.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

# RSS feeds: reputable business/macro sources (no auth)
MACRO_RSS_FEEDS = [
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Reuters", "https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("NPR Business", "https://feeds.npr.org/1006/rss.xml"),
]

# Keywords that suggest macro relevance (Fed, rates, inflation, labor, etc.)
MACRO_KEYWORDS = re.compile(
    r"\b(fed|federal reserve|interest rate|inflation|cpi|employment|unemployment|"
    r"jobless|jobs report|gdp|recession|treasury|debt|deficit|"
    r"oil|energy|crude|opec|credit|bank|ecb|central bank|"
    r"monetary|fiscal|stimulus|taper|qt|qe)\b",
    re.I,
)


def _normalize_title(s: str) -> str:
    if not s or not isinstance(s, str):
        return ""
    return re.sub(r"\s+", " ", s).strip()[:200]


def _snippet(desc: str, max_len: int = 180) -> str:
    if not desc or not isinstance(desc, str):
        return ""
    # Strip HTML
    text = re.sub(r"<[^>]+>", " ", desc)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rsplit(" ", 1)[0] + "..."


def _parse_date(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, key, None)
        if val and len(val) >= 6:
            try:
                return datetime(*val[:6])
            except Exception:
                pass
    return None


def fetch_recent_macro_news(
    max_articles: int = 12,
    max_age_days: int = 7,
) -> list[dict[str, str]]:
    """
    Fetch recent headlines from macro RSS feeds. Rank by recency and macro relevance.
    Returns list of dicts: title, source, date (iso), link, summary (1–2 sentences).
    """
    try:
        import feedparser
    except ImportError:
        return []

    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    candidates: list[tuple[datetime | None, str, dict]] = []

    for source_name, url in MACRO_RSS_FEEDS:
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "MacroDashboard/1.0"})
        except Exception:
            continue
        for entry in feed.entries[:15]:
            title = _normalize_title(entry.get("title") or "")
            if not title:
                continue
            link = (entry.get("link") or "").strip()
            desc = entry.get("summary", entry.get("description", ""))
            summary = _snippet(desc)
            pub = _parse_date(entry)
            # Prefer macro-relevant
            score = 1 if MACRO_KEYWORDS.search(title + " " + summary) else 0
            # Recency: newer = better
            if pub and pub.tzinfo:
                from datetime import timezone
                pub_utc = pub.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                pub_utc = pub
            if pub_utc and pub_utc < cutoff:
                continue
            candidates.append((pub_utc, title, {
                "title": title,
                "source": source_name,
                "date": pub_utc.strftime("%Y-%m-%d") if pub_utc else "",
                "link": link,
                "summary": summary or "No summary.",
                "score": score,
            }))
        # end entries
    # end feeds

    # Dedupe by normalized title
    seen: set[str] = set()
    unique: list[tuple[datetime | None, str, dict]] = []
    for pub, title, d in candidates:
        key = title.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        unique.append((pub, title, d))

    # Sort: macro-relevant first, then by date (newest first)
    def _sort_key(x):
        pt = x[0]
        ts = pt.timestamp() if pt else 0.0
        return (-x[2].get("score", 0), -ts)
    unique.sort(key=_sort_key)

    out: list[dict[str, str]] = []
    for _pub, _title, d in unique[:max_articles]:
        out.append({k: v for k, v in d.items() if k != "score"})
    return out


def rank_macro_relevance(
    articles: list[dict[str, str]],
    max_return: int = 5,
) -> list[dict[str, str]]:
    """
    Rank and dedupe articles for diversity (prefer different sources/topics).
    Returns up to max_return articles.
    """
    if len(articles) <= max_return:
        return articles
    # Prefer diversity: take by source round-robin then fill
    by_source: dict[str, list[dict]] = {}
    for a in articles:
        src = a.get("source") or "Other"
        by_source.setdefault(src, []).append(a)
    result: list[dict[str, str]] = []
    used_sources: set[str] = set()
    while len(result) < max_return and (by_source or result):
        for src in list(by_source.keys()):
            if not by_source[src]:
                del by_source[src]
                continue
            result.append(by_source[src].pop(0))
            if len(result) >= max_return:
                break
        if len(result) >= max_return:
            break
        # If we've gone through and didn't add enough, take rest by order
        if not by_source:
            break
    return result[:max_return]
