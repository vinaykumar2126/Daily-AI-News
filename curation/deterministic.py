"""Deterministic baseline curator.

Ranks by a simple score (keyword-interest match + recency + source signal), dedupes
near-identical titles, and trims to the feed's cap. Intentionally small and predictable:
it is the eval baseline the agent must beat, and the fallback when the agent errors.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from difflib import SequenceMatcher

from curation.base import Curator, FeedContext
from sources.base import Story

log = logging.getLogger("daily-news.curation.deterministic")

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


class DeterministicCurator(Curator):
    name = "deterministic"

    def curate(self, stories: list[Story], ctx: FeedContext) -> list[Story]:
        if not stories:
            return []

        interest_tokens: set[str] = set()
        for kw in ctx.interests:
            interest_tokens |= _tokens(kw)

        now = dt.datetime.now()
        scored: list[tuple[float, Story]] = []
        for s in stories:
            score = 0.0
            # Interest match: how many interest tokens appear in title + body.
            text_tokens = _tokens(f"{s.title} {s.body}")
            if interest_tokens:
                overlap = len(interest_tokens & text_tokens)
                score += 2.0 * overlap
            # Recency: newer is better (decays over ~3 days).
            if s.published_at:
                age_h = max((now - s.published_at).total_seconds() / 3600.0, 0.0)
                score += max(0.0, 3.0 - age_h / 24.0)
            # Popularity signal, when a source provides it (e.g. HN points).
            points = s.extra.get("points")
            if isinstance(points, (int, float)):
                score += min(points / 100.0, 3.0)
            scored.append((score, s))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Dedup near-identical titles, keeping the higher-scored one (already first).
        kept: list[Story] = []
        for _, s in scored:
            if any(_similar(s.title, k.title) > 0.8 for k in kept):
                continue
            kept.append(s)
            if len(kept) >= ctx.max_stories:
                break

        log.info(
            "[%s] deterministic curated %d -> %d stories",
            ctx.name,
            len(stories),
            len(kept),
        )
        return kept
