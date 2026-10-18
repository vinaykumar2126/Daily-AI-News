"""Tests for the MCP server tools (mcp_server.py).

Offline: the pipeline/context functions are monkeypatched, so no network or LLM calls. The
@mcp.tool() decorator leaves the functions directly callable, so we exercise them as plain
functions, plus one check that all three are actually registered with the MCP server.
"""

import asyncio
import types

import pytest

import mcp_server


class _Feed:
    def __init__(self, name):
        self.name = name


def _fake_feeds():
    return [_Feed("AI & Tech"), _Feed("US Headlines"), _Feed("Markets")]


# --- registration ------------------------------------------------------------------------- #
def test_all_three_tools_registered():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {"list_topics", "get_stories", "get_briefing"} <= names


# --- list_topics -------------------------------------------------------------------------- #
def test_list_topics_returns_feed_names(monkeypatch):
    monkeypatch.setattr(mcp_server, "load_feeds", _fake_feeds)
    assert mcp_server.list_topics() == ["AI & Tech", "US Headlines", "Markets"]


# --- _feed resolution --------------------------------------------------------------------- #
def test_feed_lookup_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(mcp_server, "load_feeds", _fake_feeds)
    assert mcp_server._feed("ai & tech").name == "AI & Tech"


def test_unknown_topic_raises_with_available_list(monkeypatch):
    monkeypatch.setattr(mcp_server, "load_feeds", _fake_feeds)
    with pytest.raises(ValueError, match="Unknown topic"):
        mcp_server._feed("Sports")


# --- get_stories -------------------------------------------------------------------------- #
def test_get_stories_returns_dicts(monkeypatch):
    monkeypatch.setattr(mcp_server, "load_feeds", _fake_feeds)

    class _Story:
        def to_dict(self):
            return {"title": "A model shipped", "url": "https://x", "source": "RSS"}

    fake_pipeline = types.SimpleNamespace(gather_stories=lambda feed: [_Story(), _Story()])
    monkeypatch.setitem(__import__("sys").modules, "pipeline", fake_pipeline)

    out = mcp_server.get_stories("AI & Tech")
    assert isinstance(out, list) and len(out) == 2
    assert out[0]["title"] == "A model shipped"


def test_get_stories_unknown_topic_raises(monkeypatch):
    monkeypatch.setattr(mcp_server, "load_feeds", _fake_feeds)
    with pytest.raises(ValueError):
        mcp_server.get_stories("Nope")


# --- get_briefing ------------------------------------------------------------------------- #
def test_get_briefing_renders_context(monkeypatch):
    monkeypatch.setattr(mcp_server, "load_feeds", _fake_feeds)
    monkeypatch.setattr(mcp_server, "_cfg", lambda: object())

    # Patch the attributes on the real agent.context module (not sys.modules): get_briefing does
    # `import agent.context as agent_context`, and with the real module already imported, binding
    # resolves to it — so attribute patches are what actually take effect.
    import agent.context as agent_context_mod

    fake_ctx = {"date": "2026-10-17", "narrative": "n", "stories": []}
    monkeypatch.setattr(agent_context_mod, "build_context", lambda cfg, feeds: fake_ctx)
    monkeypatch.setattr(
        agent_context_mod, "render_markdown", lambda ctx: f"BRIEFING for {len(ctx['stories'])} stories"
    )

    assert mcp_server.get_briefing("AI & Tech") == "BRIEFING for 0 stories"


def test_get_briefing_unknown_topic_raises(monkeypatch):
    monkeypatch.setattr(mcp_server, "load_feeds", _fake_feeds)
    monkeypatch.setattr(mcp_server, "_cfg", lambda: object())
    with pytest.raises(ValueError):
        mcp_server.get_briefing("Nope")
