# ARCHITECTURE — Daily_News
`Daily_News` · updated 2026-10-04 · _how the app fits together. Update when the structure changes._

**In one line:** every morning it pulls news from several sources, an LLM rewrites it into a spoken script, turns that into audio, and emails me the clip.

> The diagram below is [Mermaid](https://mermaid.js.org/). It renders as a graph on GitHub automatically, or in VS Code with the "Markdown Preview Mermaid Support" extension.

## The flow (what happens each run)

```mermaid
flowchart TD
    Sched[Cloud Scheduler · 7 AM] --> Run[Cloud Run Job → main.py]
    Run --> Loop{for each feed in feeds.yaml}
    Loop --> Fetch[sources/ · fetch + merge stories]
    Fetch --> Cur[curation/ · curator picks + ranks]
    Cur --> Rewrite[pipeline.rewrite · Gemini writes the segment]
    Rewrite --> Loop
    Loop -->|all segments done| Comp[composer.py · stitch into one script]
    Comp --> TTS[main.synthesize_mp3 · Cloud TTS → MP3]
    TTS --> Mail[main.send_email · Gmail]
    Comp -.optional.-> Arc[archive_to_gcs]
```

**In plain words:**
1. A timer (Cloud Scheduler) starts the job → runs `main.py`.
2. `main.py` reads the feed list from `feeds.yaml`.
3. For each feed: **fetch** stories from its sources → **curate** (pick the good ones) → **rewrite** into a spoken segment with Gemini.
4. `composer.py` stitches all segments into one script (greeting + transitions + sign-off).
5. `main.py` turns the script into an MP3 (Cloud TTS) and emails it. Optionally archives to GCS.

### The two LLM steps, and their temperature

Only two steps call a model in a normal run, and **both are paraphrase-or-judge work, not creative
work** — so both are pinned low. They had no temperature at all until 2026-10-03, which meant they
ran at Gemini's default of 1.0; that is how a `$100,000 H-1B fee` once became a `bond`.

| Step | Model | Env | Default |
|---|---|---|---|
| `curation/agentic.py` — ranks + trims the candidates | `GEMINI_MODEL` (2.5-flash) | `CURATOR_TEMPERATURE` | `0.2` |
| `pipeline.rewrite` — writes the spoken segment | `GEMINI_REWRITE_MODEL` (2.5-pro) | `REWRITE_TEMPERATURE` | `0.2` |

0.2 stops invention but is **not** deterministic — the same frozen golden set still yields a
different story selection and length each run. Export both as `0` when you need two eval runs to be
comparable.

## A second entry point: the realtime voice agent

`main.py` makes the daily clip. `agent/sync.py` is a separate, optional path that reuses the same
pipeline to keep a conversational agent's knowledge base current, so you can ask it follow-ups.

```mermaid
flowchart LR
    S[agent/sync.py] --> C[agent/context.py<br/>reuses gather + curate + rewrite]
    C --> M[render_markdown<br/>→ today_knowledge.md]
    M --> P{Provider · providers/base.py}
    P --> E[ElevenLabs<br/>knowledge-base upload]
    P -.scaffold.-> G[gemini_live.py]
    P -.scaffold.-> R[retell.py]
    V[REALTIME_PROVIDER env] -.selects.-> P
```

Same **strategy pattern** as the curator: a `Provider` contract behind `REALTIME_PROVIDER`. Only the
knowledge-base refresh is actually built — `ElevenLabsProvider.sync()`. Its live-call methods
(signed URL, outbound dial) and both other providers are still `NotImplementedError` stubs, so this
branch can prepare the agent's knowledge but not yet hold the call.

## How a curator plugs in (the swappable brain)

```mermaid
flowchart LR
    P[pipeline.py] -->|curate stories| C{Curator · base.py}
    C --> D[DeterministicCurator<br/>recency + keywords]
    C --> A[AgenticCurator · ADK<br/>tools: fetch_article, memory]
    A -.on error.-> D
    E[CURATOR env var] -.selects.-> C
```

## Observability (tracing, tokens, cost)

Everything stays on GCP — no LangSmith, no LangChain. ADK already emits OpenTelemetry GenAI spans
for every agent run, model call and tool call; `observability.py` is the bootstrap that points them
at Google Cloud and adds spans for the pipeline's own stages.

```mermaid
flowchart TD
    Cfg[config.py · TRACE_* env] --> Obs[observability.py · setup]
    Obs --> ADK[ADK spans<br/>invocation · agent_run · call_llm · execute_tool]
    Obs --> Genai[opentelemetry-instrumentation-google-genai<br/>wraps the raw genai calls]
    Obs --> Mine[our stage spans<br/>gather · curate · enrich · rewrite · compose · TTS · email]
    ADK --> TP[OTel TracerProvider]
    Genai --> TP
    Mine --> TP
    TP -->|TRACE_BACKEND=cloudtrace · default| CT[cloudtrace.googleapis.com<br/>→ Cloud Trace]
    TP -.TRACE_BACKEND=telemetry.-> TG[telemetry.googleapis.com<br/>needs a trace bucket]
    Obs --> Met[Cloud Monitoring metrics]
    Exit[flush before exit] --> CT
```

One run is one trace:

```
daily_news.run                      curator, words, feeds, outcome
├─ gather_stories (per feed)         → fetch_source per adapter, story counts
├─ feed  name="AI & Tech"
│  ├─ curate                        curation.fallback, adk.session_id
│  │  └─ invocation → agent_run → call_llm / execute_tool      ← ADK's own spans
│  ├─ enrich_stories                enriched
│  └─ rewrite                       gen_ai.request.model + input/output tokens
├─ compose · synthesize_mp3 · send_email · archive_to_gcs
```

**The knobs** (all in `.env.example`):

| Env | Default | What it does |
|---|---|---|
| `TRACE_ENABLED` | on | `0` makes every span helper a no-op |
| `TRACE_BACKEND` | `cloudtrace` | `telemetry` switches to ADK's OTLP endpoint |
| `TRACE_METRICS` | **off** | Cloud Monitoring metric export. Opt-in: spans already carry the token counts, and this exporter throws `UNAVAILABLE` tracebacks intermittently. |
| `TRACE_LOGS` | off | OTel log export (Cloud Run already captures stdout) |
| `TRACE_CONTENT` | on locally, off in Cloud Run | prompt/response text on spans |
| `EVAL_JUDGE_MODEL` | `gemini-2.5-flash` | judge for the ADK eval metrics |
| `EVAL_JUDGE_SAMPLES` | `3` | judge samples per metric per segment (ADK default 5 = 40 calls/run) |

**Two things that will bite you:**
- **Flush or lose them.** The exporter batches; a Cloud Run Job exits first. Every entry point calls
  `observability.flush()` in a `finally`.
- **`TRACE_BACKEND=telemetry` can look healthy and export nothing.** It returns HTTP 200 but the
  spans are unreadable until the project has a trace bucket (`_Trace bucket not found in project`).
  That's why `cloudtrace` is the default.

## Evals: two kinds of grading, and what each needs

A golden set is **frozen input**, not an answer key — `sources.json` is captured news that can't
change between runs, so a score change means the code changed, not the news. `expectations.md` is
the separate, hand-written answer key. That distinction decides which metrics can run at all.

```mermaid
flowchart TD
    Cap[evals/capture.py] --> Src[golden/DATE/sources.json<br/>frozen INPUT]
    Src --> Build[pipeline · curate + rewrite]
    Build --> Seg[the segments under test]
    Seg --> Code[checks.py · 0 LLM calls<br/>length · structure · tts_safety]
    Src --> RF
    Seg --> RF[REFERENCE-FREE<br/>judge.py faithfulness/coverage/relevance<br/>adk_metrics hallucinations_v1]
    Exp[golden/DATE/expectations.md<br/>answer key · I write it] --> RB
    Seg --> RB[REFERENCE-BASED<br/>judge.py expectations_adherence<br/>adk_metrics per-rubric grading]
    Src --> RB
```

- **Reference-free** compares the segment to the **sources**. Needs no answer key, so it works on a
  freshly captured day with no writing from me.
- **Reference-based** compares it to **my rules**. Skipped automatically when `expectations.md` is
  absent. ⚠ A `capture.py` stub answer key is worse than none: it is non-empty, so adherence grades
  against nothing and returns a false **1.00**. Delete the stub on a day you haven't written one.
- `adk_metrics.py` is a thin adapter — ADK owns the prompts, the sampling and the scoring; the only
  logic in this repo is `parse_expectations()`, which turns my bullets into one rubric per rule.

```bash
python -m evals.capture --name YYYY-MM-DD                    # freeze today's sources
python -m evals.run --golden DATE --curator agentic           # my judges only
python -m evals.run --golden DATE --curator agentic --adk-metrics   # + Google's
python -m evals.compare --golden DATE                        # deterministic vs agentic
```

## Where things live
| Path | Its job |
|---|---|
| `main.py` | Entry point. Orchestrates, then TTS + email + archive. |
| `pipeline.py` | The core loop: gather → curate → rewrite → compose. |
| `config.py` | Loads settings (env vars) + the feed list from `feeds.yaml`. |
| `feeds.yaml` | **The knobs.** Topics, sources, word budgets. Edit here to change what the briefing covers. |
| `sources/` | One adapter per source (TLDR AI web, Gmail, Google News, Hacker News, stocks). All return a `Story`. |
| `curation/` | The swappable brain: `deterministic.py` + `agentic.py`, both behind `base.Curator`. |
| `composer.py` | Joins segments into the final spoken script. |
| `memory.py` | Cross-run memory (what past digests covered) — used by the agent. |
| `prompts/` | One rewrite prompt per topic + `_shared_style.md`. Decides *how* each segment sounds. |
| `agent/` | The optional voice-agent branch: `sync.py` (entry point), `context.py` (builds the doc), `providers/` (ElevenLabs + two scaffolds). |
| `evals/` | Quality testing: `capture.py` freezes input, `checks.py` code checks, `judge.py` my 3 LLM judges, `compare.py` A/B, `golden/` the frozen days. |
| `evals/adk_metrics.py` | Google's own judges (ADK `hallucinations_v1` + per-rubric expectations), behind `--adk-metrics`. |
| `observability.py` | Tracing bootstrap + span helpers. One import per entry point. |
| `adk_apps/` | Dev-loop only, not part of a run: exposes the curator to `adk web` so its turns can be watched live. See below. |
| `deploy.sh` / `Dockerfile` | Package + ship to Cloud Run. |

## Watching the curator live (`adk web`)

`adk web` discovers agents by scanning a directory for subfolders exposing a module-level
`root_agent`. The real curator is built *inside* `AgenticCurator._run_agent()`, once per feed, so
there is nothing for the dev UI to find — `adk_apps/curator/` is a thin adapter that builds the same
agent from the same `_INSTRUCTION` and the same tools.

```bash
adk web adk_apps                                  # → http://127.0.0.1:8000, pick "curator"
ADK_WEB_FEED="US Headlines" adk web adk_apps      # load a different feed's persona
python adk_apps/dump_candidates.py --feed "US Headlines" [--golden DATE]   # paste-ready input
```

It shows the **curator only** — the rewrite and every judge are raw `google-genai` calls, not
agents, so they never appear here. Use Cloud Trace for a whole run.

## Key ideas (the patterns)
- **`Story`** — one normalized shape every source returns, so the rest of the app doesn't care where news came from. (*adapter pattern*)
- **`Source`** — a contract: any source implements `fetch() → [Story]`. Add one = new file in `sources/`.
- **`Curator`** — a contract for the brain: `curate(stories) → chosen stories`. Two versions, picked by `CURATOR`. (*strategy pattern*)
- **`Provider`** — the same contract again for the voice agent: `sync(ctx)`, picked by `REALTIME_PROVIDER`. (*strategy pattern*)
- **`feeds.yaml`** — config, not code. New topic = new entry here.
- **Evals** — grade a segment two ways: vs the sources (no answer key needed), and vs my hand-written `expectations.md`.
- **Fail soft on anything non-essential.** A dead source is skipped, the agentic curator falls back
  to deterministic, GCS archiving and all tracing swallow their own errors. The briefing ships.

## How to extend
- **Add a source** → new file in `sources/` implementing `fetch()`, register it, reference it in `feeds.yaml`.
- **Add a topic** → add a feed block in `feeds.yaml` + a prompt in `prompts/`. No code.
- **Change the brain** → `CURATOR=deterministic|agentic`, or add a strategy in `curation/`.
- **Change voice / length** → `TTS_VOICE` env; `length_budget_words` per feed.
- **Change how factual the rewrite is** → `REWRITE_TEMPERATURE`, and the rules in `prompts/_shared_style.md`.
- **Add a voice provider** → new file in `agent/providers/` implementing `sync()`, register it, set `REALTIME_PROVIDER`.
- **Next agent you build** → make it ADK-native from the start so `adk web` works day one: `adk create`,
  a module-level `root_agent`, a *callable* instruction (`Callable[[ReadonlyContext], str]`) reading
  per-run values from session state instead of rebuilding the Agent per feed, and a `.env` in the
  agent folder. That avoids needing an `adk_apps/`-style adapter later.
