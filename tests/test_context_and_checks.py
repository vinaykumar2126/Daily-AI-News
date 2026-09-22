"""Deterministic tests for the knowledge-doc rendering and the eval code-checks.

Guarantees the agent's knowledge doc is de-duplicated, symbol-free, and free of redundant
summaries / opaque URLs — and that the eval's TTS-safety check actually catches junk.
"""

from agent.context import render_markdown, _useful_summary
from evals import checks


def _ctx():
    return {
        "date": "2026-09-20",
        "narrative": "Good morning. First up, AI and tech. 🤖",  # emoji should be stripped
        "stories": [
            # Google News: summary just repeats title (+source), opaque redirect URL
            {"topic": "US Headlines",
             "title": "Inside airlines' panic as FAA pushed new AI tool - Politico",
             "summary": "Inside airlines' panic as FAA pushed new AI tool Politico",
             "url": "https://news.google.com/rss/articles/CBMhuge?oc=5", "source": "Politico"},
            # Hacker News: only points/comments metadata + a real URL — both should be trimmed
            {"topic": "AI & Tech",
             "title": "I think you should never use AI to write",
             "summary": "331 points, 161 comments on Hacker News.",
             "url": "https://erichgrunewald.substack.com/p/x", "source": "HN"},
            # Enriched story: real article content — this summary MUST survive
            {"topic": "AI & Tech",
             "title": "Pirate Face",
             "summary": "Turns Hugging Face models into checksum-verified torrents kept alive by a swarm.",
             "url": "https://pirateface.co/", "source": "HN"},
        ],
    }


# --- render_markdown ----------------------------------------------------------------------- #
def test_render_has_no_emoji():
    md = render_markdown(_ctx())
    assert "🤖" not in md


def test_render_drops_redundant_summary_and_opaque_url():
    md = render_markdown(_ctx())
    # Google News story: no "— <dup summary>" and no google redirect url
    assert "news.google.com" not in md
    assert "AI tool Politico —" not in md and "— Inside airlines" not in md


def test_render_trims_points_and_all_urls():
    md = render_markdown(_ctx())
    # HN points/comments metadata is trimmed...
    assert "331 points" not in md and "comments on Hacker News" not in md
    # ...and NO URLs remain (neither opaque nor real)
    assert "http" not in md
    # ...but the story titles still survive
    assert "I think you should never use AI to write" in md


def test_render_keeps_real_content_summary():
    md = render_markdown(_ctx())
    # a genuine article summary (not points, not a title echo) is preserved
    assert "checksum-verified torrents" in md


# --- helpers ------------------------------------------------------------------------------- #
def test_useful_summary_drops_title_echo():
    assert _useful_summary("Meta Muse for Mac", "Meta Muse for Mac Techgenyz") == ""


def test_useful_summary_keeps_new_info():
    assert _useful_summary("Big story", "a genuinely different description of the thing") != ""


# --- eval code-checks: TTS safety actually flags junk -------------------------------------- #
def test_tts_safety_flags_emoji_markdown_money():
    bad = "Here is **bold** and $2B and GPT-4o and 100x and an emoji 🧲."
    r = checks.check_tts_safety(bad)
    assert r.passed is False and r.score < 1.0


def test_tts_safety_passes_clean_spoken_text():
    good = "Good morning. OpenAI shipped a new agent tool today, and it matters for engineers."
    r = checks.check_tts_safety(good)
    assert r.passed is True and r.score == 1.0
