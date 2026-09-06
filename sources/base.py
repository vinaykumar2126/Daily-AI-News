"""Normalized Story schema, the Source contract, and a small type->class registry.

Every source adapter converts its raw material into a list[Story], so everything
downstream (curation, rewrite, TTS, delivery) is source-agnostic. New sources plug
in by subclassing Source and decorating with @register_source("name").
"""

from __future__ import annotations

import datetime as dt
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger("daily-news.sources")


@dataclass
class Story:
    """One normalized news item, whatever its origin."""

    title: str
    body: str = ""
    url: str = ""
    published_at: dt.datetime | None = None
    source: str = ""  # provenance label, e.g. "Hacker News", "TLDR AI"
    extra: dict = field(default_factory=dict)  # source-specific fields (points, ticker, ...)

    def as_prompt_block(self) -> str:
        """Render this story as plain text for injection into a rewrite prompt."""
        parts = [f"- {self.title}"]
        if self.body:
            parts.append(f"  {self.body.strip()}")
        note = self.extra.get("competitive_note")
        if note:
            parts.append(f"  [competitive angle: {note}]")
        if self.url:
            parts.append(f"  ({self.url})")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        """JSON-serializable form (for golden sets and agent memory)."""
        return {
            "title": self.title,
            "body": self.body,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "source": self.source,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Story":
        when = d.get("published_at")
        return cls(
            title=d.get("title", ""),
            body=d.get("body", ""),
            url=d.get("url", ""),
            published_at=dt.datetime.fromisoformat(when) if when else None,
            source=d.get("source", ""),
            extra=d.get("extra", {}) or {},
        )


class Source(ABC):
    """A place content comes from. Implementations turn raw data into Stories."""

    #: human-readable provenance label, stamped onto every Story this source emits
    label: str = "source"

    def __init__(self, params: dict | None = None) -> None:
        self.params = params or {}

    @abstractmethod
    def fetch(self) -> list[Story]:
        """Return the recent stories from this source. May be empty; should not raise
        for ordinary 'nothing found' cases (raise only on real errors)."""
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Registry: map a `type` string in feeds.yaml to a Source subclass.
# --------------------------------------------------------------------------- #
_REGISTRY: dict[str, type[Source]] = {}


def register_source(name: str) -> Callable[[type[Source]], type[Source]]:
    """Class decorator that registers a Source under a `type` name used in feeds.yaml."""

    def _decorator(cls: type[Source]) -> type[Source]:
        _REGISTRY[name] = cls
        return cls

    return _decorator


def create_source(source_type: str, params: dict | None = None) -> Source:
    """Instantiate a registered source by its type name."""
    try:
        cls = _REGISTRY[source_type]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "(none registered)"
        raise ValueError(
            f"Unknown source type {source_type!r}. Known types: {known}"
        ) from None
    return cls(params)
