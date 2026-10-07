"""The RealtimeProvider contract + factory.

A provider is the swappable backend that turns today's grounding into a live voice conversation.
The contract is deliberately small — the two things every backend must do:

  sync(context)        -> make today's knowledge available to the backend
                          (ElevenLabs: update the agent's knowledge base;
                           Gemini Live: write the session's system-instruction/context bundle).
  create_session()     -> return what a client needs to connect for a live conversation
                          (ElevenLabs: a signed conversation URL; Gemini Live: an ephemeral token).

Telephony providers add:
  place_outbound_call(to_number) -> ring the user and connect them to the agent.

Everything upstream (grounding content, persona) is shared and provider-neutral.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from config import Config


class RealtimeProvider(ABC):
    """A live voice backend grounded in today's briefing knowledge."""

    name: str = "provider"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    @abstractmethod
    def sync(self, context: dict) -> None:
        """Push today's grounding (from agent.context.build_context) to the backend."""
        raise NotImplementedError

    @abstractmethod
    def create_session(self) -> dict:
        """Return connection info for a browser/live client (e.g. {'signed_url': ...})."""
        raise NotImplementedError

    def place_outbound_call(self, to_number: str) -> dict:
        """Ring `to_number` and connect them to the agent. Telephony providers override this."""
        raise NotImplementedError(
            f"{self.name} does not implement outbound calling"
        )


def create_provider(cfg: Config, name: str | None = None) -> RealtimeProvider:
    """Build the configured realtime provider by name (default from cfg.realtime_provider)."""
    name = (name or cfg.realtime_provider or "elevenlabs").lower()
    if name == "elevenlabs":
        from agent.providers.elevenlabs import ElevenLabsProvider

        return ElevenLabsProvider(cfg)
    if name == "retell":
        from agent.providers.retell import RetellProvider

        return RetellProvider(cfg)
    if name in ("gemini_live", "gemini"):
        from agent.providers.gemini_live import GeminiLiveProvider

        return GeminiLiveProvider(cfg)
    raise ValueError(
        f"Unknown realtime provider {name!r} (expected elevenlabs | retell | gemini_live)"
    )
