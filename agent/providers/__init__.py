"""Swappable realtime voice providers (Strategy pattern, like curation/).

Select with REALTIME_PROVIDER=elevenlabs|retell|gemini_live. Concrete providers are imported
lazily so their SDKs are only required when actually used.
"""

from agent.providers.base import RealtimeProvider, create_provider

__all__ = ["RealtimeProvider", "create_provider"]
