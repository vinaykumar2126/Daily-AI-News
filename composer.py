"""Assemble per-segment scripts into one spoken digest.

Deterministic: greeting + date, each segment introduced by a short spoken transition, and a
sign-off. The transitions are templated (not LLM-generated) so the control flow stays
predictable regardless of which curator produced the segments.
"""

from __future__ import annotations

import datetime as dt
import re

# A rewrite can come back "empty" in two ways: a truly blank string, or a literal placeholder the
# model types when its prompt tells it to stay silent (the Immigration prompt does this when there
# is no genuine visa-policy news). The model emits things like "(no output)" or "[EMPTY]" — non-
# blank text that would otherwise be spoken aloud as a segment. Treat those as blank so the segment
# is dropped cleanly instead of the agent announcing "no output".
_BLANK_SEGMENT = re.compile(
    r"^[\s\(\[\]\)]*(no output|empty|none|n/?a|no (?:updates|news)\b[^.]*)[\s\(\[\]\)\.]*$",
    re.I,
)


def _is_blank_segment(text: str) -> bool:
    t = (text or "").strip()
    return not t or bool(_BLANK_SEGMENT.match(t))

# A spoken lead-in per segment position. The first uses "First up"; later ones rotate through
# natural hand-offs. Falls back to a generic transition if there are more segments than phrases.
_TRANSITIONS = [
    "First up, {name}.",
    "Next, {name}.",
    "Turning to {name}.",
    "And finally, {name}.",
]
_GENERIC_TRANSITION = "Now, {name}."


def _greeting(date: dt.date) -> str:
    date_str = date.strftime("%A, %B %-d")
    return (
        f"Good morning. Here's your briefing for {date_str}."
    )


def _transition(index: int, total: int, name: str) -> str:
    if index == total - 1 and total > 1:
        return _TRANSITIONS[-1].format(name=name)
    if index < len(_TRANSITIONS) - 1:
        return _TRANSITIONS[index].format(name=name)
    return _GENERIC_TRANSITION.format(name=name)


def compose(segments: list[tuple[str, str]], date: dt.date | None = None) -> str:
    """segments: list of (feed_name, segment_text) in order. Returns the full spoken script."""
    date = date or dt.date.today()
    segments = [(name, text.strip()) for name, text in segments if not _is_blank_segment(text)]
    if not segments:
        return ""

    parts: list[str] = [_greeting(date)]
    total = len(segments)
    for i, (name, text) in enumerate(segments):
        parts.append(_transition(i, total, name))
        parts.append(text)
    parts.append("That's your briefing. Have a great day.")

    return "\n\n".join(parts)
