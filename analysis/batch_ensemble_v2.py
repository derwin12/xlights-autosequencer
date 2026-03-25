#!/usr/bin/env python3
"""
Ensemble segmentation v2: Segmentino primary + Chordino harmonic change supplementary.

Instead of consensus voting, uses Segmentino as the backbone and Chordino
harmonic change peaks to subdivide long Segmentino sections.

Usage: python analysis/batch_ensemble_v2.py /path/to/mp3s [min_section_s]
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import librosa
import numpy as np
import vamp


@dataclass
class Section:
    start_ms: int
    end_ms: int
    label: str
    source: str  # "segmentino" or "harmonic_split"
    duration_ms: int = 0
    harmonic_peaks_inside: int = 0  # how many harmonic peaks fall inside this section

    def __post_init__(self):
        self.duration_ms = self.end_ms - self.start_ms


def run_segmentino(y: np.ndarray, sr: int) -> list[Section]:
    out = vamp.collect(y, sr, "segmentino:segmentino")
    items = out.get("list", [])
    sections = []
    for item in items:
        ts = float(item["timestamp"])
        dur = float(item.get("duration", 0))
        label = item.get("label", "?")
        sections.append(Section(
            start_ms=int(round(ts * 1000)),
            end_ms=int(round((ts + dur) * 1000)),
            label=label,
            source="segmentino",
        ))
    return sections


def get_harmonic_peaks(y: np.ndarray, sr: int, percentile: float = 99,
                       min_dist_s: float = 8.0) -> list[tuple[int, float]]:
    """Get significant harmonic change peaks as (time_ms, value) pairs."""
    out = vamp.collect(y, sr, "nnls-chroma:chordino", output="harmonicchange")
    if "vector" not in out:
        return []

    _, vals = out["vector"]
    vals = np.array(vals, dtype=np.float64)
    if len(vals) < 10:
        return []

    duration_s = len(y) / sr
    frame_s = duration_s / len(vals)
    threshold = np.percentile(vals, percentile)

    above = np.where(vals > threshold)[0]
    min_dist_frames = int(min_dist_s / frame_s)

    peaks = []
    last = -min_dist_frames
    for idx in above:
        if idx - last >= min_dist_frames:
            t_ms = int(round(idx * frame_s * 1000))
            peaks.append((t_ms, float(vals[idx])))
            last = idx

    return peaks


def augment_sections(sections: list[Section], harmonic_peaks: list[tuple[int, float]],
                     min_section_ms: int) -> list[Section]:
    """Add harmonic change peaks as subdivision boundaries inside long sections."""
    if not sections or not harmonic_peaks:
        return sections

    result = []
    for sec in sections:
        # Count harmonic peaks inside this section (for reporting)
        peaks_inside = [(t, v) for t, v in harmonic_peaks
                        if sec.start_ms + 2000 < t < sec.end_ms - 2000]  # 2s margin
        sec.harmonic_peaks_inside = len(peaks_inside)

        # Only subdivide sections longer than min_section_ms
        if sec.duration_ms < min_section_ms or not peaks_inside:
            result.append(sec)
            continue

        # Split this section at harmonic peak positions
        boundaries = [sec.start_ms] + [t for t, _ in peaks_inside] + [sec.end_ms]
        for i in range(len(boundaries) - 1):
            sub_start = boundaries[i]
            sub_end = boundaries[i + 1]
            if sub_end - sub_start < 3000:  # don't create sections < 3s
                continue
            source = "segmentino" if i == 0 and len(peaks_inside) == 0 else (
                "segmentino" if sub_start == sec.start_ms else "harmonic_split"
            )
            result.append(Section(
                start_ms=sub_start,
                end_ms=sub_end,
                label=sec.label + ("'" if source == "harmonic_split" else ""),
                source=source,
            ))

    return result


def main():
    songs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/Users/rob/mp3")
    min_section_s = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0
    min_section_ms = int(min_section_s * 1000)

    mp3s = sorted(songs_dir.glob("*.mp3"))
    if not mp3s:
        print(f"No MP3s found in {songs_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Ensemble v2: Segmentino + Chordino harmonic change")
    print(f"Min section for subdivision: {min_section_s}s")
    print("=" * 115)
    print(f"{'SONG':<35} {'DUR':<5} {'SEG':<4} {'H.PK':<5} {'FINAL':<6} "
          f"{'SPLIT':<6} {'LABELS':<25} {'LONG SECTIONS (>15s)'}")
    print("-" * 115)

    total_original = 0
    total_final = 0
    total_splits = 0
    total_harmonic_peaks = 0
    songs_with_splits = 0

    for mp3 in mp3s:
        name = mp3.stem[:33]
        try:
            y, sr = librosa.load(str(mp3), mono=True)
            duration_s = len(y) / sr

            sections = run_segmentino(y, sr)
            harmonic_peaks = get_harmonic_peaks(y, sr, percentile=99, min_dist_s=8.0)
            augmented = augment_sections(sections, harmonic_peaks, min_section_ms)

            n_original = len(sections)
            n_final = len(augmented)
            n_splits = sum(1 for s in augmented if s.source == "harmonic_split")
            n_peaks = len(harmonic_peaks)

            total_original += n_original
            total_final += n_final
            total_splits += n_splits
            total_harmonic_peaks += n_peaks
            if n_splits > 0:
                songs_with_splits += 1

            # Label distribution
            label_counts: dict[str, int] = {}
            for s in sections:
                label_counts[s.label] = label_counts.get(s.label, 0) + 1
            label_str = ",".join(f"{k}x{v}" for k, v in sorted(label_counts.items()))[:23]

            # Long sections that got split or stayed long
            long_info = []
            for s in sections:
                if s.duration_ms >= min_section_ms:
                    dur = s.duration_ms / 1000
                    peaks = s.harmonic_peaks_inside
                    if peaks > 0:
                        long_info.append(f"{s.label}({dur:.0f}s→{peaks+1}parts)")
                    else:
                        long_info.append(f"{s.label}({dur:.0f}s,no split)")
            long_str = " ".join(long_info) if long_info else "none"

            print(f"{name:<35} {duration_s:>4.0f}s {n_original:<4} {n_peaks:<5} {n_final:<6} "
                  f"{n_splits:<6} {label_str:<25} {long_str}")

        except Exception as exc:
            print(f"{name:<35} ERROR: {exc}")

    # Summary
    n = len(mp3s)
    print(f"\n{'=' * 115}")
    print(f"SUMMARY ({n} songs)")
    print(f"{'=' * 115}")
    print(f"\nSegmentino sections:    mean {total_original/n:.1f}/song")
    print(f"Harmonic peaks (99th):  mean {total_harmonic_peaks/n:.1f}/song")
    print(f"Final sections:         mean {total_final/n:.1f}/song (after augmentation)")
    print(f"Harmonic splits added:  {total_splits} across {songs_with_splits}/{n} songs")
    print(f"Net gain:               +{total_final - total_original} sections total "
          f"({(total_final/total_original - 1)*100:.0f}% increase)")

    print(f"\nConclusion:")
    if total_splits > 0:
        print(f"  Harmonic change subdivided {total_splits} long sections across {songs_with_splits} songs.")
        print(f"  This catches internal transitions that Segmentino missed (e.g., verse-to-chorus")
        print(f"  inside a merged block, or instrumental breaks within a section).")
    else:
        print(f"  No sections were long enough to subdivide at {min_section_s}s threshold.")


if __name__ == "__main__":
    main()
