"""Unit tests for the generic publisher-RSS source (sources/rss.py).

The network is mocked (we monkeypatch rss._fetch), so these are fast, offline, and deterministic.
They pin the filtering/capping contract the feeds.yaml configs rely on: keyword filtering,
lookback cutoff, per-feed cap, global cap, cross-feed de-dup, and newest-first ordering.
"""

import datetime as dt
import types

import sources.rss as rss


def _entry(title, summary="", link="https://example.com/x", days_ago=0):
    """A minimal stand-in for a feedparser entry."""
    when = (dt.datetime.now() - dt.timedelta(days=days_ago)).timetuple()
    return types.SimpleNamespace(
        title=title, summary=summary, link=link, published_parsed=when
    )


def _feed(entries, feed_title="Example Feed"):
    """A minimal stand-in for a feedparser parse result."""
    return types.SimpleNamespace(
        entries=entries, feed=types.SimpleNamespace(title=feed_title)
    )


def _patch(monkeypatch, mapping):
    """Route rss._fetch(url) -> a canned feed per URL (or a single feed for any URL)."""
    if not isinstance(mapping, dict):
        monkeypatch.setattr(rss, "_fetch", lambda url: mapping)
    else:
        monkeypatch.setattr(rss, "_fetch", lambda url: mapping[url])


def test_no_feeds_returns_empty():
    assert rss.RssSource({}).fetch() == []


def test_keyword_filter_keeps_only_matches(monkeypatch):
    _patch(monkeypatch, _feed([
        _entry("H-1B visa rule tightened"),
        _entry("Local football team wins final"),
        _entry("USCIS announces new fee"),
    ]))
    out = rss.RssSource({"feeds": ["u"], "keywords": ["visa", "uscis"]}).fetch()
    titles = [s.title for s in out]
    assert "Local football team wins final" not in titles
    assert len(out) == 2


def test_keyword_filter_matches_summary_not_just_title(monkeypatch):
    _patch(monkeypatch, _feed([
        _entry("Policy shakeup", summary="New rules affect green card applicants"),
        _entry("Weather update", summary="Rain expected tomorrow"),
    ]))
    out = rss.RssSource({"feeds": ["u"], "keywords": ["green card"]}).fetch()
    assert len(out) == 1 and out[0].title == "Policy shakeup"


def test_keyword_match_is_case_insensitive(monkeypatch):
    _patch(monkeypatch, _feed([_entry("USCIS and DACA update")]))
    out = rss.RssSource({"feeds": ["u"], "keywords": ["daca"]}).fetch()
    assert len(out) == 1


def test_lookback_drops_old_items(monkeypatch):
    _patch(monkeypatch, _feed([
        _entry("Fresh story", days_ago=0),
        _entry("Stale story", days_ago=10),
    ]))
    out = rss.RssSource({"feeds": ["u"], "lookback_days": 3}).fetch()
    assert [s.title for s in out] == ["Fresh story"]


def test_max_per_feed_caps_each_feed(monkeypatch):
    _patch(monkeypatch, _feed([_entry(f"Story {i}") for i in range(6)]))
    out = rss.RssSource({"feeds": ["u"], "max_per_feed": 2, "max_items": 10}).fetch()
    assert len(out) == 2


def test_max_items_caps_total_across_feeds(monkeypatch):
    _patch(monkeypatch, {
        "a": _feed([_entry(f"A{i}") for i in range(3)], "A"),
        "b": _feed([_entry(f"B{i}") for i in range(3)], "B"),
    })
    out = rss.RssSource(
        {"feeds": ["a", "b"], "max_per_feed": 3, "max_items": 4}
    ).fetch()
    assert len(out) == 4


def test_dedup_across_feeds_by_title(monkeypatch):
    _patch(monkeypatch, {
        "a": _feed([_entry("Shared headline")], "A"),
        "b": _feed([_entry("Shared headline"), _entry("Unique headline")], "B"),
    })
    out = rss.RssSource({"feeds": ["a", "b"]}).fetch()
    titles = [s.title for s in out]
    assert titles.count("Shared headline") == 1
    assert "Unique headline" in titles


def test_newest_first_ordering(monkeypatch):
    _patch(monkeypatch, _feed([
        _entry("Older", days_ago=2),
        _entry("Newest", days_ago=0),
        _entry("Middle", days_ago=1),
    ]))
    out = rss.RssSource({"feeds": ["u"], "lookback_days": 5}).fetch()
    assert [s.title for s in out] == ["Newest", "Middle", "Older"]


def test_story_fields_populated(monkeypatch):
    _patch(monkeypatch, _feed(
        [_entry("Visa news", summary="details", link="https://pub/1")],
        feed_title="The Publisher",
    ))
    out = rss.RssSource({"feeds": ["u"]}).fetch()
    s = out[0]
    assert s.title == "Visa news"
    assert s.body == "details"
    assert s.url == "https://pub/1"
    assert s.source == "The Publisher"
