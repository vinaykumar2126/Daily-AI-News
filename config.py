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
        self.gemini_region = os.environ.get("GEMINI_REGION", "us-central1")

        # Curation strategy: "deterministic" (default) or "agentic"
        self.curator = os.environ.get("CURATOR", "deterministic")

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
