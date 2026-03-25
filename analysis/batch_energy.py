#!/usr/bin/env python3
"""
Run bbc_energy directly on MP3s and validate energy impact assumptions.

Bypasses the JSON export issue — reads raw energy values from the Vamp plugin.

Usage: python analysis/batch_energy.py /path/to/mp3s
"""
from __future__ import annotations

import sys
from pathlib import Path

import librosa
import numpy as np
import vamp


# Thresholds from the design doc
IMPACT_RATIO = 1.8    # >1.8x = energy impact
DROP_RATIO = 0.55     # <0.55x = energy drop
SILENCE_THRESHOLD = 5  # energy value (0-100) below which we call it silence
SILENCE_DURATION_MS = 300
WINDOW_MS = 1000       # 1-second windows for impact detection


def analyze_energy(mp3_path: str) -> dict:
    """Load audio, run bbc_energy, analyze the raw curve."""
    y, sr = librosa.load(mp3_path, mono=True)
    duration_s = len(y) / sr

    # Run BBC energy plugin
    outputs = vamp.collect(y, sr, "bbc-vamp-plugins:bbc-energy")

    # Extract the curve
    vectors = outputs.get("vector")
    if vectors is None or len(vectors) < 2:
        return {"status": "NO_OUTPUT", "duration_s": round(duration_s, 1)}

    timestamps, values = vectors
    arr = np.array(values, dtype=np.float64)
    if arr.ndim > 1:
        arr = arr.mean(axis=1) if arr.shape[0] > arr.shape[1] else arr.mean(axis=0)

    # Normalize to 0-100
    vmin, vmax = float(arr.min()), float(arr.max())
    if vmax - vmin < 1e-9:
        return {"status": "FLAT", "duration_s": round(duration_s, 1)}
    curve = ((arr - vmin) / (vmax - vmin) * 100)

    # Frame rate (~50ms per frame from BBC plugin)
    frame_ms = (duration_s * 1000) / len(curve) if len(curve) > 0 else 50
    frames_per_window = max(1, int(WINDOW_MS / frame_ms))

    # Compute windowed RMS energy (1-second windows)
    n_windows = len(curve) // frames_per_window
    if n_windows < 2:
        return {"status": "TOO_SHORT", "duration_s": round(duration_s, 1)}

    window_energies = []
    for i in range(n_windows):
        chunk = curve[i * frames_per_window:(i + 1) * frames_per_window]
        window_energies.append(float(np.mean(chunk)))

    # Count energy impacts and drops
    impacts = 0
    drops = 0
    for i in range(1, len(window_energies)):
        prev = window_energies[i - 1]
        curr = window_energies[i]
        if prev > 1.0:  # avoid division by near-zero
            ratio = curr / prev
            if ratio > IMPACT_RATIO:
                impacts += 1
            elif ratio < DROP_RATIO:
                drops += 1

    # Count silence gaps
    gaps = 0
    silent_frames = 0
    for v in curve:
        if v < SILENCE_THRESHOLD:
            silent_frames += 1
        else:
            if silent_frames * frame_ms >= SILENCE_DURATION_MS:
                gaps += 1
            silent_frames = 0

    # Dynamic range
    dyn_range = (vmax - vmin) / max(abs(vmax), 0.001)

    # Energy statistics
    mean_energy = float(np.mean(curve))
    std_energy = float(np.std(curve))

    return {
        "status": "OK",
        "duration_s": round(duration_s, 1),
        "frames": len(curve),
        "frame_ms": round(frame_ms, 1),
        "mean_energy": round(mean_energy, 1),
        "std_energy": round(std_energy, 1),
        "dynamic_range": round(dyn_range, 3),
        "energy_impacts": impacts,
        "energy_drops": drops,
        "total_events": impacts + drops,
        "gaps": gaps,
    }


def main():
    songs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/Users/rob/mp3")
    mp3s = sorted(songs_dir.glob("*.mp3"))

    if not mp3s:
        print(f"No MP3s found in {songs_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"{'SONG':<38} {'DUR':<6} {'MEAN':<6} {'STD':<6} {'DYN':<6} "
          f"{'IMPACTS':<9} {'DROPS':<7} {'TOTAL':<7} {'GAPS':<5}")
    print("-" * 95)

    all_results = []
    for mp3 in mp3s:
        name = mp3.stem[:36]
        try:
            result = analyze_energy(str(mp3))
            all_results.append((name, result))

            if result["status"] != "OK":
                print(f"{name:<38} {result.get('duration_s', '?'):<6} — {result['status']}")
                continue

            print(f"{name:<38} {result['duration_s']:<6} "
                  f"{result['mean_energy']:<6} {result['std_energy']:<6} "
                  f"{result['dynamic_range']:<6} "
                  f"{result['energy_impacts']:<9} {result['energy_drops']:<7} "
                  f"{result['total_events']:<7} {result['gaps']:<5}")
        except Exception as exc:
            print(f"{name:<38} ERROR: {exc}")
            all_results.append((name, {"status": "ERROR", "error": str(exc)}))

    # Summary
    ok_results = [r for _, r in all_results if r.get("status") == "OK"]
    if ok_results:
        print(f"\n{'=' * 95}")
        print(f"SUMMARY ({len(ok_results)} songs)")
        print(f"{'=' * 95}")

        has_impacts = sum(1 for r in ok_results if r["energy_impacts"] > 0)
        has_drops = sum(1 for r in ok_results if r["energy_drops"] > 0)
        has_events = sum(1 for r in ok_results if r["total_events"] > 0)
        has_gaps = sum(1 for r in ok_results if r["gaps"] > 0)

        impact_counts = [r["energy_impacts"] for r in ok_results]
        drop_counts = [r["energy_drops"] for r in ok_results]
        total_counts = [r["total_events"] for r in ok_results]
        dyn_ranges = [r["dynamic_range"] for r in ok_results]

        print(f"\nEnergy impacts (>1.8x in 1s window):")
        print(f"  Songs with impacts: {has_impacts}/{len(ok_results)}")
        print(f"  Range: {min(impact_counts)}-{max(impact_counts)}, mean: {sum(impact_counts)/len(impact_counts):.1f}")

        print(f"\nEnergy drops (<0.55x in 1s window):")
        print(f"  Songs with drops: {has_drops}/{len(ok_results)}")
        print(f"  Range: {min(drop_counts)}-{max(drop_counts)}, mean: {sum(drop_counts)/len(drop_counts):.1f}")

        print(f"\nTotal energy events (impacts + drops):")
        print(f"  Songs with any event: {has_events}/{len(ok_results)}")
        print(f"  Range: {min(total_counts)}-{max(total_counts)}, mean: {sum(total_counts)/len(total_counts):.1f}")

        print(f"\nGaps (silence > 300ms):")
        print(f"  Songs with gaps: {has_gaps}/{len(ok_results)}")

        print(f"\nDynamic range:")
        print(f"  Range: {min(dyn_ranges):.3f}-{max(dyn_ranges):.3f}, mean: {sum(dyn_ranges)/len(dyn_ranges):.3f}")

        # Verdict
        pct = has_events / len(ok_results) * 100
        print(f"\nVERDICT: Energy events detected in {pct:.0f}% of songs")
        if pct >= 80:
            print("  -> CONFIRMED: energy impacts are universal for this song set")
        else:
            no_events = [name for name, r in all_results if r.get("status") == "OK" and r["total_events"] == 0]
            print(f"  -> NEEDS REVIEW: {len(no_events)} songs with no energy events:")
            for n in no_events:
                print(f"     {n}")


if __name__ == "__main__":
    main()
