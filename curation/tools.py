"""Tools the agentic curator's ADK agent can call.

Plain functions with clear docstrings and typed args (ADK sends the docstring to the model).
Each returns a JSON-serializable dict.
"""

from __future__ import annotations

import logging
import urllib.request

import memory as memory_store

log = logging.getLogger("daily-news.curation.tools")

_MAX_ARTICLE_CHARS = 3000


def fetch_article(url: str) -> dict:
    """Fetch a news article or page and return its readable text.

    Use this to verify a claim or pull a concrete detail (a benchmark number, a price, what a
    tool actually does) instead of trusting a headline.

    Args:
        url: The article URL to fetch.

    Returns:
        dict with 'status' and either 'text' (truncated) or 'error'.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)
        except Exception:
            text = raw.decode("utf-8", errors="replace")
        return {"status": "success", "text": text[:_MAX_ARTICLE_CHARS]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}


def recent_digest_history() -> dict:
    """Return the tools and stories surfaced in recent daily digests (last ~30 days).

    Use this to spot competitive moves: if today's launch competes with or beats something the
    digest already covered, you can call that out.

    Returns:
        dict with 'status' and 'history': a list of {date, items:[{title, url, source}]}.
    """
    try:
        return {"status": "success", "history": memory_store.recent_history(30)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc), "history": []}
