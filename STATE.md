# STATE — where I left off

_My running dev log for Daily_News. Read this first when I come back. Update it before I stop._

_Last updated: 2026-09-16_

## Right now
- **Branch:** `feature/multisource-agentic` — clean, everything committed.
- **Last commit:** `6e5c1c1` "Evaluated with a self written golden dataset with LLM as a Judge".
- **Pushed to GitHub?** Yes. **Deployed to GCP?** No — Cloud Run still runs the OLD single-source code. Pushing ≠ deploying; deploy runs `deploy.sh` on my local code, not GitHub.

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
- **Reference-free vs reference-based.** I thought my `expectations.md` was driving the scores — it wasn't. The scorecard numbers came from the judge reading only `sources.json`. `expectations.md` was just a doc until it's wired into the judge. (See next step — that wiring got reverted.)
- **`.env` vs `.env.`** — a stray trailing dot in the dotenv path meant nothing loaded. Silly but cost time.

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
