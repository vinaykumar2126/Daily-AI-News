"""Score one curator on a golden set and print a scorecard.

    python -m evals.run --golden 2026-09-06 --curator deterministic

Loads the stored source stories (so the input is fixed), builds the digest with the chosen
curator, then runs code checks + the LLM judge. Saves scorecard_<curator>.json in the golden dir.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import composer
from config import Config, load_dotenv, load_feeds
from curation import create_curator
from evals import checks
from evals.judge import judge_segment
from pipeline import build_segments_from_stories
from sources.base import Story

GOLDEN_DIR = Path(__file__).parent / "golden"


def load_golden(name: str) -> dict[str, list[Story]]:
    path = GOLDEN_DIR / name / "sources.json"
    raw = json.loads(path.read_text())
    return {feed: [Story.from_dict(d) for d in stories] for feed, stories in raw.items()}


def score(cfg: Config, golden_name: str, curator_name: str) -> dict:
    feeds = load_feeds()
    feed_stories = load_golden(golden_name)
    budgets = {f.name: f.length_budget_words for f in feeds}
    interests = {f.name: f.interests for f in feeds}

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
        judged.append(j)

    def avg(key: str) -> float:
        vals = [j[key] for j in judged]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    return {
        "golden": golden_name,
        "curator": curator_name,
        "latency_sec": round(elapsed, 1),
        "word_count": len(script.split()),
        "code_checks": {r.name: {"passed": r.passed, "score": r.score, "detail": r.detail} for r in code_results},
        "judge": {
            "faithfulness": avg("faithfulness"),
            "coverage": avg("coverage"),
            "relevance": avg("relevance"),
            "per_segment": judged,
        },
        "script": script,
    }


def print_scorecard(sc: dict) -> None:
    print(f"\n{'=' * 60}")
    print(f" Scorecard — golden={sc['golden']}  curator={sc['curator']}")
    print(f"{'=' * 60}")
    print(f" latency: {sc['latency_sec']}s   words: {sc['word_count']}")
    print(" -- code checks --")
    for name, r in sc["code_checks"].items():
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"   [{mark}] {name:18} {r['score']:.2f}  {r['detail']}")
    print(" -- LLM judge (avg 0-1) --")
    j = sc["judge"]
    print(f"   faithfulness {j['faithfulness']:.2f}   coverage {j['coverage']:.2f}   relevance {j['relevance']:.2f}")
    print(f"{'=' * 60}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--curator", default="deterministic", choices=["deterministic", "agentic"])
    args = ap.parse_args()

    load_dotenv()
    cfg = Config()
    sc = score(cfg, args.golden, args.curator)
    print_scorecard(sc)

    out = GOLDEN_DIR / args.golden / f"scorecard_{args.curator}.json"
    out.write_text(json.dumps(sc, indent=2, ensure_ascii=False))
    print(f"Saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
