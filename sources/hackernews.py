"""Hacker News source via the free Algolia HN Search API (no auth).

Great signal for newly launched AI tools/agents: Show HN posts and popular stories that
clear a points threshold. Params:

  queries:       list of search strings (e.g. ["Show HN", "AI agent", "LLM"])
  min_points:    only keep stories at/above this score (default 50)
  lookback_days: how far back to search (default 2)
  max_items:     cap per query (default 5)
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import urllib.parse
import urllib.request

from sources.base import Source, Story, register_source

log = logging.getLogger("daily-news.sources.hn")

_API = "https://hn.algolia.com/api/v1/search_by_date"
_ITEM_URL = "https://news.ycombinator.com/item?id="


@register_source("hackernews")
class HackerNewsSource(Source):
    label = "Hacker News"

    def fetch(self) -> list[Story]:
        queries = self.params.get("queries") or ["Show HN"]
        min_points = int(self.params.get("min_points", 50))
        lookback_days = int(self.params.get("lookback_days", 2))
        max_items = int(self.params.get("max_items", 5))
        since_ts = int(
            (dt.datetime.now() - dt.timedelta(days=lookback_days)).timestamp()
        )

        stories: list[Story] = []
        seen_ids: set[str] = set()
        for query in queries:
            params = {
                "query": query,
                "tags": "story",
                "numericFilters": f"points>={min_points},created_at_i>{since_ts}",
                "hitsPerPage": max_items,
            }
            url = f"{_API}?{urllib.parse.urlencode(params)}"
            try:
                with urllib.request.urlopen(url, timeout=15) as resp:
                    data = json.load(resp)
            except Exception as exc:  # noqa: BLE001
                log.warning("HN query %r failed: %s", query, exc)
                continue

            for hit in data.get("hits", []):
                obj_id = str(hit.get("objectID", ""))
                if not obj_id or obj_id in seen_ids:
                    continue
                seen_ids.add(obj_id)
                title = (hit.get("title") or "").strip()
                if not title:
                    continue
                points = hit.get("points", 0)
                num_comments = hit.get("num_comments", 0)
                created = hit.get("created_at_i")
                published = (
                    dt.datetime.fromtimestamp(created) if created else None
                )
                # Prefer the linked article; fall back to the HN discussion.
                link = hit.get("url") or f"{_ITEM_URL}{obj_id}"
                stories.append(
                    Story(
                        title=title,
                        body=f"{points} points, {num_comments} comments on Hacker News.",
                        url=link,
                        published_at=published,
                        source=self.label,
                        extra={"points": points, "comments": num_comments},
                    )
                )
        # Most-discussed first — a decent proxy for "what people actually care about".
        stories.sort(key=lambda s: s.extra.get("points", 0), reverse=True)
        log.info("Hacker News: %d stories from %d query(ies)", len(stories), len(queries))
        return stories
