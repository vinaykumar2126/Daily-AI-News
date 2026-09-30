"""The news curator, exposed the way `adk web` expects to find it.

`adk web adk_apps` scans each subdirectory for a module-level `root_agent`. The real curator is
built inside `AgenticCurator._run_agent()` -- once per feed, with the instruction formatted for
that feed -- so there is nothing for the dev UI to discover. This module builds the same agent
once, at import, from the same constant and the same tool functions the pipeline uses. It is an
adapter, not a copy: change `_INSTRUCTION` or the tools in curation/agentic.py and this follows.

    .venv/bin/adk web adk_apps                  # then pick "curator" in the UI
    ADK_WEB_FEED="US Headlines" .venv/bin/adk web adk_apps
    .venv/bin/adk web --otel_to_cloud adk_apps  # also export to Cloud Trace

Paste-ready candidate stories for the chat box:
    .venv/bin/python adk_apps/dump_candidates.py --feed "AI & Tech"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# adk web puts the agents dir on sys.path, not the repo root, so `import curation` would fail.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from config import load_dotenv, load_feeds  # noqa: E402


def _bootstrap_env() -> None:
    """Point ADK at Vertex, the way config.Config does.

    Deliberately not `Config()`: that hard-fails without GMAIL_ADDRESS / GMAIL_APP_PASSWORD, and a
    dev UI for the curator has no business needing mail credentials. Without these three, ADK falls
    back to the AI Studio API-key path and dies with "No API key was provided".
    """
    load_dotenv()
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT", "")
    if project:
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", os.environ.get("GEMINI_REGION", "us-central1"))


# Must run before importing curation.agentic: its _MODEL is read from GEMINI_MODEL at import time.
_bootstrap_env()

from curation.agentic import _INSTRUCTION, _MODEL  # noqa: E402
from curation.tools import fetch_article, recent_digest_history  # noqa: E402
from google.adk.agents import Agent  # noqa: E402

# Which feed's persona to load. The instruction is per-feed (interests + max_stories come from
# feeds.yaml), and the UI serves one agent, so pick one -- override with ADK_WEB_FEED.
_FEED_NAME = os.environ.get("ADK_WEB_FEED", "AI & Tech")


def _feed_or_die(name: str):
    feeds = load_feeds()
    for feed in feeds:
        if feed.name == name:
            return feed
    raise SystemExit(
        f"ADK_WEB_FEED={name!r} is not in feeds.yaml. Available: {[f.name for f in feeds]}"
    )


_feed = _feed_or_die(_FEED_NAME)

root_agent = Agent(
    name="curator",
    model=_MODEL,
    instruction=_INSTRUCTION.format(
        feed_name=_feed.name,
        interests=", ".join(_feed.interests) or "general relevance",
        max_stories=_feed.max_stories,
    ),
    tools=[fetch_article, recent_digest_history],
)
