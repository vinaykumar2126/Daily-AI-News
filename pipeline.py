"""Core briefing pipeline, independent of TTS/email so evals can reuse it.

Flow per feed: merge sources -> curate -> rewrite into a spoken segment. Then compose all
segments into one script. main.py wraps this with audio synthesis and email delivery.
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import composer
from config import Config, Feed
from curation import create_curator
from curation.base import Curator, FeedContext
from sources import create_source
from sources.base import Story

log = logging.getLogger("daily-news.pipeline")

_PROMPT_DIR = Path(__file__).parent
_SHARED_STYLE = (_PROMPT_DIR / "prompts" / "_shared_style.md").read_text()


def gather_stories(feed: Feed) -> list[Story]:
    """Fetch and merge stories from all of a feed's sources. One dead source is skipped."""
    merged: list[Story] = []
    for spec in feed.sources:
        try:
            src = create_source(spec.type, spec.params)
            got = src.fetch()
            log.info("[%s] source %s -> %d stories", feed.name, spec.type, len(got))
            merged.extend(got)
        except Exception as exc:  # noqa: BLE001
            log.warning("[%s] source %s failed (skipping): %s", feed.name, spec.type, exc)
    return merged


def build_prompt(feed: Feed, stories: list[Story]) -> str:
    """Assemble the rewrite prompt: persona template + shared style, with placeholders filled."""
    template = (_PROMPT_DIR / feed.prompt).read_text()
    source_block = "\n\n".join(s.as_prompt_block() for s in stories)
    body = f"{template}\n\n{_SHARED_STYLE}"
    body = body.replace("{{SOURCE}}", source_block)
    body = body.replace("{{BUDGET}}", str(feed.length_budget_words))
    return body


def rewrite(cfg: Config, feed: Feed, stories: list[Story]) -> str:
    """Rewrite a feed's curated stories into a spoken segment via Vertex Gemini."""
    from google import genai

    prompt = build_prompt(feed, stories)
    client = genai.Client(
        vertexai=True, project=cfg.gcp_project, location=cfg.gemini_region
    )
    log.info("[%s] rewriting %d stories via %s", feed.name, len(stories), cfg.gemini_model)
    resp = client.models.generate_content(model=cfg.gemini_model, contents=prompt)
    return (resp.text or "").strip()


def build_segments_from_stories(
    cfg: Config,
    feeds: list[Feed],
    feed_stories: dict[str, list[Story]],
    curator: Curator | None = None,
) -> list[tuple[str, str]]:
    """Curate + rewrite each feed from already-fetched stories. Used by both the live
    pipeline and the eval harness (which supplies stored golden stories for repeatability)."""
    curator = curator or create_curator(cfg.curator)
    log.info("Curator: %s", curator.name)
    segments: list[tuple[str, str]] = []
    for feed in feeds:
        stories = feed_stories.get(feed.name, [])
        if not stories:
            log.warning("[%s] no stories; skipping segment", feed.name)
            continue
        ctx = FeedContext(
            name=feed.name, interests=feed.interests, max_stories=feed.max_stories
        )
        curated = curator.curate(stories, ctx)
        if not curated:
            log.warning("[%s] nothing survived curation; skipping segment", feed.name)
            continue
        text = rewrite(cfg, feed, curated)
        if text:
            segments.append((feed.name, text))
    return segments


def build_segments(
    cfg: Config, feeds: list[Feed], curator: Curator | None = None
) -> list[tuple[str, str]]:
    """Fetch, curate, and rewrite every feed to a (name, segment_text) pair."""
    feed_stories = {f.name: gather_stories(f) for f in feeds}
    return build_segments_from_stories(cfg, feeds, feed_stories, curator)


def generate_script(
    cfg: Config,
    feeds: list[Feed],
    curator: Curator | None = None,
    date: dt.date | None = None,
) -> str:
    """End-to-end: feeds -> segments -> one composed spoken script."""
    segments = build_segments(cfg, feeds, curator)
    return composer.compose(segments, date=date)
