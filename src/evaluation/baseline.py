"""Baseline read/write and regression gate logic."""
from __future__ import annotations

import json
import subprocess
import os
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass

from src.evaluation.models import MetricValue
from src.evaluation.metrics import DEFAULT_TOLERANCE, MetricTolerance

SCHEMA_VERSION = 1
DEFAULT_BASELINE_PATH = Path("tests/golden/baseline.json")


class BaselineMissingError(Exception):
    pass


class BaselineSchemaError(Exception):
    pass


@dataclass
class RegressionViolation:
    song_id: str
    metric_name: str
    baseline_value: float
    current_value: float
    delta: float          # current - baseline
    tolerance_str: str    # human-readable tolerance description


@dataclass
class CompareResult:
    passed: bool
    violations: list[RegressionViolation]
    song_count_mismatch: bool
    baseline_songs: set[str]
    current_songs: set[str]


def write_baseline(song_metrics: dict[str, list[MetricValue]], path: Path) -> None:
    """Write a baseline snapshot JSON file.

    Args:
        song_metrics: Mapping of song_id to list of MetricValue objects.
        path: Destination file path.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        generator_commit = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        generator_commit = ""

    entries: dict[str, dict] = {}
    for song_id, metrics in song_metrics.items():
        entries[song_id] = {"metrics": [mv.to_dict() for mv in metrics]}

    data = {
        "schema_version": SCHEMA_VERSION,
        "generator_commit": generator_commit,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "entries": entries,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def load_baseline(path: Path) -> dict:
    """Load a baseline JSON file.

    Returns:
        Parsed dict with schema_version, generator_commit, generated_at, entries.

    Raises:
        BaselineMissingError: If the file does not exist.
        BaselineSchemaError: If the schema_version does not match SCHEMA_VERSION.
    """
    if not path.exists():
        raise BaselineMissingError(f"Baseline file not found: {path}")

    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if data.get("schema_version") != SCHEMA_VERSION:
        raise BaselineSchemaError(
            f"Baseline schema version {data.get('schema_version')!r} "
            f"does not match expected {SCHEMA_VERSION}"
        )

    return data


def compare_against_baseline(
    baseline_dict: dict,
    current_song_metrics: dict[str, list[MetricValue]],
    registry: dict,
) -> CompareResult:
    """Compare current metrics against a loaded baseline.

    Args:
        baseline_dict: Result of load_baseline().
        current_song_metrics: Mapping of song_id to list of MetricValue objects.
        registry: Output of get_registry() — maps metric name to MetricDefinition.

    Returns:
        CompareResult with all violations found.
    """
    baseline_songs: set[str] = set(baseline_dict.get("entries", {}).keys())
    current_songs: set[str] = set(current_song_metrics.keys())

    song_count_mismatch = False
    if baseline_songs != current_songs:
        # Only flag as a mismatch when not in a CI baseline-update commit
        if not _baseline_updated_in_same_commit(DEFAULT_BASELINE_PATH):
            song_count_mismatch = True

    violations: list[RegressionViolation] = []

    for song_id in baseline_songs & current_songs:
        baseline_metrics_raw: list[dict] = baseline_dict["entries"][song_id].get("metrics", [])
        baseline_by_name: dict[str, dict] = {m["name"]: m for m in baseline_metrics_raw}

        current_metrics: list[MetricValue] = current_song_metrics[song_id]
        current_by_name: dict[str, MetricValue] = {mv.name: mv for mv in current_metrics}

        for metric_name, baseline_raw in baseline_by_name.items():
            baseline_value = baseline_raw.get("value")

            # Skip when baseline had no measurement
            if baseline_value is None:
                continue

            # Determine if this metric is gated
            defn = registry.get(metric_name)
            if defn is not None and not defn.gated:
                continue

            current_mv = current_by_name.get(metric_name)
            if current_mv is None or current_mv.value is None:
                # Missing or unmeasured on our side — treat as regression
                violations.append(
                    RegressionViolation(
                        song_id=song_id,
                        metric_name=metric_name,
                        baseline_value=float(baseline_value),
                        current_value=float("nan"),
                        delta=float("nan"),
                        tolerance_str="metric missing in current run",
                    )
                )
                continue

            # Resolve tolerance
            if defn is not None and defn.tolerance is not None:
                tolerance: MetricTolerance = defn.tolerance
            else:
                tolerance = DEFAULT_TOLERANCE

            current_value = float(current_mv.value)
            bv = float(baseline_value)
            delta = current_value - bv

            if tolerance.kind == "relative":
                exceeded = abs(delta) / max(abs(bv), 1e-9) > tolerance.value
                tolerance_str = f"relative ±{tolerance.value * 100:.1f}%"
            else:  # absolute
                exceeded = abs(delta) > tolerance.value
                tolerance_str = f"absolute ±{tolerance.value}"

            if exceeded:
                violations.append(
                    RegressionViolation(
                        song_id=song_id,
                        metric_name=metric_name,
                        baseline_value=bv,
                        current_value=current_value,
                        delta=delta,
                        tolerance_str=tolerance_str,
                    )
                )

    passed = not violations and not song_count_mismatch

    return CompareResult(
        passed=passed,
        violations=violations,
        song_count_mismatch=song_count_mismatch,
        baseline_songs=baseline_songs,
        current_songs=current_songs,
    )


def _baseline_updated_in_same_commit(baseline_path: Path) -> bool:
    """Check whether the baseline file was updated in the most recent commit.

    In CI: runs git diff to inspect HEAD~1..HEAD.  If the command fails (shallow
    clone, no prior commit, etc.) we conservatively return False so the mismatch
    is still flagged.

    Locally (CI env var absent): return True, which suppresses the mismatch
    warning and doesn't penalise developers running tests locally.
    """
    if not os.environ.get("CI"):
        return True  # local run — skip the check

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        changed_files = result.stdout.splitlines()
        return str(baseline_path) in changed_files
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
