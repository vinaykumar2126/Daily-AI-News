"""Agentic curator (Google ADK).

An ADK agent that ranks stories for the listener, dedupes, optionally enriches by fetching an
article, and — for the AI & Tech feed — flags competitive moves against prior digests (via the
recent_digest_history tool). Implements the same Curator interface as the deterministic baseline,
and falls back to it on any error so the digest always ships.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from curation.base import Curator, FeedContext
from curation.deterministic import DeterministicCurator
from curation.tools import fetch_article, recent_digest_history
from sources.base import Story

log = logging.getLogger("daily-news.curation.agentic")

_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_INSTRUCTION = """You are a news curator for a spoken daily briefing. You are given a numbered
list of candidate stories for the "{feed_name}" segment. The listener cares about: {interests}.

Your job:
1. Select the most important, relevant, non-duplicate stories (at most {max_stories}).
2. Rank them best-first for a spoken briefing.
3. For AI/tech stories about new tools or launches, you MAY call fetch_article to confirm a key
   detail, and call recent_digest_history to check whether a launch competes with or beats
   something covered before. If it does, write a short competitive_note (e.g. "beats last week's
   X on cost").

Return ONLY a JSON object of this exact shape and nothing else:
{{"selected": [<original story numbers, best first>],
  "notes": {{"<story number>": "<optional competitive_note>"}}}}
"""


def _format_stories(stories: list[Story]) -> str:
    lines = []
    for i, s in enumerate(stories):
        extra = ""
        if s.source:
            extra = f" [{s.source}]"
        lines.append(f"{i}. {s.title}{extra}\n   {s.body.strip()[:200]}\n   {s.url}")
    return "\n".join(lines)


class AgenticCurator(Curator):
    name = "agentic"

    def __init__(self, fallback: Curator | None = None) -> None:
        self.fallback = fallback or DeterministicCurator()

    def curate(self, stories: list[Story], ctx: FeedContext) -> list[Story]:
        if not stories:
            return []
        try:
            selected = self._run_agent(stories, ctx)
            if not selected:
                raise RuntimeError("agent returned no selection")
        except Exception as exc:  # noqa: BLE001
            log.warning("[%s] agentic curation failed (%s); using fallback", ctx.name, exc)
            return self.fallback.curate(stories, ctx)

        # Record what we surfaced (for future competitive comparisons), unless in eval mode.
        if not os.environ.get("EVAL_MODE") and "ai" in ctx.name.lower():
            self._record(selected)
        log.info("[%s] agentic curated %d -> %d stories", ctx.name, len(stories), len(selected))
        return selected

    def _run_agent(self, stories: list[Story], ctx: FeedContext) -> list[Story]:
        from google.adk.agents import Agent
        from google.adk.runners import InMemoryRunner
        from google.genai import types

        agent = Agent(
            name="curator",
            model=_MODEL,
            instruction=_INSTRUCTION.format(
                feed_name=ctx.name,
                interests=", ".join(ctx.interests) or "general relevance",
                max_stories=ctx.max_stories,
            ),
            tools=[fetch_article, recent_digest_history],
        )
        prompt = "Candidate stories:\n\n" + _format_stories(stories)

        async def _go() -> str:
            runner = InMemoryRunner(agent=agent, app_name="curator")
            await runner.session_service.create_session(
                app_name="curator", user_id="pipeline", session_id="s1"
            )
            final = ""
            async for event in runner.run_async(
                user_id="pipeline",
                session_id="s1",
                new_message=types.Content(
                    role="user", parts=[types.Part.from_text(text=prompt)]
                ),
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    final = event.content.parts[0].text or ""
            return final

        raw = asyncio.run(_go())
        return self._parse(raw, stories)

    @staticmethod
    def _parse(raw: str, stories: list[Story]) -> list[Story]:
        text = raw.strip()
        # Tolerate ```json fences or surrounding prose.
        if "{" in text:
            text = text[text.index("{") : text.rindex("}") + 1]
        data = json.loads(text)
        notes = {str(k): v for k, v in (data.get("notes") or {}).items()}
        out: list[Story] = []
        for idx in data.get("selected", []):
            try:
                s = stories[int(idx)]
            except (ValueError, IndexError, TypeError):
                continue
            note = notes.get(str(idx))
            if note:
                s.extra = {**s.extra, "competitive_note": note}
            out.append(s)
        return out

    @staticmethod
    def _record(selected: list[Story]) -> None:
        import datetime as dt

        import memory as memory_store

        items = [
            {"title": s.title, "url": s.url, "source": s.source} for s in selected
        ]
        try:
            memory_store.append_record(dt.date.today().isoformat(), items)
        except Exception as exc:  # noqa: BLE001
            log.warning("memory record failed (non-fatal): %s", exc)
