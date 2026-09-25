"""Score one curator on a golden set and print a scorecard.

    python -m evals.run --golden 2026-09-06 --curator deterministic
    python -m evals.run --golden 2026-09-06 --curator agentic --adk-metrics

Loads the stored source stories (so the input is fixed), builds the digest with the chosen
curator, then runs code checks + the LLM judge. Saves scorecard_<curator>.json in the golden dir.
The run is traced to Cloud Trace, so latency and token spend land next to the scores.

--adk-metrics adds Google's own evaluators (ADK hallucinations_v1 + per-rubric grading of
expectations.md) as a second opinion. Off by default: it costs extra judge tokens, and leaving it
off keeps a scorecard directly comparable with the ones already captured.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import composer
import observability
from config import Config, load_dotenv, load_feeds
from curation import create_curator
from evals import adk_metrics, checks
from evals.judge import judge_against_expectations, judge_segment
from pipeline import build_segments_from_stories
from sources.base import Story

GOLDEN_DIR = Path(__file__).parent / "golden"


def load_golden(name: str) -> dict[str, list[Story]]:
    path = GOLDEN_DIR / name / "sources.json"
    raw = json.loads(path.read_text())
    return {feed: [Story.from_dict(d) for d in stories] for feed, stories in raw.items()}


def load_expectations(name: str) -> str:
    """Read the human-written expectations.md answer key, if present."""
    path = GOLDEN_DIR / name / "expectations.md"
    return path.read_text() if path.exists() else ""


def score(
    cfg: Config, golden_name: str, curator_name: str, with_adk_metrics: bool = False
) -> dict:
    feeds = load_feeds()
    feed_stories = load_golden(golden_name)
    budgets = {f.name: f.length_budget_words for f in feeds}
    interests = {f.name: f.interests for f in feeds}

    expectations = load_expectations(golden_name)

    curator = create_curator(curator_name)
    t0 = time.time()
    segments = build_segments_from_stories(cfg, feeds, feed_stories, curator)
    elapsed = time.time() - t0
    script = composer.compose(segments)

    code_results = checks.run_code_checks(script, segments, budgets)

    judged = []
    for name, text in segments:
        focus = ", ".join(interests.get(name, [])) or name
        j = judge_segment(cfg, focus, text, feed_stories.get(name, []))
        j["segment"] = name
        # Reference-based grade against the human answer key (if expectations.md exists).
        if expectations:
            exp = judge_against_expectations(cfg, name, text, expectations)
            j["expectations_adherence"] = exp["expectations_adherence"]
            j["missed_must_includes"] = exp["missed_must_includes"]
            j["kept_noise"] = exp["kept_noise"]
            j["expectations_rationale"] = exp["rationale"]
        judged.append(j)

    adk = (
        adk_metrics.score_segments(cfg, segments, feed_stories, expectations)
        if with_adk_metrics
        else None
    )

    def avg(key: str) -> float:
        vals = [j[key] for j in judged if key in j]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    scorecard = {
        "golden": golden_name,
        "curator": curator_name,
        "latency_sec": round(elapsed, 1),
        "word_count": len(script.split()),
        "has_expectations": bool(expectations),
        "code_checks": {r.name: {"passed": r.passed, "score": r.score, "detail": r.detail} for r in code_results},
        "judge": {
            "faithfulness": avg("faithfulness"),
            "coverage": avg("coverage"),
            "relevance": avg("relevance"),
            "expectations_adherence": avg("expectations_adherence"),
            "per_segment": judged,
        },
        "script": script,
    }
    if adk is not None:
        scorecard["adk_metrics"] = adk
    return scorecard


def print_scorecard(sc: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f" Scorecard — golden={sc['golden']}  curator={sc['curator']}")
    print(f"{'=' * 60}")
    print(f" latency: {sc['latency_sec']}s   words: {sc['word_count']}")
    print(" -- code checks --")
    for name, r in sc["code_checks"].items():
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"   [{mark}] {name:18} {r['score']:.2f}  {r['detail']}")
    print(" -- LLM judge, source-based (avg 0-1) --")
    j = sc["judge"]
    print(f"   faithfulness {j['faithfulness']:.2f}   coverage {j['coverage']:.2f}   relevance {j['relevance']:.2f}")
    _print_adk_metrics(sc)
    if sc.get("has_expectations"):
        print(" -- LLM judge vs YOUR expectations.md (avg 0-1) --")
        print(f"   expectations_adherence {j['expectations_adherence']:.2f}")
        for seg in j["per_segment"]:
            if "expectations_adherence" not in seg:
                continue
            missed = ", ".join(seg.get("missed_must_includes") or []) or "none"
            kept = ", ".join(seg.get("kept_noise") or []) or "none"
            print(f"     [{seg['segment']}] {seg['expectations_adherence']:.2f}  "
                  f"missed: {missed} | kept noise: {kept}")
    print(f"{'=' * 60}\n")


def _print_adk_metrics(sc: dict) -> None:
    """Print the ADK block, if --adk-metrics was used."""
    adk = sc.get("adk_metrics")
    if not adk:
        return
    print(f" -- ADK / Google metrics (judge {adk.get('judge_model')}) --")
    if adk.get("error"):
        print(f"   ERROR: {adk['error']}")
        return
    halluc = adk.get("hallucinations_v1")
    rubrics = adk.get("expectations_rubrics")
    print(
        f"   hallucinations_v1 {_fmt(halluc)}   expectations_rubrics {_fmt(rubrics)}"
    )
    for seg in adk.get("per_segment", []):
        rubric = seg.get("expectations_rubrics") or {}
        failed = ", ".join(rubric.get("failed") or []) or "none"
        print(
            f"     [{seg['segment']}] halluc {_fmt((seg.get('hallucinations_v1') or {}).get('score'))}"
            f"  rubrics {_fmt(rubric.get('score'))}  failed: {failed}"
        )
        for row in rubric.get("rubrics", []):
            if row.get("score") is not None and row["score"] < 0.5:
                print(f"        x {row['rubric_id']}: {row['rationale'][:120]}")


def _fmt(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:.2f}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--curator", default="deterministic", choices=["deterministic", "agentic"])
    ap.add_argument(
        "--adk-metrics",
        action="store_true",
        help="also score with ADK's hallucinations_v1 + per-rubric expectations grading",
    )
    args = ap.parse_args()

    load_dotenv()
    cfg = Config()
    observability.setup(cfg)
    try:
        with observability.span(
            "daily_news.eval",
            golden=args.golden,
            curator=args.curator,
            adk_metrics=args.adk_metrics,
        ):
            sc = score(cfg, args.golden, args.curator, with_adk_metrics=args.adk_metrics)
            observability.set_attrs(words=sc["word_count"], latency_sec=sc["latency_sec"])
        print_scorecard(sc)

        out = GOLDEN_DIR / args.golden / f"scorecard_{args.curator}.json"
        out.write_text(json.dumps(sc, indent=2, ensure_ascii=False))
        print(f"Saved {out}")
        return 0
    finally:
        observability.flush()


if __name__ == "__main__":
    raise SystemExit(main())
