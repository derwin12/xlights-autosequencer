#!/usr/bin/env python3
"""
Batch-test ensemble segmentation on all MP3s.

Runs three segmenters per song, finds consensus boundaries, and reports:
- How many boundaries each segmenter finds
- How many consensus boundaries (2+ agree within window)
- Which boundaries are unique to one segmenter (potential false positives or missed by others)
- Whether Segmentino repeat labels survive into the ensemble

Usage: python analysis/batch_ensemble.py /path/to/mp3s [consensus_window_s]
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import librosa
import numpy as np
import vamp


@dataclass
class Segment:
    time_ms: int
    label: str
    duration_ms: int = 0
    source: str = ""


@dataclass
class EnsembleResult:
    song: str
    duration_s: float
    segmentino: list[Segment]
    qm_tuned: list[Segment]
    qm_granular: list[Segment]
    consensus: list[dict] = field(default_factory=list)
    unique_segmentino: list[int] = field(default_factory=list)
    unique_qm_tuned: list[int] = field(default_factory=list)
    unique_qm_granular: list[int] = field(default_factory=list)


def run_segmentino(y: np.ndarray, sr: int) -> list[Segment]:
    out = vamp.collect(y, sr, "segmentino:segmentino")
    items = out.get("list", [])
    segments = []
    for item in items:
        ts = float(item["timestamp"])
        dur = float(item.get("duration", 0))
        label = item.get("label", "?")
        segments.append(Segment(
            time_ms=int(round(ts * 1000)),
            label=label,
            duration_ms=int(round(dur * 1000)),
            source="segmentino",
        ))
    return segments


def run_qm_segmenter(y: np.ndarray, sr: int, n_types: int, n_limit: int) -> list[Segment]:
    out = vamp.collect(y, sr, "qm-vamp-plugins:qm-segmenter",
                       output="segmentation",
                       parameters={"nSegmentTypes": n_types, "neighbourhoodLimit": n_limit, "featureType": 1})
    items = out.get("list", [])
    segments = []
    for item in items:
        ts = float(item["timestamp"])
        label = item.get("label", "?")
        segments.append(Segment(
            time_ms=int(round(ts * 1000)),
            label=label,
            source=f"qm_n{n_types}_h{n_limit}",
        ))
    return segments


def find_consensus(sources: list[list[Segment]], window_ms: int) -> list[dict]:
    """Find boundaries where 2+ sources agree within window_ms."""
    # Collect all boundaries with source tags
    all_bounds: list[tuple[int, str, str]] = []  # (time_ms, source, label)
    for segs in sources:
        for seg in segs:
            all_bounds.append((seg.time_ms, seg.source, seg.label))
    all_bounds.sort(key=lambda x: x[0])

    # Group boundaries that fall within window_ms of each other
    consensus = []
    used = set()

    for i, (t1, s1, l1) in enumerate(all_bounds):
        if i in used:
            continue
        group = [(t1, s1, l1)]
        used.add(i)

        for j, (t2, s2, l2) in enumerate(all_bounds):
            if j in used or s2 == s1:
                # Skip already-used or same-source duplicates
                if j in used:
                    continue
                if s2 == s1:
                    continue
            if abs(t2 - t1) <= window_ms:
                group.append((t2, s2, l2))
                used.add(j)

        sources_in_group = set(s for _, s, _ in group)
        avg_time = int(sum(t for t, _, _ in group) / len(group))
        labels = {s: l for _, s, l in group}

        consensus.append({
            "time_ms": avg_time,
            "time_s": round(avg_time / 1000, 1),
            "n_sources": len(sources_in_group),
            "sources": sorted(sources_in_group),
            "labels": labels,
            "segmentino_label": labels.get("segmentino"),
        })

    return sorted(consensus, key=lambda x: x["time_ms"])


def find_unique(segments: list[Segment], consensus: list[dict], window_ms: int) -> list[int]:
    """Find boundaries from a source that didn't make it into any consensus group."""
    unique = []
    for seg in segments:
        matched = False
        for c in consensus:
            if abs(seg.time_ms - c["time_ms"]) <= window_ms and seg.source in c["sources"]:
                matched = True
                break
        if not matched:
            unique.append(seg.time_ms)
    return unique


def analyze_song(mp3_path: str, window_ms: int) -> EnsembleResult:
    y, sr = librosa.load(mp3_path, mono=True)
    duration_s = len(y) / sr
    name = Path(mp3_path).stem

    segmentino = run_segmentino(y, sr)
    qm_tuned = run_qm_segmenter(y, sr, n_types=3, n_limit=8)
    qm_granular = run_qm_segmenter(y, sr, n_types=5, n_limit=6)

    consensus = find_consensus([segmentino, qm_tuned, qm_granular], window_ms)

    return EnsembleResult(
        song=name,
        duration_s=duration_s,
        segmentino=segmentino,
        qm_tuned=qm_tuned,
        qm_granular=qm_granular,
        consensus=consensus,
        unique_segmentino=find_unique(segmentino, consensus, window_ms),
        unique_qm_tuned=find_unique(qm_tuned, consensus, window_ms),
        unique_qm_granular=find_unique(qm_granular, consensus, window_ms),
    )


def main():
    songs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/Users/rob/mp3")
    window_s = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    window_ms = int(window_s * 1000)

    mp3s = sorted(songs_dir.glob("*.mp3"))
    if not mp3s:
        print(f"No MP3s found in {songs_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Ensemble segmentation — {len(mp3s)} songs, consensus window: {window_s}s")
    print("=" * 110)
    print(f"{'SONG':<35} {'DUR':<5} {'SEGM':<5} {'QM-T':<5} {'QM-G':<5} "
          f"{'CONS':<5} {'2+':<4} {'3':<4} {'LABELS':<20} {'UNIQUE S/T/G'}")
    print("-" * 110)

    all_results = []
    total_consensus_2plus = 0
    total_consensus_3 = 0
    total_segmentino = 0
    total_qm_tuned = 0
    total_qm_granular = 0
    songs_with_repeat_labels = 0

    for mp3 in mp3s:
        name = mp3.stem[:33]
        try:
            result = analyze_song(str(mp3), window_ms)
            all_results.append(result)

            n_seg = len(result.segmentino)
            n_tuned = len(result.qm_tuned)
            n_gran = len(result.qm_granular)
            n_cons = len(result.consensus)
            n_2plus = sum(1 for c in result.consensus if c["n_sources"] >= 2)
            n_3 = sum(1 for c in result.consensus if c["n_sources"] >= 3)

            total_segmentino += n_seg
            total_qm_tuned += n_tuned
            total_qm_granular += n_gran
            total_consensus_2plus += n_2plus
            total_consensus_3 += n_3

            # Segmentino repeat labels in consensus
            seg_labels = [s.label for s in result.segmentino]
            label_counts = {}
            for l in seg_labels:
                label_counts[l] = label_counts.get(l, 0) + 1
            repeat_labels = sorted(k for k, v in label_counts.items() if v > 1)
            if repeat_labels:
                songs_with_repeat_labels += 1
            label_str = ",".join(f"{k}x{v}" for k, v in sorted(label_counts.items()))[:18]

            unique_str = f"{len(result.unique_segmentino)}/{len(result.unique_qm_tuned)}/{len(result.unique_qm_granular)}"

            print(f"{name:<35} {result.duration_s:>4.0f}s {n_seg:<5} {n_tuned:<5} {n_gran:<5} "
                  f"{n_cons:<5} {n_2plus:<4} {n_3:<4} {label_str:<20} {unique_str}")

        except Exception as exc:
            print(f"{name:<35} ERROR: {exc}")

    # Summary
    print(f"\n{'=' * 110}")
    print(f"SUMMARY ({len(all_results)} songs, {window_s}s consensus window)")
    print(f"{'=' * 110}")

    print(f"\nSegment counts:")
    print(f"  Segmentino:    mean {total_segmentino/len(all_results):.1f} segments/song")
    print(f"  QM tuned:      mean {total_qm_tuned/len(all_results):.1f} segments/song")
    print(f"  QM granular:   mean {total_qm_granular/len(all_results):.1f} segments/song")

    print(f"\nConsensus (2+ sources agree within {window_s}s):")
    print(f"  Total consensus boundaries: {total_consensus_2plus} across {len(all_results)} songs")
    print(f"  Mean per song: {total_consensus_2plus/len(all_results):.1f}")
    print(f"  All-three-agree boundaries: {total_consensus_3} ({total_consensus_3/max(total_consensus_2plus,1)*100:.0f}% of consensus)")

    print(f"\nSegmentino repeat labels:")
    print(f"  Songs with repeating sections: {songs_with_repeat_labels}/{len(all_results)}")

    # Consensus quality — are there songs where ensemble finds significantly more/fewer than segmentino alone?
    print(f"\nEnsemble vs Segmentino alone:")
    more = 0
    fewer = 0
    same = 0
    for r in all_results:
        n_2plus = sum(1 for c in r.consensus if c["n_sources"] >= 2)
        n_seg = len(r.segmentino)
        if n_2plus > n_seg:
            more += 1
        elif n_2plus < n_seg:
            fewer += 1
        else:
            same += 1
    print(f"  Ensemble finds MORE boundaries than Segmentino alone: {more} songs")
    print(f"  Ensemble finds FEWER boundaries: {fewer} songs")
    print(f"  Same count: {same} songs")

    # Songs where all 3 agree well (high % of 3-source consensus)
    print(f"\nAgreement quality per song:")
    for r in all_results:
        n_cons = len(r.consensus)
        n_2plus = sum(1 for c in r.consensus if c["n_sources"] >= 2)
        n_3 = sum(1 for c in r.consensus if c["n_sources"] >= 3)
        if n_cons > 0:
            pct_2 = n_2plus / n_cons * 100
            pct_3 = n_3 / n_cons * 100
        else:
            pct_2 = pct_3 = 0
        flag = ""
        if pct_3 < 30 and n_cons > 3:
            flag = " <-- low agreement"
        if n_cons <= 2:
            flag = " <-- very few segments"
        name = r.song[:40]
        print(f"  {name:<40} {n_cons:>3} boundaries, {n_2plus:>3} consensus(2+), {n_3:>3} consensus(3) "
              f"({pct_3:.0f}% all-agree){flag}")


if __name__ == "__main__":
    main()
