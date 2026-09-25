# STATE — where I left off
`Daily_News` · updated 2026-09-24 · _read this first, update before I stop_

## ▶ Start here (next)
- [ ] **Immigration segment shipped as literally "(empty response)"** — the 2.5-pro rewrite returned that string (2 words / 4 output tokens) and `if text:` happily kept it. Found it in the very first trace. Guard `rewrite()` against junk output, or re-prompt.
- [ ] **Agentic curator silently falls back on US Headlines** — "agent returned no selection", every time I've looked. Trace label `curation.fallback=true`. This is probably the same thing as the old "US Headlines coverage low" note: the agent isn't ranking that feed at all, deterministic is. Fix the curator there, not the ranking.
- [ ] **The per-rubric grading works — act on what it found** (2026-09-18, agentic, judge 2.5-flash):
  - `Markets / redline_1` — the rewrite invents interpretation ("positive day", "strongest showing") when my red line says report only the numbers present. My own judge gave Markets 1.00 and missed this entirely.
  - `US Headlines / cross_rule_1` — reads "ICE" as "Immigration and Customs Enforcement"; my acronyms-for-the-ear rule wants the letters. Style nit but it's in the TTS output.
  - `Immigration / must_2` — dropped the JD Vance H-1B story.
  - `AI & Tech / drop_1` — kept one should-drop item ("LLM Classification is Feature Engineering").
- [ ] Try 2-host podcast format (less "reading the screen" — script/composer, not voice).
- [ ] Deploy: `deploy.sh` still needs `telemetry.googleapis.com`/`cloudtrace.googleapis.com` enabled + `roles/cloudtrace.agent` & `roles/monitoring.metricWriter` on `vertex-ai-runner@`, and the `TRACE_*` env vars. Left alone on purpose this pass.

## Now
- **Branch:** `feature/evaluations-tracing` (cut from `feature/hackathon`, *before* `b24789e` — so `CURATOR` still defaults to `deterministic` here)
- **Pushed?** not yet · **Deployed to GCP?** ❌ no (Cloud Run runs OLD code; push ≠ deploy)
- **Latest eval (2026-09-18, agentic, `--adk-metrics`):** adherence **0.84** · faithfulness 1.0 · coverage 0.66 · latency 123s · 787 words
  - ADK metrics alongside: `hallucinations_v1` **0.75** · `expectations_rubrics` **0.78**
  - ⚠ Not comparable to the old 0.985/148s line — that was a different generation. The curator is nondeterministic, so scores move run to run; compare *within* a run, not across.
- **Tracing is live.** Verified: a full agentic DRY_RUN = one 51-span trace in Cloud Trace, 149s, token counts on every model call. Trace id from that run: `eaeab797cbf00f5b0459ceba57304cd6`.

## What it is
Daily audio news briefing: fetch sources → curate → LLM rewrites → Cloud TTS → email me. One digest, 4 segments: AI & Tech / US Headlines / Immigration / Markets.

## Built
- **Tracing, all Google, no LangSmith.** ADK already emits the GenAI spans — I just never called the bootstrap. `observability.py` does that + adds stage spans (gather/curate/enrich/rewrite/compose/TTS/email). Knobs are `TRACE_*` in `.env.example`; see ARCHITECTURE.md.
- **Token counts exist now.** They were being thrown away at all 5 LLM call sites. So the field-notes line about the agentic curator "not justifying ~2× the cost" is finally measurable instead of a guess.
- **`evals/adk_metrics.py`** — Google's own judges (`hallucinations_v1`, `rubric_based_final_response_quality_v1`) behind `--adk-metrics`. My `expectations.md` gets parsed into individual rubrics, so a miss gets *named* instead of averaged into 0.985. Old judges and scorecard keys untouched, so old scorecards stay comparable.
- Config-driven pipeline; add topics in `feeds.yaml` (no code)
- Swappable curator (Strategy): `deterministic` | `agentic` (ADK), via `CURATOR` env; agent → deterministic fallback on error
- Eval harness (`evals/`): code checks + LLM-judge (vs sources) + expectations-judge (vs my answer key) + compare
- TTS = stable Chirp3-HD (dropped Gemini TTS preview — no gain)
- Notes: `docs/field-notes.html`

## Gotchas I hit (one-liners)
- **I did NOT need LangSmith/LangChain.** `langsmith` is out of `requirements.txt`; `google-adk[gcp]` ships the exporters. (`.env` still has dead `LANGSMITH_*`, `LLM_PROVIDER`, `USE_VERTEX`, `VERTEX_MODEL`, `VERTEX_REGION` keys — nothing reads them, clean them out when convenient.)
- **`telemetry.googleapis.com` lies to you.** ADK's default backend returned HTTP 200 for every span and Cloud Trace had nothing — reading a trace id back gives `_Trace bucket not found in project`. The project isn't onboarded to the new Trace storage. Fixed by defaulting `TRACE_BACKEND=cloudtrace` (classic BatchWriteSpans, queryable in seconds). `telemetry` is still there for later.
- **Batched exporter + one-shot job = zero traces.** Must `force_flush()` before exit, in a `finally` so the failure path exports too. This cost me a confusing "it works but nothing shows up".
- **A 400 from the OTLP endpoint just means no `gcp.project_id`** on the OTel resource → always pass `get_gcp_resource(project)`.
- **`gcloud trace list` doesn't exist** in my gcloud. Read traces with the REST API: `GET https://cloudtrace.googleapis.com/v1/projects/$P/traces/$TRACE_ID` (+ `?filter=span:daily_news.run` on the list endpoint; the unfiltered list is stale/useless).
- **ADK evaluators sample the judge 5x by default** (`JudgeModelOptions.num_samples`) = 40 judge calls for a 4-segment digest on top of the pipeline rebuild; got the process OOM-killed twice on this laptop. Now `EVAL_JUDGE_SAMPLES=3` + `parallelism_limit=1` -> 24 sequential calls.
- **Cloud Monitoring metric export is flaky** — `Error while writing to Cloud Monitoring` / `UNAVAILABLE: Getting metadata from plugin failed ... Connection reset by peer`, 3x in one eval run, 0x in a pipeline run. Non-fatal (exporter logs + continues) but it dumps a full traceback each time. So `TRACE_METRICS` now defaults **off** — the spans already carry `gen_ai.usage.*`, so I lose nothing.
- **Content off ≠ label gone.** With `TRACE_CONTENT=0` ADK still writes `gcp.vertex.agent.llm_request` but as `"{}"` (2 bytes). Check the *value*, not the key.
- **`ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS` is read once**, at `TelemetryConfig` construction — set it before the first agent run, not lazily.
- Span helper's name arg is positional-only on purpose: `span("feed", name=...)` blew up with "got multiple values for argument 'name'" until I made it `span(span_name, /, **attrs)`.
- `opentelemetry-instrumentation-google-genai>=1.2b0` is **unresolvable** with `google-adk` 2.9.0 (wants otel-api ~=1.43, ADK caps <=1.42.1). Use `>=0.7b1,<1` + `opentelemetry-instrumentation<0.64b0`.
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
.venv/bin/python -m evals.run --golden YYYY-MM-DD --curator agentic --adk-metrics   # + Google's judges
TRACE_ENABLED=0 DRY_RUN=1 .venv/bin/python main.py          # untraced

# read a trace back (gcloud has no `trace` command)
TOK=$(gcloud auth print-access-token)
curl -s -H "Authorization: Bearer $TOK" \
  "https://cloudtrace.googleapis.com/v1/projects/dailynews-507123/traces/<TRACE_ID>"
```

## Open Qs
- Judge = same model as generator → self-bias? Partly handled: ADK metrics judge with `EVAL_JUDGE_MODEL` (2.5-flash) while the rewrite is 2.5-pro. My own judges in `evals/judge.py` still use `gemini_model`.
- **`hallucinations_v1` is stricter than my faithfulness judge, and it's probably right.** Two runs: mine 0.80 / ADK 0.78 (agreed), then mine **1.00** / ADK **0.75** (disagreed). Both runs put Immigration lowest (0.33, then 0.20). When my judge says a segment is perfectly faithful and Google's says 0.20, I should look at the segment, not the judge. Worth reading the ADK rationales before I trust my own 1.0 again.
- `call_llm` reports far more output tokens than its child `generate_content` (7336 vs 5 on one AI & Tech call) — ADK is aggregating thoughts/turns. Worth understanding before I quote cost numbers.
- Capture full article text into golden sets (faithfulness needs it)
- Agent memory: lookback window? store structured tool records, not just titles?

