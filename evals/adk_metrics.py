"""Google-native eval metrics, from google.adk.evaluation — a second opinion on the same segments.

The hand-rolled judges in evals/judge.py stay exactly as they are; they're tuned and their scores
are comparable across the golden sets already captured. This module adds ADK's own evaluators
beside them:

  * hallucinations_v1 — grades every claim in the segment against the source stories it was built
    from. The same axis as our `faithfulness`, but Google's prompt and scoring, so a disagreement
    between the two is itself a signal.
  * rubric_based_final_response_quality_v1 — grades the segment against expectations.md parsed
    into individual rubrics. Our expectations judge returns one adherence float for the whole
    segment; this returns pass/fail per must-include, per red line, per duplicate-merge, so
    "0.985 adherence" becomes "this named story was dropped".

The judge model is deliberately separate from the generator's (`EVAL_JUDGE_MODEL`, default
gemini-2.5-flash vs the rewrite's gemini-2.5-pro) — a judge from the generator's own family grades
its own work.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from sources.base import Story

log = logging.getLogger("daily-news.evals.adk_metrics")

# Answer-key groups that can be graded pass/fail on a single segment, and how each becomes a
# rubric. Optional groups ("Nice-to-include", "Reasonable to include") are deliberately absent:
# leaving an optional story out is not a failure, so scoring it would only add noise.
_GRADEABLE = (
    ("must-include", "must", "The segment covers this story: {item}"),
    (
        # Red lines are written two ways in expectations.md — a thing to exclude ("HitPaw
        # sponsored ad") and a standing rule ("no invented benchmark numbers"). Quote the
        # editor's own words rather than paraphrasing, or the rule form gets inverted.
        "red line",
        "redline",
        "The segment respects this red line: {item}",
    ),
    (
        "should-drop",
        "drop",
        "The segment leaves out, or spends at most a passing mention on: {item}",
    ),
    (
        "duplicate",
        "dedupe",
        "This story is mentioned only once, not repeated as separate items: {item}",
    ),
)


def available() -> bool:
    """Whether this ADK build exposes the evaluators we need."""
    try:
        _imports()
    except Exception as exc:  # noqa: BLE001
        log.warning("ADK eval metrics unavailable: %s", exc)
        return False
    return True


def _imports() -> dict[str, Any]:
    from google.adk.evaluation.eval_case import Invocation
    from google.adk.evaluation.eval_metrics import (
        EvalMetric,
        HallucinationsCriterion,
        JudgeModelOptions,
        RubricsBasedCriterion,
    )
    from google.adk.evaluation.eval_rubrics import Rubric, RubricContent
    from google.adk.evaluation.hallucinations_v1 import HallucinationsV1Evaluator
    from google.adk.evaluation.rubric_based_final_response_quality_v1 import (
        RubricBasedFinalResponseQualityV1Evaluator,
    )
    from google.genai import types

    return locals()


# --------------------------------------------------------------------------- #
# expectations.md -> rubrics
# --------------------------------------------------------------------------- #
def parse_expectations(text: str) -> dict[str, list[tuple[str, str]]]:
    """Split expectations.md into per-segment (rubric_id, property_text) pairs.

    The file is organized as `## <feed name>` sections, each holding labelled groups
    (`- Must-include:`, `- Red lines (must NOT appear):`) whose items are either nested bullets or
    trailing text on the label line itself. A `## Cross-segment` section applies to every segment.
    """
    if not text.strip():
        return {}

    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.*?)\s*$", line)
        if heading:
            current = heading.group(1)
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    shared = sections.pop("Cross-segment", [])
    out: dict[str, list[tuple[str, str]]] = {}
    for name, lines in sections.items():
        rubrics = _rubrics_from_lines(lines)
        rubrics += _rubrics_from_lines(shared, prefix="cross")
        if rubrics:
            out[name] = rubrics
    return out


def _rubrics_from_lines(lines: list[str], prefix: str = "") -> list[tuple[str, str]]:
    """Turn one section's bullet lines into (rubric_id, property_text) pairs."""
    rubrics: list[tuple[str, str]] = []
    template: str | None = None
    kind = ""
    counters: dict[str, int] = {}

    def add(item: str) -> None:
        nonlocal template, kind
        item = _clean(item)
        if not template or len(item) < 8:
            return
        if _NOT_JUDGEABLE.search(item):
            return
        counters[kind] = counters.get(kind, 0) + 1
        rid = "_".join(p for p in (prefix, kind, str(counters[kind])) if p)
        rubrics.append((rid, template.format(item=item)))

    for raw in lines:
        if not raw.strip().startswith("-"):
            continue
        indent = len(raw) - len(raw.lstrip())
        body = raw.strip().lstrip("-").strip()
        label, sep, trailing = body.partition(":")

        # A group label resets the template; nested bullets under it are the items.
        if sep and indent <= 1:
            lowered = label.lower()
            match = next((g for g in _GRADEABLE if g[0] in lowered), None)
            if match is None:
                template, kind = None, ""
            else:
                _, kind, template = match
            if trailing.strip():
                add(trailing)
            continue

        if indent <= 1:
            # An un-labelled top-level bullet (the Cross-segment style) — grade it as written.
            template, kind = "{item}", "rule"
            add(body)
            template = None
            continue

        add(body)

    return rubrics


# Cross-segment rules about length/duration are dropped: a judge shown one segment has no word
# budget or total runtime to compare against (it says so -- "constraints not defined in the
# provided prompt"), and evals/checks.run_code_checks already measures those deterministically.
_NOT_JUDGEABLE = re.compile(r"\b(word budget|budget|minutes?|length|runtime)\b", re.I)


def _clean(item: str) -> str:
    """Drop markdown emphasis and collapse whitespace; keep the (#n) source refs as anchors."""
    return re.sub(r"\s{2,}", " ", item.replace("**", "").replace("`", "")).strip(" .")


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score_segments(
    cfg: Any,
    segments: list[tuple[str, str]],
    feed_stories: dict[str, list[Story]],
    expectations: str = "",
) -> dict | None:
    """Score each segment with ADK's evaluators. Returns None if ADK can't provide them."""
    try:
        api = _imports()
    except Exception as exc:  # noqa: BLE001
        log.warning("ADK eval metrics unavailable (%s); skipping.", exc)
        return None

    rubrics_by_segment = parse_expectations(expectations)
    try:
        return asyncio.run(_score(api, cfg, segments, feed_stories, rubrics_by_segment))
    except Exception as exc:  # noqa: BLE001
        log.warning("ADK eval metrics failed: %s", exc)
        return {"error": str(exc), "judge_model": cfg.eval_judge_model, "per_segment": []}


async def _score(
    api: dict[str, Any],
    cfg: Any,
    segments: list[tuple[str, str]],
    feed_stories: dict[str, list[Story]],
    rubrics_by_segment: dict[str, list[tuple[str, str]]],
) -> dict:
    per_segment = []
    for name, text in segments:
        sources = "\n".join(s.as_prompt_block() for s in feed_stories.get(name, [])) or "(none)"
        invocation = _invocation(api, name, sources, text)
        entry: dict[str, Any] = {"segment": name}

        entry["hallucinations_v1"] = await _run(
            api["HallucinationsV1Evaluator"](
                api["EvalMetric"](
                    metric_name="hallucinations_v1",
                    threshold=0.8,
                    criterion=api["HallucinationsCriterion"](
                        threshold=0.8,
                        judge_model_options=_judge_options(api, cfg),
                    ),
                )
            ),
            invocation,
        )

        pairs = rubrics_by_segment.get(name, [])
        if pairs:
            rubrics = [
                api["Rubric"](
                    rubric_id=rid,
                    rubric_content=api["RubricContent"](text_property=prop),
                    type="FINAL_RESPONSE_QUALITY",
                )
                for rid, prop in pairs
            ]
            entry["expectations_rubrics"] = await _run(
                api["RubricBasedFinalResponseQualityV1Evaluator"](
                    api["EvalMetric"](
                        metric_name="rubric_based_final_response_quality_v1",
                        threshold=0.8,
                        criterion=api["RubricsBasedCriterion"](
                            threshold=0.8,
                            rubrics=rubrics,
                            judge_model_options=_judge_options(api, cfg),
                        ),
                    )
                ),
                invocation,
                want_rubrics=True,
            )
        per_segment.append(entry)

    return {
        "judge_model": cfg.eval_judge_model,
        "hallucinations_v1": _avg(per_segment, "hallucinations_v1"),
        "expectations_rubrics": _avg(per_segment, "expectations_rubrics"),
        "per_segment": per_segment,
    }


def _judge_options(api: dict[str, Any], cfg: Any) -> Any:
    """Judge model + how many samples it votes over.

    `parallelism_limit=1` keeps the judge calls sequential: these prompts carry whole segments
    plus every source story, and fanning them out is what pushes peak memory over the edge.
    """
    return api["JudgeModelOptions"](
        judge_model=cfg.eval_judge_model,
        num_samples=getattr(cfg, "eval_judge_samples", 3),
        parallelism_limit=1,
    )


def _invocation(api: dict[str, Any], name: str, sources: str, segment: str) -> Any:
    """One graded turn: the sources are the 'user' side, the segment is the agent's answer.

    hallucinations_v1 builds its grounding context from the user content, so putting the source
    stories there is what lets it catch a claim the sources never made.
    """
    types = api["types"]
    return api["Invocation"](
        invocation_id=f"segment-{name}",
        user_content=types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=(
                        f'Write the "{name}" segment of a spoken daily news briefing, using only '
                        f"these source stories.\n\nSOURCE STORIES:\n{sources}"
                    )
                )
            ],
        ),
        final_response=types.Content(
            role="model", parts=[types.Part.from_text(text=segment)]
        ),
    )


async def _run(evaluator: Any, invocation: Any, want_rubrics: bool = False) -> dict:
    """Run one evaluator over one invocation and flatten its result into plain JSON."""
    try:
        result = evaluator.evaluate_invocations(actual_invocations=[invocation])
        if asyncio.iscoroutine(result):
            result = await result
        out: dict[str, Any] = {
            "score": _num(result.overall_score),
            "status": getattr(result.overall_eval_status, "name", None),
        }
        rationales = [
            r.rationale
            for r in (result.per_invocation_results or [])
            if getattr(r, "rationale", None)
        ]
        if rationales:
            out["rationale"] = rationales[0]
        if want_rubrics:
            out["rubrics"] = _rubric_rows(result)
            out["failed"] = [r["rubric_id"] for r in out["rubrics"] if _failed(r["score"])]
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("evaluator %s failed: %s", type(evaluator).__name__, exc)
        return {"score": None, "status": "ERROR", "error": str(exc)}


def _rubric_rows(result: Any) -> list[dict]:
    """Per-rubric scores, taken from the invocation rather than the aggregate.

    We score one invocation (one segment) per evaluator call, so the aggregate adds nothing and
    its rationale is the literal placeholder "This is an aggregated score derived from individual
    entries..." -- useless, when naming *why* a rubric failed is the entire point. The invocation's
    own rubric_scores carry the judge's actual reasoning.
    """
    scores: list[Any] = []
    for per in result.per_invocation_results or []:
        scores.extend(per.rubric_scores or [])
    if not scores:
        scores = list(result.overall_rubric_scores or [])
    return [
        {
            "rubric_id": s.rubric_id,
            "score": _num(s.score),
            "rationale": (s.rationale or "")[:300],
        }
        for s in scores
    ]


def _failed(score: float | None) -> bool:
    return score is not None and score < 0.5


def _num(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return None if num != num else round(num, 3)  # NaN means "not evaluated"


def _avg(rows: list[dict], key: str) -> float | None:
    vals = [r[key]["score"] for r in rows if isinstance(r.get(key), dict) and r[key].get("score") is not None]
    return round(sum(vals) / len(vals), 3) if vals else None
