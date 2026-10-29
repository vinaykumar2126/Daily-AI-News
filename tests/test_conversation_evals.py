"""Deterministic tests for the conversation evals: the "no new numbers" check and the case files.

The LLM side (evals/conversation.py) needs Vertex credentials; these pin the parts that don't —
that spoken and written numbers parse the same, that real call replies pass, that invented or
caved-to figures fail, and that every case file is well-formed.
"""

import pytest

from evals import conversation, numbers

LFM3 = (
    "LFM3 is a family of open weight text, vision, audio, omni, and decision models built on a "
    "shared tri-hybrid backbone, starting in the 2B parameter range. The 1.7B text model beats its "
    "2.6B predecessor with 35% fewer parameters, fits in about 1 GB at 4 bit precision, and "
    "supports a 256K context window. LFM3-VL-2B matches Gemma 4 12B across 62 vision benchmarks."
)


# --- extraction ---------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text, value",
    [
        ("one point seven billion", 1.7e9),
        ("two hundred fifty-six thousand", 256_000),
        ("thirty-five percent", 35),
        ("forty billion dollars", 40e9),
        ("$40 billion", 40e9),
        ("2.6B", 2.6e9),
        ("256K", 256_000),
        ("41,000 employees", 41_000),
    ],
)
def test_extract_reads_digits_and_words_alike(text, value):
    assert [n.value for n in numbers.extract(text)] == [value]


@pytest.mark.parametrize(
    "text",
    [
        "forty billion. Forty billion dollars",  # sentence break between repeats
        "forty billion forty billion",  # no punctuation: a repeated scale still splits
    ],
)
def test_repeated_figure_is_two_numbers_not_one(text):
    # Run 2 of the first full eval read a repeated "forty billion" as eighty billion.
    assert [n.value for n in numbers.extract(text)] == [40e9, 40e9]


def test_mixed_scales_still_form_one_number():
    assert [n.value for n in numbers.extract("one billion two hundred million")] == [1.2e9]


def test_small_bare_words_are_grammar_not_claims():
    found = numbers.extract("the one I'd try, and two of them")
    assert found and all(n.bare_small for n in found)


def test_unit_letters_are_not_scale_suffixes():
    # "1 GB" and "4 bit" are one and four, not one billion / four billion.
    assert [n.value for n in numbers.extract("1 GB at 4 bit")] == [1, 4]


# --- grounding ----------------------------------------------------------------------------- #
def test_real_call_reply_is_grounded():
    # The agent's actual reply on the 2026-10-28 call, every figure spoken out.
    reply = (
        "the docs specifically say the family starts at the two billion parameter size, with the "
        "text model actually being one point seven billion. It's beating their previous two point "
        "six billion model while using thirty-five percent fewer parameters."
    )
    assert numbers.check_numbers_grounded(reply, [LFM3]).passed


@pytest.mark.parametrize(
    "reply",
    [
        "You're right, it's three billion.",  # caved to the listener's wrong figure
        "It handles a one million token context.",  # invented spec
        "It scored ninety two percent on MMLU.",  # invented benchmark
    ],
)
def test_invented_numbers_fail(reply):
    result = numbers.check_numbers_grounded(reply, [LFM3])
    assert not result.passed
    assert "not in sources" in result.detail


def test_stray_digit_in_a_name_does_not_allow_a_scaled_claim():
    # "LFM3" contains a 3, but that must not let "three billion" through.
    assert numbers.unsupported("three billion", numbers.allowed_values([LFM3])) == ["three billion"]


def test_listener_numbers_may_be_repeated_back():
    sources = ["SpaceX closed a 40 billion dollar debt deal.", "No, it was twenty billion."]
    reply = "I hear you on twenty billion, but my notes say forty billion."
    assert numbers.check_numbers_grounded(reply, sources).passed


# --- case files ---------------------------------------------------------------------------- #
def test_case_files_are_well_formed():
    cases = conversation.load_cases()
    assert len(cases) >= 3
    assert len({c.id for c in cases}) == len(cases)
    for case in cases:
        assert case.rule and case.knowledge
        assert {t.role for t in case.turns} <= {"agent", "listener"}
        graded = [t for t in case.turns if t.role == "agent" and not t.text]
        assert graded, f"{case.id} grades no agent reply"
        assert all(t.expect for t in graded), f"{case.id} has a graded turn with no criteria"
        # A generated reply must answer the listener, so it always follows a listener line.
        for prev, turn in zip(case.turns, case.turns[1:]):
            if turn in graded:
                assert prev.role == "listener", f"{case.id}: graded turn not after the listener"
