"""Tests for the digest composer's empty/placeholder-segment handling.

The Immigration prompt tells the model to stay silent when there's no genuine visa-policy news,
and the model does that by emitting a literal placeholder like "(no output)" or "[EMPTY]" — non-
blank text. The composer must treat those as empty so the segment is dropped, not spoken.
"""

import composer


def test_placeholder_segment_is_dropped():
    out = composer.compose([
        ("AI & Tech", "A real AI segment."),
        ("Immigration & Visas", "(no output)"),
        ("Markets", "Indices rose."),
    ])
    assert "Immigration" not in out
    assert "(no output)" not in out
    assert "AI & Tech" in out and "Markets" in out


def test_truly_blank_segment_is_dropped():
    out = composer.compose([("AI & Tech", "Real."), ("US Headlines", "   ")])
    assert "US Headlines" not in out


def test_real_segments_survive():
    out = composer.compose([
        ("Immigration & Visas", "USCIS raised the H-1B fee to one hundred thousand dollars."),
    ])
    assert "Immigration" in out and "H-1B" in out


def test_all_blank_returns_empty_string():
    assert composer.compose([("Immigration & Visas", "[EMPTY]")]) == ""


def test_blank_detection_variants():
    for blank in ["(no output)", "[EMPTY]", "  [empty] ", "No output.", "None", "n/a"]:
        assert composer._is_blank_segment(blank) is True, blank
    for real in ["ICE announced a new rule.", "A story about green cards."]:
        assert composer._is_blank_segment(real) is False, real
