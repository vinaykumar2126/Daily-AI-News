"""Retell AI provider (alternate; telephony-native).

STATUS: scaffold for later A/B comparison. Retell is bring-your-own-LLM and telephony-first; it can
render ElevenLabs voices (billed as a premium). Implement against current docs (https://docs.retellai.com)
when comparing. Env: RETELL_API_KEY, RETELL_AGENT_ID, USER_PHONE_NUMBER.
"""

from __future__ import annotations

from agent.providers.base import RealtimeProvider


class RetellProvider(RealtimeProvider):
    name = "retell"

    def __init__(self, cfg) -> None:
        super().__init__(cfg)
        if not cfg.retell_api_key:
            raise RuntimeError("RETELL_API_KEY not set")

    def sync(self, context: dict) -> None:
        raise NotImplementedError("Retell provider is a documented alternate — build when A/B testing.")

    def create_session(self) -> dict:
        raise NotImplementedError("Retell provider is a documented alternate — build when A/B testing.")

    def place_outbound_call(self, to_number: str) -> dict:
        raise NotImplementedError("Retell provider is a documented alternate — build when A/B testing.")
