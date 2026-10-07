"""Normalized Story schema, the Source contract, and a small type->class registry.

Every source adapter converts its raw material into a list[Story], so everything
downstream (curation, rewrite, TTS, delivery) is source-agnostic. New sources plug
in by subclassing Source and decorating with @register_source("name").
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger("daily-news.sources")

# Emoji / pictographs / arrows / misc-technical (incl. ⌘ U+2318) — junk that confuses TTS.
# Keeps normal punctuation like em/en dashes and curly quotes (those read fine aloud).
_SYMBOLS = re.compile(
    "[\U0001F000-\U0001FAFF"   # emoji & pictographs
    "\U00002600-\U000027BF"    # misc symbols + dingbats
    "\U00002190-\U000021FF"    # arrows
    "\U00002B00-\U00002BFF"    # misc symbols & arrows
    "\U0001F1E6-\U0001F1FF"    # regional-indicator (flags)
    "⌀-⏿"            # misc technical (⌘, ⌨, ⏰, …)
    "‍️]"            # zero-width joiner, variation selector
)


# Invisible/zero-width characters that HTML emails inject as spacing (esp. TLDR): zero-width
# space/non-joiner/joiner, LRM/RLM, word-joiner, BOM. Pure bloat.
_INVISIBLE = re.compile("[​‌‍‎‏⁠﻿]")


def strip_symbols(text: str) -> str:
    """Remove emoji/pictographic/technical symbols and zero-width/invisible characters that TTS
    mispronounces or that bloat the text; normalize no-break spaces; collapse leftover spaces."""
    if not text:
        return text
    text = _SYMBOLS.sub("", text)
    text = _INVISIBLE.sub("", text)
    text = text.replace(" ", " ")  # no-break space -> normal space
    return re.sub(r"[ \t]{2,}", " ", text)


# Sentence end: ., ! or ? followed by whitespace. Decimals ("$2.50", "SAM 3.1") have no space
# after the dot, so they are not split.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def clip_sentences(text: str, limit: int) -> str:
    """Trim to roughly `limit` chars without cutting a sentence in half.

    Hard character slicing left summaries ending mid-thought ("The incident"), which strands the
    agent without the point of the story. Instead we keep whole sentences up to the limit; if even
    the first sentence is longer, we keep it whole as long as it stays under a generous ceiling,
    and only fall back to a word-boundary cut for genuinely runaway text.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return text

    sentences = _SENTENCE_END.split(text)
    kept: list[str] = []
    total = 0
    for sent in sentences:
        extra = len(sent) + (1 if kept else 0)
        if kept and total + extra > limit:
            break
        kept.append(sent)
        total += extra
    if kept:
        clipped = " ".join(kept).strip()
        # A single opening sentence may overshoot the limit; keep it whole unless it is runaway.
        if len(clipped) <= limit * 2:
            return clipped

    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{cut}..." if cut else text[:limit]


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
