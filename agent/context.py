"""Build today's grounding knowledge for the realtime agent.

Provider-neutral: reuses the existing pipeline to produce (a) the spoken NARRATIVE (the composed
briefing the agent opens with) and (b) the STORY LIST (title/summary/url per topic) the agent uses
as its knowledge base for follow-up questions. Stories are gathered once and shared between both,
so we don't fetch twice.

    python -m agent.context            # print today's knowledge doc (markdown)
    python -m agent.context --json     # emit the structured context as JSON
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re

import composer
import pipeline
from config import Config, Feed, load_dotenv, load_feeds
from sources.base import Story, clip_sentences

_SUMMARY_CHARS = 600
_KB_SUMMARY_CHARS = 500


def _story_dict(topic: str, s: Story) -> dict:
    return {
        "topic": topic,
        "title": s.title,
        "summary": clip_sentences(s.body or "", _SUMMARY_CHARS),
        "url": s.url,
        "source": s.source,
    }


def build_context(cfg: Config, feeds: list[Feed], date: dt.date | None = None) -> dict:
    """Fetch once, then produce {date, narrative, stories:[...]} for the agent's grounding."""
    date = date or dt.date.today()
    # Fetch every feed's stories a single time, then reuse for both narrative and KB.
    feed_stories = {f.name: pipeline.gather_stories(f) for f in feeds}
    segments = pipeline.build_segments_from_stories(cfg, feeds, feed_stories)
    narrative = composer.compose(segments, date=date)

    stories: list[dict] = []
    seen: set[str] = set()  # global de-dup: a story can match two feeds' queries
    for feed in feeds:
        for s in feed_stories.get(feed.name, []):
            if not s.title.strip():
                continue
            key = _norm(s.title)
            if key in seen:
                continue
            seen.add(key)
            stories.append(_story_dict(feed.name, s))

    return {"date": date.isoformat(), "narrative": narrative, "stories": stories}


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", text or "").strip().lower()


def _useful_summary(title: str, summary: str) -> str:
    """Keep a summary only if it adds info beyond the title (RSS summaries are usually just the
    title + source repeated). Trim to keep the KB lean."""
    if not summary:
        return ""
    t, s = _norm(title), _norm(summary)
    if not s or s == t or s.startswith(t) or (t in s and len(s) <= len(t) + 40):
        return ""
    return clip_sentences(summary, _KB_SUMMARY_CHARS)


# Hacker News popularity metadata ("266 points, 104 comments on Hacker News.") — not content;
# strip it from grounding so only the actual story survives.
_HN_META = re.compile(r"\d+\s*points?,\s*\d+\s*comments?(?:\s*on\s*hacker news)?\.?", re.I)


def render_markdown(ctx: dict) -> str:
    """Human/agent-readable knowledge doc: the opening narrative + grounded source stories.
    Trims HN points/comments metadata and source URLs — grounding is for the agent to answer
    from, and it neither speaks URLs nor needs vote counts."""
    lines = [f"# Daily briefing knowledge — {ctx['date']}", ""]
    lines.append("## Opening narrative (what the agent delivers first)")
    lines.append(ctx.get("narrative", "").strip() or "(none)")
    lines.append("")
    lines.append("## Source stories (grounding for follow-up questions)")
    current = None
    for s in ctx.get("stories", []):
        if s["topic"] != current:
            current = s["topic"]
            lines.append(f"\n### {current}")
        line = f"- {s['title']}"
        summary = _HN_META.sub("", _useful_summary(s["title"], s.get("summary", ""))).strip()
        if summary:
            line += f" — {summary}"
        lines.append(line)
    from sources.base import strip_symbols

    return strip_symbols("\n".join(lines).strip()) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="emit structured JSON instead of markdown")
    args = ap.parse_args()

    load_dotenv()
    cfg = Config()
    feeds = load_feeds()
    ctx = build_context(cfg, feeds)

    if args.json:
        print(json.dumps(ctx, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(ctx))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
