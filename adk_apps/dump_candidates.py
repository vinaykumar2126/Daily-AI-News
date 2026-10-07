"""Print one feed's real candidate stories, formatted exactly as the curator receives them.

The pipeline hands the agent a numbered list built by curation.agentic._format_stories. Paste this
output into the `adk web` chat box and you are giving the agent the same input it gets in a real
run, rather than something hand-typed that only looks similar.

    .venv/bin/python adk_apps/dump_candidates.py                        # AI & Tech
    .venv/bin/python adk_apps/dump_candidates.py --feed "US Headlines"
    .venv/bin/python adk_apps/dump_candidates.py --golden 2026-09-18    # replay a frozen day
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_dotenv, load_feeds  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feed", default="AI & Tech", help="feed name from feeds.yaml")
    ap.add_argument("--golden", help="replay a captured golden set instead of fetching live")
    args = ap.parse_args()

    load_dotenv()
    from curation.agentic import _format_stories
    from pipeline import gather_stories

    feeds = {f.name: f for f in load_feeds()}
    if args.feed not in feeds:
        raise SystemExit(f"No feed {args.feed!r}. Available: {list(feeds)}")
    feed = feeds[args.feed]

    if args.golden:
        from evals.run import load_golden

        stories = load_golden(args.golden).get(feed.name, [])
    else:
        stories = gather_stories(feed)

    if not stories:
        raise SystemExit(f"No stories for {feed.name}.")

    # Same wrapper the pipeline uses, so the agent sees a byte-identical user turn.
    print("Candidate stories:\n")
    print(_format_stories(stories))
    print(
        f"\n--- {len(stories)} candidates · feed {feed.name!r} · max_stories {feed.max_stories} ---",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
