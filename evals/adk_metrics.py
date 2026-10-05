"""Google's own eval metrics, from `google.adk.evaluation`, run beside the judges in evals/judge.py.

WHAT THIS ADDS
    hallucinations_v1
        Splits the segment into sentences and demands a quotable source excerpt for each one.
        Same axis as our `faithfulness`, but far stricter: where our judge answers one holistic
        question per segment, this one defaults a sentence to "unsupported" unless it can cite
        the context. A disagreement between the two is the useful signal -- it is how we found
        that the Immigration sources are `<a href>` markup with no prose to cite.

    rubric_based_final_response_quality_v1
        Grades the segment against expectations.md, parsed into one rubric per must-include /
        red line / should-drop / duplicate-merge. Our expectations judge returns a single
        adherence float; this returns pass/fail *per rubric*, so "0.985 adherence" becomes
        "Markets invented 'positive day' against your own red line".

HOW ADK'S MACHINERY WORKS (the part that is hard to read in ADK itself)
    Every ADK metric exposes exactly one method:

        evaluate_invocations(actual_invocations, expected_invocations=None) -> EvaluationResult

    An `Invocation` is one graded turn: what went in (`user_content`), what came out
    (`final_response`). We fake one per segment -- sources as the user turn, the segment as the
    model's answer -- see `_invocation`.

    The two metrics reach their score by different routes:

      * The rubric grader inherits `LlmAsJudge`, which owns a template-method loop: build one
        prompt, send it `num_samples` times (a judge at temperature > 0 is not stable), parse
        each reply, vote across the samples, then average across invocations. "auto-rater" is
        ADK's word for the judge LLM.
      * hallucinations_v1 overrides that loop with two phases of its own -- a segmenter prompt
        that splits the text into sentences, then a validator prompt that labels each sentence
        `supported` / `unsupported` / `contradictory` / `disputed` / `not_applicable`. Its score
        is arithmetic, not opinion: the fraction labelled `supported` or `not_applicable`. Note
        it therefore costs *two* judge calls per sample, not one.

    We call `evaluate_invocations` once per segment with a single-item list, rather than handing
    it all four segments at once, because rubrics live on the criterion and each feed has its own
    set. The consequence to remember: `per_invocation_results` always has length 1, and
    `overall_rubric_scores` is the "aggregate" of one item, whose rationale is a placeholder
    string. `_rubric_rows` reads the invocation instead -- see its docstring.

The judge model is deliberately not the generator's (`EVAL_JUDGE_MODEL` default gemini-2.5-flash
vs the rewrite's gemini-2.5-pro): a judge from the same family grades its own work.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from sources.base import Story

log = logging.getLogger("daily-news.evals.adk_metrics")

# Imported up front so the rest of this file reads as plain class names. Guarded because a future
# ADK could rename or drop an experimental evaluator, and that must degrade this one module rather
# than break the whole harness -- evals/run.py imports us even when --adk-metrics is off.
_IMPORT_ERROR: str | None = None
try:
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
except ImportError as exc:  # pragma: no cover - depends on the installed ADK
    _IMPORT_ERROR = str(exc)

# Score at or below which a rubric counts as failed, and the metric threshold ADK uses to stamp
# PASSED/FAILED on a result.
_FAIL_BELOW = 0.5
_THRESHOLD = 0.8


def available() -> bool:
    """Whether the installed ADK exposes the evaluators this module needs."""
    if _IMPORT_ERROR:
        log.warning("ADK eval metrics unavailable: %s", _IMPORT_ERROR)
        return False
    return True


# --------------------------------------------------------------------------- #
# expectations.md -> rubrics
# --------------------------------------------------------------------------- #
# The answer-key groups that can be graded pass/fail against a single segment, and the sentence
# each becomes. Optional groups ("Nice-to-include", "Reasonable to include") are deliberately
# absent: leaving an optional story out is not a failure, so grading it would only add noise.
_GRADEABLE = (
    ("must-include", "must", "The segment covers this story: {item}"),
    # Red lines appear in two forms -- a thing to exclude ("HitPaw sponsored ad") and a standing
    # rule ("no invented benchmark numbers"). Quote the editor's words instead of paraphrasing,
    # or the rule form gets inverted into nonsense.
    ("red line", "redline", "The segment respects this red line: {item}"),
    ("should-drop", "drop", "The segment leaves out, or spends at most a passing mention on: {item}"),
    ("duplicate", "dedupe", "This story is mentioned only once, not repeated as separate items: {item}"),
)

# Rules about length or duration are dropped: a judge shown one segment has no word budget or
# total runtime to compare against (it says so outright -- "constraints not defined in the
# provided prompt"), and evals/checks.run_code_checks already measures those deterministically.
_NOT_JUDGEABLE = re.compile(r"\b(word budget|budget|minutes?|length|runtime)\b", re.I)


def parse_expectations(text: str) -> dict[str, list[tuple[str, str]]]:
    """Split expectations.md into per-segment (rubric_id, property_text) pairs.

    The file is `## <feed name>` sections holding labelled groups (`- Must-include:`,
    `- Red lines (must NOT appear):`) whose items are nested bullets, or trailing text on the
    label line itself. A `## Cross-segment` section applies to every segment. A freshly captured
    golden set has only capture.py's stub, which has no `##` headings and so yields nothing --
    that is the intended way for rubric grading to skip a day with no answer key.
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
        rubrics = _rubrics_from_lines(lines) + _rubrics_from_lines(shared, prefix="cross")
        if rubrics:
            out[name] = rubrics
    return out


def _rubrics_from_lines(lines: list[str], prefix: str = "") -> list[tuple[str, str]]:
    """Turn one section's bullet lines into (rubric_id, property_text) pairs.

    Walks top to bottom holding the current group's template: a label line
    ("- Must-include:") selects it, the bullets indented beneath it are the items.
    """
    lines = _join_wrapped(lines)
    rubrics: list[tuple[str, str]] = []
    template: str | None = None
    kind = ""
    counters: dict[str, int] = {}

    def add(item: str) -> None:
        item = _clean(item)
        if not template or len(item) < 8 or _NOT_JUDGEABLE.search(item):
            return
        counters[kind] = counters.get(kind, 0) + 1
        rubric_id = "_".join(p for p in (prefix, kind, str(counters[kind])) if p)
        rubrics.append((rubric_id, template.format(item=item)))

    for raw in lines:
        if not raw.strip().startswith("-"):
            continue
        indent = len(raw) - len(raw.lstrip())
        body = raw.strip().lstrip("-").strip()
        label, sep, trailing = body.partition(":")

        if indent > 1:  # a nested bullet: an item under whatever group we are in
            add(body)
        elif sep:  # a group label, e.g. "- Red lines (must NOT appear):"
            match = next((g for g in _GRADEABLE if g[0] in label.lower()), None)
            kind, template = (match[1], match[2]) if match else ("", None)
            if trailing.strip():  # the label may carry its only item inline
                add(trailing)
        else:  # an unlabelled top-level bullet (the Cross-segment style): grade it verbatim
            kind, template = "rule", "{item}"
            add(body)
            template = None

    return rubrics


# A parenthesised source reference as written in expectations.md: "(#21)",
# "(#0 TLDR / #3 HN)", "(#2 Indian Express / #3 Times of India)". Only the parenthesised form --
# bare refs like "#2 = #3" ARE the content of a dedupe bullet, and stripping those would empty it.
_SOURCE_REF = re.compile(r"\s*\(\s*#\d+[^)]*\)")

# Your editorial aside, which follows the source ref after an em-dash:
#   "**Green Card rules -- public-charge scrutiny** (#2 IE / #3 ToI) - it's TODAY and hits ..."
#                                                                     ^^^^ from here, dropped
# Anchoring on "ref then em-dash" is what makes this safe: an em-dash *inside* the claim
# ("Canada / EU membership -- Trump's reaction") comes before the ref and survives, where cutting
# at the first em-dash would have truncated the claim itself.
_ASIDE_AFTER_REF = re.compile(r"(\(\s*#\d+[^)]*\))\s*\u2014.*$")


def _join_wrapped(lines: list[str]) -> list[str]:
    """Fold continuation lines back into their bullet.

    A bullet wrapped over several lines is ordinary markdown, and the walker below only inspects
    lines that start with "-", so without this a long rule is silently truncated at its first line
    -- a cross-segment rule once reached the judge as `...read naturally for the ear ("H-1B" -> "H
    one B"` with the rest of the sentence missing.
    """
    out: list[str] = []
    for raw in lines:
        if raw.strip().startswith("-") or not raw.strip():
            out.append(raw)
        elif out and out[-1].strip().startswith("-"):
            out[-1] = out[-1].rstrip() + " " + raw.strip()
        else:
            out.append(raw)
    return out


def _clean(item: str) -> str:
    """Reduce one bullet to the claim the judge should verify.

    Drops the trailing editorial aside, the source refs (meaningless to a judge that never sees
    sources.json indices), markdown emphasis, and the punctuation left behind.
    """
    item = _ASIDE_AFTER_REF.sub(r"\1", item)
    item = _SOURCE_REF.sub("", item)
    item = item.replace("**", "").replace("`", "")
    item = re.sub(r"\s+([,;.])", r"\1", item)  # " ," left where a ref was removed mid-list
    return re.sub(r"\s{2,}", " ", item).strip(" .,;")


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score_segments(
    cfg: Any,
    segments: list[tuple[str, str]],
    feed_stories: dict[str, list[Story]],
    expectations: str = "",
) -> dict | None:
    """Score every segment with ADK's evaluators.

    Returns None when the installed ADK can't provide them, so the caller drops the block rather
    than failing the eval. A failure mid-run returns a dict carrying `error` for the same reason.
    """
    if not available():
        return None

    rubrics_by_segment = parse_expectations(expectations)
    try:
        return asyncio.run(_score_all(cfg, segments, feed_stories, rubrics_by_segment))
    except Exception as exc:  # noqa: BLE001
        log.warning("ADK eval metrics failed: %s", exc)
        return {"error": str(exc), "judge_model": cfg.eval_judge_model, "per_segment": []}


async def _score_all(
    cfg: Any,
    segments: list[tuple[str, str]],
    feed_stories: dict[str, list[Story]],
    rubrics_by_segment: dict[str, list[tuple[str, str]]],
) -> dict:
    per_segment: list[dict[str, Any]] = []
    for name, text in segments:
        sources = "\n".join(s.as_prompt_block() for s in feed_stories.get(name, [])) or "(none)"
        invocation = _invocation(name, sources, text)

        entry: dict[str, Any] = {"segment": name}
        # hallucinations_v1 scores each step exactly once -- its evaluate_invocations override has
        # no num_samples loop -- so unlike the rubric grader there is no vote to absorb one flaky
        # judge call. A single transient failure returned NOT_EVALUATED and silently lost the whole
        # metric for this segment on two consecutive runs. One retry costs a judge call and only
        # happens on failure.
        entry["hallucinations_v1"] = await _run_with_retry(
            lambda: _hallucinations_evaluator(cfg), invocation, label=f"hallucinations_v1/{name}"
        )

        pairs = rubrics_by_segment.get(name, [])
        if pairs:
            entry["expectations_rubrics"] = await _run(
                _rubric_evaluator(cfg, pairs), invocation, want_rubrics=True
            )
        per_segment.append(entry)

    return {
        "judge_model": cfg.eval_judge_model,
        "hallucinations_v1": _avg(per_segment, "hallucinations_v1"),
        "expectations_rubrics": _avg(per_segment, "expectations_rubrics"),
        "per_segment": per_segment,
    }


def _judge_options(cfg: Any) -> Any:
    """Which judge, how many samples it votes over, and how many run at once.

    `parallelism_limit=1` keeps samples sequential on purpose: each prompt carries a whole segment
    plus every source story, and fanning them out is what got this process OOM-killed.
    """
    return JudgeModelOptions(
        judge_model=cfg.eval_judge_model,
        num_samples=getattr(cfg, "eval_judge_samples", 3),
        parallelism_limit=1,
    )


def _keep_failure_reason(evaluator: Any) -> Any:
    """Make hallucinations_v1 say WHY it could not score something.

    `_evaluate_nl_response` returns `(score, reason)` and names the problem exactly -- "Segmenter
    returned no text.", "Error during sentence validation: {e}", and three others. ADK's caller
    throws it away (`fs_score, _ = await ...`), the None then propagates to
    `overall_eval_status=NOT_EVALUATED`, and the scorecard shows a bare `n/a` with nothing in the
    log to explain it. That happened on AI & Tech in two consecutive runs and cost real time to
    chase. This wrapper keeps the reason, logs it, and stashes it for the scorecard.

    Reaches into a private method, so it is defensive: if ADK renames it, grading still works and
    we only lose the diagnostic.
    """
    inner = getattr(evaluator, "_evaluate_nl_response", None)
    if inner is None:  # pragma: no cover - depends on the installed ADK
        log.debug("hallucinations_v1 has no _evaluate_nl_response; failure reasons unavailable.")
        return evaluator

    evaluator._daily_news_failure = None

    async def _with_reason(nl_response: str, context: str) -> Any:
        score, reason = await inner(nl_response, context)
        if score is None:
            evaluator._daily_news_failure = reason
            log.warning(
                "hallucinations_v1 could not score a response (%d chars, context %d chars): %s",
                len(nl_response or ""),
                len(context or ""),
                (reason or "no reason given")[:300],
            )
        return score, reason

    evaluator._evaluate_nl_response = _with_reason
    return evaluator


def _hallucinations_evaluator(cfg: Any) -> Any:
    """Sentence-level grounding check of the segment against its sources.

    Note this metric does NOT sample and vote the way the rubric grader does -- its
    `evaluate_invocations` override scores each step exactly once, so `EVAL_JUDGE_SAMPLES` has no
    effect here and a single flaky judge call loses the metric for that segment outright.
    """
    return _keep_failure_reason(
        HallucinationsV1Evaluator(
            EvalMetric(
                metric_name="hallucinations_v1",
                threshold=_THRESHOLD,
                criterion=HallucinationsCriterion(
                    threshold=_THRESHOLD, judge_model_options=_judge_options(cfg)
                ),
            )
        )
    )


def _rubric_evaluator(cfg: Any, pairs: list[tuple[str, str]]) -> Any:
    """Per-rubric grading of the segment against this feed's slice of expectations.md."""
    rubrics = [
        Rubric(
            rubric_id=rubric_id,
            rubric_content=RubricContent(text_property=prop),
            # Must match RubricBasedFinalResponseQualityV1Evaluator.RUBRIC_TYPE, which it filters on.
            type="FINAL_RESPONSE_QUALITY",
        )
        for rubric_id, prop in pairs
    ]
    return RubricBasedFinalResponseQualityV1Evaluator(
        EvalMetric(
            metric_name="rubric_based_final_response_quality_v1",
            threshold=_THRESHOLD,
            criterion=RubricsBasedCriterion(
                threshold=_THRESHOLD, rubrics=rubrics, judge_model_options=_judge_options(cfg)
            ),
        )
    )


def _invocation(name: str, sources: str, segment: str) -> Any:
    """One graded turn: the sources are the 'user' side, the segment is the agent's answer.

    hallucinations_v1 builds its grounding context out of the user content, so the source stories
    have to live there -- that is what lets it catch a claim the sources never made.
    """
    return Invocation(
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
        final_response=types.Content(role="model", parts=[types.Part.from_text(text=segment)]),
    )


async def _run_with_retry(
    build: Any, invocation: Any, label: str, attempts: int = 2
) -> dict:
    """Run an evaluator, retrying once if it comes back with no score.

    Takes a factory rather than an instance: the evaluator caches the failure reason on itself, so a
    retry needs a fresh one to avoid reporting the first attempt's reason alongside a later success.
    """
    out: dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        out = await _run(build(), invocation)
        if out.get("score") is not None:
            if attempt > 1:
                log.info("%s succeeded on attempt %d", label, attempt)
            return out
        if attempt < attempts:
            log.warning("%s returned no score (attempt %d/%d); retrying", label, attempt, attempts)
    out["attempts"] = attempts
    return out


async def _run(evaluator: Any, invocation: Any, want_rubrics: bool = False) -> dict:
    """Run one evaluator over one invocation and flatten its EvaluationResult into plain JSON."""
    try:
        result = evaluator.evaluate_invocations(actual_invocations=[invocation])
        if asyncio.iscoroutine(result):
            result = await result

        out: dict[str, Any] = {
            "score": _num(result.overall_score),
            "status": getattr(result.overall_eval_status, "name", None),
        }
        # A metric that did not run is not the same as a metric that scored badly, and a bare `n/a`
        # in the scorecard reads like the latter. Say so, and carry any reason the evaluator kept.
        if out["score"] is None:
            out["not_evaluated_reason"] = getattr(evaluator, "_daily_news_failure", None) or (
                "evaluator returned no score and gave no reason"
            )
            log.warning(
                "%s did not score this segment (status=%s): %s",
                type(evaluator).__name__,
                out["status"],
                str(out["not_evaluated_reason"])[:200],
            )
        for per in result.per_invocation_results or []:
            if getattr(per, "rationale", None):
                out["rationale"] = per.rationale
                break
        if want_rubrics:
            out["rubrics"] = _rubric_rows(result)
            out["failed"] = [r["rubric_id"] for r in out["rubrics"] if _failed(r["score"])]
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("evaluator %s failed: %s", type(evaluator).__name__, exc)
        return {"score": None, "status": "ERROR", "error": str(exc)}


def _rubric_rows(result: Any) -> list[dict]:
    """Per-rubric scores, read off the invocation rather than the aggregate.

    We grade one invocation per call, so `overall_rubric_scores` is the aggregate of a single item
    and its rationale is the literal placeholder "This is an aggregated score derived from
    individual entries..." -- useless, when naming *why* a rubric failed is the entire point. The
    invocation's own rubric_scores carry the judge's actual reasoning.
    """
    scores: list[Any] = []
    for per in result.per_invocation_results or []:
        scores.extend(per.rubric_scores or [])
    if not scores:  # only reachable if ADK stops populating per-invocation scores
        scores = list(result.overall_rubric_scores or [])
    return [
        {"rubric_id": s.rubric_id, "score": _num(s.score), "rationale": (s.rationale or "")[:300]}
        for s in scores
    ]


def _failed(score: float | None) -> bool:
    return score is not None and score < _FAIL_BELOW


def _num(value: Any) -> float | None:
    """Round a score, mapping None and ADK's NaN ("not evaluated") to None."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return None if num != num else round(num, 3)


def _avg(rows: list[dict], key: str) -> float | None:
    """Mean of a metric across segments, ignoring segments where it did not run."""
    scores = [
        row[key]["score"]
        for row in rows
        if isinstance(row.get(key), dict) and row[key].get("score") is not None
    ]
    return round(sum(scores) / len(scores), 3) if scores else None
