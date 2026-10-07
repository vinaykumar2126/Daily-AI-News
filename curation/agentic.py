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
import re
import uuid

import observability
from curation.base import Curator, FeedContext
from curation.deterministic import DeterministicCurator
from curation.tools import fetch_article, recent_digest_history
from sources.base import Story, clip_sentences

log = logging.getLogger("daily-news.curation.agentic")

_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# Ranking by significance should come out the same way twice. Unset, this ran at the API default
# (1.0) and the same frozen sources.json produced a different selection every eval run, which made
# score changes impossible to attribute. Mirrors REWRITE_TEMPERATURE; read here rather than from
# Config because curate() only receives a FeedContext.
_TEMPERATURE = float(os.environ.get("CURATOR_TEMPERATURE", "0.2"))

# The feed-agnostic shell. Everything that differs per segment -- who is listening, the significance
# ladder, what to drop, the worked example -- comes from that feed's `curate_prompt` file and lands
# in {priorities}. This used to be one instruction carrying a ladder explicitly written "for a
# tech/AI segment", applied to all four feeds: US Headlines had no valid criteria to rank by, so it
# kept a sea-arch collapse and an assault case over a stimulus story and a Senate-race poll
# (2026-10-03 eval: rubrics 0.20, adherence 0.00, while AI & Tech scored 0.93 on the same run).
_INSTRUCTION = """You are the news curator for one segment ("{feed_name}") of a spoken daily
briefing. The listener cares about: {interests}.

You are given a numbered list of candidate stories. Select and RANK the ones that matter most,
up to {max_stories}, best-first. Rank by SIGNIFICANCE — what this listener needs to know — NOT by
keyword match, recency, or vote count.

{priorities}

Now curate the REAL candidates below. Return ONLY a JSON object of this exact shape, nothing else:
{{"selected": [<original story numbers, best first>],
  "notes": {{"<story number>": "<optional competitive_note>"}}}}
"""

# Fallback when a feed declares no curate_prompt: the generic rules that are true for every segment.
# Deliberately thin -- a feed that wants real ranking should name a priorities file.
_DEFAULT_PRIORITIES = """Prefer stories where something actually changed or shipped over commentary
about it. Prefer ONE story per event: several outlets covering the same thing is one slot, not
several. DROP opinion and analysis pieces, self-promotional "a thing WE built" posts, generic
roundups and listicles, PR blurbs, duplicates, thin title-only entries with no substance, and
anything that merely matched a search keyword without being about this segment's topic."""


# How much of each candidate's body the curator sees. Clipped on a sentence boundary so the
# model never ranks a story from half a sentence.
_CANDIDATE_BODY_CHARS = 300


def _slug(name: str) -> str:
    """Feed name -> a token safe to use in an ADK app/session id (e.g. 'AI & Tech' -> 'ai-tech')."""
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-") or "feed"


def _format_stories(stories: list[Story]) -> str:
    lines = []
    for i, s in enumerate(stories):
        extra = ""
        if s.source:
            extra = f" [{s.source}]"
        body = clip_sentences(s.body or "", _CANDIDATE_BODY_CHARS)
        lines.append(f"{i}. {s.title}{extra}\n   {body}\n   {s.url}")
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
            # The digest still ships on the deterministic curator, but a silent daily fallback
            # would otherwise look identical to a healthy agentic run. Make it queryable.
            observability.record_exception(
                exc, **{"curation.fallback": True, "curation.fallback_reason": str(exc)[:200]}
            )
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

        # A per-feed app/session id. These land on ADK's own spans, so a shared constant would
        # make the four per-feed agent runs in one pipeline execution indistinguishable in
        # Trace Explorer.
        slug = _slug(ctx.name)
        app_name = f"curator-{slug}"
        session_id = f"{slug}-{uuid.uuid4().hex[:8]}"

        agent = Agent(
            name="curator",
            model=_MODEL,
            instruction=_INSTRUCTION.format(
                feed_name=ctx.name,
                interests=", ".join(ctx.interests) or "general relevance",
                max_stories=ctx.max_stories,
                priorities=ctx.priorities or _DEFAULT_PRIORITIES,
            ),
            tools=[fetch_article, recent_digest_history],
            generate_content_config=types.GenerateContentConfig(temperature=_TEMPERATURE),
        )
        prompt = "Candidate stories:\n\n" + _format_stories(stories)

        async def _go() -> str:
            runner = InMemoryRunner(agent=agent, app_name=app_name)
            await runner.session_service.create_session(
                app_name=app_name, user_id="pipeline", session_id=session_id
            )
            final = ""
            async for event in runner.run_async(
                user_id="pipeline",
                session_id=session_id,
                new_message=types.Content(
                    role="user", parts=[types.Part.from_text(text=prompt)]
                ),
            ):
                if event.is_final_response() and event.content and event.content.parts:
                    # The model may split its answer across several parts; joining them keeps a
                    # long JSON selection intact instead of reading a half object from parts[0].
                    final = "".join(p.text or "" for p in event.content.parts)
            return final

        observability.set_attrs(
            **{
                "adk.app_name": app_name,
                "adk.session_id": session_id,
                "adk.model": _MODEL,
                "gen_ai.request.temperature": _TEMPERATURE,
            }
        )
        # asyncio.run copies the current context into its task, so ADK's invocation /
        # agent_run / call_llm / execute_tool spans nest under the caller's `curate` span.
        raw = asyncio.run(_go())
        selected = self._parse(raw, stories)
        observability.set_attrs(
            **{
                "curation.fallback": False,
                "curation.notes": sum(1 for s in selected if s.extra.get("competitive_note")),
            }
        )
        return selected

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
