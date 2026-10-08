"""Google News RSS source: one adapter, two modes.

  * search  — params.queries: list of search strings -> rss/search?q=...
  * section — params.topic:   a Google News topic like NATION/WORLD/BUSINESS/TECHNOLOGY,
              or params.feed_url for an explicit endpoint (e.g. top stories).

No API key required. Uses feedparser. Results are filtered to params.lookback_days and
capped at params.max_items (per query for search mode; total for section mode).
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import time
import urllib.parse
import urllib.request

import feedparser

from sources.base import Source, Story, register_source

log = logging.getLogger("daily-news.sources.gnews")

# Google News serves its RSS differently to datacenter IPs (GCP/AWS) than to residential ones:
# with feedparser's default User-Agent it returns an empty feed (0 entries) from Cloud Run, even
# though the same URL works from a laptop. A browser UA + the EU-consent cookie (harmless in the
# US, required in some regions) makes it serve real content. See fetch() below.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
# "YES+" pre-accepts Google's consent interstitial so the RSS endpoint returns the feed, not a
# consent redirect page.
_CONSENT_COOKIE = "CONSENT=YES+cb.20210328-17-p0.en+FX+000"
_FETCH_TIMEOUT = 15
_FETCH_RETRIES = 2


def _fetch_feed(url: str):
    """Fetch an RSS URL with a browser User-Agent and parse it, retrying on empty/error.

    Returns a parsed feedparser result. Logs why a fetch came back empty (HTTP status, parse
    error, or simply zero entries) so a silent datacenter-IP block is visible in the logs instead
    of looking like "no news today".
    """
    last = None
    for attempt in range(1, _FETCH_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": _BROWSER_UA,
                    "Accept": "application/rss+xml, application/xml, text/xml, */*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Cookie": _CONSENT_COOKIE,
                },
            )
            with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
                status = getattr(resp, "status", None) or resp.getcode()
                raw = resp.read()
            parsed = feedparser.parse(raw)
            n = len(parsed.entries)
            if n:
                return parsed
            # 200 with zero entries is the datacenter-block signature — log and retry.
            bozo = getattr(parsed, "bozo_exception", None)
            log.warning(
                "google_news_rss: 0 entries (HTTP %s%s) attempt %d/%d: %s",
                status,
                f", parse error {bozo!r}" if bozo else "",
                attempt,
                _FETCH_RETRIES,
                url,
            )
            last = parsed
        except Exception as exc:  # noqa: BLE001 - network/DNS/timeout; log and retry
            log.warning(
                "google_news_rss: fetch failed attempt %d/%d (%r): %s",
                attempt,
                _FETCH_RETRIES,
                exc,
                url,
            )
            last = None
        if attempt < _FETCH_RETRIES:
            time.sleep(1.0 * attempt)
    return last if last is not None else feedparser.parse(b"")


def _strip_html(text: str) -> str:
    """Google News RSS summaries are HTML (<a>, <font>, &nbsp;, <ol><li>) wrapping huge redirect
    URLs — strip to plain text so it doesn't bloat tokens or confuse the LLM."""
    if not text:
        return ""
    try:
        from bs4 import BeautifulSoup

        text = BeautifulSoup(text, "html.parser").get_text(" ")
    except Exception:
        text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_HL = "en-US"
_GL = "US"
_CEID = "US:en"
_TOP_STORIES = f"https://news.google.com/rss?hl={_HL}&gl={_GL}&ceid={_CEID}"


def _search_url(query: str) -> str:
    q = urllib.parse.quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl={_HL}&gl={_GL}&ceid={_CEID}"


def _section_url(topic: str) -> str:
    if topic.upper() in {"TOP", "TOP_STORIES", "HEADLINES"}:
        return _TOP_STORIES
    t = urllib.parse.quote(topic.upper())
    return (
        f"https://news.google.com/rss/headlines/section/topic/{t}"
        f"?hl={_HL}&gl={_GL}&ceid={_CEID}"
    )


def _entry_datetime(entry) -> dt.datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if not parsed:
        return None
    return dt.datetime.fromtimestamp(time.mktime(parsed))


@register_source("google_news_rss")
class GoogleNewsRssSource(Source):
    """params: queries: list[str] OR topic: str OR feed_url: str;
    max_items: int (default 8); lookback_days: int (default 2)."""

    label = "Google News"

    def fetch(self) -> list[Story]:
        max_items = int(self.params.get("max_items", 8))
        lookback_days = int(self.params.get("lookback_days", 2))
        cutoff = dt.datetime.now() - dt.timedelta(days=lookback_days)

        urls: list[str] = []
        if self.params.get("feed_url"):
            urls = [self.params["feed_url"]]
        elif self.params.get("topic"):
            urls = [_section_url(self.params["topic"])]
        elif self.params.get("queries"):
            urls = [_search_url(q) for q in self.params["queries"]]
        else:
            log.warning("google_news_rss feed has no queries/topic/feed_url; skipping")
            return []

        stories: list[Story] = []
        seen_titles: set[str] = set()
        for url in urls:
            feed = _fetch_feed(url)
            count = 0
            for entry in feed.entries:
                when = _entry_datetime(entry)
                if when and when < cutoff:
                    continue
                title = getattr(entry, "title", "").strip()
                if not title:
                    continue
                key = title.lower()
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                summary = _strip_html(getattr(entry, "summary", "") or "")
                stories.append(
                    Story(
                        title=title,
                        body=summary,
                        url=getattr(entry, "link", ""),
                        published_at=when,
                        source=getattr(getattr(entry, "source", None), "title", "")
                        or self.label,
                    )
                )
                count += 1
                if count >= max_items:
                    break
        log.info("Google News: %d stories from %d feed(s)", len(stories), len(urls))
        return stories
