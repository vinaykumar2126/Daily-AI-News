"""MCP server exposing the Daily News engine as tools.

Wraps the existing pipeline (sources -> curate -> rewrite) so any MCP client (Claude Desktop,
Cursor, ...) can pull AI/news content. This is the *content engine* only — the voice/phone-call
product is intentionally not exposed here (it's a hosted, real-time telephony service, not a
request/response tool).

Run locally:
    python mcp_server.py            # speaks MCP over stdio
Or, once published / from git:
    uvx daily-news-mcp

Credentials (bring your own, kept on your machine):
    * list_topics / get_stories  -> none needed.
    * get_briefing               -> Google Cloud / Vertex AI: set GOOGLE_CLOUD_PROJECT and run
                                    `gcloud auth application-default login` (curate + rewrite
                                    call Gemini).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from config import Config, load_dotenv, load_feeds

mcp = FastMCP("daily-news")


def _cfg() -> Config:
    """Load .env (if present) and build the app config. Cheap; no network."""
    load_dotenv()
    return Config()


def _feed(topic: str):
    """Resolve a topic name (as returned by list_topics) to its Feed, case-insensitively."""
    feeds = load_feeds()
    for feed in feeds:
        if feed.name.strip().lower() == topic.strip().lower():
            return feed
    available = ", ".join(repr(f.name) for f in feeds)
    raise ValueError(f"Unknown topic {topic!r}. Available topics: {available}.")


@mcp.tool()
def list_topics() -> list[str]:
    """List the news topics this briefing covers (e.g. "AI & Tech", "US Headlines",
    "Immigration & Visas", "Markets").

    Call this first to discover the valid `topic` values for get_stories and get_briefing.
    Requires no credentials.
    """
    return [feed.name for feed in load_feeds()]


@mcp.tool()
def get_stories(topic: str) -> list[dict]:
    """Fetch today's raw source stories for one topic, straight from the feeds (RSS, Hacker News,
    TLDR, markets) with no AI processing applied.

    `topic` must be one of the names from list_topics(). Each story is a dict with title, url,
    source, body, and published_at. Use this for the underlying material; use get_briefing for a
    curated, narrated version. Requires no credentials.
    """
    import pipeline

    stories = pipeline.gather_stories(_feed(topic))
    return [s.to_dict() for s in stories]


@mcp.tool()
def get_briefing(topic: str | None = None) -> str:
    """Produce today's curated, rewritten briefing: the sources are ranked by significance and
    rewritten into a spoken-style narrated digest, followed by the grounded source list.

    Pass a `topic` from list_topics() for a single segment, or omit it for the full briefing
    across all topics. Requires Google Cloud / Vertex AI credentials (set GOOGLE_CLOUD_PROJECT
    and run `gcloud auth application-default login`), because curation and rewriting call Gemini.
    """
    import agent.context as agent_context

    cfg = _cfg()
    feeds = [_feed(topic)] if topic else load_feeds()
    ctx = agent_context.build_context(cfg, feeds)
    return agent_context.render_markdown(ctx)


def main() -> None:
    """Console-script entry point (see pyproject [project.scripts])."""
    mcp.run()


if __name__ == "__main__":
    main()
