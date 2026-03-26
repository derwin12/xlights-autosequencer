"""Solo region detection from per-stem energy curves.

A solo is a sustained period where one stem's energy fraction is significantly
above its song-wide baseline — the same thing a human engineer sees when
looking at the stem waveform and one track is clearly louder than everything
else for an extended stretch.

Algorithm
---------
1. For each frame, compute each stem's fraction of total stem energy.
2. Smooth fractions with a ~2s rolling window (reduces beat-to-beat noise).
3. Compute each stem's baseline as the median of its smoothed fractions.
4. A frame is "candidate solo" for a stem when:
       smoothed_fraction > baseline * prominence_factor
   AND smoothed_fraction > min_absolute_prominence
5. Group contiguous candidate frames into regions, discard < min_duration_ms.
6. Return as TimingMark objects (time_ms = region start, duration_ms = length).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.analyzer.result import TimingMark, ValueCurve


def detect_solos(
    energy_curves: dict[str, "ValueCurve"],
    duration_ms: int,
    *,
    prominence_factor: float = 2.0,
    min_absolute_prominence: float = 0.45,
    min_duration_ms: int = 8000,
    smooth_window_s: float = 3.0,
    exclude_stems: tuple[str, ...] = ("full_mix",),
) -> dict[str, list["TimingMark"]]:
    """Detect solo regions per stem.

    Args:
        energy_curves:  stem → ValueCurve (BBC RMS energy).
        duration_ms:    total song duration in ms.
        prominence_factor:  how much above baseline a stem must be (2.0 = 2× baseline).
            High-baseline stems (e.g. bass at 0.53 in a stripped arrangement) will
            need an impossible >1.0 fraction, effectively suppressing false solos.
        min_absolute_prominence:  stem must hold ≥ this fraction of total energy (0–1).
            0.45 requires genuine dominance — one stem at nearly half the mix.
        min_duration_ms:  minimum solo region length (8 s filters short flukes).
        smooth_window_s:  rolling-average window for prominence smoothing.
        exclude_stems:  stems to skip (full_mix is the sum, not a stem).

    Returns:
        dict mapping stem name → list of TimingMark (time_ms + duration_ms set).
    """
    from src.analyzer.result import TimingMark

    # Only work with stems that have energy curves and are not excluded
    stems = {k: v for k, v in energy_curves.items() if k not in exclude_stems}
    if len(stems) < 2:
        return {}

    # Align to common fps (use the most common fps; resample if needed)
    fps_counts: dict[int, int] = {}
    for vc in stems.values():
        fps_counts[vc.fps] = fps_counts.get(vc.fps, 0) + 1
    target_fps = max(fps_counts, key=fps_counts.__getitem__)

    def _get_values(vc: "ValueCurve") -> list[float]:
        if vc.fps == target_fps:
            return [float(v) for v in vc.values]
        # Simple nearest-neighbour resample
        n_out = int(duration_ms * target_fps / 1000) + 1
        ratio = vc.fps / target_fps
        return [float(vc.values[min(len(vc.values) - 1, int(i * ratio))]) for i in range(n_out)]

    aligned: dict[str, list[float]] = {k: _get_values(v) for k, v in stems.items()}
    n_frames = min(len(v) for v in aligned.values())
    if n_frames < 2:
        return {}

    # Per-frame total energy and each stem's fraction
    totals = [
        sum(aligned[k][f] for k in aligned) or 1.0
        for f in range(n_frames)
    ]
    fractions: dict[str, list[float]] = {
        k: [aligned[k][f] / totals[f] for f in range(n_frames)]
        for k in aligned
    }

    # Rolling-average smoothing
    half_win = max(1, int(smooth_window_s * target_fps / 2))

    def _smooth(vals: list[float]) -> list[float]:
        out = []
        n = len(vals)
        for i in range(n):
            lo, hi = max(0, i - half_win), min(n, i + half_win + 1)
            out.append(sum(vals[lo:hi]) / (hi - lo))
        return out

    smoothed: dict[str, list[float]] = {k: _smooth(fractions[k]) for k in fractions}

    # Baseline = median of smoothed fractions (reflects "normal" presence)
    def _median(vals: list[float]) -> float:
        s = sorted(vals)
        n = len(s)
        return (s[n // 2] + s[(n - 1) // 2]) / 2

    baselines: dict[str, float] = {k: _median(smoothed[k]) for k in smoothed}

    # Detect solo regions per stem
    min_frames = max(1, int(min_duration_ms * target_fps / 1000))
    result: dict[str, list[TimingMark]] = {}

    for stem, sm in smoothed.items():
        baseline = baselines[stem]
        threshold = max(baseline * prominence_factor, min_absolute_prominence)

        # Boolean mask of candidate frames
        mask = [v >= threshold for v in sm]

        # Group into contiguous runs
        regions: list[tuple[int, int]] = []
        in_run = False
        run_start = 0
        for i, active in enumerate(mask):
            if active and not in_run:
                run_start = i
                in_run = True
            elif not active and in_run:
                regions.append((run_start, i))
                in_run = False
        if in_run:
            regions.append((run_start, n_frames))

        # Merge regions separated by < 1s gap, then filter by min duration
        merged: list[tuple[int, int]] = []
        gap_frames = int(target_fps)
        for start, end in regions:
            if merged and start - merged[-1][1] <= gap_frames:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))

        marks = []
        for start, end in merged:
            dur_ms = int((end - start) * 1000 / target_fps)
            if dur_ms >= min_duration_ms:
                t_ms = int(start * 1000 / target_fps)
                marks.append(TimingMark(
                    time_ms=t_ms,
                    confidence=round(float(max(sm[start:end])), 3),
                    label=f"{stem}_solo",
                    duration_ms=dur_ms,
                ))

        if marks:
            result[stem] = marks

    return result
