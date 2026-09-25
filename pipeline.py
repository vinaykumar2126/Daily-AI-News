"""Core briefing pipeline, independent of TTS/email so evals can reuse it.

Flow per feed: merge sources -> curate -> rewrite into a spoken segment. Then compose all
segments into one script. main.py wraps this with audio synthesis and email delivery.
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import composer
import observability
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
    with observability.span("gather_stories", feed=feed.name, sources=len(feed.sources)):
        for spec in feed.sources:
            with observability.span("fetch_source", feed=feed.name, source=spec.type):
                try:
                    src = create_source(spec.type, spec.params)
                    got = src.fetch()
                    log.info("[%s] source %s -> %d stories", feed.name, spec.type, len(got))
                    observability.set_attrs(stories=len(got))
                    merged.extend(got)
                except Exception as exc:  # noqa: BLE001
                    log.warning("[%s] source %s failed (skipping): %s", feed.name, spec.type, exc)
                    # Skipping is deliberate, but a source that quietly dies every morning
                    # should be findable in a trace rather than only in the logs.
                    observability.record_exception(exc, skipped=True, stories=0)
        observability.set_attrs(stories=len(merged))
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
    log.info("[%s] rewriting %d stories via %s", feed.name, len(stories), cfg.gemini_rewrite_model)
    with observability.span(
        "rewrite",
        feed=feed.name,
        stories=len(stories),
        budget_words=feed.length_budget_words,
        **{"gen_ai.request.model": cfg.gemini_rewrite_model},
    ):
        resp = client.models.generate_content(model=cfg.gemini_rewrite_model, contents=prompt)
        # The rewrite is the run's biggest token spend and the only place to measure it; the
        # google-genai instrumentation adds its own child span, this is the per-feed roll-up.
        observability.record_tokens(getattr(resp, "usage_metadata", None))
        text = (resp.text or "").strip()
        observability.set_attrs(words=len(text.split()))
    return text


def _needs_enrichment(story: Story) -> bool:
    """A story the rewrite would otherwise hallucinate from: real link, but a thin (headline /
    vote-count-only) body. Skip opaque Google News redirect URLs (they don't fetch cleanly, and
    those segments' headlines are self-contained)."""
    if not story.url or "news.google.com" in story.url:
        return False
    return len((story.body or "").strip()) < 200


import re as _re

# Standalone UI chrome that leaks in when we scrape a page (buttons/menus), safe to drop.
_CHROME = _re.compile(
    r"\b(log ?in|sign ?up|subscribe|theme|light\s+dark|menu|share|read more|"
    r"accept( all)?( cookies)?|cookie settings|skip to content|toggle)\b",
    _re.I,
)


def _clean_enriched(text: str) -> str:
    """Strip emoji/symbols and obvious UI chrome from fetched article text, collapse whitespace."""
    from sources.base import strip_symbols

    text = strip_symbols(text)
    text = _CHROME.sub("", text)
    return _re.sub(r"\s{2,}", " ", text).strip()


def enrich_stories(stories: list[Story], max_stories: int) -> None:
    """Fetch real article text for thin-bodied stories so the rewrite grounds on facts, not a
    headline. Mutates stories in place; bounded per feed; failures leave the story unchanged."""
    from curation.tools import fetch_article

    enriched = 0
    with observability.span("enrich_stories", candidates=len(stories), budget=max_stories):
        for s in stories:
            if enriched >= max_stories:
                break
            if not _needs_enrichment(s):
                continue
            res = fetch_article(s.url)
            if res.get("status") == "success" and len(res.get("text", "")) > 200:
                s.body = _clean_enriched(res["text"])
                enriched += 1
                log.info("Enriched %r from %s (%d chars)", s.title[:50], s.url, len(s.body))
        observability.set_attrs(enriched=enriched)
    if enriched:
        log.info("Enriched %d stories with article text", enriched)


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
        with observability.span(
            "feed",
            name=feed.name,
            curator=curator.name,
            max_stories=feed.max_stories,
            stories_in=len(stories),
        ):
            if not stories:
                log.warning("[%s] no stories; skipping segment", feed.name)
                observability.set_attrs(skipped="no_stories")
                continue
            ctx = FeedContext(
                name=feed.name, interests=feed.interests, max_stories=feed.max_stories
            )
            with observability.span(
                "curate", feed=feed.name, curator=curator.name, stories_in=len(stories)
            ):
                curated = curator.curate(stories, ctx)
                observability.set_attrs(stories_out=len(curated))
            if not curated:
                log.warning("[%s] nothing survived curation; skipping segment", feed.name)
                observability.set_attrs(skipped="nothing_curated")
                continue
            observability.set_attrs(stories_curated=len(curated))
            if cfg.enrich_articles:
                enrich_stories(curated, cfg.enrich_max_per_feed)
            text = rewrite(cfg, feed, curated)
            if text:
                segments.append((feed.name, text))
            else:
                observability.set_attrs(skipped="empty_rewrite")
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
    with observability.span("compose", segments=len(segments)):
        script = composer.compose(segments, date=date)
        observability.set_attrs(words=len(script.split()))
    return script
