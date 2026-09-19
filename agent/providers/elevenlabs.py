"""ElevenLabs Conversational AI provider (MVP).

STATUS: scaffold. The methods below describe exactly what to implement, but the concrete
ElevenLabs SDK/API calls are intentionally left as TODOs because the API is past the assistant's
knowledge cutoff — VERIFY against current docs (https://elevenlabs.io/docs) during implementation
and fill these in. Do not guess method names.

Env used (see config.py): ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID, ELEVENLABS_VOICE_ID,
ELEVENLABS_PHONE_NUMBER_ID, USER_PHONE_NUMBER.
"""

from __future__ import annotations

import logging

from agent.providers.base import RealtimeProvider

log = logging.getLogger("daily-news.agent.elevenlabs")


class ElevenLabsProvider(RealtimeProvider):
    name = "elevenlabs"

    def __init__(self, cfg) -> None:
        super().__init__(cfg)
        if not cfg.eleven_api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set")
        # TODO(verify): construct the client, e.g. `from elevenlabs.client import ElevenLabs;
        # self.client = ElevenLabs(api_key=cfg.eleven_api_key)`
        self.client = None

    def sync(self, context: dict) -> None:
        """Refresh the agent's grounding with today's knowledge.

        Implement (verify against current ElevenLabs Conversational AI docs):
          1. Render `context` to text via agent.context.render_markdown.
          2. Upload/replace it as the agent's KNOWLEDGE BASE document
             (create a KB doc from text, then attach it to ELEVENLABS_AGENT_ID; remove the
             previous day's doc so only today's is attached).
          3. Optionally set/refresh the agent's first message from context['narrative'] so the
             call opens with today's briefing.
        """
        raise NotImplementedError(
            "ElevenLabs sync() not implemented — verify current KB/agent API and fill in "
            "(see docstring). Requires ELEVENLABS_AGENT_ID."
        )

    def create_session(self) -> dict:
        """Return {'signed_url': ...} for the browser client to open a live conversation.

        Implement: call the ElevenLabs 'get signed URL' endpoint for ELEVENLABS_AGENT_ID using the
        server-side API key, so the key never reaches the browser. Return the signed URL.
        """
        raise NotImplementedError(
            "ElevenLabs create_session() not implemented — verify the signed-URL endpoint and fill in."
        )

    def place_outbound_call(self, to_number: str) -> dict:
        """Ring `to_number` and connect them to the agent (the daily morning call).

        Implement (verify): use ElevenLabs' outbound-call API (via ELEVENLABS_PHONE_NUMBER_ID, or
        a Twilio integration) to dial `to_number` and attach ELEVENLABS_AGENT_ID. Return the call id.
        """
        raise NotImplementedError(
            "ElevenLabs place_outbound_call() not implemented — verify the telephony/outbound-call "
            "API and fill in. Requires a configured phone number."
        )
