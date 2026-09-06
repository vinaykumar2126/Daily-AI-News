"""LLM-as-judge scoring (Gemini).

Given a segment's spoken text and the source stories it was built from, score it on
faithfulness, coverage, and relevance (each 0-1) with a short rationale. Reference-free: the
judge reasons from the source material, not a golden answer.
"""

from __future__ import annotations

import json
import logging

from config import Config
from sources.base import Story

log = logging.getLogger("daily-news.evals.judge")

_JUDGE_PROMPT = """You are a strict evaluator of an audio news briefing segment. You are given
the SOURCE STORIES the segment was built from, and the SEGMENT SCRIPT that was produced.

Score the segment on three axes, each from 0.0 to 1.0:
- faithfulness: Are all claims in the script supported by the source stories? Penalize any
  invented facts, numbers, names, or dates not present in the sources.
- coverage: Does the segment include the most important stories from the sources? Penalize
  missing clearly-important items.
- relevance: Are the included stories relevant to the segment's focus ({focus})? Penalize
  off-topic or filler content.

Respond ONLY with a JSON object of this exact shape:
{{"faithfulness": <float>, "coverage": <float>, "relevance": <float>, "rationale": "<one or two sentences>"}}

SOURCE STORIES:
{sources}

SEGMENT SCRIPT:
{segment}
"""


def judge_segment(
    cfg: Config,
    focus: str,
    segment_text: str,
    source_stories: list[Story],
) -> dict:
    """Return {faithfulness, coverage, relevance, rationale}. On error, zeros + note."""
    from google import genai

    sources_block = "\n".join(s.as_prompt_block() for s in source_stories) or "(none)"
    prompt = _JUDGE_PROMPT.format(
        focus=focus, sources=sources_block, segment=segment_text
    )
    client = genai.Client(
        vertexai=True, project=cfg.gcp_project, location=cfg.gemini_region
    )
    try:
        resp = client.models.generate_content(
            model=cfg.gemini_model,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        data = json.loads(resp.text)
        return {
            "faithfulness": float(data.get("faithfulness", 0.0)),
            "coverage": float(data.get("coverage", 0.0)),
            "relevance": float(data.get("relevance", 0.0)),
            "rationale": str(data.get("rationale", "")),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("judge failed for %s: %s", focus, exc)
        return {
            "faithfulness": 0.0,
            "coverage": 0.0,
            "relevance": 0.0,
            "rationale": f"judge error: {exc}",
        }


def judge_pairwise(
    cfg: Config, focus: str, segment_a: str, segment_b: str
) -> dict:
    """Blind A/B: which segment is the better briefing? Returns {winner: 'A'|'B'|'tie', reason}."""
    from google import genai

    prompt = f"""Two audio news briefing segments cover the same topic ({focus}). Decide which is
the better briefing overall (clearer, better prioritized, more useful, natural to listen to).
Respond ONLY as JSON: {{"winner": "A" | "B" | "tie", "reason": "<one sentence>"}}

SEGMENT A:
{segment_a}

SEGMENT B:
{segment_b}
"""
    client = genai.Client(
        vertexai=True, project=cfg.gcp_project, location=cfg.gemini_region
    )
    try:
        resp = client.models.generate_content(
            model=cfg.gemini_model,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        data = json.loads(resp.text)
        return {"winner": data.get("winner", "tie"), "reason": data.get("reason", "")}
    except Exception as exc:  # noqa: BLE001
        log.warning("pairwise judge failed for %s: %s", focus, exc)
        return {"winner": "tie", "reason": f"judge error: {exc}"}
