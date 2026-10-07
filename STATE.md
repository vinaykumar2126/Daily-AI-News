# STATE — where I left off
`Daily_News` · updated 2026-10-03 · _read this first, update before I stop_

## ▶ Start here (next) — 2026-10-04

### 🔴 Pick up exactly here: finish the 2026-10-03 answer key, then run both harnesses
I stopped mid-task. `evals/golden/2026-10-03/expectations.md` exists (33 rubrics, parses fine) but
**Claude drafted it, not me** — it is still untracked and still has the `# REVIEW` block in it. My
own rule is that this file is my judgment, not a model's, so until I review it the
`expectations_adherence` and rubric scores from this day are provisional.

- [ ] **Review the draft key.** Specifically the calls flagged in the `# REVIEW` block: whether the
      Meta Muse cluster deserves a line (I currently have it in duplicates, which is wrong — see
      below), and whether Offrun (#22) / Pi pod (#23) are hobby projects or tier-2 agent tooling.
      Delete the `# REVIEW` block when done.
- [ ] **Fix `dedupe_2` (Meta Muse: #3 ≡ #35 ≡ #37) — it is incoherent.** Those are three *different
      opinion pieces about the same subject*, not three reports of one event. "Merge into one
      mention" is the wrong instruction; they belong in should-drop. Contrast `dedupe_1` (Cloudflare
      Clef #4 ≡ #38 ≡ #33), which is legitimate: #4 and #38 are literally the same article and #33
      is third-party coverage of it.
- [ ] **Then run BOTH harnesses and compare:**
      `EVAL_MODE=1 .venv/bin/python -m evals.run --golden 2026-10-03 --curator agentic --adk-metrics`
      Baseline to beat (own judges only, 2026-10-03, temps 0.2/0.2): faithfulness **1.00** ·
      coverage 0.65–0.74 · relevance 1.00.

#### What I learned about dedupe rubrics (do not re-derive this)
- **A `dedupe_*` rubric passes vacuously when the story is absent.** The judge's own words on 09-18:
  *"The final answer does not mention the Green Card rules … Therefore the condition [holds]"* →
  scored **1.0**. So **pair every `dedupe` with a `must-include`**, or it is a free point.
  `dedupe_1` has teeth because Clef is also `must_1`: must_1 forces it to appear, dedupe_1 forces it
  to appear only once.
- **What dedupe actually tests:** count the distinct times the segment presents one event as a news
  item; is it exactly one? Structural, not factual. "Clef and Clef-flash" in one sentence is 2 word
  occurrences but 1 item — a pass. Facts are `faithfulness` / `hallucinations_v1`'s job, not this.
- **The `#n` refs are invisible to the judge.** `Story.as_prompt_block()` renders
  `- title / body / (url)` with **no index numbers**, so nothing in the prompt maps `#4` to a story.
  The judge matches on the human-readable name ("Cloudflare Clef") — that phrase is what does the
  work. Keep the refs for my own bookkeeping, but **write every bullet so it stands alone.**
- **Beware the judge echoing my numbers back.** On 09-18 it wrote *"successfully combined the
  information from Source Stories 2 and 3"*, which sounds like verification but cannot be — it was
  repeating the numbers from my property text. The verdict may be right; the stated reasoning is
  partly theatre.
- **My label text never reaches the judge.** "- Known duplicates (merge into ONE mention each):" is
  scanned only for the word "duplicate", which selects a template; the label words are discarded.
  What the judge sees is the generated sentence, e.g. `This story is mentioned only once, not
  repeated as separate items: Cloudflare Clef: #4 ≡ #38 ≡ #33`.
- **There is no code comparing rubric to segment.** One LLM reads `<properties>` + `<user_prompt>`
  (sources) + `<response>` (segment) and writes a verdict per `[id: …]`. The only deterministic
  comparisons in the whole harness are the 3 checks in `evals/checks.py`.

### 🟠 The big one I keep deferring: DEPLOY
- [ ] **Cloud Run is running an image built 2026-09-04** — four weeks stale. The job itself runs fine
      every morning (`daily-news-6rk8n`, 2026-10-03T11:03Z, succeeded), but on code that has **none**
      of: the fee→bond fix, either temperature, the broadened prompt rules, any tracing, the
      significance-ranking curator, or `_strip_html`. **Everything I fixed this week is laptop-only.**
      `deploy.sh` still needs: `telemetry.googleapis.com` + `cloudtrace.googleapis.com` in the enable
      list, `roles/cloudtrace.agent` on `vertex-ai-runner@`, and `GEMINI_REWRITE_MODEL`,
      `REWRITE_TEMPERATURE`, `CURATOR_TEMPERATURE`, `TRACE_ENABLED`, `TRACE_BACKEND`,
      `OTEL_SERVICE_NAME` in `--set-env-vars`. `TRACE_CONTENT` needs nothing — Cloud Run sets
      `K_SERVICE`, so prompt text is excluded in prod automatically. Note `deploy.sh` still sets
      `CURATOR=deterministic`; flip it only *after* one clean traced run, so a bad briefing is
      attributable to one change rather than three.

### ✅ Closed today — do NOT redo these
- ~~Google News RSS markup~~ — **I already fixed this on 2026-09-20 in `9b7db6d`.** `_strip_html`
  runs at `sources/google_news_rss.py:109` and works; today's capture had **0 markup bodies in all
  four feeds**. The markup only survives in golden sets captured *before* 09-20 (09-07, 09-08,
  09-13, 09-18). So `hallucinations_v1` scoring Immigration 0.20 was an artifact of a stale eval
  fixture, not a live defect. I had this wrong at the top of this file for a week.
- ~~`_needs_enrichment` HTML blob~~ — moot once bodies are clean prose. The `news.google.com` URL
  guard still short-circuits before the length check, but with real prose arriving that is now a
  design choice rather than a bug.
- ~~`fee` → `bond` hallucination~~ — fixed (see Today, 2026-10-03). Faithfulness 1.00 on all four
  segments across two consecutive runs.

### Still open
- [ ] **`[Markets] agent returned no selection` — reproducible, and it is NOT US Headlines.**
      Fired in all 4 runs today, Markets every time. My old note blaming US Headlines was wrong.
      Likely cause: Markets has 2 candidates against `max_stories=4`, so the agent has nothing to
      trim and returns an empty selection; `_run_agent` raises `RuntimeError("agent returned no
      selection")` on an empty list and falls back to deterministic. Fix: treat "selected
      everything" / "nothing to trim" as success when `len(stories) <= max_stories`.
- [ ] **`cross_rule_1` (acronyms for the ear) fails consistently** — 2 segments, 2 runs.
      "ICE" read as "Immigration and Customs Enforcement". Consistent = real, not noise.
      Fix in `prompts/_shared_style.md`.
- [ ] **Immigration segment once shipped as literally "(empty response)"** — the rewrite returned
      that string (2 words / 4 output tokens) and `if text:` kept it. Not seen since the
      temperature change, but the guard is still missing in `pipeline.rewrite`.
- [ ] **Pin `google-adk`.** `requirements.txt` says `>=2.9.0` and the evaluators are marked
      EXPERIMENTAL (that's the `UserWarning` spam). An upgrade can change their prompts and move my
      scores with no code change from me.
- [ ] **Tidy `adk_apps.curator/`** — `adk web` saved `eval_set_1.evalset.json` into a directory
      whose name has a **dot**, not a slash, so it is a sibling of `adk_apps/` rather than inside
      it. Move it under `adk_apps/curator/` or delete it.
- [ ] **Coverage is the weak axis now that faithfulness is fixed** — 0.65–0.78, driven by AI & Tech
      (41 candidates → 10) and Immigration. That is the next quality lever.
- [ ] **`evals/judge.py` has no temperature set** — my own 3 judges run at the API default (1.0).
      The ruler itself moves. Pinning it costs nothing in production (eval-only code) and would
      make score changes attributable.
- [ ] Try 2-host podcast format (less "reading the screen" — script/composer, not voice).
- [ ] Deploy: `deploy.sh` still needs `telemetry.googleapis.com`/`cloudtrace.googleapis.com` enabled + `roles/cloudtrace.agent` & `roles/monitoring.metricWriter` on `vertex-ai-runner@`, and the `TRACE_*` env vars. Left alone on purpose this pass.

## Today (2026-10-03) — killed a real hallucination, pinned both temperatures

**The defect.** Immigration faithfulness came back **0.60** on a fresh golden set. The segment said
a court blocked a "$100,000 **bond**" for H-1B visas, "aimed primarily at **IT consulting and
outsourcing firms**". Neither "bond" nor "outsourcing" appears anywhere in the 13 source stories —
the source says **fee**. Both inventions are *true in the real world*, which is the tell: the model
filled in from its own knowledge instead of the sources.

**Why my existing prompt rule did not catch it.** `_shared_style.md` already said "Never invent
facts" and listed *"a number, price, model name, date, or benchmark"*. The model substituted a
**noun** (fee → bond) and added a **scope** (who it targets). Neither is on that list, and it read
the enumeration as exhaustive. So the fix was not to say it louder — it was to close the hole.

**What I changed:**
- `prompts/_shared_style.md` — broadened to "number, price, name, date, benchmark, cause, or scope",
  plus **"This list is not exhaustive — anything not in the source is off limits, including things
  you happen to know are true."** Added two rules: *call things what the source calls them* (a fee
  is not a bond/tax/deposit; a proposal is not a law) and *do not add who something targets or
  exempts unless the source says so*.
- `pipeline.rewrite` passed **no generation config at all** — my most accuracy-critical step ran at
  the API default (1.0). Now `config={"temperature": cfg.rewrite_temperature}`.
- `curation/agentic.py` — same for the curator's ADK Agent via
  `generate_content_config=types.GenerateContentConfig(temperature=_TEMPERATURE)`.
- Both knobs: `REWRITE_TEMPERATURE` / `CURATOR_TEMPERATURE`, default **0.2**, in `.env.example`.
  Both land on their spans as `gen_ai.request.temperature`, so a trace shows what ran at what.

**Result (same frozen golden set 2026-10-03, two consecutive runs):**
- Faithfulness **1.00 on every segment, both runs** (was 0.90 avg / 0.60 on Immigration). "bond",
  "IT consulting", "outsourcing" all gone from the text — I checked the string, not just the score.
- No collateral damage: AI & Tech / US Headlines / Markets stayed at 1.00.
- **0.2 stops invention but does NOT give reproducibility.** Scripts differed (869 vs 800 words).
  Traces show why: `curate` picked **3** Immigration stories in run A and **2** in run B, and the
  rewrite produced **492 vs 407** words on AI & Tech from the *same* 10 stories. Coverage still
  swings 0.65–0.74.
- Decision: **keep 0.2/0.2.** For a clean comparison, run with
  `CURATOR_TEMPERATURE=0 REWRITE_TEMPERATURE=0` — no code change needed.

**Also today:**
- `adk web` adapter — `adk_apps/curator/` exposes `root_agent` reusing the real `_INSTRUCTION` and
  tools (`adk web adk_apps` → `/list-apps` returns `["curator"]`). `ADK_WEB_FEED` picks the feed.
  `adk_apps/dump_candidates.py --feed X [--golden DATE]` prints paste-ready input.
  ⚠ It only shows the **curator** — the rewrite and all judges are raw `genai` calls, not agents.
- Next time, build agents ADK-native from the start: `adk create`, module-level `root_agent`, a
  **callable instruction** (`Callable[[ReadonlyContext], str]`) reading per-run values from session
  state instead of rebuilding the Agent per feed, and a `.env` in the agent folder (ADK loads it).
- `evals/capture.py`'s stub `expectations.md` is **actively dangerous**: non-empty, so
  `has_expectations=True` and the expectations judge graded against an empty key and returned
  **1.00 on all four segments** — a false perfect score. Deleted the stub; the judge then skips.

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
- **Latest eval (2026-10-03, agentic, own judges only):** faithfulness **1.00** · coverage 0.65–0.74
  · relevance 1.00 · latency 158–165s · 800–869 words · temperatures 0.2/0.2
  - Two consecutive runs on the same frozen set: faithfulness identical, coverage and wording not.
- **Previous eval (2026-09-18, agentic, `--adk-metrics`, 2026-09-26):** adherence **0.78** ·
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
- **Both LLM steps have a pinned temperature** (0.2/0.2, `REWRITE_TEMPERATURE` /
  `CURATOR_TEMPERATURE`). They had none, so they ran at Gemini's default of 1.0.
- **Prompt rules against invention are now about *kinds* of claim, not a checklist of entity types**
  — renaming a thing, and adding unstated scope, are both explicitly out.
- **`adk_apps/curator/`** — the curator exposed for `adk web`, reusing the real instruction + tools.
- **Tracing, all Google, no LangSmith.** ADK already emits the GenAI spans — I just never called the bootstrap. `observability.py` does that + adds stage spans (gather/curate/enrich/rewrite/compose/TTS/email). Knobs are `TRACE_*` in `.env.example`; see ARCHITECTURE.md.
- **Token counts exist now.** They were being thrown away at all 5 LLM call sites. So the field-notes line about the agentic curator "not justifying ~2× the cost" is finally measurable instead of a guess.
- **`evals/adk_metrics.py`** — Google's own judges (`hallucinations_v1`, `rubric_based_final_response_quality_v1`) behind `--adk-metrics`. My `expectations.md` gets parsed into individual rubrics, so a miss gets *named* instead of averaged into 0.985. Old judges and scorecard keys untouched, so old scorecards stay comparable.
- Config-driven pipeline; add topics in `feeds.yaml` (no code)
- Swappable curator (Strategy): `deterministic` | `agentic` (ADK), via `CURATOR` env; agent → deterministic fallback on error
- Eval harness (`evals/`): code checks + LLM-judge (vs sources) + expectations-judge (vs my answer key) + compare
- TTS = stable Chirp3-HD (dropped Gemini TTS preview — no gain)
- Notes: `docs/field-notes.html`

## Where I struggled, 2026-09-26 (so I don't burn the time twice)
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
- **`dedupe_*` rubrics pass for free when the story is absent** — always pair one with a must-include.
- **The judge never sees my `#n` source refs** — `as_prompt_block()` emits no indices. The
  human-readable name in the bullet is what it matches on.
- **My expectations.md label text is discarded** — only the keyword in it ("duplicate", "red line")
  selects a template. The judge reads the generated sentence, not my wording.
- **Gemini 2.5's default temperature is 1.0, not ~0.** Neither the rewrite nor the curator set one,
  so my most accuracy-critical steps were sampling freely. That was the root of both the invented
  "bond" and the un-comparable eval scores.
- **A prompt rule phrased as a list gets read as exhaustive.** "Never invent a number, price, model
  name, date, or benchmark" did not stop fee → bond, because a noun swap is not on the list.
- **Temperature 0.2 ≠ deterministic.** Stops invention; does not stabilise ranking or length. Use 0
  when I need runs to be comparable.
- **`capture.py`'s stub `expectations.md` produces a FALSE 1.00 adherence**, not an error. Delete it
  on a day I have not written a real answer key.
- **`evals/run.py` logs nothing at INFO** — no `basicConfig`, so only WARNINGs reach the log. To see
  per-feed curation counts, read the trace (`curate` span → `stories_out`), not the log.
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

