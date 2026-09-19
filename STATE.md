# STATE — where I left off
`Daily_News` · updated 2026-09-19 · _read this first, update before I stop_

## ▶ Start here (next)
- [ ] Chase the 1 remaining eval miss → OpenAI "concerning AI behaviour" safety story dropped in AI segment (0.985 adherence otherwise). Nudge curator to prioritize major-lab safety news, or accept.
- [ ] US Headlines coverage low → fix ranking (Option A only touched AI feed).
- [ ] Try 2-host podcast format (less "reading the screen" — script/composer, not voice).
- [ ] Later: observability/cost tracing → then deploy.

## Now
- **Branch:** `feature/multisource-agentic` · clean · last commit `a2fd443`
- **Pushed?** yes · **Deployed to GCP?** ❌ no (Cloud Run runs OLD code; push ≠ deploy)
- **Latest eval (2026-09-18, agentic):** adherence **0.985** · faithfulness 1.0 · latency 148s

## What it is
Daily audio news briefing: fetch sources → curate → LLM rewrites → Cloud TTS → email me. One digest, 4 segments: AI & Tech / US Headlines / Immigration / Markets.

## Built
- Config-driven pipeline; add topics in `feeds.yaml` (no code)
- Swappable curator (Strategy): `deterministic` | `agentic` (ADK), via `CURATOR` env; agent → deterministic fallback on error
- Eval harness (`evals/`): code checks + LLM-judge (vs sources) + expectations-judge (vs my answer key) + compare
- TTS = stable Chirp3-HD (dropped Gemini TTS preview — no gain)
- Notes: `docs/field-notes.html`

## Gotchas I hit (one-liners)
- TTS = hard **per-request** limit: Gemini 4000 / standard 5000 bytes → chunk + stitch
- Limit is **bytes, not chars** (em-dash = 3 bytes) → chunker counts UTF-8
- Gemini TTS field is `model_name`, not `model` (lib ≥ 2.29.0)
- ADK "No API key" = wrong backend → set `GOOGLE_GENAI_USE_VERTEXAI=True` (+project/region), don't add a key
- LLM-judge reads **segment + reference in ONE prompt**, grades one vs the other; it can't browse links (no tool = no web)
- Only the **curator** differs between det/agentic — clean A/B
- `expectations.md` = my rubric (must-include/drop/merge/red-lines), written by me from `sources.json` — NOT a model answer
- **Trust expectations-adherence over source-coverage** — source-coverage 0.5 was misleading (counts dropping junk as "missing")
- **Cramming hurts faithfulness** — max_stories 14 → 0.8 faith + 5min; back to 10 → 1.0 + 148s

## Run
```bash
DRY_RUN=1 CURATOR=deterministic .venv/bin/python main.py    # print, no send
.venv/bin/python main.py                                    # full: audio + email
.venv/bin/python -m evals.capture --name YYYY-MM-DD         # snapshot golden set
.venv/bin/python -m evals.run --golden YYYY-MM-DD --curator agentic
.venv/bin/python -m evals.compare --golden YYYY-MM-DD       # head-to-head
```

## Open Qs
- Judge = same model as generator → self-bias? try a different judge model
- Capture full article text into golden sets (faithfulness needs it)
- Agent memory: lookback window? store structured tool records, not just titles?
