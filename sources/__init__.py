"""Source adapters: each turns a raw feed (email, RSS, API) into normalized Story items.

Import the concrete adapters here so they register themselves via @register_source,
then build any of them by name with `create_source(type, params)`.
"""

from sources.base import Story, Source, create_source, register_source

# Importing the modules triggers their @register_source decorators.
from sources import gmail_newsletter  # noqa: F401
from sources import google_news_rss  # noqa: F401
from sources import hackernews  # noqa: F401
from sources import stocks  # noqa: F401

__all__ = ["Story", "Source", "create_source", "register_source"]
