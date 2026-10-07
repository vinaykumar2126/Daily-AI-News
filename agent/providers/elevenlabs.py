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
from pathlib import Path

from agent.providers.base import RealtimeProvider

log = logging.getLogger("daily-news.agent.elevenlabs")

# The host persona/system prompt, kept in-repo so the call's voice is version-controlled.
_ANCHOR_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "anchor.md"


def _read_anchor_prompt() -> str:
    """Load the agent's system prompt (agent/prompts/anchor.md), or '' if it's missing."""
    try:
        return _ANCHOR_PROMPT.read_text().strip()
    except OSError:
        return ""


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

        # Push the host persona (agent/prompts/anchor.md) as the system prompt alongside today's
        # knowledge, so the voice/style is version-controlled here instead of pasted in the
        # dashboard. One update sets both.
        prompt_cfg: dict = {
            "knowledge_base": [{"type": "text", "name": doc.name, "id": doc.id}],
            # Give the agent the end_call system tool. Without it the model can SAY goodbye but
            # cannot actually hang up — "hang up" is just more words, so the turn loops back to the
            # caller and the call never ends. Reasserted on every sync so it can't drift out of the
            # dashboard. The prompt tells it when to use this.
            "built_in_tools": {
                "end_call": {
                    "name": "end_call",
                    "description": (
                        "End the phone call. Call this when the listener says they're done, says "
                        "goodbye, asks you to hang up, or once you've given your sign-off. Say a "
                        "brief, warm goodbye first, then call this tool to actually hang up."
                    ),
                    "params": {"system_tool_type": "end_call"},
                }
            },
        }
        anchor = _read_anchor_prompt()
        if anchor:
            prompt_cfg["prompt"] = anchor

        self.client.conversational_ai.agents.update(
            agent_id=self.cfg.eleven_agent_id,
            conversation_config={"agent": {"prompt": prompt_cfg}},
        )
        log.info(
            "Agent %s refreshed -> doc %s, persona %s",
            self.cfg.eleven_agent_id,
            doc.id,
            "updated" if anchor else "left as-is (anchor.md not found)",
        )
        return {"document_id": doc.id, "name": doc.name, "persona_pushed": bool(anchor)}

    def create_session(self) -> dict:
        """Return {'signed_url': ...} for the browser client to open a live conversation.

        Implement: call the ElevenLabs 'get signed URL' endpoint for ELEVENLABS_AGENT_ID using the
        server-side API key, so the key never reaches the browser. Return the signed URL.
        """
        raise NotImplementedError(
            "ElevenLabs create_session() not implemented — verify the signed-URL endpoint and fill in."
        )

    def _resolve_phone_number_id(self) -> str:
        """The ElevenLabs id of the Twilio number to call FROM.

        Prefers ELEVENLABS_PHONE_NUMBER_ID. With that unset, looks up the account's registered
        Twilio numbers -- convenient, and it means a fresh checkout works before anyone copies an
        id into .env. Set the env var in production so a second number appearing in the account
        cannot silently change which line you call from.
        """
        if self.cfg.eleven_phone_number_id:
            return self.cfg.eleven_phone_number_id

        numbers = [
            n for n in self.client.conversational_ai.phone_numbers.list()
            if getattr(n, "provider", None) == "twilio"
        ]
        if not numbers:
            raise RuntimeError(
                "No Twilio number registered in ElevenLabs. Import the number under "
                "Conversational AI -> Phone Numbers, then set ELEVENLABS_PHONE_NUMBER_ID."
            )
        if len(numbers) > 1:
            labels = ", ".join(f"{n.phone_number} ({n.phone_number_id})" for n in numbers)
            raise RuntimeError(
                f"{len(numbers)} Twilio numbers registered; set ELEVENLABS_PHONE_NUMBER_ID to pick "
                f"one: {labels}"
            )
        chosen = numbers[0]
        log.info(
            "Using Twilio number %s (%s) — set ELEVENLABS_PHONE_NUMBER_ID to pin it",
            chosen.phone_number,
            chosen.phone_number_id,
        )
        return chosen.phone_number_id

    def place_outbound_call(self, to_number: str | None = None) -> dict:
        """Ring `to_number` and connect them to the agent (the daily morning call).

        ElevenLabs places the call itself using the Twilio credentials held against the number you
        imported into its dashboard -- so TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN are NOT needed here
        and this code never talks to Twilio directly.

        Call `sync()` first: the agent answers from whatever knowledge base is attached, so dialling
        before the refresh means today's call discusses yesterday's news.
        """
        to_number = to_number or self.cfg.user_phone_number
        if not to_number:
            raise RuntimeError("No destination number: pass to_number or set USER_PHONE_NUMBER")
        if not self.cfg.eleven_agent_id:
            raise RuntimeError("ELEVENLABS_AGENT_ID not set")

        phone_number_id = self._resolve_phone_number_id()
        log.info("Calling %s from phone_number_id=%s as agent %s",
                 to_number, phone_number_id, self.cfg.eleven_agent_id)
        resp = self.client.conversational_ai.twilio.outbound_call(
            agent_id=self.cfg.eleven_agent_id,
            agent_phone_number_id=phone_number_id,
            to_number=to_number,
        )
        out = {
            "success": getattr(resp, "success", None),
            "message": getattr(resp, "message", None),
            "conversation_id": getattr(resp, "conversation_id", None),
            "call_sid": getattr(resp, "call_sid", None),
        }
        # ElevenLabs answers 200 with success=False for a refused call (bad number, unverified
        # Twilio trial destination), so the HTTP status alone does not tell you it rang.
        if not out["success"]:
            raise RuntimeError(f"ElevenLabs refused the call: {out['message']!r}")
        log.info("Call placed: conversation=%s call_sid=%s", out["conversation_id"], out["call_sid"])
        return out
