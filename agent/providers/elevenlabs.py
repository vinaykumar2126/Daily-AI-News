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
        from elevenlabs import ElevenLabs

        self.client = ElevenLabs(api_key=cfg.eleven_api_key)

    def sync(self, context: dict) -> dict:
        """Refresh the agent's knowledge base with today's briefing (create doc + attach to agent).

        Creates a fresh dated knowledge-base document from today's rendered doc and points the
        agent's `knowledge_base` at just that document (previous days' docs remain in the KB but
        are no longer attached). Verified against the ElevenLabs Conversational AI Python SDK.
        """
        from agent.context import render_markdown

        if not self.cfg.eleven_agent_id:
            raise RuntimeError("ELEVENLABS_AGENT_ID not set")

        text = render_markdown(context)
        name = f"Daily briefing {context.get('date', '')}".strip()
        log.info("Uploading knowledge doc %r (%d chars)", name, len(text))
        doc = self.client.conversational_ai.knowledge_base.documents.create_from_text(
            text=text, name=name
        )

        # Attach ONLY today's document to the agent.
        self.client.conversational_ai.agents.update(
            agent_id=self.cfg.eleven_agent_id,
            conversation_config={
                "agent": {
                    "prompt": {
                        "knowledge_base": [
                            {"type": "text", "name": doc.name, "id": doc.id},
                        ]
                    }
                }
            },
        )
        log.info("Agent %s knowledge refreshed -> doc %s", self.cfg.eleven_agent_id, doc.id)
        return {"document_id": doc.id, "name": doc.name}

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
