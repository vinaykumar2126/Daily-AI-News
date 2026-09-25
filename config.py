"""Configuration and feed loading.

Runtime settings come from environment variables (injected from Secret Manager in the
cloud, or a local .env for development). The feed catalog — which topics/segments make up
the digest and where each pulls from — lives in feeds.yaml.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger("daily-news.config")


def load_dotenv() -> None:
    """Load a local .env for development. No-op in the cloud (no file present)."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _flag(name: str, default: bool) -> bool:
    """Read a boolean env var. Unset falls back to `default`; 0/false/no are off."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", ""}


@dataclass
class SourceSpec:
    type: str
    params: dict = field(default_factory=dict)


@dataclass
class Feed:
    name: str
    prompt: str
    length_budget_words: int
    sources: list[SourceSpec]
    order: int = 100
    enabled: bool = True
    interests: list[str] = field(default_factory=list)
    max_stories: int = 6


@dataclass
class Config:
    def __init__(self) -> None:
        self.gmail_address = self._req("GMAIL_ADDRESS")
        self.gmail_app_password = self._req("GMAIL_APP_PASSWORD")
        self.recipient = os.environ.get("RECIPIENT", self.gmail_address)

        # LLM: Gemini on Vertex AI
        self.gcp_project = os.environ.get(
            "GOOGLE_CLOUD_PROJECT", os.environ.get("GCP_PROJECT", "")
        )
        self.gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.gemini_rewrite_model = os.environ.get("GEMINI_REWRITE_MODEL", "gemini-2.5-pro")
        self.gemini_region = os.environ.get("GEMINI_REGION", "us-central1")

        # Point ADK (agentic curator) at Vertex AI, matching pipeline.rewrite's
        # genai.Client(vertexai=True). Without this ADK defaults to the AI Studio
        # API-key path and fails with "No API key was provided".
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
        if self.gcp_project:
            os.environ.setdefault("GOOGLE_CLOUD_PROJECT", self.gcp_project)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", self.gemini_region)

        # Curation strategy: "deterministic" (default) or "agentic"
        self.curator = os.environ.get("CURATOR", "deterministic")

        # Article enrichment: fetch real article text for thin (headline-only) curated stories
        # before rewriting, so the LLM grounds on facts instead of hallucinating from a headline.
        self.enrich_articles = os.environ.get("ENRICH_ARTICLES", "1").lower() not in {"0", "false", "no"}
        self.enrich_max_per_feed = int(os.environ.get("ENRICH_MAX_PER_FEED", "6"))

        # Text-to-Speech. Default to a stable Chirp3-HD voice. Set TTS_MODEL to a Gemini-TTS
        # model (e.g. gemini-3.1-flash-tts-preview) to enable model_name + style prompt.
        self.tts_language = os.environ.get("TTS_LANGUAGE", "en-US")
        self.tts_voice = os.environ.get("TTS_VOICE", "en-US-Chirp3-HD-Charon")
        self.tts_model = os.environ.get("TTS_MODEL", "")  # empty = plain stable voice
        self.tts_prompt = os.environ.get(
            "TTS_PROMPT", "Read this in a warm, natural, upbeat morning-briefing tone."
        )

        # Optional archive (also used by the agentic curator's memory)
        self.gcs_bucket = os.environ.get("GCS_BUCKET", "")

        # --- Tracing (OpenTelemetry -> Cloud Trace, via ADK's Google Cloud exporters) ---
        # No third-party observability SDK: ADK already emits GenAI spans and ships the GCP
        # exporters. See observability.py.
        self.trace_enabled = _flag("TRACE_ENABLED", True)
        # Metrics are opt-in. The spans already carry gen_ai.usage.* token counts, so the Cloud
        # Monitoring reader adds no information — but it does add a gRPC export path that fails
        # intermittently ("Error while writing to Cloud Monitoring", UNAVAILABLE on the auth
        # metadata fetch) and prints a traceback each time, which buries real output.
        self.trace_metrics = _flag("TRACE_METRICS", False)
        # Cloud Run already captures stdout, so OTel log export is opt-in.
        self.trace_logs = _flag("TRACE_LOGS", False)
        # Prompt/response text on spans: what makes a trace useful for debugging a bad segment,
        # but the rewrite prompts carry whole articles. On locally, off in the deployed job
        # (Cloud Run sets K_SERVICE) to keep span size and Trace ingestion cost down.
        self.trace_content = _flag("TRACE_CONTENT", not os.environ.get("K_SERVICE"))
        self.trace_service_name = os.environ.get("OTEL_SERVICE_NAME", "daily-news")
        # "cloudtrace" = classic cloudtrace.googleapis.com, queryable straight away.
        # "telemetry"  = ADK's default OTLP to telemetry.googleapis.com; that one needs the
        # project onboarded to a trace bucket, or it accepts spans (HTTP 200) that can never be
        # read back. Verified on dailynews-507123: telemetry -> "_Trace bucket not found".
        self.trace_backend = os.environ.get("TRACE_BACKEND", "cloudtrace").strip().lower()

        # Judge model for the ADK eval metrics. Deliberately not gemini_rewrite_model: a judge
        # from the same model as the generator grades its own family.
        self.eval_judge_model = os.environ.get("EVAL_JUDGE_MODEL", "gemini-2.5-flash")
        # How many times each ADK evaluator samples the judge and votes. ADK's default is 5,
        # which is 5 judge calls per metric per segment -- 40 for a 4-segment digest, enough to
        # get the process OOM-killed on a laptop. 3 still votes.
        self.eval_judge_samples = int(os.environ.get("EVAL_JUDGE_SAMPLES", "3"))

        # --- Realtime interactive agent (all optional; only needed for the phone-call mode) ---
        self.realtime_provider = os.environ.get("REALTIME_PROVIDER", "elevenlabs")
        # ElevenLabs Conversational AI
        self.eleven_api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        self.eleven_agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "")
        self.eleven_voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
        self.eleven_phone_number_id = os.environ.get("ELEVENLABS_PHONE_NUMBER_ID", "")
        # Retell (alternate provider)
        self.retell_api_key = os.environ.get("RETELL_API_KEY", "")
        self.retell_agent_id = os.environ.get("RETELL_AGENT_ID", "")
        # Telephony (Twilio, when the provider uses it) + who to call
        self.twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        self.twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        self.twilio_from_number = os.environ.get("TWILIO_FROM_NUMBER", "")
        self.user_phone_number = os.environ.get("USER_PHONE_NUMBER", "")

        # Dev conveniences
        self.dry_run = os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes"}

    @staticmethod
    def _req(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return value


def load_feeds(path: str | Path | None = None) -> list[Feed]:
    """Load and validate the feed catalog from feeds.yaml, sorted by `order`."""
    path = Path(path) if path else Path(__file__).with_name("feeds.yaml")
    raw = yaml.safe_load(path.read_text()) or {}
    feeds: list[Feed] = []
    for item in raw.get("feeds", []):
        sources = [
            SourceSpec(type=s["type"], params=s.get("params", {}))
            for s in item.get("sources", [])
        ]
        feeds.append(
            Feed(
                name=item["name"],
                prompt=item["prompt"],
                length_budget_words=int(item.get("length_budget_words", 250)),
                sources=sources,
                order=int(item.get("order", 100)),
                enabled=bool(item.get("enabled", True)),
                interests=list(item.get("interests", [])),
                max_stories=int(item.get("max_stories", 6)),
            )
        )
    feeds = [f for f in feeds if f.enabled]
    feeds.sort(key=lambda f: f.order)
    return feeds
