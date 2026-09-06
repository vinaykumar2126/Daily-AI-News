"""The Curator contract (Strategy pattern).

A curator takes the merged raw stories for one feed and returns a shorter, ranked, deduped
list ready for the rewrite step. Every strategy — a 20-line deterministic ranker or a full
ADK agent — honors this one method, so the pipeline never changes when you add a new one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sources.base import Story


@dataclass
class FeedContext:
    """What a curator needs to know about the feed it is curating."""

    name: str
    interests: list[str]  # keywords describing what matters for this feed
    max_stories: int  # rough cap on how many stories the segment should carry


class Curator(ABC):
    """Chooses and orders the stories that make it into a segment."""

    name: str = "curator"

    @abstractmethod
    def curate(self, stories: list[Story], ctx: FeedContext) -> list[Story]:
        """Return a ranked, deduped, trimmed subset of `stories` for this feed."""
        raise NotImplementedError
