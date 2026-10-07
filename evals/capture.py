"""Snapshot today's real source stories into a golden set for repeatable evals.

    python -m evals.capture --name 2026-09-06

Writes evals/golden/<name>/sources.json = {feed_name: [story, ...]} and a stub expectations.md
you can fill with notes (must-include stories, known duplicates). Re-running evals against a
golden set gives stable, comparable scores because the input never changes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from config import load_dotenv, load_feeds
from pipeline import gather_stories

GOLDEN_DIR = Path(__file__).parent / "golden"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default=dt.date.today().isoformat(), help="golden set name")
    args = ap.parse_args()

    load_dotenv()
    feeds = load_feeds()
    out_dir = GOLDEN_DIR / args.name
    out_dir.mkdir(parents=True, exist_ok=True)

    data = {}
    for feed in feeds:
        stories = gather_stories(feed)
        data[feed.name] = [s.to_dict() for s in stories]
        print(f"  {feed.name}: {len(stories)} stories")

    (out_dir / "sources.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
    exp = out_dir / "expectations.md"
    if not exp.exists():
        exp.write_text(
            f"# Expectations for golden set {args.name}\n\n"
            "- Must-include stories:\n- Known duplicates:\n- Notes:\n"
        )
    print(f"Wrote golden set to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
