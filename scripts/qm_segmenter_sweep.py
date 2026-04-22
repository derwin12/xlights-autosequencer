#!/usr/bin/env python3
"""
QM Segmenter parameter sweep with boundary-agreement fitness.

For each parameter combination, run the QM segmenter on a song and score how
many of its boundaries land within ±1 bar of a multi-source cluster built
from *other* signals (stem entries, energy impacts, key changes, chord
density, segmentino, Genius story). Higher agreement = better parameters
for finding real structural transitions.

Parameters swept:
  nSegmentTypes     ∈ [3, 5, 7, 10]
  featureType       ∈ [1 (Hybrid), 2 (Chroma), 3 (MFCC)]
  neighbourhoodLimit ∈ [2.0, 4.0, 6.0, 10.0] (seconds)

Output: ranked list of (params, score) per song, plus an aggregate.

Usage:
  python scripts/qm_segmenter_sweep.py <song_folder> [<song_folder> ...]
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np


# ── Run QM segmenter with arbitrary params ──────────────────────────────────

def run_qm_segmenter(
    audio_path: Path, params: dict, sr: int = 22050,
) -> list[int]:
    """Return list of segment boundary times in ms."""
    import librosa
    import vamp

    y, _ = librosa.load(str(audio_path), sr=sr, mono=True)
    result = vamp.collect(
        y, sr,
        "qm-vamp-plugins:qm-segmenter",
        output="segmentation",
        parameters=params,
    )
    # result["list"] = [{"timestamp": ts, "duration": dur, "label": ...}, ...]
    boundaries_ms: list[int] = []
    for seg in result.get("list", []):
        t = float(seg["timestamp"])
        boundaries_ms.append(int(round(t * 1000)))
    # Dedupe + sort
    return sorted(set(boundaries_ms))


# ── Build non-QM baseline boundaries from hierarchy + story ─────────────────

@dataclass
class Boundary:
    time_ms: int
    source: str


def _beat_times_from_hierarchy(hier: dict) -> list[float]:
    """Find a beats track and return its timestamps in seconds."""
    # Look at top-level tracks for something beat-ish
    for track in hier.get("tracks", []):
        name = track.get("name", "").lower()
        if "beat" in name and "tracker" in name:
            marks = track.get("marks", []) or track.get("timestamps", [])
            out: list[float] = []
            for m in marks:
                if isinstance(m, dict):
                    t = m.get("t_ms") or m.get("timestamp_ms") or m.get("timestamp")
                    if t is None:
                        continue
                    # Heuristic: ms vs seconds
                    out.append(float(t) / 1000.0 if t > 50 else float(t))
                elif isinstance(m, (int, float)):
                    out.append(float(m))
            if len(out) >= 4:
                return out
    return []


def load_baseline_boundaries(
    song_folder: Path,
) -> tuple[list[Boundary], int, int]:
    """Collect all non-QM boundaries + (median_bar_ms, duration_ms)."""
    # Hierarchy JSON
    hier_path = None
    for p in (song_folder / f"{song_folder.name}_hierarchy.json",
              song_folder / song_folder.name / f"{song_folder.name}_hierarchy.json"):
        if p.exists():
            hier_path = p
            break
    if hier_path is None:
        # Fallback: any _hierarchy.json in the folder tree
        for p in song_folder.rglob("*_hierarchy.json"):
            hier_path = p
            break
    if hier_path is None:
        raise FileNotFoundError(f"No hierarchy.json under {song_folder}")
    hier = json.loads(hier_path.read_text())

    # Story JSON (optional, used for story boundaries)
    story_path = None
    for p in song_folder.glob("*_story.json"):
        story_path = p
        break
    story = json.loads(story_path.read_text()) if story_path else {}

    # Reuse the confidence-map's extraction helpers
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from boundary_confidence_map import (
        extract_segmentino,
        extract_key_changes,
        extract_energy_events,
        extract_chord_density_spikes,
        extract_stem_entry_events,
        extract_story_sections,
    )

    bs: list[Boundary] = []
    # Compute bar_ms first (below) so we can pass it to chord_density
    bpm = float(hier.get("estimated_bpm") or hier.get("tempo_bpm") or 120.0)
    bar_ms_local = int(round(60_000.0 / bpm * 4))
    for fn in (extract_stem_entry_events,
               extract_segmentino,
               extract_energy_events,
               extract_key_changes):
        try:
            for b in fn(hier):
                bs.append(Boundary(b.time_ms, b.source))
        except Exception as _e:
            print(f"    baseline: {fn.__name__} failed: {_e}", file=sys.stderr)
    try:
        for b in extract_chord_density_spikes(hier, bar_ms_local):
            bs.append(Boundary(b.time_ms, b.source))
    except Exception as _e:
        print(f"    baseline: chord_density failed: {_e}", file=sys.stderr)
    try:
        for b in extract_story_sections(story):
            bs.append(Boundary(b.time_ms, b.source))
    except Exception:
        pass

    # Estimate median bar duration (ms)
    bpm = float(hier.get("estimated_bpm") or hier.get("tempo_bpm") or 120.0)
    median_bar_ms = int(round(60_000.0 / bpm * 4))  # assume 4/4 time
    duration_ms = int(hier.get("duration_ms", 0) or 0)
    return bs, median_bar_ms, duration_ms


# ── Scoring ─────────────────────────────────────────────────────────────────

def _distinct_sources_within(
    baseline: list[Boundary], t_ms: int, tol_ms: int,
) -> set[str]:
    """Return the set of distinct source labels within ±tol_ms of t_ms."""
    # Normalize stem_entry:X → stem_entry (count once per stem)
    sources: set[str] = set()
    for b in baseline:
        if abs(b.time_ms - t_ms) <= tol_ms:
            src = b.source
            if src.startswith("stem_entry:"):
                sources.add(src)  # keep per-stem — each stem is an independent signal
            else:
                # Collapse "story (genius)" / "story (heuristic)" to just "story"
                sources.add(src.split(" ")[0])
    return sources


def score_params(
    qm_boundaries_ms: list[int],
    baseline: list[Boundary],
    tol_ms: int,
    duration_ms: int,
    min_sources: int = 3,
) -> tuple[float, dict]:
    """Score a parameter set by multi-source agreement at QM boundaries.

    Score = (# QM boundaries with >=min_sources OTHER sources nearby) / (# QM boundaries)
    Plus a penalty for pathological boundary counts (too few or too many).
    """
    if not qm_boundaries_ms:
        return 0.0, {"n_qm": 0, "n_agree_ge3": 0, "note": "no boundaries"}

    # Exclude QM's own output from baseline (it's not in baseline by construction)
    n_agree_ge3 = 0
    n_agree_ge4 = 0
    for t in qm_boundaries_ms:
        srcs = _distinct_sources_within(baseline, t, tol_ms)
        if len(srcs) >= min_sources:
            n_agree_ge3 += 1
        if len(srcs) >= (min_sources + 1):
            n_agree_ge4 += 1

    n = len(qm_boundaries_ms)
    precision = n_agree_ge3 / n  # fraction of QM boundaries that agree
    # Typical song has 6-14 sections; penalize counts far outside that band
    expected_lo, expected_hi = 5, 18
    if n < expected_lo:
        count_penalty = n / expected_lo
    elif n > expected_hi:
        count_penalty = expected_hi / n
    else:
        count_penalty = 1.0

    score = precision * count_penalty
    return score, {
        "n_qm": n,
        "n_agree_ge3": n_agree_ge3,
        "n_agree_ge4": n_agree_ge4,
        "precision": round(precision, 3),
        "count_penalty": round(count_penalty, 3),
    }


# ── Sweep loop ──────────────────────────────────────────────────────────────

PARAM_GRID = {
    "nSegmentTypes": [3, 5, 7, 10],
    "featureType": [1, 2, 3],  # 1=Hybrid, 2=Chroma, 3=MFCC
    "neighbourhoodLimit": [2.0, 4.0, 6.0, 10.0],
}
FEATURE_NAMES = {1: "Hybrid", 2: "Chroma", 3: "MFCC"}


def sweep_song(song_folder: Path) -> tuple[str, list[dict]]:
    name = song_folder.name
    mp3_files = list(song_folder.glob("*.mp3"))
    if not mp3_files:
        return name, []
    mp3 = mp3_files[0]

    baseline, bar_ms, duration_ms = load_baseline_boundaries(song_folder)
    tol_ms = bar_ms  # ±1 bar tolerance, same as confidence map
    print(f"  [{name}] baseline={len(baseline)} boundaries, bar={bar_ms}ms, dur={duration_ms/1000:.1f}s",
          file=sys.stderr)

    results: list[dict] = []
    for n_types in PARAM_GRID["nSegmentTypes"]:
        for ftype in PARAM_GRID["featureType"]:
            for nlim in PARAM_GRID["neighbourhoodLimit"]:
                params = {
                    "nSegmentTypes": float(n_types),
                    "featureType": float(ftype),
                    "neighbourhoodLimit": float(nlim),
                }
                try:
                    bounds = run_qm_segmenter(mp3, params)
                except Exception as exc:
                    print(f"    ERROR {params}: {exc}", file=sys.stderr)
                    continue
                score, info = score_params(bounds, baseline, tol_ms, duration_ms)
                results.append({
                    "nSegmentTypes": n_types,
                    "featureType": ftype,
                    "featureName": FEATURE_NAMES[ftype],
                    "neighbourhoodLimit": nlim,
                    "score": round(score, 4),
                    **info,
                })
    results.sort(key=lambda r: -r["score"])
    return name, results


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: qm_segmenter_sweep.py <song_folder> [<song_folder> ...]")
        sys.exit(1)

    out_dir = Path("/tmp/qm_sweep")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results: dict[str, list[dict]] = {}
    for arg in sys.argv[1:]:
        folder = Path(arg)
        if not folder.is_dir():
            print(f"skip: {folder}", file=sys.stderr)
            continue
        name, results = sweep_song(folder)
        all_results[name] = results

        out = out_dir / f"{name}.txt"
        lines = [f"QM Segmenter Sweep — {name}", ""]
        lines.append(f"{'rank':<5} {'nTypes':<7} {'feature':<8} {'nLim':<6} {'n_qm':<6} {'≥3':<5} {'≥4':<5} {'prec':<6} {'pen':<6} {'score':<6}")
        for rank, r in enumerate(results, 1):
            lines.append(
                f"{rank:<5} {r['nSegmentTypes']:<7} {r['featureName']:<8} "
                f"{r['neighbourhoodLimit']:<6} {r['n_qm']:<6} "
                f"{r['n_agree_ge3']:<5} {r['n_agree_ge4']:<5} "
                f"{r['precision']:<6} {r['count_penalty']:<6} {r['score']:<6}"
            )
        out.write_text("\n".join(lines) + "\n")
        print(f"  → wrote {out}", file=sys.stderr)

    # Aggregate: for each (nTypes, feature, nLim) combo, mean score across songs
    combo_scores: dict[tuple, list[float]] = {}
    for results in all_results.values():
        for r in results:
            k = (r["nSegmentTypes"], r["featureName"], r["neighbourhoodLimit"])
            combo_scores.setdefault(k, []).append(r["score"])
    agg = [
        (k, float(np.mean(v)), float(np.std(v)), len(v))
        for k, v in combo_scores.items()
    ]
    agg.sort(key=lambda x: -x[1])

    summary_path = out_dir / "summary.txt"
    lines = [f"QM Segmenter Sweep — Aggregate across {len(all_results)} song(s)", ""]
    lines.append(f"{'nTypes':<7} {'feature':<8} {'nLim':<6} {'mean_score':<12} {'stdev':<8} {'n':<3}")
    for (nt, feat, nlim), mean, std, n in agg[:20]:
        lines.append(f"{nt:<7} {feat:<8} {nlim:<6} {mean:<12.4f} {std:<8.4f} {n:<3}")
    # Also show current defaults for comparison
    lines.append("")
    lines.append("Current pipeline uses defaults: nSegmentTypes=10, featureType=Hybrid, neighbourhoodLimit=4.0")
    default_key = (10, "Hybrid", 4.0)
    for (k, mean, std, n) in agg:
        if k == default_key:
            default_rank = [x[0] for x in agg].index(k) + 1
            lines.append(f"Defaults ranked #{default_rank}/{len(agg)} with mean score {mean:.4f}")
            break
    summary_path.write_text("\n".join(lines) + "\n")
    print(f"\nAggregate summary → {summary_path}")


if __name__ == "__main__":
    main()
