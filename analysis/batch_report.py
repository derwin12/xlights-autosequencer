#!/usr/bin/env python3
"""
Read batch analysis results and check assumptions from musical-analysis-design.md.

Usage: python analysis/batch_report.py [results_dir]
       Defaults to analysis/batch_results/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


# ── Thresholds from the design doc ────────────────────────────────────────────
ENERGY_IMPACT_RATIO = 1.8       # >1.8x = impact
ENERGY_DROP_RATIO = 0.55        # <0.55x = drop
SILENCE_RMS = 0.01              # RMS below this = silence
SILENCE_DURATION_MS = 300       # silence must last this long
EXPECTED_BEAT_FREQ = (1.5, 3.0) # beats per second
EXPECTED_BAR_FREQ = (0.3, 0.8)  # bars per second
EXPECTED_ONSET_DENSITY = (1.0, 5.0)  # onsets/s — reasonable range for lighting


def load_results(results_dir: Path) -> list[dict]:
    results = []
    # Search recursively — CLI creates <song_name>/<song_name>_analysis.json subfolders
    for f in sorted(results_dir.rglob("*_analysis.json")):
        try:
            data = json.loads(f.read_text())
            data["_file"] = str(f)
            results.append(data)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARNING: skipping {f.name}: {exc}", file=sys.stderr)
    return results


def get_track(data: dict, name: str) -> dict | None:
    for t in data.get("timing_tracks", []):
        if t.get("name") == name:
            return t
    return None


def analyze_energy(data: dict) -> dict:
    """Check energy dynamics using mark density in time windows.

    bbc_energy marks are evenly spaced timestamps (no value field stored).
    We can still detect dynamics by looking at whether the track exists and
    its density characteristics. The actual energy values aren't preserved
    in the JSON export — this is the 'misclassified as timing marks' issue
    noted in the design doc.
    """
    track = get_track(data, "bbc_energy")
    if not track:
        return {"status": "MISSING", "note": "bbc_energy track not found"}

    marks = track.get("marks", [])
    if not marks:
        return {"status": "MISSING", "note": "no marks in bbc_energy"}

    mark_count = track.get("mark_count", len(marks))
    avg_interval = track.get("avg_interval_ms", 0)
    density = track.get("quality_score", 0)

    # Detect gaps in the mark stream — if bbc_energy has gaps > 500ms
    # between marks (normally 50ms apart), that indicates silence
    gaps = 0
    for i in range(1, len(marks)):
        delta = marks[i].get("time_ms", 0) - marks[i - 1].get("time_ms", 0)
        if delta > 500:  # 10x the normal 50ms interval
            gaps += 1

    return {
        "status": "OK",
        "mark_count": mark_count,
        "avg_interval_ms": avg_interval,
        "gaps": gaps,
        "note": "energy values not in export — impacts require raw audio re-analysis",
    }


def analyze_bars(data: dict) -> dict:
    """Check beat/bar frequency."""
    track = get_track(data, "qm_bars")
    if not track:
        return {"status": "MISSING", "note": "qm_bars track not found"}

    marks = track.get("marks", [])
    if len(marks) < 2:
        return {"status": "LOW_DATA", "note": f"only {len(marks)} bar marks"}

    duration_ms = data.get("duration_ms", 0)
    if duration_ms <= 0 and marks:
        duration_ms = marks[-1].get("time_ms", 0)
    duration_s = duration_ms / 1000.0

    mark_count = track.get("mark_count", len(marks))
    avg_interval = track.get("avg_interval_ms", 0)
    freq = mark_count / duration_s if duration_s > 0 else 0

    in_range = EXPECTED_BAR_FREQ[0] <= freq <= EXPECTED_BAR_FREQ[1]

    return {
        "status": "OK" if in_range else "OUT_OF_RANGE",
        "mark_count": mark_count,
        "duration_s": round(duration_s, 1),
        "frequency_hz": round(freq, 3),
        "avg_interval_ms": avg_interval,
        "expected_range": f"{EXPECTED_BAR_FREQ[0]}-{EXPECTED_BAR_FREQ[1]} Hz",
    }


def analyze_segmentino(data: dict) -> dict:
    """Check section structure and repeat labels."""
    track = get_track(data, "segmentino")
    if not track:
        return {"status": "MISSING", "note": "segmentino track not found"}

    marks = track.get("marks", [])
    if not marks:
        return {"status": "MISSING", "note": "no segmentino marks"}

    # Count distinct labels and their frequencies
    labels: dict[str, int] = {}
    for m in marks:
        label = m.get("label", "?")
        labels[label] = labels.get(label, 0) + 1

    section_count = len(marks)
    unique_labels = len(labels)
    has_repeats = any(v > 1 for v in labels.values())
    repeat_labels = {k: v for k, v in labels.items() if v > 1}

    return {
        "status": "OK",
        "section_count": section_count,
        "unique_labels": unique_labels,
        "has_repeats": has_repeats,
        "label_counts": labels,
        "repeat_labels": repeat_labels,
    }


def analyze_onsets(data: dict) -> dict:
    """Check onset density."""
    track = get_track(data, "aubio_onset")
    if not track:
        return {"status": "MISSING", "note": "aubio_onset track not found"}

    marks = track.get("marks", [])
    if len(marks) < 2:
        return {"status": "LOW_DATA", "note": f"only {len(marks)} onset marks"}

    duration_ms = data.get("duration_ms", 0)
    if duration_ms <= 0 and marks:
        duration_ms = marks[-1].get("time_ms", 0)
    duration_s = duration_ms / 1000.0

    mark_count = track.get("mark_count", len(marks))
    avg_interval = track.get("avg_interval_ms", 0)
    freq = mark_count / duration_s if duration_s > 0 else 0

    in_range = EXPECTED_ONSET_DENSITY[0] <= freq <= EXPECTED_ONSET_DENSITY[1]
    density_note = ""
    if freq > EXPECTED_ONSET_DENSITY[1]:
        density_note = "TOO DENSE for lighting"
    elif freq < EXPECTED_ONSET_DENSITY[0]:
        density_note = "very sparse"

    return {
        "status": "OK" if in_range else "OUT_OF_RANGE",
        "mark_count": mark_count,
        "duration_s": round(duration_s, 1),
        "frequency_hz": round(freq, 2),
        "avg_interval_ms": avg_interval,
        "expected_range": f"{EXPECTED_ONSET_DENSITY[0]}-{EXPECTED_ONSET_DENSITY[1]} /s",
        "note": density_note,
    }


def print_report(results: list[dict]) -> None:
    """Print the validation report."""
    print("=" * 90)
    print("BATCH ANALYSIS REPORT — Design Doc Validation")
    print(f"Songs analyzed: {len(results)}")
    print("=" * 90)

    # ── Summary table ─────────────────────────────────────────────────────────
    print(f"\n{'SONG':<35} {'GAPS':<6} {'BAR Hz':<9} {'SEGMENTS':<10} {'REPEATS':<9} {'ONSET/s':<9}")
    print("-" * 80)

    all_energy = []
    all_bars = []
    all_segments = []
    all_onsets = []

    for data in results:
        name = Path(data["_file"]).stem.replace("_analysis", "")[:33]

        energy = analyze_energy(data)
        bars = analyze_bars(data)
        seg = analyze_segmentino(data)
        onsets = analyze_onsets(data)

        all_energy.append(energy)
        all_bars.append(bars)
        all_segments.append(seg)
        all_onsets.append(onsets)

        # Format cells
        gaps = energy.get("gaps", "?")

        bar_hz = bars.get("frequency_hz", "?")
        if isinstance(bar_hz, float):
            bar_flag = "" if bars["status"] == "OK" else " !"
            bar_hz = f"{bar_hz:.2f}{bar_flag}"

        seg_count = seg.get("section_count", "?")
        has_rep = "yes" if seg.get("has_repeats") else "NO"

        onset_hz = onsets.get("frequency_hz", "?")
        if isinstance(onset_hz, float):
            onset_flag = ""
            if onsets["status"] == "OUT_OF_RANGE":
                onset_flag = " !"
            onset_hz = f"{onset_hz:.1f}{onset_flag}"

        print(f"{name:<35} {str(gaps):<6} {str(bar_hz):<9} {str(seg_count):<10} "
              f"{has_rep:<9} {str(onset_hz):<9}")

    # ── Assumption checks ─────────────────────────────────────────────────────
    print("\n" + "=" * 90)
    print("DESIGN DOC ASSUMPTION CHECKS")
    print("=" * 90)

    # 1. Energy analysis note
    total_valid = sum(1 for e in all_energy if e.get("status") == "OK")
    print(f"\n1. 'Energy impacts are universal'")
    print(f"   CANNOT VALIDATE — bbc_energy marks don't store values in JSON export.")
    print(f"   This confirms the doc's finding: bbc_energy is misclassified as timing marks.")
    print(f"   To validate energy impacts, we need to re-run with raw value extraction.")

    # 2. Bars at ~0.5/s
    bars_in_range = sum(1 for b in all_bars if b.get("status") == "OK")
    bars_valid = sum(1 for b in all_bars if b.get("status") in ("OK", "OUT_OF_RANGE"))
    print(f"\n2. 'Bar detection at ~0.5/s'")
    print(f"   In range ({EXPECTED_BAR_FREQ[0]}-{EXPECTED_BAR_FREQ[1]} Hz): {bars_in_range}/{bars_valid}")
    out_of_range = [b for b in all_bars if b.get("status") == "OUT_OF_RANGE"]
    for b in out_of_range:
        print(f"   ! Out of range: {b.get('frequency_hz')} Hz (avg interval: {b.get('avg_interval_ms')}ms)")

    # 3. Segmentino repeat labels
    songs_with_repeats = sum(1 for s in all_segments if s.get("has_repeats"))
    seg_valid = sum(1 for s in all_segments if s.get("status") == "OK")
    print(f"\n3. 'Segmentino repeat labels are useful'")
    print(f"   Songs with repeating sections: {songs_with_repeats}/{seg_valid}")
    if seg_valid > 0:
        pct = songs_with_repeats / seg_valid * 100
        print(f"   Result: {'CONFIRMED' if pct >= 80 else 'NEEDS REVIEW'} ({pct:.0f}%)")
    # Show the songs without repeats
    no_repeats = [(Path(results[i]["_file"]).stem.replace("_analysis", ""), all_segments[i])
                  for i in range(len(results)) if not all_segments[i].get("has_repeats") and all_segments[i].get("status") == "OK"]
    for name, seg in no_repeats:
        print(f"   ! No repeats: {name} ({seg.get('section_count')} sections, labels: {seg.get('label_counts')})")

    # 4. Gaps (from bbc_energy mark stream irregularities)
    songs_with_gaps = sum(1 for e in all_energy if e.get("gaps", 0) > 0)
    print(f"\n4. 'Gaps are genre-dependent'")
    print(f"   Songs with gaps (>500ms breaks in energy stream): {songs_with_gaps}/{total_valid}")
    if songs_with_gaps > 0:
        gap_songs = [(Path(results[i]["_file"]).stem.replace("_analysis", ""), all_energy[i].get("gaps", 0))
                     for i in range(len(results)) if all_energy[i].get("gaps", 0) > 0]
        for name, g in gap_songs:
            print(f"   {name}: {g} gaps")

    # 6. Onset density
    onset_freqs = [o["frequency_hz"] for o in all_onsets if isinstance(o.get("frequency_hz"), float)]
    if onset_freqs:
        print(f"\n6. 'Onset density in usable range'")
        print(f"   Range: {min(onset_freqs):.1f} - {max(onset_freqs):.1f} /s")
        too_dense = sum(1 for f in onset_freqs if f > EXPECTED_ONSET_DENSITY[1])
        too_sparse = sum(1 for f in onset_freqs if f < EXPECTED_ONSET_DENSITY[0])
        in_range = len(onset_freqs) - too_dense - too_sparse
        print(f"   In range: {in_range}, too dense: {too_dense}, too sparse: {too_sparse}")
        if too_dense:
            print(f"   ! {too_dense} song(s) with onset density > {EXPECTED_ONSET_DENSITY[1]}/s — needs sensitivity tuning")

    # ── Per-song detail (for songs with issues) ───────────────────────────────
    problem_songs = []
    for i, data in enumerate(results):
        issues = []
        if all_bars[i].get("status") == "OUT_OF_RANGE":
            issues.append(f"bars: {all_bars[i].get('frequency_hz')} Hz")
        if all_segments[i].get("status") != "OK":
            issues.append(f"segments: {all_segments[i].get('status')}")
        if not all_segments[i].get("has_repeats") and all_segments[i].get("status") == "OK":
            issues.append(f"no repeating sections ({all_segments[i].get('section_count')} segments)")
        if all_onsets[i].get("status") == "OUT_OF_RANGE":
            issues.append(f"onsets: {all_onsets[i].get('frequency_hz')}/s — {'too dense' if all_onsets[i].get('frequency_hz', 0) > EXPECTED_ONSET_DENSITY[1] else 'too sparse'}")
        if issues:
            name = Path(data["_file"]).stem.replace("_analysis", "")
            problem_songs.append((name, issues))

    if problem_songs:
        print(f"\n{'=' * 90}")
        print("SONGS WITH ISSUES (may need deeper investigation)")
        print("=" * 90)
        for name, issues in problem_songs:
            print(f"\n  {name}:")
            for issue in issues:
                print(f"    - {issue}")

    # ── Write detailed JSON ───────────────────────────────────────────────────
    report_path = Path(results[0]["_file"]).parent if results else Path(".")
    # Use the results dir passed in, not the file's own path
    detail = {
        "summary": {
            "songs_analyzed": len(results),
            "energy_needs_revalidation": True,  # bbc_energy values not in export
            "bars_all_in_range": bars_in_range == bars_valid,
            "segmentino_repeats_universal": songs_with_repeats == seg_valid,
        },
        "per_song": {},
    }
    for i, data in enumerate(results):
        name = Path(data["_file"]).stem.replace("_analysis", "")
        detail["per_song"][name] = {
            "energy": all_energy[i],
            "bars": all_bars[i],
            "segments": all_segments[i],
            "onsets": all_onsets[i],
        }

    print(f"\n\nDetailed results written to: batch_validation_report.json")
    return detail


def main():
    results_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("analysis/batch_results")
    if not results_dir.exists():
        print(f"ERROR: Directory not found: {results_dir}", file=sys.stderr)
        print(f"Usage: python analysis/batch_report.py /path/to/songs", file=sys.stderr)
        print(f"  (point at the directory containing MP3s or analysis subfolders)", file=sys.stderr)
        sys.exit(1)

    results = load_results(results_dir)
    if not results:
        print(f"ERROR: No *_analysis.json files found in {results_dir} (searched recursively)", file=sys.stderr)
        print(f"Run batch_analyze.sh first.", file=sys.stderr)
        sys.exit(1)

    detail = print_report(results)

    # Write detailed report next to this script
    report_path = Path(__file__).parent / "batch_validation_report.json"
    report_path.write_text(json.dumps(detail, indent=2))
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
