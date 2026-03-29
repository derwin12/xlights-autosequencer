"""Shared helper functions for Vamp plugin algorithm wrappers."""
from __future__ import annotations

from src.analyzer.result import TimingMark


def vamp_outputs_to_marks(
    outputs: list, extract_label: bool = False,
) -> list[TimingMark]:
    """Convert vamp plugin output list to TimingMark list.

    When *extract_label* is True, the ``label`` field of each output item is
    captured into :pyattr:`TimingMark.label`.
    """
    marks: list[TimingMark] = []
    for output in outputs:
        t = output["timestamp"]
        t_sec = t.to_float() if hasattr(t, "to_float") else float(t)
        label: str | None = None
        if extract_label:
            raw = output.get("label")
            if raw is not None:
                label = str(raw).strip() or None
        marks.append(TimingMark(time_ms=int(round(t_sec * 1000)), confidence=None, label=label))
    return marks


def vamp_list_to_marks(items: list) -> list[TimingMark]:
    """Convert a generic vamp list output to TimingMark list.

    Handles both dict-style and attribute-style timestamp access.
    """
    marks: list[TimingMark] = []
    for item in items:
        ts = item.get("timestamp") if isinstance(item, dict) else getattr(item, "timestamp", None)
        if ts is not None:
            ms = int(round(float(ts) * 1000))
            marks.append(TimingMark(time_ms=ms, confidence=None))
    return marks
