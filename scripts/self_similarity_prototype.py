#!/usr/bin/env python3
"""
Self-similarity matrix prototype for song structure detection.

Uses librosa's recurrence matrix primitives to detect repeated sections:
  1. Beat-synchronous chroma + MFCC features.
  2. Build a k-NN recurrence matrix (sparse — only top-k nearest beats kept).
  3. Enhance diagonal paths (suppress point matches, reinforce stripes).
  4. Convert to time-lag representation; find lags with strong horizontal stripes.
  5. Group repetitions by segment occurrence.

Output per song:
  - text report: repetition groups + alignment with story sections
  - PNG: SSM heatmap + time-lag view

Usage:
  python scripts/self_similarity_prototype.py <song_folder> [<song_folder> ...]
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np


# ── Feature + SSM computation ────────────────────────────────────────────────

def compute_features(
    audio_path: Path, sr: int = 22050, hop_length: int = 2048,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return (feature_matrix [F, T_beats], beat_times_s, duration_s).

    Features = stacked beat-synced chroma (12) + MFCC (13) = 25 dims.
    """
    import librosa

    y, sr = librosa.load(str(audio_path), sr=sr, mono=True)
    duration_s = float(len(y) / sr)

    _, beats = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop_length)
    beat_times = librosa.frames_to_time(beats, sr=sr, hop_length=hop_length)

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
    chroma_sync = librosa.util.sync(chroma, beats, aggregate=np.median)

    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=hop_length, n_mfcc=13)
    mfcc_sync = librosa.util.sync(mfcc, beats, aggregate=np.mean)

    # Stack features (chroma for harmony, MFCC for timbre)
    features = np.vstack([chroma_sync, mfcc_sync])
    return features, beat_times, duration_s


def compute_recurrence(features: np.ndarray) -> np.ndarray:
    """Return a diagonal-enhanced recurrence matrix [T, T]."""
    import librosa

    # k-NN recurrence: each beat connects to its k-nearest neighbors
    R = librosa.segment.recurrence_matrix(
        features, mode="affinity", sym=True, k=max(5, features.shape[1] // 20),
    )

    # Diagonal enhancement: reinforce stripes (= real repeats), suppress points
    R = librosa.segment.path_enhance(R, 15)

    return R


# ── Repetition detection via time-lag analysis ──────────────────────────────

@dataclass
class RepetitionGroup:
    """A set of mutually-similar segment occurrences (e.g. all 3 choruses)."""

    occurrences: list[tuple[int, int]]  # (start_beat, end_beat)
    mean_sim: float


def detect_repetition_groups(
    R: np.ndarray,
    beat_times: np.ndarray,
    min_len_beats: int = 12,
    min_gap_beats: int = 16,
    stripe_threshold: float = 0.3,
) -> list[RepetitionGroup]:
    """Find repeated segments from diagonal stripes in the recurrence matrix.

    For each lag k, sum the diagonal. Strong diagonals = candidate repeats.
    For each strong diagonal, find the stripe's start and length.
    """
    n = R.shape[0]
    # Time-lag representation: L[k, i] = R[i, i+k]
    # Only look at positive lags >= min_gap_beats
    stripes: list[tuple[int, int, int, float]] = []  # (lag, start_beat, length, mean)

    for k in range(min_gap_beats, n - min_len_beats):
        diag = np.array([R[i, i + k] for i in range(n - k)])
        # Find contiguous runs above threshold
        above = diag >= stripe_threshold
        i = 0
        while i < len(above):
            if not above[i]:
                i += 1
                continue
            j = i
            while j < len(above) and above[j]:
                j += 1
            if j - i >= min_len_beats:
                stripes.append((k, i, j - i, float(np.mean(diag[i:j]))))
            i = j + 1

    if not stripes:
        return []

    # Dedupe near-identical stripes (same region detected at multiple adjacent lags)
    # Prefer longer, stronger stripes
    stripes.sort(key=lambda s: (-s[2], -s[3]))
    kept: list[tuple[int, int, int, float]] = []
    for s in stripes:
        k, start, length, mean = s
        # Check overlap with already-kept stripe occurrences
        a_region = (start, start + length)
        b_region = (start + k, start + k + length)
        overlaps = False
        for kk in kept:
            kk_k, kk_s, kk_l, _ = kk
            kk_a = (kk_s, kk_s + kk_l)
            kk_b = (kk_s + kk_k, kk_s + kk_k + kk_l)
            for r1 in (a_region, b_region):
                for r2 in (kk_a, kk_b):
                    overlap = min(r1[1], r2[1]) - max(r1[0], r2[0])
                    if overlap > 0.5 * min(r1[1] - r1[0], r2[1] - r2[0]):
                        overlaps = True
                        break
                if overlaps:
                    break
            if overlaps:
                break
        if not overlaps:
            kept.append(s)

    # Group stripes that share occurrences → unified repetition groups
    # Each stripe gives two occurrences (a, b); merge via union-find
    occurrences: list[tuple[int, int, float]] = []  # (start, end, mean_sim)
    for k, start, length, mean in kept:
        occurrences.append((start, start + length, mean))
        occurrences.append((start + k, start + k + length, mean))

    # Merge occurrences that overlap >50%
    occurrences.sort()
    merged: list[tuple[int, int, float]] = []
    for o in occurrences:
        if merged:
            last = merged[-1]
            overlap = min(o[1], last[1]) - max(o[0], last[0])
            min_len = min(o[1] - o[0], last[1] - last[0])
            if overlap > 0.5 * min_len:
                # Merge: take the longer span, max similarity
                merged[-1] = (
                    min(last[0], o[0]),
                    max(last[1], o[1]),
                    max(last[2], o[2]),
                )
                continue
        merged.append(o)

    # Build union-find on merged occurrences using the stripe links
    parent = list(range(len(merged)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def find_occ_idx(start: int, end: int) -> int | None:
        """Find the merged occurrence index that contains/matches (start, end)."""
        for idx, (s, e, _) in enumerate(merged):
            overlap = min(e, end) - max(s, start)
            min_len = min(e - s, end - start)
            if min_len > 0 and overlap > 0.5 * min_len:
                return idx
        return None

    for k, start, length, _mean in kept:
        a_idx = find_occ_idx(start, start + length)
        b_idx = find_occ_idx(start + k, start + k + length)
        if a_idx is not None and b_idx is not None:
            ra, rb = find(a_idx), find(b_idx)
            if ra != rb:
                parent[ra] = rb

    groups_map: dict[int, list[int]] = {}
    for i in range(len(merged)):
        root = find(i)
        groups_map.setdefault(root, []).append(i)

    groups: list[RepetitionGroup] = []
    for members in groups_map.values():
        if len(members) < 2:
            continue
        occs = sorted([(merged[i][0], merged[i][1]) for i in members])
        mean_sim = float(np.mean([merged[i][2] for i in members]))
        groups.append(RepetitionGroup(occurrences=occs, mean_sim=mean_sim))

    groups.sort(key=lambda g: (-len(g.occurrences), -g.mean_sim))
    return groups


# ── Story comparison ────────────────────────────────────────────────────────

def load_story(song_folder: Path) -> dict | None:
    for f in song_folder.glob("*_story.json"):
        return json.loads(f.read_text())
    return None


def role_at(story: dict, t_s: float) -> str:
    for s in story.get("sections", []):
        start = float(s.get("start", 0))
        end = float(s.get("end", start))
        if start - 0.5 <= t_s <= end + 0.5:
            return s.get("role", "?")
    return "?"


def compare_to_story(groups: list[RepetitionGroup], beat_times: np.ndarray, story: dict) -> str:
    src = story.get("global", {}).get("section_source", "?")
    lines = [f"Story section_source: {src}",
             f"Story sections: {len(story.get('sections', []))}"]
    for i, s in enumerate(story.get("sections", []), 1):
        lines.append(
            f"  [{i}] {s.get('role','?'):12} "
            f"{float(s.get('start',0)):6.1f}–{float(s.get('end',0)):6.1f}s "
            f"({float(s.get('end',0)) - float(s.get('start',0)):5.1f}s)"
        )
    lines.append("")
    lines.append("SSM-detected repetition groups:")
    if not groups:
        lines.append("  (none found above threshold)")
        return "\n".join(lines)

    for gi, g in enumerate(groups, 1):
        occ_lines = []
        for s_beat, e_beat in g.occurrences:
            s_beat = min(s_beat, len(beat_times) - 1)
            e_beat = min(e_beat, len(beat_times) - 1)
            s_s = float(beat_times[s_beat])
            e_s = float(beat_times[e_beat])
            mid_s = (s_s + e_s) / 2
            occ_lines.append(f"{s_s:6.1f}–{e_s:6.1f}s [{role_at(story, mid_s):12}]")
        lines.append(
            f"  Group {gi} ({len(g.occurrences)}× , sim={g.mean_sim:.2f}, len≈{g.occurrences[0][1]-g.occurrences[0][0]} beats):"
        )
        for ol in occ_lines:
            lines.append(f"      {ol}")
    return "\n".join(lines)


# ── PNG output ──────────────────────────────────────────────────────────────

def save_png(
    R: np.ndarray,
    beat_times: np.ndarray,
    story: dict | None,
    groups: list[RepetitionGroup],
    out_path: Path,
    title: str,
) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 10))
    extent = (
        float(beat_times[0]), float(beat_times[-1]),
        float(beat_times[-1]), float(beat_times[0]),
    )
    ax.imshow(R, aspect="auto", cmap="magma", extent=extent, vmin=0, vmax=max(0.5, float(R.max())))
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Time (s)")
    ax.set_title(f"{title} — recurrence matrix")

    if story:
        for s in story.get("sections", []):
            start = float(s.get("start", 0))
            ax.axvline(start, color="cyan", alpha=0.4, linewidth=0.8)
            ax.axhline(start, color="cyan", alpha=0.4, linewidth=0.8)

    colors = plt.cm.tab10.colors
    for gi, g in enumerate(groups[:10]):
        c = colors[gi % len(colors)]
        for s_b, e_b in g.occurrences:
            s_b = min(s_b, len(beat_times) - 1)
            e_b = min(e_b, len(beat_times) - 1)
            s_s = float(beat_times[s_b])
            e_s = float(beat_times[e_b])
            ax.plot([s_s, e_s], [s_s, s_s], color=c, linewidth=3.0, alpha=0.9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


# ── Main ────────────────────────────────────────────────────────────────────

def process_song(song_folder: Path, out_dir: Path) -> str:
    mp3_files = list(song_folder.glob("*.mp3"))
    if not mp3_files:
        return f"{song_folder.name}: no MP3"
    mp3 = mp3_files[0]

    print(f"  → {mp3.name}: features...", file=sys.stderr)
    features, beat_times, duration_s = compute_features(mp3)
    print(f"    {features.shape[1]} beats, {duration_s:.1f}s", file=sys.stderr)

    print("    recurrence matrix + diagonal enhancement...", file=sys.stderr)
    R = compute_recurrence(features)

    print("    repetition detection...", file=sys.stderr)
    groups = detect_repetition_groups(R, beat_times)
    print(f"    {len(groups)} repetition groups", file=sys.stderr)

    story = load_story(song_folder)
    out_txt = out_dir / f"{song_folder.name}.txt"
    out_png = out_dir / f"{song_folder.name}.png"

    lines = [
        f"SSM Prototype — {song_folder.name}",
        f"Duration: {duration_s:.1f}s, Beats: {features.shape[1]}",
        f"Repetition groups: {len(groups)}",
        "",
    ]
    if story:
        lines.append(compare_to_story(groups, beat_times, story))
    else:
        lines.append("(no _story.json)")

    out_txt.write_text("\n".join(lines) + "\n")
    save_png(R, beat_times, story, groups, out_png, song_folder.name)
    return f"{song_folder.name}: {len(groups)} groups → {out_txt}"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: self_similarity_prototype.py <song_folder> [<song_folder> ...]")
        sys.exit(1)

    out_dir = Path("/tmp/ssm")
    out_dir.mkdir(parents=True, exist_ok=True)

    for arg in sys.argv[1:]:
        folder = Path(arg)
        if not folder.is_dir():
            print(f"skip: {folder}", file=sys.stderr)
            continue
        print(process_song(folder, out_dir))


if __name__ == "__main__":
    main()
