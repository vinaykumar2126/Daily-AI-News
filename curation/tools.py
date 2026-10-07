"""Tools the agentic curator's ADK agent can call.

Plain functions with clear docstrings and typed args (ADK sends the docstring to the model).
Each returns a JSON-serializable dict.
"""

from __future__ import annotations

import logging
import re
import urllib.request

import memory as memory_store

log = logging.getLogger("daily-news.curation.tools")

_MAX_ARTICLE_CHARS = 3000

# A Show HN post usually links a GitHub repo, and scraping the rendered repo page yields GitHub's
# own furniture -- "Navigation Sign in Appearance settings ... You signed in with another tab or
# window" -- which is long enough to pass every length check while telling the rewrite nothing. The
# README is the description the author actually wrote, served as plain markdown.
_GITHUB_REPO = re.compile(r"^https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+)", re.I)
_README_BRANCHES = ("HEAD", "main", "master")
_README_NAMES = ("README.md", "readme.md", "README.rst", "README")


def _readme_urls(url: str) -> list[str]:
    """raw.githubusercontent URLs to try for a GitHub repo link, or [] if it isn't one."""
    m = _GITHUB_REPO.match(url or "")
    if not m:
        return []
    owner, repo = m.group(1), m.group(2).removesuffix(".git")
    # Skip non-repo paths (github.com/features, /orgs/..., a user profile has no second segment).
    if owner.lower() in {"features", "about", "pricing", "orgs", "sponsors", "topics", "collections"}:
        return []
    return [
        f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{name}"
        for branch in _README_BRANCHES
        for name in _README_NAMES
    ]


# Site furniture that survives tag-stripping. If the top of a fetch is mostly this, the page gave
# us navigation rather than content -- better to report nothing than to hand the rewrite a long
# string with no facts in it, which is the trap the Google News markup fell into.
_NAV_PHRASES = re.compile(
    r"appearance settings|reload to refresh|you signed (?:in|out)|skip to (?:main )?content|"
    r"navigation|sign ?in|sign ?up|log ?in|press copyright|contact us|creators advertise|"
    r"terms privacy|privacy policy|enter a search term|cookie|subscribe now|accept all",
    re.I,
)
_CHROME_SAMPLE_CHARS = 600
_CHROME_PHRASE_LIMIT = 3


def _looks_like_chrome(text: str) -> bool:
    """True when the opening of a fetch is dominated by site navigation rather than content."""
    return len(_NAV_PHRASES.findall(text[:_CHROME_SAMPLE_CHARS])) >= _CHROME_PHRASE_LIMIT


def _get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _html_to_text(raw: bytes) -> str:
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()
        return soup.get_text(" ", strip=True)
    except Exception:  # noqa: BLE001
        return raw.decode("utf-8", errors="replace")


def fetch_article(url: str) -> dict:
    """Fetch a news article or page and return its readable text.

    Use this to verify a claim or pull a concrete detail (a benchmark number, a price, what a
    tool actually does) instead of trusting a headline.

    Args:
        url: The article URL to fetch.

    Returns:
        dict with 'status' and either 'text' (truncated) or 'error'.
    """
    # GitHub repos: go straight for the README; the rendered page is mostly chrome.
    for readme in _readme_urls(url):
        try:
            text = _get(readme).decode("utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001
            continue  # wrong branch or filename; try the next candidate
        if len(text) > 200:
            return {"status": "success", "text": text[:_MAX_ARTICLE_CHARS], "via": "readme"}

    try:
        text = _html_to_text(_get(url))
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc)}

    if _looks_like_chrome(text):
        # Deliberately an error, not a short success: a caller checking `len(text) > 200` would
        # otherwise accept navigation as article text and overwrite a thin body with a useless one.
        log.info("Discarded chrome-only fetch from %s", url)
        return {"status": "error", "error": "page returned navigation chrome, not article text"}

    return {"status": "success", "text": text[:_MAX_ARTICLE_CHARS]}


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
