"""Deterministic tests for the text-cleaning guardrails.

These give a 100%-reliable regression guarantee that TTS-hostile junk (ads, HTML, emojis, UI
chrome) stays stripped and that real content survives. No network / no LLM — fast and repeatable.
"""

from sources.base import strip_symbols
from sources.gmail_newsletter import _clean_newsletter
from sources.google_news_rss import _strip_html
from pipeline import _clean_enriched, _needs_enrichment
from sources.base import Story


# --- strip_symbols: emojis out, normal punctuation kept ------------------------------------ #
def test_strip_symbols_removes_emojis_and_technical():
    out = strip_symbols("Turn AI into torrents ⌘K ☀ 🌙 🧲 forever")
    assert not any(ch in out for ch in "⌘☀🌙🧲")


def test_strip_symbols_keeps_dashes_and_quotes():
    src = "It's “decentralized” — with an en–dash"
    out = strip_symbols(src)
    assert "—" in out and "–" in out and "“" in out and "”" in out


def test_strip_symbols_handles_empty():
    assert strip_symbols("") == ""


# --- newsletter cleaning: ads/nav/refs out, real "sponsor" content kept -------------------- #
def test_clean_newsletter_drops_ads_and_nav():
    raw = (
        "Sign Up [1] |Advertise [2]|View Online [3]\n"
        "TOGETHER WITH [Plasma] [4]\n"
        "THE 5% AI CASHBACK CARD (SPONSOR) [4]\n"
        "Anthropic ships Claude Code Projects [5].\n"
        "Unsubscribe | Manage your preferences"
    )
    out = _clean_newsletter(raw)
    for junk in ["Sign Up", "Advertise", "View Online", "TOGETHER WITH",
                 "CASHBACK", "(SPONSOR)", "Unsubscribe", "[1]", "[5]"]:
        assert junk not in out, f"{junk!r} should be stripped"
    assert "Claude Code Projects" in out  # real content survives


def test_clean_newsletter_keeps_legit_sponsor_word():
    # "sponsor" as real content (not the (SPONSOR) ad tag) must NOT be dropped.
    out = _clean_newsletter("Companies that sponsor H-1B visas face new fees.")
    assert "Companies that sponsor H-1B visas" in out


# --- Google News RSS HTML stripping -------------------------------------------------------- #
def test_strip_html_removes_tags_and_urls():
    html = ('<a href="https://news.google.com/rss/articles/CBMhuge?oc=5">'
            'Meta Muse for Mac</a>&nbsp;&nbsp;<font color="#6f6f6f">Techgenyz</font>')
    out = _strip_html(html)
    assert "Meta Muse for Mac" in out and "Techgenyz" in out
    assert "<" not in out and "href" not in out and "news.google.com" not in out


# --- enrichment targeting ------------------------------------------------------------------ #
def test_needs_enrichment_true_for_thin_real_link():
    s = Story(title="Pirate Face", body="266 points, 104 comments on Hacker News.",
              url="https://pirateface.co/")
    assert _needs_enrichment(s) is True


def test_needs_enrichment_false_for_google_news_redirect():
    s = Story(title="Trump news", body="short",
              url="https://news.google.com/rss/articles/CBMhuge?oc=5")
    assert _needs_enrichment(s) is False


def test_needs_enrichment_false_when_body_is_rich():
    s = Story(title="Story", body="x" * 400, url="https://example.com/a")
    assert _needs_enrichment(s) is False


def test_needs_enrichment_false_without_url():
    s = Story(title="Story", body="short", url="")
    assert _needs_enrichment(s) is False


# --- enriched-text cleaning: chrome + symbols out ------------------------------------------ #
def test_clean_enriched_strips_chrome_and_symbols():
    out = _clean_enriched("Pirate Face ⌘ Log in Sign up Theme Light Dark 🧲 Turn AI into torrents.")
    assert "Turn AI into torrents." in out
    for junk in ["Log in", "Sign up", "Theme", "🧲", "⌘"]:
        assert junk not in out
