"""Curation strategies: the swappable 'brain' that ranks, dedupes, and trims stories.

Select one by name with `create_curator(name)`. The deterministic curator is always
available; the agentic (ADK) curator is imported lazily so its heavier deps are only
required when actually used.
"""

from __future__ import annotations

from curation.base import Curator
from curation.deterministic import DeterministicCurator


def create_curator(name: str) -> Curator:
    """Build a curator by name: 'deterministic' (default) or 'agentic'."""
    name = (name or "deterministic").lower()
    if name == "deterministic":
        return DeterministicCurator()
    if name == "agentic":
        # Lazy import: only pull in ADK when the agentic curator is requested.
        from curation.agentic import AgenticCurator

        return AgenticCurator(fallback=DeterministicCurator())
    raise ValueError(f"Unknown curator {name!r} (expected 'deterministic' or 'agentic')")


__all__ = ["Curator", "DeterministicCurator", "create_curator"]
