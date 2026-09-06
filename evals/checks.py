"""Code-only eval checks — no LLM, run on every evaluation for free.

Each check returns a Result(name, passed, score 0-1, detail). These catch the boring-but-common
failures: over-long segments, missing structure, and TTS-hostile tokens that would mangle audio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Result:
    name: str
    passed: bool
    score: float  # 0..1
    detail: str


def check_length(segments: list[tuple[str, str]], budgets: dict[str, int]) -> Result:
    """Each segment should stay within ~130% of its word budget."""
    offenders = []
    ratios = []
    for name, text in segments:
        budget = budgets.get(name, 250)
        words = len(text.split())
        ratio = words / budget if budget else 0
        ratios.append(min(ratio, 2.0))
        if ratio > 1.3:
            offenders.append(f"{name}: {words}w > {budget}w budget")
    # Score: 1.0 when everything is at/under budget, decaying as segments overshoot.
    avg_over = sum(max(0.0, r - 1.0) for r in ratios) / len(ratios) if ratios else 0
    score = max(0.0, 1.0 - avg_over)
    return Result(
        "length_adherence",
        not offenders,
        round(score, 2),
        "; ".join(offenders) if offenders else "all segments within budget",
    )


def check_structure(script: str, segment_names: list[str]) -> Result:
    """Greeting, every segment's transition, and a sign-off should all be present."""
    missing = []
    if "good morning" not in script.lower():
        missing.append("greeting")
    for name in segment_names:
        if name.lower() not in script.lower():
            missing.append(f"transition:{name}")
    if "briefing" not in script.lower():
        missing.append("sign-off")
    total = 2 + len(segment_names)
    score = max(0.0, 1.0 - len(missing) / total)
    return Result(
        "structure",
        not missing,
        round(score, 2),
        "complete" if not missing else "missing: " + ", ".join(missing),
    )


# Tokens that read badly through TTS if left raw.
_TTS_PATTERNS = {
    "markdown": re.compile(r"[#*`_]{1,}"),
    "money_abbrev": re.compile(r"\$\d+(\.\d+)?\s?[BMK]\b"),
    "model_hyphen_digit": re.compile(r"\b(GPT|Claude|Gemini|Llama)-?\d", re.I),
    "raw_multiplier": re.compile(r"\b\d+x\b"),
}


def check_tts_safety(script: str) -> Result:
    """Flag tokens likely to mangle in audio (markdown, $2B, GPT-4o, 100x)."""
    hits = []
    for label, pat in _TTS_PATTERNS.items():
        found = pat.findall(script)
        if found:
            hits.append(f"{label}({len(found)})")
    score = 1.0 if not hits else max(0.0, 1.0 - 0.25 * len(hits))
    return Result(
        "tts_safety",
        not hits,
        round(score, 2),
        "clean" if not hits else "found: " + ", ".join(hits),
    )


def run_code_checks(
    script: str, segments: list[tuple[str, str]], budgets: dict[str, int]
) -> list[Result]:
    names = [n for n, _ in segments]
    return [
        check_length(segments, budgets),
        check_structure(script, names),
        check_tts_safety(script),
    ]
