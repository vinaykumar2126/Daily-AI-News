"""Generic publisher-RSS source.

Reads one or more publishers' own RSS feeds directly (NPR, The Hill, Immigration Impact, ...).
Unlike google_news_rss, these are served from each publisher's own site/CDN, so they are NOT
blocked from datacenter IPs the way Google News is (Google returns HTTP 503 to Cloud Run). That
makes this the reliable option for topics that have no other source.

There is no keyword *search* in a plain RSS feed — a feed just lists a publisher's latest items.
So for a focused topic (immigration, say) point at topical feeds and optionally pass `keywords`
to keep only items whose title/summary mentions one of them.

params:
  feeds:        list[str]  — RSS feed URLs (required)
  keywords:     list[str]  — optional; keep only items matching at least one (case-insensitive)
  max_items:    int        — total cap across all feeds (default 8)
  max_per_feed: int        — cap per feed before the global cap (default 6)
  lookback_days:int        — drop items older than this when a date is present (default 3)
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import time
import urllib.request

import feedparser

from sources.base import Source, Story, register_source

log = logging.getLogger("daily-news.sources.rss")

_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_FETCH_TIMEOUT = 15


def _strip_html(text: str) -> str:
    """RSS summaries are often HTML; reduce to plain text so it doesn't bloat tokens."""
    if not text:
        return ""
    try:
        from bs4 import BeautifulSoup

        text = BeautifulSoup(text, "html.parser").get_text(" ")
    except Exception:
        text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_datetime(entry) -> dt.datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if not parsed:
        return None
    return dt.datetime.fromtimestamp(time.mktime(parsed))


def _fetch(url: str):
    """Fetch and parse one RSS URL with a browser User-Agent. Returns a feedparser result;
    logs and returns an empty result on error so one dead feed never sinks the others."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT) as resp:
            raw = resp.read()
        return feedparser.parse(raw)
    except Exception as exc:  # noqa: BLE001 - network/DNS/timeout; keep going
        log.warning("rss: fetch failed (%r): %s", exc, url)
        return feedparser.parse(b"")


@register_source("rss")
class RssSource(Source):
    label = "RSS"

    def fetch(self) -> list[Story]:
        urls = self.params.get("feeds") or self.params.get("feed_urls") or []
        if not urls:
            log.warning("rss source has no 'feeds'; skipping")
            return []
        keywords = [k.lower() for k in self.params.get("keywords", []) if k]
        max_items = int(self.params.get("max_items", 8))
        max_per_feed = int(self.params.get("max_per_feed", 6))
        lookback_days = int(self.params.get("lookback_days", 3))
        cutoff = dt.datetime.now() - dt.timedelta(days=lookback_days)

        stories: list[Story] = []
        seen: set[str] = set()
        for url in urls:
            feed = _fetch(url)
            feed_title = getattr(getattr(feed, "feed", None), "title", "") or self.label
            count = 0
            for entry in feed.entries:
                when = _entry_datetime(entry)
                if when and when < cutoff:
                    continue
                title = getattr(entry, "title", "").strip()
                if not title:
                    continue
                summary = _strip_html(getattr(entry, "summary", "") or "")
                if keywords:
                    haystack = f"{title} {summary}".lower()
                    if not any(k in haystack for k in keywords):
                        continue
                key = title.lower()
                if key in seen:
                    continue
                seen.add(key)
                stories.append(
                    Story(
                        title=title,
                        body=summary,
                        url=getattr(entry, "link", ""),
                        published_at=when,
                        source=feed_title,
                    )
                )
                count += 1
                if count >= max_per_feed:
                    break
        # Newest first when we have dates, so the global cap keeps the freshest across feeds.
        stories.sort(key=lambda s: s.published_at or dt.datetime.min, reverse=True)
        stories = stories[:max_items]
        log.info("RSS: %d stories from %d feed(s)%s", len(stories), len(urls),
                 f" (keyword-filtered)" if keywords else "")
        return stories
