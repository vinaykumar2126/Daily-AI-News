# STATE — where I left off
`Daily_News` · updated 2026-09-26 · _read this first, update before I stop_

## ▶ Start here (next) — 2026-09-27
**Do this first. It's the root cause of three separate symptoms.**
- [ ] **Google News RSS bodies are raw `<a href>` markup, not article text.** Every Immigration and
      US Headlines story's `body` is a link blob (`<a href="https://news.google.com/rss/articles/CBMi…`),
      522–3061 chars of junk. So the rewrite only ever sees the *headline*. This is why
      `hallucinations_v1` scores Immigration 0.20–0.25 while my own judge says 1.00 — the judge
      literally has nothing to cite. Fix: strip HTML in `sources/google_news_rss.py` so `body` holds
      prose or nothing. Helpers already exist: `sources.base.strip_symbols`, `_strip_html`
      (tested in `tests/test_cleaning.py`), `pipeline._clean_enriched`.
- [ ] **Then revisit `pipeline._needs_enrichment`.** Two problems, and I had the reason wrong at first:
      the *operative* one is the `news.google.com` URL guard, which returns False on line 1 and never
      reaches the length check. The docstring's assumption — "those segments' headlines are
      self-contained" — is simply false for Immigration. The `len(body) < 200` test is a *latent*
      second bug: the HTML blob is >200 chars so it would sail through anyway.
- [ ] **`cross_rule_1` (acronyms for the ear) now fails consistently** — 2 segments, 2 runs in a row.
      "ICE" read as "Immigration and Customs Enforcement". Consistent = real, not noise. Prompt fix in
      `prompts/_shared_style.md`, not a curator fix.
- [ ] **Commit the tail end.** Tracing + evals are in (`ce3ea58`, `bfe43c1`). Still uncommitted:
      `STATE.md`, `evals/adk_metrics.py` (the source-ref/aside stripping), and
      `evals/golden/2026-09-18/scorecard_agentic.json`. **Nothing pushed yet** — branch
      `feature/evaluations-tracing` is local only.
- [ ] **Pin `google-adk`.** `requirements.txt` says `>=2.9.0`, and the evaluators are marked
      EXPERIMENTAL by Google (that's the `UserWarning` spam in eval logs). An upgrade can change the
      prompts and move my scores with no code change on my side.
- [ ] **Immigration segment shipped as literally "(empty response)"** — the 2.5-pro rewrite returned that string (2 words / 4 output tokens) and `if text:` happily kept it. Found it in the very first trace. Guard `rewrite()` against junk output, or re-prompt.
- [ ] **Agentic curator silently falls back on US Headlines** — "agent returned no selection", every time I've looked. Trace label `curation.fallback=true`. This is probably the same thing as the old "US Headlines coverage low" note: the agent isn't ranking that feed at all, deterministic is. Fix the curator there, not the ranking.
- [ ] **The per-rubric grading works — act on what it found** (2026-09-18, agentic, judge 2.5-flash):
  - `Markets / redline_1` — the rewrite invents interpretation ("positive day", "strongest showing") when my red line says report only the numbers present. My own judge gave Markets 1.00 and missed this entirely.
  - `US Headlines / cross_rule_1` — reads "ICE" as "Immigration and Customs Enforcement"; my acronyms-for-the-ear rule wants the letters. Style nit but it's in the TTS output.
  - `Immigration / must_2` — dropped the JD Vance H-1B story.
  - `AI & Tech / drop_1` — kept one should-drop item ("LLM Classification is Feature Engineering").
- [ ] Try 2-host podcast format (less "reading the screen" — script/composer, not voice).
- [ ] Deploy: `deploy.sh` still needs `telemetry.googleapis.com`/`cloudtrace.googleapis.com` enabled + `roles/cloudtrace.agent` & `roles/monitoring.metricWriter` on `vertex-ai-runner@`, and the `TRACE_*` env vars. Left alone on purpose this pass.

## Today (2026-09-26) — understood the ADK eval metrics, then cleaned up my own code
Spent today NOT building features: reading ADK's evaluation source until I actually understood what
I'd wired up yesterday, then fixing what was confusing or wrong.

**What the two ADK metrics actually do** (settled, don't re-derive this):
- `hallucinations_v1` — **two LLM phases**, not one. A *segmenter* prompt splits my segment into
  sentences, then a *validator* prompt labels each sentence `supported` / `unsupported` /
  `contradictory` / `disputed` / `not_applicable`, and must quote an excerpt for the positive ones.
  Score = plain arithmetic: fraction labelled `supported` or `not_applicable`. **Needs no
  expectations.md.** It overrides `evaluate_invocations` instead of using the shared judge loop, so
  it costs *two* judge calls per sample.
- `rubric_based_final_response_quality_v1` — inherits `LlmAsJudge`, which owns a template-method
  loop: build one prompt → send it `num_samples` times → parse → vote → average. Metrics plug in 4
  hooks (`format_auto_rater_prompt`, `convert_auto_rater_response_to_score`,
  `aggregate_per_invocation_samples`, `aggregate_invocation_results`). **Needs expectations.md.**
- "auto-rater" is just ADK's word for the judge LLM. `Invocation` = one graded turn
  (`user_content` in, `final_response` out). Every metric exposes exactly one public method:
  `evaluate_invocations(actual_invocations, expected_invocations=None) -> EvaluationResult`.

**The ADK source is readable — it's in my own venv, Apache-2.0:**
`.venv/lib/python3.14/site-packages/google/adk/evaluation/` → `hallucinations_v1.py` (class L258),
`rubric_based_final_response_quality_v1.py` (L243), `llm_as_judge.py` (the shared loop, L68).
The prompts are the metric; everything else is plumbing. `inspect.getsource(X.method)` also works.

**What one rubric judge prompt actually contains** (measured, Immigration, 27,175 chars):

| slot | chars | share | whose |
|---|---|---|---|
| Instructions (Mission/Rubric/Principles/Output Format) | 5,027 | 18.5% | ADK |
| One fully worked few-shot example | 6,384 | 23.5% | ADK |
| `<user_prompt>` = my 12 source stories | 14,183 | **52.2%** | mine |
| `<response>` = the 102-word segment | 868 | 3.2% | mine |
| `<properties>` = my 5 rubrics | 676 | 2.5% | mine |

So ~42% is ADK scaffolding before my data appears, and **my rubrics are 2.5% of it**. This whole
thing goes out 3× per segment. Token cost is dominated by source text, not by anything I control.

**Why the sources are in the rubric prompt at all** (I got confused by this — the segment is
already there, so why?). Because *I* put them there: `_invocation()` sets `user_content` to the
sources, and ADK's prompt has a `{user_input}` slot it fills from that. It matters per rubric kind:
- `must_*` ("covers story X") — **doesn't really need sources**, the rubric text names the story.
- `drop_*` — weak need; a paraphrase is ambiguous without the source.
- `dedupe_*` — **needs them**: the rubric is literally `#2 ≡ #3`, meaningless otherwise.
- `redline_*` — **needs them by definition**: "report only the numbers *present*" means present in
  the sources. Without them, "+1.69%" is indistinguishable from a fabrication.
Decision: leave it. Splitting into sourced/unsourced evaluators would double the calls to halve
each prompt. Net worse.

**Visualizations I built today (real data, not mock-ups):**
- Rubric grading trace — every bullet → property → verdict: https://claude.ai/artifact/ALw4fAJNXzXZN86HPKkASQ
- Judge prompt anatomy — the full 27k prompt, slot by slot: https://claude.ai/artifact/WUPtLQPhgEZNahuZ8iEEdc

**Code changes today:**
- Rewrote `evals/adk_metrics.py`. Killed the `api["Rubric"]` dictionary (an `_imports()` that
  returned `locals()`) — 11 lookups → 0, real imports, so Go-to-Definition works. File reads in
  execution order now, plus a 46-line docstring explaining the machinery above.
- Fixed per-rubric rationales: I was reading `overall_rubric_scores` (the *aggregate* of one item),
  whose rationale is the literal placeholder "This is an aggregated score derived from individual
  entries…". Now reads `per_invocation_results[].rubric_scores` → real reasoning.
- `parse_expectations` now strips `(#2 Indian Express / #3 ToI)` source refs and my trailing
  editorial asides. Rubric counts unchanged (27 for 09-13, 24 for 09-18) so nothing got silently
  dropped.
- Dropped non-judgeable rubrics (word budget / runtime) — the judge said outright "constraints not
  defined in the provided prompt", and `evals/checks.py` already measures length deterministically.
- **`EVAL_MODE` was read but never set** (`curation/agentic.py:124`). Any eval run not prefixed
  `EVAL_MODE=1` was writing its replayed golden picks into `.digest_memory.json`, which
  `recent_digest_history` then feeds into the next real digest. `evals/run.py` sets it itself now.

## Now
- **Branch:** `feature/evaluations-tracing` (cut from `feature/hackathon`, *before* `b24789e` — so `CURATOR` still defaults to `deterministic` here)
- **Pushed?** not yet · **Deployed to GCP?** ❌ no (Cloud Run runs OLD code; push ≠ deploy)
- **Latest eval (2026-09-18, agentic, `--adk-metrics`, 2026-09-26):** adherence **0.78** ·
  faithfulness 1.00 · coverage 0.60 · relevance 1.00 · latency 130.5s · 782 words
  - ADK alongside: `hallucinations_v1` **0.81** · `expectations_rubrics` **0.80**
  - Rubric failures: AI & Tech `must_3, must_4, drop_1, cross_rule_1` (0.67) · US Headlines
    `cross_rule_1` (0.75) · Immigration `must_2` (0.80) · **Markets clean (1.00)**
  - Both judges independently flagged the same AI & Tech misses (Meta Muse Mac app, OpenAI
    "concerning behaviour") — good cross-validation, and it's the same story that's been slipping
    for over a week.
  - ⚠ **Do not compare across runs.** Three runs of this same golden set gave adherence 0.95 / 0.84 /
    0.78 and Markets rubrics 0.667 → 1.00. That's curator nondeterminism, not progress or
    regression. Isolating a real change needs the curator pinned to temperature 0.
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

## Where I struggled today (so I don't burn the time twice)
- **My own `adk_metrics.py` was the main obstacle.** I read it for 30+ minutes and still found it
  elusive. The culprit was a function that imported everything and returned `locals()` as a dict, so
  every call site read `api["EvalMetric"](...)` — no symbol to click, no autocomplete, no way to tell
  a class from a string. Rewritten. **Lesson: don't hide imports in a dict to centralise
  ImportError handling.** A `try:` block around real module-level imports does the same job.
- **"Golden data set" tripped me up hardest.** I assumed golden = a reference answer to diff output
  against. It is **not**. In this repo: `sources.json` = the *frozen input* (news stories), and
  `expectations.md` = the *answer key*. Two different files, two different jobs. "Golden" only means
  the input can't move between runs, so a score change is my code and not the news.
- **I thought `capture.py` generated `expectations.md` content.** It writes a **95-byte stub**
  (`- Must-include stories:` and nothing else). I hand-wrote the real ones. Proof: 09-07 and 09-08
  are still 95-byte stubs; 09-13 (2,821 B) and 09-18 (3,011 B) are mine, with `## <feed>` sections.
  Also: the stub inside `2026-09-07/` says "golden set 2026-09-06" — `capture.py` only writes it
  `if not exp.exists()`, so a renamed directory keeps the old date.
- **The name `hallucinations_v1` is misleading and cost me time.** It does not measure "the model
  made something up". It measures **"I cannot find this in the context"** — which includes claims
  that are true but simply absent from my sources. With Google News RSS giving me `<a href>` markup,
  those two things are wildly different. The 0.20 was my *data* failing, not Gemini inventing facts.
- **A reference-free judge needs no answer key, and that confused me.** `faithfulness` and
  `hallucinations_v1` compare output → **sources**; `expectations_adherence` and the rubric grader
  compare output → **my answer key**. So I can eval a freshly captured day with zero writing from me
  and still get faithfulness/coverage/relevance/hallucinations — just not the two answer-key metrics.
- **Rubrics are not all "is it present?"** Half of mine pass by *absence*: `must_*` = present,
  `redline_*`/`drop_*` = absent, `dedupe_*` = present exactly once. Markets failed because the
  segment **added** "positive day"/"strongest showing" — a failure a presence-only check can't see.
- **ADK returns a confidence 0–1 per rubric, not pass/fail.** The red/failed marking in my scorecard
  is *my* threshold, `_FAIL_BELOW = 0.5` in `evals/adk_metrics.py`. I can move it.

## Gotchas I hit (one-liners)
- **I did NOT need LangSmith/LangChain.** `langsmith` is out of `requirements.txt`; `google-adk[gcp]` ships the exporters. (`.env` still has dead `LANGSMITH_*`, `LLM_PROVIDER`, `USE_VERTEX`, `VERTEX_MODEL`, `VERTEX_REGION` keys — nothing reads them, clean them out when convenient.)
- **`telemetry.googleapis.com` lies to you.** ADK's default backend returned HTTP 200 for every span and Cloud Trace had nothing — reading a trace id back gives `_Trace bucket not found in project`. The project isn't onboarded to the new Trace storage. Fixed by defaulting `TRACE_BACKEND=cloudtrace` (classic BatchWriteSpans, queryable in seconds). `telemetry` is still there for later.
- **Batched exporter + one-shot job = zero traces.** Must `force_flush()` before exit, in a `finally` so the failure path exports too. This cost me a confusing "it works but nothing shows up".
- **A 400 from the OTLP endpoint just means no `gcp.project_id`** on the OTel resource → always pass `get_gcp_resource(project)`.
- **`gcloud trace list` doesn't exist** in my gcloud. Read traces with the REST API: `GET https://cloudtrace.googleapis.com/v1/projects/$P/traces/$TRACE_ID` (+ `?filter=span:daily_news.run` on the list endpoint; the unfiltered list is stale/useless).
- **`EVAL_MODE` was read but never set anywhere** — evals were polluting `.digest_memory.json`
  unless I remembered the prefix. `evals/run.py` sets it now.
- **`overall_rubric_scores` is a trap when you grade one invocation at a time.** Its rationale is the
  string "This is an aggregated score derived from individual entries…". Read
  `per_invocation_results[].rubric_scores` instead.
- **Don't cut a bullet at the first em-dash.** My titles contain em-dashes ("New Green Card rules
  effective Sept 18 — public-charge scrutiny", "Canada / EU membership — Trump's reaction"). Anchor
  on *source-ref then em-dash* instead, which is where my commentary actually starts.
- **Don't strip bare `#n` refs** — `dedupe` bullets are literally `#2 ≡ #3`; stripping those empties
  the property and the `len < 8` guard then deletes the rubric silently. Only strip the
  parenthesised `(#n …)` form.
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
EVAL_JUDGE_SAMPLES=1 .venv/bin/python -m evals.run --golden X --curator agentic --adk-metrics  # cheap
TRACE_ENABLED=0 DRY_RUN=1 .venv/bin/python main.py          # untraced

# see my expectations.md as the rubrics the judge receives
.venv/bin/python -c "from evals.adk_metrics import parse_expectations; from evals.run import load_expectations
[print(f'[id: {r}] {p}') for r,p in parse_expectations(load_expectations('2026-09-18'))['Markets']]"

# read ADK's own source (it's in my venv, Apache-2.0)
sed -n '113,209p' .venv/lib/python3.14/site-packages/google/adk/evaluation/hallucinations_v1.py

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

