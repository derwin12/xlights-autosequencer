"""Compare current microscope metric results against a per-song golden baseline.

This module produces a ``DiffReport`` of ``DiffRow`` rows, one per
``(song, metric)`` pair encountered in either the current run or the on-disk
baseline. Direction arrows are rendered using the
``MetricDefinition.higher_is_better`` field from the metric registry:

* ``None`` (direction unvalidated) -> bare ``"↑"`` / ``"↓"``.
* ``True``  -> ``"↑✓"`` for positive deltas, ``"↓✗"`` for negative.
* ``False`` -> inverted: ``"↑✗"`` / ``"↓✓"``.

Structured (non-scalar) metrics are excluded from the table and counted in
a footnote. Missing baseline entries produce ``"NEW"`` rows; metrics present
in baseline but absent from the current run produce ``"MISSING"`` rows.

The ``current_results`` parameter is intentionally typed as a ``Protocol`` so
this module does not need to import ``MicroscopeResult`` (which is owned by
a downstream phase of the same OpenSpec change). Any object exposing ``.slug``
and ``.metrics`` will work.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Protocol

from src.evaluation.metrics import get_registry
from src.evaluation.models import MetricValue


_SCALAR_KIND = "scalar"


class _ResultLike(Protocol):
    """Minimal interface required from a microscope result.

    The runtime objects passed in are ``MicroscopeResult`` instances (defined
    in a sibling module that doesn't exist yet); this Protocol keeps the
    diff module decoupled from that import.
    """

    @property
    def slug(self) -> str: ...

    @property
    def metrics(self) -> dict[str, MetricValue]: ...


@dataclass(frozen=True)
class DiffRow:
    """One row in the diff table — a single (song, metric) comparison."""

    slug: str
    metric: str
    baseline: float | None
    current: float | None
    absolute_delta: float | None
    relative_pct: float | None
    direction: str
    note: str  # "", "NEW", "MISSING", or "STRUCTURED"


@dataclass
class DiffReport:
    """A collection of diff rows plus structured-metric exclusion count.

    ``structured_excluded`` counts metrics that exist in either side as
    non-scalar; they are deliberately not represented as rows because no
    scalar comparison is defined.
    """

    rows: list[DiffRow] = field(default_factory=list)
    structured_excluded: int = 0

    def format_table(self) -> str:
        """Render the rows as a fixed-width text table.

        The widths are computed from the data so very long song slugs or
        metric names don't get truncated; tests assert on token presence,
        not exact column widths.
        """
        headers = ("Song", "Metric", "Baseline", "Current", "Delta", "%Change", "Dir")
        rendered: list[tuple[str, str, str, str, str, str, str]] = []
        for row in self.rows:
            rendered.append(
                (
                    row.slug,
                    row.metric,
                    _fmt_value(row.baseline),
                    _fmt_value(row.current),
                    _fmt_delta(row.absolute_delta),
                    _fmt_pct(row.relative_pct),
                    row.note if row.note in {"NEW", "MISSING"} else row.direction,
                )
            )

        widths = [len(h) for h in headers]
        for cells in rendered:
            for i, cell in enumerate(cells):
                if len(cell) > widths[i]:
                    widths[i] = len(cell)

        # Left-align text columns (Song, Metric, Dir/note); right-align numeric.
        align_left = {0, 1, 6}

        def _fmt_row(cells: tuple[str, ...]) -> str:
            parts = []
            for i, cell in enumerate(cells):
                if i in align_left:
                    parts.append(cell.ljust(widths[i]))
                else:
                    parts.append(cell.rjust(widths[i]))
            return "  ".join(parts).rstrip()

        lines = [_fmt_row(headers)]
        sep = "  ".join("-" * w for w in widths)
        lines.append(sep)
        for cells in rendered:
            lines.append(_fmt_row(cells))

        if self.structured_excluded > 0:
            lines.append(
                f"({self.structured_excluded} structured metric(s) excluded — "
                "no scalar comparison defined.)"
            )

        return "\n".join(lines)


def diff_results(
    current_results: Iterable[_ResultLike],
    baseline_dir: Path,
) -> DiffReport:
    """Compare current results against per-song JSON baselines.

    For each result, look up ``baseline_dir/<slug>/baseline.json``. If
    missing, every row for that slug is marked ``NEW``. Otherwise, each
    metric in the union of current + baseline names produces one row.

    Structured (non-scalar) metrics are skipped from the rows list and
    counted in ``DiffReport.structured_excluded``.
    """
    baseline_dir = Path(baseline_dir)
    registry = get_registry()
    report = DiffReport()

    for result in current_results:
        slug = result.slug
        current_metrics = dict(result.metrics)
        baseline_path = baseline_dir / slug / "baseline.json"
        baseline_metrics = _load_baseline(baseline_path)

        if baseline_metrics is None:
            # No baseline file at all — every current metric is NEW.
            for name, value in current_metrics.items():
                if not _is_scalar(value.kind):
                    report.structured_excluded += 1
                    continue
                report.rows.append(
                    DiffRow(
                        slug=slug,
                        metric=name,
                        baseline=None,
                        current=_safe_float(value.value),
                        absolute_delta=None,
                        relative_pct=None,
                        direction="",
                        note="NEW",
                    )
                )
            continue

        names = sorted(set(current_metrics) | set(baseline_metrics))
        for name in names:
            current_entry = current_metrics.get(name)
            baseline_entry = baseline_metrics.get(name)

            current_kind = current_entry.kind if current_entry is not None else None
            baseline_kind = (
                baseline_entry.get("kind") if baseline_entry is not None else None
            )

            # Skip structured metrics (no scalar comparison defined). We
            # treat the metric as structured if either side reports a
            # non-scalar kind.
            if (current_kind is not None and not _is_scalar(current_kind)) or (
                baseline_kind is not None and not _is_scalar(baseline_kind)
            ):
                report.structured_excluded += 1
                continue

            if current_entry is None:
                # In baseline but not in current.
                report.rows.append(
                    DiffRow(
                        slug=slug,
                        metric=name,
                        baseline=_safe_float(baseline_entry.get("value")),
                        current=None,
                        absolute_delta=None,
                        relative_pct=None,
                        direction="",
                        note="MISSING",
                    )
                )
                continue

            current_value = _safe_float(current_entry.value)
            baseline_value = (
                _safe_float(baseline_entry.get("value"))
                if baseline_entry is not None
                else None
            )

            if baseline_value is None or current_value is None:
                report.rows.append(
                    DiffRow(
                        slug=slug,
                        metric=name,
                        baseline=baseline_value,
                        current=current_value,
                        absolute_delta=None,
                        relative_pct=None,
                        direction="",
                        note="",
                    )
                )
                continue

            absolute_delta = current_value - baseline_value
            if baseline_value != 0:
                relative_pct = (absolute_delta / baseline_value) * 100.0
            else:
                relative_pct = None

            higher_is_better = (
                registry[name].higher_is_better if name in registry else None
            )
            direction = _direction_arrow(absolute_delta, higher_is_better)

            report.rows.append(
                DiffRow(
                    slug=slug,
                    metric=name,
                    baseline=baseline_value,
                    current=current_value,
                    absolute_delta=absolute_delta,
                    relative_pct=relative_pct,
                    direction=direction,
                    note="",
                )
            )

    return report


def _load_baseline(path: Path) -> dict[str, dict] | None:
    """Return the ``metrics`` dict from a baseline JSON file, or ``None``.

    The file shape is ``{"slug": str, "metrics": {<name>: {"value": ..., "kind": ...}}}``.
    A missing file returns ``None`` to signal "no baseline for this slug".
    """
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    metrics = data.get("metrics", {})
    if not isinstance(metrics, dict):
        return {}
    return metrics


def _is_scalar(kind: str | None) -> bool:
    return kind == _SCALAR_KIND


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        # ``bool`` is a subclass of ``int``; we don't treat it as numeric here.
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _direction_arrow(absolute_delta: float, higher_is_better: bool | None) -> str:
    if absolute_delta == 0:
        return ""
    positive = absolute_delta > 0
    if higher_is_better is None:
        return "↑" if positive else "↓"
    if higher_is_better is True:
        return "↑✓" if positive else "↓✗"
    # higher_is_better is False — invert.
    return "↑✗" if positive else "↓✓"


def _fmt_value(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}"


def _fmt_delta(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.1f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:+.1f}%"
