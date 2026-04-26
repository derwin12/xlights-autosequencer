"""Analyzer-layer regression baseline.

Parallel to `src/evaluation/baseline.py` (which gates generator-layer quality
metrics), this module snapshots and checks the analyzer's timing-track outputs
per-fixture. A baseline captures every algorithm's full event list on each
fixture plus a per-algorithm tolerance rule; regression checks allow count
drift within a percentage and timing drift within a fixed millisecond window.

Byte-exact matching is not viable — madmom, demucs, and some vamp plugins have
non-deterministic paths (threading, BLAS order, GPU fallback) that cause
sub-millisecond float drift. Tolerances are the source of truth for "same".

The actual snapshot-taking (running the analyzer on audio) is orchestrated by
`src/evaluation/acceptance_gate.py`; this module is pure data / logic and is
fully testable without audio or the analyzer pipeline.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.analyzer.result import TimingTrack

SCHEMA_VERSION = 2  # bumped 2026-04-25: add per-fixture repetition_groups
DEFAULT_BASELINE_PATH = Path("tests/golden/analyzer/baseline.json")

DEFAULT_COUNT_TOLERANCE_PCT = 5.0
DEFAULT_TIMING_TOLERANCE_MS = 50

# Per-algorithm tolerances. Algorithms not in this map fall back to defaults.
# Values here reflect each algorithm's real-world determinism (beat trackers
# are tighter than onset detectors, chord trackers need enharmonic flex, etc.).
ALGORITHM_TOLERANCES: dict[str, dict[str, Any]] = {
    "qm_bar_beat_tracker": {"count_tolerance_pct": 2.0, "timing_tolerance_ms": 30},
    "beatroot_beat_tracker": {"count_tolerance_pct": 2.0, "timing_tolerance_ms": 30},
    "librosa_beats": {"count_tolerance_pct": 2.0, "timing_tolerance_ms": 30},
    "madmom_beat_rnn_dbn": {"count_tolerance_pct": 2.0, "timing_tolerance_ms": 30},
    "madmom_downbeat_rnn_dbn": {"count_tolerance_pct": 3.0, "timing_tolerance_ms": 50},
    "qm_onset_detector": {"count_tolerance_pct": 10.0, "timing_tolerance_ms": 50},
    "librosa_bands": {"count_tolerance_pct": 10.0, "timing_tolerance_ms": 50},
    "librosa_hpss": {"count_tolerance_pct": 10.0, "timing_tolerance_ms": 50},
    "qm_segmenter": {
        "count_tolerance_pct": 15.0,
        "timing_tolerance_ms": 500,
        "merge_window_ms": 2000,
    },
    # `qm_segments` and `segmentino` are section-boundary detectors with
    # observed run-to-run variance of 6 → 15 events on identical input.
    # That's not float drift — the algorithms produce fundamentally different
    # segmentations across runs (likely thread-scheduling or unseeded RNG in
    # the underlying clustering). Wide tolerance can't paper over a 150%
    # event-count swing. Mark them `skip_check` so the gate captures their
    # output for inspection in the baseline but doesn't fail on drift.
    # Genuine regressions in section detection still get caught by the
    # higher-level story builder + downstream tests.
    # See: tests/golden/analyzer/baseline.json — these tracks are recorded
    # for forensic value but not gated.
    "qm_segments": {
        "count_tolerance_pct": 25.0,
        "timing_tolerance_ms": 5000,
        "merge_window_ms": 3000,
        "skip_check": True,
    },
    "segmentino": {
        "count_tolerance_pct": 25.0,
        "timing_tolerance_ms": 5000,
        "merge_window_ms": 3000,
        "skip_check": True,
    },
    "qm_tempo_tracker": {"count_tolerance_pct": 5.0, "timing_tolerance_ms": 100},
    "chordino": {
        "count_tolerance_pct": 10.0,
        "timing_tolerance_ms": 100,
        "enharmonic_equivalents": True,
    },
    "nnls_chroma": {"count_tolerance_pct": 10.0, "timing_tolerance_ms": 100},
    "pyin_notes": {"count_tolerance_pct": 15.0, "timing_tolerance_ms": 100},
}


def tolerance_for(algorithm_name: str) -> dict[str, Any]:
    """Return the tolerance rule for an algorithm, falling back to defaults."""
    base = {
        "count_tolerance_pct": DEFAULT_COUNT_TOLERANCE_PCT,
        "timing_tolerance_ms": DEFAULT_TIMING_TOLERANCE_MS,
    }
    base.update(ALGORITHM_TOLERANCES.get(algorithm_name, {}))
    return base


@dataclass
class TrackSnapshot:
    """Per-algorithm baseline entry: event timestamps + tolerance rule."""

    algorithm_name: str
    event_times_ms: list[int]
    event_labels: list[Optional[str]]  # parallel to event_times_ms, for chord labels etc.
    tolerance: dict[str, Any]

    @property
    def count(self) -> int:
        return len(self.event_times_ms)

    def to_dict(self) -> dict:
        return {
            "algorithm_name": self.algorithm_name,
            "event_times_ms": list(self.event_times_ms),
            "event_labels": list(self.event_labels),
            "tolerance": dict(self.tolerance),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TrackSnapshot":
        return cls(
            algorithm_name=d["algorithm_name"],
            event_times_ms=list(d["event_times_ms"]),
            event_labels=list(d.get("event_labels", [None] * len(d["event_times_ms"]))),
            tolerance=dict(d["tolerance"]),
        )

    @classmethod
    def from_track(cls, track: TimingTrack) -> "TrackSnapshot":
        """Snapshot a live TimingTrack into a baseline entry."""
        return cls(
            algorithm_name=track.algorithm_name,
            event_times_ms=[m.time_ms for m in track.marks],
            event_labels=[m.label for m in track.marks],
            tolerance=tolerance_for(track.algorithm_name),
        )


@dataclass
class FixtureSnapshot:
    """All algorithm snapshots for a single fixture.

    `repetition_groups` (added in schema v2) captures the SSM Chorus
    validator's output (`HierarchyResult.repetition_groups`) — which is
    a per-fixture field, not a per-algorithm one, so it lives at this
    level rather than nested under `algorithms`. Each element is the
    serialized form of `RepetitionGroup.to_dict()`. None means the SSM
    pass either errored or wasn't run; an empty list means SSM ran and
    found no repetition.
    """

    fixture_slug: str
    algorithms: dict[str, TrackSnapshot] = field(default_factory=dict)
    repetition_groups: Optional[list[dict]] = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "fixture_slug": self.fixture_slug,
            "algorithms": {name: snap.to_dict() for name, snap in self.algorithms.items()},
        }
        # Only emit when not None so v1-equivalent fixtures stay diff-friendly.
        if self.repetition_groups is not None:
            d["repetition_groups"] = self.repetition_groups
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FixtureSnapshot":
        return cls(
            fixture_slug=d["fixture_slug"],
            algorithms={
                name: TrackSnapshot.from_dict(data)
                for name, data in d.get("algorithms", {}).items()
            },
            repetition_groups=d.get("repetition_groups"),  # None when absent (v1 baseline)
        )


@dataclass
class AnalyzerBaseline:
    """Top-level baseline: all fixtures, all algorithms."""

    fixtures: dict[str, FixtureSnapshot] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "fixtures": {slug: fs.to_dict() for slug, fs in self.fixtures.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AnalyzerBaseline":
        schema = d.get("schema_version", 0)
        # Use the shared stale-cache helper with on_older="raise" — a stale
        # baseline is gating data, so silently swapping it would mask
        # regressions. snapshot_analyzer in src/cli/evaluate.py catches the
        # resulting ValueError and rebuilds from scratch; the acceptance
        # gate lets it propagate so the user is told how to refresh.
        from src.schema_check import check_stale_cache

        check_stale_cache(
            schema,
            SCHEMA_VERSION,
            name="Analyzer baseline",
            refresh_hint="xlight-evaluate snapshot-analyzer",
            on_older="raise",
        )
        return cls(
            fixtures={
                slug: FixtureSnapshot.from_dict(data)
                for slug, data in d.get("fixtures", {}).items()
            },
            schema_version=schema,
        )


# ---------- Load / save ----------

class BaselineMissingError(FileNotFoundError):
    pass


def load(path: Path = DEFAULT_BASELINE_PATH) -> AnalyzerBaseline:
    if not path.exists():
        raise BaselineMissingError(f"Analyzer baseline not found at {path}")
    return AnalyzerBaseline.from_dict(json.loads(path.read_text()))


def save(baseline: AnalyzerBaseline, path: Path = DEFAULT_BASELINE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline.to_dict(), indent=2) + "\n")


# ---------- Comparison ----------

@dataclass(frozen=True)
class Violation:
    fixture_slug: str
    algorithm_name: str
    kind: str  # "count" | "timing" | "label"
    detail: str


def _chord_equivalent(a: Optional[str], b: Optional[str]) -> bool:
    """Enharmonic equivalence for chord labels (e.g., 'F#m' ≡ 'Gbm').

    Simple implementation: tolerate both spellings of the 5 common enharmonic
    pairs. Not a full theory engine — gate purpose is regression, not musicology.
    """
    if a == b:
        return True
    if a is None or b is None:
        return False
    pairs = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}
    for left, right in pairs.items():
        if a.startswith(left) and b.startswith(right) and a[len(left):] == b[len(right):]:
            return True
        if a.startswith(right) and b.startswith(left) and a[len(right):] == b[len(left):]:
            return True
    return False


def _merge_close_events(times_ms: list[int], window_ms: int) -> list[int]:
    """Merge events within `window_ms` of each other (section boundary helper)."""
    if not times_ms:
        return []
    merged = [times_ms[0]]
    for t in times_ms[1:]:
        if t - merged[-1] < window_ms:
            continue
        merged.append(t)
    return merged


def check_track(
    baseline_snap: TrackSnapshot,
    current_snap: TrackSnapshot,
    fixture_slug: str,
) -> list[Violation]:
    """Compare a current snapshot against baseline; return violations (empty = pass)."""
    violations: list[Violation] = []
    tol = baseline_snap.tolerance
    algo = baseline_snap.algorithm_name

    # Algorithms with `skip_check: True` are recorded in the baseline for
    # forensic value but don't gate. Used for fundamentally non-deterministic
    # detectors (e.g. qm_segments — see ALGORITHM_TOLERANCES for context).
    #
    # Read from BOTH the saved baseline tolerance and the live config so
    # config changes take effect without requiring a baseline re-snapshot —
    # the saved tolerance dict reflects whatever was current at snapshot
    # time; the live tolerance_for() reflects current code intent.
    if tol.get("skip_check") or tolerance_for(algo).get("skip_check"):
        return violations

    base_times = list(baseline_snap.event_times_ms)
    curr_times = list(current_snap.event_times_ms)

    # Apply section-style merge before comparing if tolerance requests it.
    merge_window = tol.get("merge_window_ms")
    if merge_window:
        base_times = _merge_close_events(base_times, merge_window)
        curr_times = _merge_close_events(curr_times, merge_window)

    # Count tolerance check.
    count_pct = float(tol.get("count_tolerance_pct", DEFAULT_COUNT_TOLERANCE_PCT))
    base_count = len(base_times)
    curr_count = len(curr_times)
    if base_count == 0:
        if curr_count != 0:
            violations.append(Violation(
                fixture_slug, algo, "count",
                f"baseline has 0 events; current has {curr_count}",
            ))
            return violations
        return violations

    drift_pct = abs(curr_count - base_count) / base_count * 100
    if drift_pct > count_pct:
        violations.append(Violation(
            fixture_slug, algo, "count",
            f"event count drifted {drift_pct:.1f}% (tolerance {count_pct:.1f}%): "
            f"baseline {base_count} → current {curr_count}",
        ))
        # Pairing below doesn't make sense with mismatched counts — return early.
        return violations

    # Timing tolerance check — pair events in order, compare timestamps.
    timing_ms = int(tol.get("timing_tolerance_ms", DEFAULT_TIMING_TOLERANCE_MS))
    for i, (base_t, curr_t) in enumerate(zip(base_times, curr_times)):
        if abs(curr_t - base_t) > timing_ms:
            violations.append(Violation(
                fixture_slug, algo, "timing",
                f"event #{i} drifted {abs(curr_t - base_t)}ms "
                f"(tolerance {timing_ms}ms): baseline {base_t} → current {curr_t}",
            ))

    # Label check — chord trackers with enharmonic_equivalents get flex.
    if tol.get("enharmonic_equivalents"):
        compare_labels = _chord_equivalent
    else:
        compare_labels = lambda a, b: a == b  # noqa: E731

    for i, (base_l, curr_l) in enumerate(zip(baseline_snap.event_labels, current_snap.event_labels)):
        if base_l is None and curr_l is None:
            continue
        if not compare_labels(base_l, curr_l):
            violations.append(Violation(
                fixture_slug, algo, "label",
                f"event #{i} label changed: baseline {base_l!r} → current {curr_l!r}",
            ))

    return violations


def check_fixture(
    baseline: AnalyzerBaseline,
    fixture_slug: str,
    current: FixtureSnapshot,
) -> list[Violation]:
    """Compare a freshly-snapshot fixture against baseline; return all violations."""
    if fixture_slug not in baseline.fixtures:
        return [Violation(
            fixture_slug, "*", "missing",
            f"fixture '{fixture_slug}' has no baseline entry — run snapshot --analyzer",
        )]

    baseline_fixture = baseline.fixtures[fixture_slug]
    violations: list[Violation] = []
    for algo_name, current_snap in current.algorithms.items():
        if algo_name not in baseline_fixture.algorithms:
            # New algorithm without baseline — warn but don't fail (per spec).
            continue
        violations.extend(
            check_track(baseline_fixture.algorithms[algo_name], current_snap, fixture_slug)
        )
    return violations
