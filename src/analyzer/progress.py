"""Multi-track live progress display for parallel pipeline execution (T031)."""
from __future__ import annotations

import sys
import threading
import time

__all__ = [
    "ProgressDisplay",
]

_STATUS_ICONS = {
    "pending":  "○",
    "waiting":  "◐",
    "running":  "●",
    "done":     "✓",
    "failed":   "✗",
    "skipped":  "–",
}

_STATUS_COLORS = {
    "pending":  "white",
    "waiting":  "yellow",
    "running":  "cyan",
    "done":     "green",
    "failed":   "red",
    "skipped":  "bright_black",
}


class ProgressDisplay:
    """Live multi-track progress display using rich (or plain text as fallback).

    Call :meth:`update` from the ``progress_callback`` passed to
    :class:`~src.analyzer.parallel.ParallelRunner`.  When stdout is not a TTY
    the display falls back to one ``click.echo`` line per status change
    (FR-010 / FR-011).

    Usage::

        display = ProgressDisplay(step_names=["librosa_beats", "librosa_onset"])
        display.start()
        # … run algorithms, calling display.update(name, status, detail) …
        display.stop()
    """

    def __init__(self, step_names: list[str], use_rich: bool | None = None) -> None:
        self._step_names = list(step_names)
        self._states: dict[str, dict] = {
            name: {"status": "pending", "mark_count": 0, "elapsed_ms": 0, "error": ""}
            for name in step_names
        }
        self._lock = threading.Lock()
        self._start_time: float | None = None
        # Auto-detect rich availability and TTY
        if use_rich is None:
            use_rich = sys.stdout.isatty() and _rich_available()
        self._use_rich = use_rich
        self._live = None  # rich Live context

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._start_time = time.perf_counter()
        if self._use_rich:
            self._start_rich()

    def stop(self) -> None:
        if self._use_rich and self._live:
            self._live.stop()
            self._live = None

    def update(self, step_name: str, status: str, detail: dict) -> None:
        """Update a step's state and refresh the display."""
        with self._lock:
            if step_name not in self._states:
                self._states[step_name] = {"status": "pending", "mark_count": 0, "elapsed_ms": 0, "error": ""}
            self._states[step_name].update({
                "status": status,
                "mark_count": detail.get("mark_count", 0),
                "elapsed_ms": detail.get("duration_ms", 0),
                "error": detail.get("error", ""),
            })
        if self._use_rich and self._live:
            self._live.update(self._build_rich_table())
        else:
            self._plain_line(step_name, status, detail)

    def as_callback(self):
        """Return a callable compatible with ParallelRunner's progress_callback."""
        def _cb(step_name: str, status: str, detail: dict) -> None:
            self.update(step_name, status, detail)
        return _cb

    # ── Rich rendering ────────────────────────────────────────────────────────

    def _start_rich(self) -> None:
        try:
            from rich.live import Live
            self._live = Live(self._build_rich_table(), refresh_per_second=10)
            self._live.start()
        except Exception:
            self._use_rich = False
            self._live = None

    def _build_rich_table(self):
        from rich.table import Table
        from rich import box
        from rich.text import Text

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
        table.add_column("Step", style="dim", width=24)
        table.add_column("Status", width=10)
        table.add_column("Marks", justify="right", width=7)
        table.add_column("Time", justify="right", width=8)

        with self._lock:
            states = dict(self._states)

        for name, state in states.items():
            status = state["status"]
            icon = _STATUS_ICONS.get(status, "?")
            color = _STATUS_COLORS.get(status, "white")
            status_text = Text(f"{icon} {status}", style=color)
            marks = str(state["mark_count"]) if state["mark_count"] else "–"
            elapsed = f"{state['elapsed_ms']}ms" if state["elapsed_ms"] else "–"
            table.add_row(name, status_text, marks, elapsed)

        return table

    # ── Plain-text fallback ───────────────────────────────────────────────────

    def _plain_line(self, step_name: str, status: str, detail: dict) -> None:
        import click
        icon = _STATUS_ICONS.get(status, "?")
        marks = detail.get("mark_count", 0)
        err = detail.get("error", "")
        suffix = f" ({marks} marks)" if marks else ""
        suffix += f" ERROR: {err}" if err else ""
        click.echo(f"  {icon} {step_name}: {status}{suffix}")


def _rich_available() -> bool:
    try:
        import rich  # noqa: F401
        return True
    except ImportError:
        return False
