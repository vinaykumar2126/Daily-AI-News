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
import time
import urllib.parse

import feedparser

from sources.base import Source, Story, register_source

log = logging.getLogger("daily-news.sources.gnews")

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
            feed = feedparser.parse(url)
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
                summary = getattr(entry, "summary", "") or ""
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
