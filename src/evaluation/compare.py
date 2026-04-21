"""Per-song comparison assembly and cross-song trend detection."""
from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from src.evaluation.models import MetricValue, SequenceSummary

CONSISTENCY_THRESHOLD = 0.80
REPORT_DIR = Path("tests/golden/reports")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_generator_commit() -> str:
    """Return the current git commit hash, or 'unknown' if git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _hash_manifest(manifest_path: Path) -> str:
    """Return md5:... hash of the manifest file."""
    digest = hashlib.md5(manifest_path.read_bytes()).hexdigest()
    return f"md5:{digest}"


def _import_all_metrics() -> None:
    """Import all metric modules to populate the registry."""
    import src.evaluation.metrics.pacing  # noqa: F401
    import src.evaluation.metrics.palette  # noqa: F401
    import src.evaluation.metrics.effects  # noqa: F401
    import src.evaluation.metrics.alignment  # noqa: F401
    import src.evaluation.metrics.sections  # noqa: F401
    import src.evaluation.metrics.internal  # noqa: F401


def _compute_metrics_for_summary(
    summary: SequenceSummary,
    audio_context: dict | None = None,
) -> list[MetricValue]:
    """Compute all registered metrics for a SequenceSummary."""
    from src.evaluation.metrics import get_registry

    if audio_context is None:
        audio_context = {}

    registry = get_registry()
    results: list[MetricValue] = []

    beats: list[int] = audio_context.get("beats", [])
    energy_curve = audio_context.get("energy_curve", [])
    sections = audio_context.get("sections", None)
    window_ms: int = audio_context.get("window_ms", 500)

    for name, defn in registry.items():
        try:
            if name == "placements_per_minute":
                mv = defn.compute(summary)
            elif name == "density_energy_correlation":
                mv = defn.compute(summary, {"energy_curve": energy_curve, "window_ms": window_ms})
            elif name == "palette_top5_colors":
                mv = defn.compute(summary)
            elif name == "per_section_palette_diversity":
                mv = defn.compute(summary, sections)
            elif name == "effect_type_histogram":
                mv = defn.compute(summary)
            elif name == "beat_alignment_pct":
                mv = defn.compute(summary, beats)
            elif name == "section_transition_delta":
                mv = defn.compute(summary, sections)
            elif name == "tier_utilization":
                mv = defn.compute(summary, sections)
            elif name == "theme_assignment_consistency":
                mv = defn.compute(summary, sections)
            else:
                mv = defn.compute(summary)
        except Exception as exc:
            mv = MetricValue(
                name=name,
                kind="scalar",
                value=None,
                payload={"error": str(exc)},
                reliability="reduced",
            )
        results.append(mv)

    return results


def _compute_intra_pro_variance(
    pro_entries: list[dict],
) -> dict | None:
    """Compute min/max/range per metric across ≥2 pro entries.

    Returns None if fewer than 2 pro entries have metrics.
    """
    if len(pro_entries) < 2:
        return None

    # Collect per-metric scalar values
    metric_values: dict[str, list[float]] = {}
    for entry in pro_entries:
        for mv_dict in entry.get("metrics", []):
            name = mv_dict.get("name", "")
            value = mv_dict.get("value")
            if value is not None:
                metric_values.setdefault(name, []).append(float(value))

    if not metric_values:
        return None

    variance: dict[str, dict] = {}
    for name, values in metric_values.items():
        if len(values) >= 2:
            lo = min(values)
            hi = max(values)
            variance[name] = {"min": lo, "max": hi, "range": hi - lo}

    return variance if variance else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_intra_pro_variance(
    pro_metrics_list: list[list[MetricValue]],
) -> dict | None:
    """Compute per-metric min/max/range across multiple pro takes.

    Args:
        pro_metrics_list: list of metric lists, one per pro take.

    Returns:
        Dict of metric_name → {"min": float, "max": float, "range": float},
        or None if < 2 pro takes.
    """
    if len(pro_metrics_list) < 2:
        return None

    metric_values: dict[str, list[float]] = {}
    for metrics in pro_metrics_list:
        for mv in metrics:
            if mv.value is not None:
                metric_values.setdefault(mv.name, []).append(float(mv.value))

    if not metric_values:
        return None

    variance: dict[str, dict] = {}
    for name, values in metric_values.items():
        if len(values) >= 2:
            lo = min(values)
            hi = max(values)
            variance[name] = {"min": lo, "max": hi, "range": hi - lo}

    return variance if variance else None


def annotate_delta_vs_variance(
    ours_value: float,
    pro_mean: float,
    variance: dict | None,
    metric_name: str,
) -> str:
    """Return 'within-variance', 'exceeds pro variance', or 'no-variance-data'.

    If variance is None (only 1 pro), return 'no-variance-data'.
    The within-variance check is inclusive: abs(ours - pro_mean) <= range / 2.
    """
    if variance is None or metric_name not in variance:
        return "no-variance-data"

    v = variance[metric_name]
    if v["min"] <= ours_value <= v["max"]:
        return "within-variance"
    return "exceeds pro variance"


def compare_song(
    song_id: str,
    pro_summaries: list[tuple[str, list[MetricValue]]],
    ours_metrics: list[MetricValue],
) -> dict:
    """Assemble the report entry dict for one song.

    Args:
        song_id: Corpus identifier.
        pro_summaries: List of (pro_id, list[MetricValue]) tuples.
        ours_metrics: Metric values computed from our generator output.

    Returns:
        Dict matching the Report.entries[*] schema.
    """
    pro_entries = [
        {
            "pro_id": pro_id,
            "metrics": [mv.to_dict() for mv in metrics],
        }
        for pro_id, metrics in pro_summaries
    ]

    intra_pro_variance = _compute_intra_pro_variance(pro_entries)

    return {
        "song_id": song_id,
        "pro_entries": pro_entries,
        "ours": {"metrics": [mv.to_dict() for mv in ours_metrics]},
        "intra_pro_variance": intra_pro_variance,
        "skips": [],
    }


def compute_cross_song_trends(
    song_comparisons: list[dict],
    registry: dict,
) -> list[dict]:
    """Detect cross-song trends for each pro_comparable metric.

    For each metric with pro_comparable=True, determine direction (ours>pro,
    ours<pro, or equal) on each song that has both sides, count how many
    songs share the dominant direction, and flag consistent_gap when
    agreement_count / total_comparable >= CONSISTENCY_THRESHOLD.

    Args:
        song_comparisons: List of report entry dicts (compare_song output).
        registry: Metric registry from get_registry().

    Returns:
        List of cross_song_trends dicts.
    """
    # Identify which metrics are pro_comparable
    pro_comparable_names = {
        name for name, defn in registry.items() if defn.pro_comparable
    }

    # Per metric: collect directions across songs
    # direction: "ours>pro", "ours<pro", "equal"
    metric_directions: dict[str, list[str]] = {}

    for entry in song_comparisons:
        pro_entries = entry.get("pro_entries", [])
        ours = entry.get("ours")

        if not pro_entries or ours is None:
            continue

        # Build lookup: metric_name -> ours value
        ours_by_name: dict[str, float | None] = {}
        for mv_dict in ours.get("metrics", []):
            ours_by_name[mv_dict["name"]] = mv_dict.get("value")

        # Build lookup: metric_name -> mean pro value across all pro entries
        pro_values_by_name: dict[str, list[float]] = {}
        for pro_entry in pro_entries:
            for mv_dict in pro_entry.get("metrics", []):
                name = mv_dict.get("name", "")
                value = mv_dict.get("value")
                if value is not None:
                    pro_values_by_name.setdefault(name, []).append(float(value))

        for name in pro_comparable_names:
            ours_val = ours_by_name.get(name)
            pro_vals = pro_values_by_name.get(name, [])

            if ours_val is None or not pro_vals:
                continue

            pro_mean = sum(pro_vals) / len(pro_vals)

            if ours_val > pro_mean:
                direction = "ours>pro"
            elif ours_val < pro_mean:
                direction = "ours<pro"
            else:
                direction = "equal"

            metric_directions.setdefault(name, []).append(direction)

    trends: list[dict] = []

    for metric_name, directions in metric_directions.items():
        if not directions:
            continue

        # Find the dominant direction
        counts: dict[str, int] = {}
        for d in directions:
            counts[d] = counts.get(d, 0) + 1

        dominant_dir, dominant_count = max(counts.items(), key=lambda x: x[1])
        total = len(directions)
        consistent = (dominant_count / total) >= CONSISTENCY_THRESHOLD

        trends.append({
            "metric": metric_name,
            "direction": dominant_dir,
            "songs_agreeing": dominant_count,
            "songs_total": total,
            "consistent_gap": consistent,
        })

    return trends


def build_audio_context(mp3_path: Path) -> dict:
    """Build audio context dict from the cached hierarchy analysis for an MP3.

    Pulls beats, sections, and L5 energy curve from the existing analysis
    cache (run_orchestrator with fresh=False uses cache when available).

    Returns a dict with keys:
        beats       : list[int]   — beat timestamps in ms
        energy_curve: list[tuple] — (time_ms, energy_float) pairs
        sections    : list[dict]  — {"start_ms", "end_ms", "label"} per section
        window_ms   : int         — window size for density computation (500ms)
    """
    from src.analyzer.orchestrator import run_orchestrator

    try:
        hierarchy = run_orchestrator(str(mp3_path), fresh=False)
    except Exception:
        return {"beats": [], "energy_curve": [], "sections": None, "window_ms": 500}

    # --- beats ---
    beats: list[int] = []
    if hierarchy.beats is not None:
        beats = [int(m.time_ms) for m in hierarchy.beats.marks]

    # --- energy curve (full_mix, normalised 0-100) ---
    energy_curve: list[tuple[int, float]] = []
    ec = hierarchy.energy_curves.get("full_mix")
    if ec is not None and ec.values and ec.fps > 0:
        ms_per_frame = 1000.0 / ec.fps
        energy_curve = [
            (int(i * ms_per_frame), float(v))
            for i, v in enumerate(ec.values)
        ]

    # --- sections: convert boundary marks to [start, end) windows ---
    sections: list[dict] = []
    duration_ms = int(hierarchy.duration_ms)
    if hierarchy.sections:
        marks = sorted(hierarchy.sections, key=lambda m: m.time_ms)
        for i, mark in enumerate(marks):
            start_ms = int(mark.time_ms)
            end_ms = int(marks[i + 1].time_ms) if i + 1 < len(marks) else duration_ms
            sections.append({
                "start_ms": start_ms,
                "end_ms": end_ms,
                "label": mark.label or f"section_{i}",
            })

    return {
        "beats": beats,
        "energy_curve": energy_curve,
        "sections": sections if sections else None,
        "window_ms": 500,
    }


def run_compare(
    corpus,
    song_ids: list[str] | None = None,
    audio_context_provider: Optional[Callable[[str, str], dict]] = None,
) -> dict:
    """Run full comparison: generate ours, compute metrics for both sides, assemble report.

    Args:
        corpus: A Corpus instance.
        song_ids: Optional list of song_ids to restrict to. None means all measurable.
        audio_context_provider: Optional callable (song_id, audio_hash) -> dict.
            If None, empty audio context is used.

    Returns:
        The full Report dict (not written to disk).
    """
    import src.evaluation.generator_runner as generator_runner
    from src.evaluation.metrics import get_registry
    from src.evaluation.xsq_reader import parse, parse_bytes

    _import_all_metrics()
    registry = get_registry()

    measurable = corpus.measurable_songs()
    if song_ids is not None:
        measurable = [s for s in measurable if s in song_ids]

    all_skips = corpus.skips()
    if song_ids is not None:
        all_skips = [s for s in all_skips if s.song_id in song_ids]

    entries: list[dict] = []
    songs_measured = 0
    songs_skipped_our_side = 0

    # Corpus-side skip entries (songs that never made it into measurable)
    corpus_skip_song_ids: set[str] = set()
    for skip in all_skips:
        corpus_skip_song_ids.add(skip.song_id)

    # Build corpus-side skip entry if we have any
    for skip in all_skips:
        # Deduplicate per song_id — only emit one entry per song
        existing = next(
            (e for e in entries if e["song_id"] == skip.song_id),
            None,
        )
        if existing is None:
            entries.append({
                "song_id": skip.song_id,
                "pro_entries": [],
                "ours": None,
                "intra_pro_variance": None,
                "skips": [
                    {
                        "pro_id": skip.pro_id,
                        "reason": skip.reason,
                        "category": skip.category,
                    }
                ],
            })
        else:
            existing["skips"].append({
                "pro_id": skip.pro_id,
                "reason": skip.reason,
                "category": skip.category,
            })

    our_side_errors: list[str] = []

    for song_id in measurable:
        mp3_path = corpus.mp3_path_for_song(song_id)
        audio_hash = corpus.audio_hash_for_song(song_id)

        # Build audio context — use provider if given, else load from cache
        if audio_context_provider is not None:
            audio_context = audio_context_provider(song_id, audio_hash)
        elif mp3_path is not None:
            try:
                audio_context = build_audio_context(mp3_path)
            except Exception:
                audio_context = {
                    "beats": [],
                    "energy_curve": [],
                    "sections": None,
                    "window_ms": 500,
                }
        else:
            audio_context = {
                "beats": [],
                "energy_curve": [],
                "sections": None,
                "window_ms": 500,
            }

        # Run generator for our output
        try:
            xsq_bytes = generator_runner.run(
                song_id=song_id,
                audio_path=mp3_path,
                audio_hash=audio_hash,
            )
        except generator_runner.GeneratorError as exc:
            our_side_errors.append(f"{song_id}: {exc}")
            songs_skipped_our_side += 1
            # Record as our-side skip entry
            pro_entries_for_song = corpus.entries_for_song(song_id)
            song_entry = {
                "song_id": song_id,
                "pro_entries": [],
                "ours": None,
                "intra_pro_variance": None,
                "skips": [
                    {
                        "pro_id": e.pro_id,
                        "reason": "generator_error",
                        "category": "our-side",
                    }
                    for e in pro_entries_for_song
                ],
            }
            entries.append(song_entry)
            continue

        # Parse ours
        ours_summary = parse_bytes(
            xsq_bytes, song_id=song_id, source_label="ours"
        )
        ours_metrics = _compute_metrics_for_summary(ours_summary, audio_context)

        # Parse and compute metrics for each pro entry
        pro_summaries: list[tuple[str, list[MetricValue]]] = []
        pro_manifest_entries = corpus.entries_for_song(song_id)
        pro_parse_skips: list[dict] = []
        _AUDIO_DEPENDENT_METRICS = {
            "beat_alignment_pct",
            "section_transition_delta",
            "per_section_palette_diversity",
        }
        for manifest_entry in pro_manifest_entries:
            try:
                pro_summary = parse(
                    manifest_entry.xsq_path,
                    song_id=song_id,
                    source_label=f"pro:{manifest_entry.pro_id}",
                )
                pro_metrics = _compute_metrics_for_summary(pro_summary, audio_context)
                # Propagate reduced reliability for audio-dependent metrics when
                # master_may_differ is set (audio used to generate pro differs from ours)
                if manifest_entry.master_may_differ:
                    pro_metrics = [
                        MetricValue(
                            name=mv.name,
                            kind=mv.kind,
                            value=mv.value,
                            payload=mv.payload,
                            reliability="reduced",
                        )
                        if mv.name in _AUDIO_DEPENDENT_METRICS
                        else mv
                        for mv in pro_metrics
                    ]
                pro_summaries.append((manifest_entry.pro_id, pro_metrics))
            except Exception as exc:
                # Pro xsq parse failure — corpus-side skip for this pro entry
                pro_parse_skips.append({
                    "pro_id": manifest_entry.pro_id,
                    "reason": "pro_unparseable",
                    "category": "corpus-side",
                })

        song_entry = compare_song(
            song_id=song_id,
            pro_summaries=pro_summaries,
            ours_metrics=ours_metrics,
        )
        song_entry["skips"].extend(pro_parse_skips)
        entries.append(song_entry)
        songs_measured += 1

    # Compute cross-song trends from measured entries only
    measured_entries = [e for e in entries if e.get("ours") is not None]
    trends = compute_cross_song_trends(measured_entries, registry)

    # Count skips
    songs_skipped_corpus_side = len(corpus_skip_song_ids)
    # If filtered by song_ids, only count corpus skips in that filter
    if song_ids is not None:
        songs_skipped_corpus_side = len(
            corpus_skip_song_ids & set(song_ids)
        )

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator_commit": _get_generator_commit(),
        "corpus_manifest_hash": "",  # filled in by CLI with actual manifest path
        "entries": entries,
        "cross_song_trends": trends,
        "summary": {
            "songs_measured": songs_measured,
            "songs_skipped_corpus_side": songs_skipped_corpus_side,
            "songs_skipped_our_side": songs_skipped_our_side,
            "ci_status": "pass" if not our_side_errors else "fail-generator-error",
        },
        "_our_side_errors": our_side_errors,  # consumed by CLI, not written to report
    }

    return report


def render_terminal_summary(report: dict, corpus_dir: str = "") -> str:
    """Render a human-readable terminal summary from a report dict.

    Produces formatted output matching the contract specification.
    """
    lines: list[str] = []
    lines.append("xLights Quality Calibration — compare")

    entries = report.get("entries", [])
    measured_entries = [e for e in entries if e.get("ours") is not None]
    skipped_entries = [e for e in entries if e.get("ours") is None]

    # Count total pro sequences across measured entries
    total_pro_seqs = sum(len(e.get("pro_entries", [])) for e in measured_entries)
    total_songs = len(measured_entries) + len(skipped_entries)

    summary = report.get("summary", {})
    songs_measured = summary.get("songs_measured", 0)
    songs_skipped_corpus = summary.get("songs_skipped_corpus_side", 0)
    songs_skipped_our_side = summary.get("songs_skipped_our_side", 0)

    corpus_label = corpus_dir or "tests/golden/pro_reference"
    lines.append(
        f"  Corpus: {corpus_label} ({total_songs} songs, {total_pro_seqs} pro sequences)"
    )

    total_skipped = songs_skipped_corpus + songs_skipped_our_side
    if songs_skipped_our_side > 0:
        skip_detail = f"{songs_skipped_corpus} corpus-side, {songs_skipped_our_side} our-side"
        skip_str = f"{total_skipped} ({skip_detail})"
    else:
        skip_str = f"{songs_skipped_corpus} (corpus-side)"
    lines.append(f"  Measured: {songs_measured} songs   Skipped: {skip_str}")
    lines.append("")

    for entry in measured_entries:
        song_id = entry["song_id"]
        pro_entries = entry.get("pro_entries", [])
        ours = entry.get("ours", {})
        intra_var = entry.get("intra_pro_variance") or {}

        lines.append(f"Song: {song_id}  ({len(pro_entries)} pro takes)")

        # Build header
        header = f"  {'metric':<36} {'pro(min..max)':<18} {'ours':<10} {'Δ-vs-pro-mean'}"
        lines.append(header)

        if not pro_entries or not ours:
            lines.append("  (no data)")
            lines.append("")
            continue

        # Compute pro mean and range per metric
        pro_by_metric: dict[str, list[float]] = {}
        for pe in pro_entries:
            for mv_dict in pe.get("metrics", []):
                name = mv_dict.get("name", "")
                value = mv_dict.get("value")
                if value is not None:
                    pro_by_metric.setdefault(name, []).append(float(value))

        ours_by_metric: dict[str, float | None] = {}
        for mv_dict in ours.get("metrics", []):
            ours_by_metric[mv_dict["name"]] = mv_dict.get("value")

        for name in sorted(pro_by_metric.keys()):
            pro_vals = pro_by_metric[name]
            ours_val = ours_by_metric.get(name)

            if not pro_vals:
                continue

            pro_min = min(pro_vals)
            pro_max = max(pro_vals)
            pro_mean = sum(pro_vals) / len(pro_vals)

            # Show range only when multiple pro takes exist for this metric
            if len(pro_vals) >= 2:
                pro_range_str = f"{pro_min:.1f} .. {pro_max:.1f}"
            else:
                pro_range_str = f"{pro_min:.1f}"

            ours_str = f"{ours_val:.1f}" if ours_val is not None else "N/A"

            if ours_val is not None and pro_mean != 0:
                delta_pct = (ours_val - pro_mean) / abs(pro_mean) * 100
                delta_str = f"{delta_pct:+.0f}%"
                # Annotate vs intra-pro variance when available
                annotation = annotate_delta_vs_variance(
                    ours_value=ours_val,
                    pro_mean=pro_mean,
                    variance=intra_var if intra_var else None,
                    metric_name=name,
                )
                if annotation == "exceeds pro variance":
                    delta_str += "  ⚠ exceeds pro variance"
                elif annotation == "within-variance":
                    delta_str += "  within-variance"
                # "no-variance-data" → no suffix (single pro, no range to compare against)
            else:
                delta_str = "N/A"

            lines.append(
                f"  {name:<36} {pro_range_str:<18} {ours_str:<10} {delta_str}"
            )

        lines.append("")

    # Cross-song trends
    trends = report.get("cross_song_trends", [])
    consistent_trends = [t for t in trends if t.get("consistent_gap")]

    lines.append(f"Cross-song trends (≥{int(CONSISTENCY_THRESHOLD * 100)}% consistent):")
    if consistent_trends:
        for trend in consistent_trends:
            metric = trend["metric"]
            direction = trend["direction"]
            agreeing = trend["songs_agreeing"]
            total = trend["songs_total"]
            lines.append(f"  {metric}: {direction} on {agreeing}/{total} songs  (consistent gap)")
    else:
        lines.append("  (none)")

    return "\n".join(lines)
