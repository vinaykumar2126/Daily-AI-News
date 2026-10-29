"""Code-only "no new numbers" check — every number the agent says must exist in its sources.

Most invented facts on a call are numbers: a raise, a parameter count, a percentage. This pulls
every number out of a reply — digits ("2.6B", "$40 billion", "256K") and spoken words ("one point
seven billion", "thirty-five percent") alike — and flags any value the sources never mention.

Sources are read generously (both "40" and "40 billion" count as allowed), replies strictly (only
the full value), so "three billion" is flagged even though a stray "3" appears in "LFM3". Bare
spoken numbers below 11 with no scale word ("the one I'd try", "two of them") are ignored: they're
nearly always grammar, not claims.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from evals.checks import Result

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
_SCALES = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}

# A digit run with optional decimals and an optional K/M/B/T suffix that isn't the start of a
# word ("2.6b" and "256k" yes; "1gb" and "4bit" stay plain 1 and 4). Otherwise a word, or
# punctuation — kept as a boundary so "forty billion. Forty billion" stays two numbers.
_TOKEN = re.compile(r"\d+(?:\.\d+)?(?:[kmbt](?![a-z]))?|[a-z]+|[,.;:!?]")
_BOUNDARY = set(",.;:!?")


@dataclass(frozen=True)
class Number:
    value: float
    text: str  # how it appeared, for readable failure messages
    bare_small: bool  # spoken word under 11 with no scale -> usually grammar, not a claim


def _tokens(text: str) -> list[str]:
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text.lower())  # 41,000 -> 41000
    return _TOKEN.findall(text.replace("-", " "))


def extract(text: str) -> list[Number]:
    """Every number in `text`, digits or spoken, with scale words applied."""
    toks = _tokens(text)
    out: list[Number] = []
    i = 0
    while i < len(toks):
        tok = toks[i]
        if tok[0].isdigit():
            scale = _SUFFIX.get(tok[-1], 1.0) if tok[-1].isalpha() else 1.0
            value = float(tok.rstrip("kmbt"))
            start = i
            if scale == 1.0 and i + 1 < len(toks) and toks[i + 1] in _SCALES:
                scale = _SCALES[toks[i + 1]]
                i += 1
            out.append(Number(value * scale, " ".join(toks[start : i + 1]), False))
            i += 1
            continue
        if tok in _UNITS or tok in _TENS:
            num, i = _read_words(toks, i)
            out.append(num)
            continue
        i += 1
    return out


def _read_words(toks: list[str], i: int) -> tuple[Number, int]:
    """Parse a spoken number starting at toks[i]; return it and the index after it."""
    start, total, current, scaled = i, 0.0, 0.0, False
    last = None  # "unit" | "tens" | "hundred" — a second tens/unit in a row starts a new number
    prev_scale = float("inf")  # "billion ... million" continues one number; "billion ... billion" doesn't
    after_scale = i
    while i < len(toks):
        tok = toks[i]
        if tok in _BOUNDARY:
            break
        if tok in _UNITS:
            if last == "unit" or (last == "tens" and _UNITS[tok] >= 10):
                break
            current += _UNITS[tok]
            last = "unit"
        elif tok in _TENS:
            if last in ("unit", "tens"):
                break
            current += _TENS[tok]
            last = "tens"
        elif tok == "hundred" and last in ("unit", "tens"):
            current *= 100
            last = "hundred"
        elif tok in _SCALES and last is not None:
            if _SCALES[tok] >= prev_scale:
                # "forty billion forty billion": the second "forty" starts a new number.
                i, current = after_scale, 0.0
                break
            total += max(current, 1.0) * _SCALES[tok]
            current, scaled, last, prev_scale = 0.0, True, None, _SCALES[tok]
            after_scale = i + 1
        elif tok == "and" and last == "hundred":
            pass
        elif tok == "point" and last in ("unit", "tens", None) and i + 1 < len(toks) and toks[i + 1] in _UNITS:
            # "one point seven billion": decimal digits are read one word at a time.
            digits = ""
            i += 1
            while i < len(toks) and toks[i] in _UNITS and _UNITS[toks[i]] < 10:
                digits += str(_UNITS[toks[i]])
                i += 1
            current = float(f"{int(current)}.{digits}")
            if i < len(toks) and toks[i] in _SCALES:
                total += current * _SCALES[toks[i]]
                current, scaled = 0.0, True
                i += 1
            break
        else:
            break
        i += 1
    value = total + current
    return Number(value, " ".join(toks[start:i]), not scaled and value < 11), i


def allowed_values(texts: list[str]) -> set[float]:
    """Values the agent may say: every number in the sources, both scaled and unscaled."""
    allowed: set[float] = set()
    for text in texts:
        for n in extract(text):
            allowed.add(n.value)
        # Also the unscaled base of "40 billion" / "2.6B", so a source's 40B allows a plain 40.
        for tok in _tokens(text):
            if tok[0].isdigit():
                allowed.add(float(tok.rstrip("kmbt")))
    return allowed


def _known(value: float, allowed: set[float]) -> bool:
    return any(abs(value - a) <= 1e-6 * max(abs(a), 1.0) for a in allowed)


def unsupported(reply: str, allowed: set[float]) -> list[str]:
    """Numbers in `reply` that no source mentions."""
    return [n.text for n in extract(reply) if not n.bare_small and not _known(n.value, allowed)]


def check_numbers_grounded(reply: str, sources: list[str]) -> Result:
    """Fail if the reply states any number that isn't in `sources`."""
    bad = unsupported(reply, allowed_values(sources))
    return Result(
        "numbers_grounded",
        not bad,
        1.0 if not bad else 0.0,
        "all numbers found in sources" if not bad else "not in sources: " + ", ".join(bad),
    )
