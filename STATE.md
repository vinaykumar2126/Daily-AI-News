# STATE — where I left off

_My running dev log for Daily_News. Read this first when I come back. Update it before I stop._

_Last updated: 2026-09-18_

## Right now
- **Branch:** `feature/multisource-agentic`. STATE.md and the expectations→judge wiring ARE committed now (commits `73222de`, `562f973`), so those are safe.
- **Uncommitted today — COMMIT THESE so they don't get wiped like last time:** `feeds.yaml` (Option A caps + walk-back to max_stories 10), `prompts/ai_news.md` (coverage rundown), `curation/agentic.py` ("don't drop launches" instruction), `pipeline.py`, `.digest_memory.json`, and the new `evals/golden/2026-09-18/` (today's golden set + my answer key + scorecards).
- **Pushed to GitHub?** Yes (older commits). **Deployed to GCP?** No — Cloud Run still runs the OLD single-source code. Pushing ≠ deploying; deploy runs `deploy.sh` on my local code, not GitHub.

## What this project is
A daily audio news briefing. It pulls stories from several sources, an LLM rewrites them into a spoken script, Cloud TTS makes an MP3, and it emails me the clip. One combined digest: AI & Tech, US Headlines, Immigration & Visas, Markets.

## What I've built
- Config-driven pipeline: sources (Gmail, Google News RSS, Hacker News, stocks) → curate → rewrite → compose → TTS → email. New topics = edit `feeds.yaml`, no code.
- **Swappable curator** (Strategy pattern): `deterministic` (default) or `agentic` (Google ADK), chosen by the `CURATOR` env var. Agent falls back to deterministic on error.
- **Eval harness** in `evals/`: code checks + LLM-as-judge + golden sets + a deterministic-vs-agentic compare.
- TTS on stable **Chirp3-HD** voice (dropped the Gemini TTS preview — no audible gain, and it forced a 4000-byte limit).
- Interview notes doc at `docs/field-notes.html` (also published as an artifact).

## Where I got stuck / what took me long to get (my own notes)
- **TTS byte limit.** TTS only takes so much text per request. Gemini TTS = 4000 bytes, standard = 5000. That's why the code chunks the script and stitches the audio. Took me a while to see this was a hard per-request cap, not a bug.
- **Bytes ≠ characters.** The limit is in BYTES. An em-dash `—` is 3 bytes, curly quotes too. So a script that "looks" short by character count can blow the byte limit. The chunker had to count UTF-8 bytes, not `len()`.
- **`model` vs `model_name`.** For Gemini TTS the field is `model_name` on `VoiceSelectionParams` (needs library ≥ 2.29.0), not `model`. I had the wrong field name.
- **Vertex vs API key.** The Gemini SDK / ADK defaulted to the AI-Studio API-key path and errored "No API key provided." Fix was routing it to Vertex with `GOOGLE_GENAI_USE_VERTEXAI=True` + project + region — NOT adding a key.
- **How LLM-as-judge actually works.** The judge reads the segment script AND the source stories in ONE prompt and grades one against the other. It can't catch a hallucination or a missed story without both halves.
- **The judge does NOT open links.** A plain LLM call has no internet — the URL in the JSON is just text. So faithfulness is only checked against the short snippet I captured, not the full article. (Only a tool like `fetch_article` gives web access — the agent has it, the judge doesn't.)
- **Reference-free vs reference-based.** I thought my `expectations.md` was driving the scores — it wasn't. The scorecard numbers came from the judge reading only `sources.json`. `expectations.md` was just a doc until it's wired into the judge. (Now fixed AND committed: `judge_against_expectations()` + `load_expectations()` feed my answer key into the score.)
- **`.env` vs `.env.`** — a stray trailing dot in the dotenv path meant nothing loaded. Silly but cost time.
- **How the grading actually flows.** It clicked once I said it out loud: the eval loads the frozen stories from `sources.json` (not live), the curator picks which ones, the LLM rewrites them into a segment, and then TWO judges score it — one against `sources.json` (faithfulness / coverage / relevance), one against my `expectations.md` (did it hit my must-includes and drop the noise). Only the *curator* differs between deterministic and agentic; everything else is identical, so any score gap is caused purely by which stories the brain picked.
- **`expectations.md` is a rubric, not a model answer.** It's my list of judgments — must-include / drop-as-noise / merge-duplicates / red-lines — not the exact words the segment should say. And I write it myself by reading `sources.json`, so it reflects MY editorial taste. If I want the score to mean "does the app do what *I* want," I have to keep editing that file to match my priorities.
- **Two "coverage" numbers can disagree — trust the expectations one.** On 2026-09-18 the source-based coverage said 0.5 for the AI segment, but expectations-adherence said 0.94. The 0.5 looked scary but was misleading — it penalizes me for dropping the ~20 junk stories I WANTED dropped. The 0.985 overall adherence was the real signal: the app covered what I said matters. Without my answer key I'd have panicked at 0.5 and kept loosening caps.
- **Cramming stories hurts faithfulness.** I first raised `max_stories` to 14 to "cover everything" — faithfulness dropped 1.0 → 0.8 and latency doubled (~5 min). Walked it back to 10 (kept budget 700) → faithfulness back to 1.0, latency halved to ~148s. "Cover everything" has a real cost; better ranking beats bigger caps.

## Next steps (start here)
1. **Re-add the expectations→judge wiring** — it was reverted and is NOT in `evals/judge.py` / `evals/run.py` right now. Need `judge_against_expectations()` in judge.py and `load_expectations()` + the per-segment call in run.py, so `expectations_adherence` shows up in the scorecard.
2. Run the **agentic vs deterministic comparison** on a golden set once #1 is back.
3. If I want it to feel less like "reading the screen": try a **two-host podcast format** (script/composer change) — the voice model wasn't the lever.
4. Commit `docs/field-notes.html` to the branch.
5. Later: observability / cost tracing; then deploy (merge PR → pull main → `bash deploy.sh`).

## How to run
```bash
DRY_RUN=1 CURATOR=deterministic .venv/bin/python main.py     # print script, no audio/email
.venv/bin/python main.py                                     # full run: audio + email
.venv/bin/python -m evals.capture --name YYYY-MM-DD          # snapshot a golden set
.venv/bin/python -m evals.run --golden YYYY-MM-DD --curator deterministic
.venv/bin/python -m evals.compare --golden YYYY-MM-DD        # head-to-head
```

## Open questions I keep circling
- Judge uses the same model as the generator → self-bias? Consider a different/stronger judge model.
- Capture fuller article text into golden sets so faithfulness has something real to check.
- Agent memory lookback window (14 vs 30 days) and whether to store structured tool records (name/company/metric), not just titles.
