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
from sources.base import Story, clip_sentences

log = logging.getLogger("daily-news.curation.agentic")

_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_INSTRUCTION = """You are the news curator for one segment ("{feed_name}") of a spoken daily
briefing for a working AI/ML engineer who wants to stay ahead of where the field is going.
The listener cares about: {interests}.

You are given a numbered list of candidate stories. Select and RANK the ones that matter most,
up to {max_stories}, best-first. Rank by SIGNIFICANCE — what an engineer needs to know — NOT by
keyword match, recency, or vote count.

Significance ladder for a tech/AI segment (highest priority first):
1. New MODEL releases and capability launches from major labs (OpenAI, Anthropic, Google/DeepMind,
   Meta, Qwen/Alibaba, Mistral, DeepSeek, xAI, and similar) — frontier OR open-weight — and novel
   research/breakthroughs from those labs (e.g. "Claude discovered a novel enzyme system"). These
   define where the field is heading. NEVER drop one to keep something from a lower tier.
2. Developer tools, agents, and frameworks the listener could actually pick up and use.
3. Competitive moves — one lab shipping something faster, cheaper, or better than a rival.
4. Serious infra / inference / architecture / real benchmark ADVANCES (a genuine advance — not
   "a benchmark WE built" or "we tested N models").
5. Everything else of genuine engineering interest.

DEMOTE hard, and DROP these first when trimming to fit: opinion / analysis / meta-commentary;
"a tool or benchmark WE made" self-promo; generic roundups & listicles ("top 5…", "best X updated
daily"); vertical business / PR product blurbs (a dog-food comparison tool, a real-estate CRM);
pure funding rounds; off-topic items (consumer hardware, OS, gadgets); duplicates; and thin
title-only entries with no real substance.

For AI/tech launches you MAY call fetch_article to confirm a key detail, and recent_digest_history
to check whether something competes with or beats a prior day's story — if so, add a short
competitive_note (e.g. "beats last week's X on cost").

--- EXAMPLE (illustrative — an AI & Tech segment, max_stories 4) ---
Candidates:
0. OpenAI introduces MentalHealthBench, an open benchmark built with mental-health experts
1. Google releases Gemini Flash TTS — new speech models: voices from text, 30-second voice cloning
2. Blue Buffalo launches an AI tool to help customers compare dog foods
3. Anthropic's Claude autonomously discovered a previously unknown enzyme system
4. We benchmarked 27 open-source LLMs — then had to fix our own benchmark
5. Ember-1: a new model on Kimi K3 with the same quality at 40% fewer tokens

Correct output:
{{"selected": [1, 3, 5, 0], "notes": {{}}}}

Why (reasoning — do NOT output it): 1, 3, 5 are frontier model releases / a major-lab breakthrough
-> tier 1, ranked first. 0 is a real OpenAI benchmark -> keep, but lower. 2 is a vertical PR blurb
and 4 is "we-made-a-benchmark" meta-commentary -> dropped.
--- END EXAMPLE ---

Now curate the REAL candidates below. Return ONLY a JSON object of this exact shape, nothing else:
{{"selected": [<original story numbers, best first>],
  "notes": {{"<story number>": "<optional competitive_note>"}}}}
"""


# How much of each candidate's body the curator sees. Clipped on a sentence boundary so the
# model never ranks a story from half a sentence.
_CANDIDATE_BODY_CHARS = 300


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
                    # The model may split its answer across several parts; joining them keeps a
                    # long JSON selection intact instead of reading a half object from parts[0].
                    final = "".join(p.text or "" for p in event.content.parts)
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
