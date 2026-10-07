"""Gemini Live API provider (later — the web-based comparison harness).

STATUS: scaffold. Gemini Live is a raw bidirectional audio stream on Vertex (not a hosted agent),
so it drives a WebSocket mic<->model loop in the browser rather than telephony. Grounding is passed
as system instructions + context built from agent.context. Implement against current Gemini Live
docs when building the ElevenLabs-vs-Gemini comparison. Reuses existing Vertex config
(GOOGLE_CLOUD_PROJECT / GEMINI_REGION, already wired for Vertex in config.py).
"""

from __future__ import annotations

from agent.providers.base import RealtimeProvider


class GeminiLiveProvider(RealtimeProvider):
    name = "gemini_live"

    def sync(self, context: dict) -> None:
        raise NotImplementedError(
            "Gemini Live provider is planned for the web comparison harness — build later."
        )

    def create_session(self) -> dict:
        raise NotImplementedError(
            "Gemini Live provider is planned for the web comparison harness — build later."
        )
