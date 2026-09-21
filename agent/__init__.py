"""Real-time interactive briefing agent.

Reuses the existing pipeline (sources -> curate -> rewrite) to produce today's grounding
knowledge, then serves it to a swappable realtime voice provider (ElevenLabs now; Retell /
Gemini Live later) so the user can listen and ask questions live over a phone call.
"""
