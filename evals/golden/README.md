# Golden sets

Each subdirectory is one captured day of real source material, used for **repeatable** evals —
the input never changes, so scores are comparable across prompt/curator tweaks.

```
evals/golden/<name>/
  sources.json       # {feed_name: [story, ...]} captured from real feeds
  expectations.md    # human notes: must-include stories, known duplicates
  scorecard_*.json   # written by `python -m evals.run`
  comparison.json    # written by `python -m evals.compare`
```

## Workflow

```bash
# 1. Capture a real day (do this on a few different days to build variety)
python -m evals.capture --name 2026-09-06

# 2. Score a curator
python -m evals.run --golden 2026-09-06 --curator deterministic

# 3. Once the agentic curator exists, compare them head-to-head
python -m evals.compare --golden 2026-09-06
```
