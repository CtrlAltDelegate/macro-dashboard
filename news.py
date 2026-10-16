"""
Macro Drivers: fetch and rank recent macro-relevant headlines from reputable RSS feeds.
No API key required. Used to support the AI interpretation layer and PDF report.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

log = logging.getLogger(__name__)

# RSS feeds: reputable business/macro sources (no auth). Third field: every item is macro-relevant
# (skip the keyword filter) — Fed press releases often have titles like "Minutes of ... meetings".
MACRO_RSS_FEEDS = [
    ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", False),
    ("CNBC Economy", "https://www.cnbc.com/id/20910258/device/rss/rss.html", False),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", False),
    ("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml", True),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", False),
    ("NPR Business", "https://feeds.npr.org/1006/rss.xml", False),
]
FEED_TIMEOUT_S = 6

# Keywords that suggest macro relevance (Fed, rates, inflation, labor, etc.)
# Specific macro terms only: bare words like "bank", "debt" or "credit" matched company news
# (e.g. a bank's earnings or a personal-finance column).
MACRO_KEYWORDS = re.compile(
    r"\b(fed|federal reserve|fomc|powell|interest rates?|rate (?:cut|hike)s?|inflation|cpi|pce|"
    r"unemployment|jobless|jobs report|payrolls|labor market|gdp|recession|economy|economic|"
    r"treasur(?:y|ies) (?:yields?|market)|bond (?:yields?|market)|yield curve|"
    r"national debt|debt ceiling|budget deficit|fiscal|stimulus|tariffs?|trade war|"
    r"crude|oil prices?|opec|ecb|central banks?|monetary policy|quantitative (?:easing|tightening)|"
    r"retail sales|consumer spending|housing starts|credit spreads?|"
    # the currency, not "multimillion-dollar"
    r"(?<![-\w])(?:the|u\.s\.|us|strong(?:er)?|weak(?:er)?) dollar|dollar index)\b",
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


def _fetch_feed(url: str) -> list:
    """One feed's entries ([] on any failure). requests gives us a timeout; feedparser alone can hang."""
    import feedparser
    import requests

    try:
        resp = requests.get(url, timeout=FEED_TIMEOUT_S, headers={"User-Agent": "MacroDashboard/1.0"})
        resp.raise_for_status()
        return feedparser.parse(resp.content).entries
    except Exception as e:
        log.warning("RSS feed failed %s: %s", url, e)
        return []


def fetch_recent_macro_news(
    max_articles: int = 12,
    max_age_days: int = 7,
) -> list[dict[str, str]]:
    """
    Fetch recent headlines from macro RSS feeds. Rank by recency and macro relevance.
    Returns list of dicts: title, source, date (iso), link, summary (1–2 sentences).
    """
    try:
        import feedparser  # noqa: F401
    except ImportError:
        return []

    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    candidates: list[tuple[datetime | None, str, dict]] = []

    # All feeds at once: total time ≈ the slowest feed, not the sum
    with ThreadPoolExecutor(max_workers=len(MACRO_RSS_FEEDS)) as pool:
        entries_by_feed = list(pool.map(lambda feed: _fetch_feed(feed[1]), MACRO_RSS_FEEDS))

    for (source_name, _url, always_macro), entries in zip(MACRO_RSS_FEEDS, entries_by_feed):
        for entry in entries[:15]:
            title = _normalize_title(entry.get("title") or "")
            if not title:
                continue
            link = (entry.get("link") or "").strip()
            desc = entry.get("summary", entry.get("description", ""))
            summary = _snippet(desc)
            pub = _parse_date(entry)
            # Prefer macro-relevant
            if not always_macro and not MACRO_KEYWORDS.search(title + " " + summary):
                continue
            score = 2 if always_macro or MACRO_KEYWORDS.search(title) else 1  # macro term in the headline ranks first
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
