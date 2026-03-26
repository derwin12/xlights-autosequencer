"""Hierarchy mark placement validator.

Evaluates whether timing marks are placed at musically meaningful positions
by correlating marks against audio features (energy curves, onset density).

Produces a per-level quality report and populates TimingMark.confidence.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve


# ── Internal helpers ──────────────────────────────────────────────────────────

def _cv(intervals: list[float]) -> float:
    """Coefficient of variation (std/mean). Lower = more regular."""
    if len(intervals) < 2:
        return 1.0
    mean = sum(intervals) / len(intervals)
    if mean < 1e-6:
        return 1.0
    variance = sum((x - mean) ** 2 for x in intervals) / len(intervals)
    return (variance ** 0.5) / mean


def _regularity(track: "TimingTrack") -> float:
    """1 - CV of inter-mark intervals, clamped to [0, 1]. Higher = more regular."""
    marks = track.marks
    if len(marks) < 2:
        return 0.0
    intervals = [float(marks[i + 1].time_ms - marks[i].time_ms) for i in range(len(marks) - 1)]
    return max(0.0, min(1.0, 1.0 - _cv(intervals)))


def _nearest_distance(t: int, sorted_times: list[int]) -> int:
    """Binary-search for the nearest time in a sorted list; return absolute distance."""
    if not sorted_times:
        return 999999
    lo, hi = 0, len(sorted_times) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_times[mid] < t:
            lo = mid + 1
        else:
            hi = mid
    best = abs(sorted_times[lo] - t)
    if lo > 0:
        best = min(best, abs(sorted_times[lo - 1] - t))
    return best


def _onset_alignment_rate(track: "TimingTrack", onset_times_ms: list[int],
                           window_ms: int = 60) -> float:
    """Fraction of marks that have an onset within window_ms."""
    if not track.marks or not onset_times_ms:
        return 0.0
    sorted_onsets = sorted(onset_times_ms)
    aligned = sum(
        1 for m in track.marks
        if _nearest_distance(m.time_ms, sorted_onsets) <= window_ms
    )
    return aligned / len(track.marks)


def _transient_rate(track: "TimingTrack", curve: "ValueCurve",
                    window_ms: int = 100) -> float:
    """Fraction of onset marks that look like transients in the energy curve.

    A mark passes if EITHER:
      (a) short-window slope: energy in the 40ms after the mark exceeds the
          40ms before (catches sharp attacks — kick, snare, pluck), OR
      (b) local peak: energy at the mark frame is above the mean of the
          surrounding ±window_ms region (catches sustained-onset instruments
          like bass and legato guitar where the slope check often fails).

    Using two criteria with OR union gives better coverage across stems
    without artificially inflating scores — both conditions require the mark
    to be at a genuine energy event.
    """
    if not track.marks or not curve or not curve.values:
        return 0.0
    values = curve.values
    n = len(values)
    fps = curve.fps

    short_frames = max(3, int(60 * fps / 1000))           # 60 ms attack window (≥3 frames)
    broad_frames = max(2, int(window_ms * fps / 1000))   # ±window_ms context

    aligned = 0
    for mark in track.marks:
        center = int(mark.time_ms * fps / 1000)

        # (a) short-window slope check
        pre_short  = values[max(0, center - short_frames): center]
        post_short = values[center: min(n, center + short_frames)]
        slope_ok = (
            pre_short and post_short and
            sum(post_short) / len(post_short) > sum(pre_short) / len(pre_short)
        )

        # (b) local peak check
        region = values[max(0, center - broad_frames): min(n, center + broad_frames)]
        peak_ok = bool(
            region and
            values[max(0, min(n - 1, center))] >= sum(region) / len(region)
        )

        if slope_ok or peak_ok:
            aligned += 1

    return aligned / len(track.marks)


def _energy_ratio_at(mark: "TimingMark", curve: "ValueCurve",
                     window_ms: int = 1000) -> float:
    """Ratio of energy after vs before the mark.

    > 1 means energy increases at mark (impact), < 1 means it decreases (drop).
    """
    if not curve or not curve.values:
        return 1.0
    fps = curve.fps
    center = int(mark.time_ms * fps / 1000)
    w = max(1, int(window_ms * fps / 1000))
    values = curve.values
    n = len(values)

    before = values[max(0, center - w): center]
    after = values[center: min(n, center + w)]
    if not before or not after:
        return 1.0
    before_avg = sum(before) / len(before)
    after_avg = sum(after) / len(after)
    if before_avg < 1:
        return 1.0
    return after_avg / before_avg


def _bar_alignment_rate(sections: list["TimingMark"], bars: "TimingTrack",
                        window_ms: int | None = None) -> tuple[int, int, int]:
    """Count how many section boundaries fall within window_ms of a bar boundary.

    window_ms defaults to half the median bar interval (clamped 400–1200ms),
    so the tolerance scales with tempo rather than being fixed.
    Returns (aligned, total, window_ms_used).
    """
    if not sections or not bars or not bars.marks:
        return 0, len(sections), window_ms or 500
    bar_times = sorted(m.time_ms for m in bars.marks)
    if window_ms is None:
        if len(bar_times) > 1:
            intervals = [bar_times[i + 1] - bar_times[i] for i in range(len(bar_times) - 1)]
            median_interval = sorted(intervals)[len(intervals) // 2]
            window_ms = max(400, min(1200, median_interval // 2))
        else:
            window_ms = 500
    aligned = sum(
        1 for s in sections
        if _nearest_distance(s.time_ms, bar_times) <= window_ms
    )
    return aligned, len(sections), window_ms


def _beat_bar_consistency(beats: "TimingTrack", bars: "TimingTrack",
                          window_ms: int = 80) -> float:
    """Fraction of bar boundaries that land on a beat."""
    if not bars or not bars.marks or not beats or not beats.marks:
        return 0.0
    beat_times = sorted(m.time_ms for m in beats.marks)
    aligned = sum(
        1 for b in bars.marks
        if _nearest_distance(b.time_ms, beat_times) <= window_ms
    )
    return aligned / len(bars.marks)


# ── Public API ────────────────────────────────────────────────────────────────

def validate_hierarchy(result: "HierarchyResult") -> dict:
    """Evaluate mark placement quality across all hierarchy levels.

    Checks:
      L1 sections  — bar alignment rate (sections start on bar boundaries)
      L2 bars      — inter-mark regularity + onset alignment
      L3 beats     — inter-mark regularity + onset alignment
      L2↔L3        — beat/bar cross-level consistency (bars land on beats)
      L4 events    — transient rate (onsets land near energy peaks per stem)
      L0 impacts   — mean energy ratio at impact marks
      L0 drops     — mean energy ratio at drop marks

    Populates TimingMark.confidence on all marks where a score is computable.

    Returns a dict suitable for storage as HierarchyResult.validation.
    """
    report: dict = {}

    full_mix_curve = result.energy_curves.get("full_mix")

    # Prefer drum stem onsets for bar/beat alignment — drums are on-beat by
    # definition and much less noisy than full_mix (which includes off-beat
    # hi-hats, guitar strums, etc.).  Fall back to full_mix when unavailable.
    def _best_onsets() -> list[int]:
        for stem in ("drums", "full_mix"):
            track = result.events.get(stem)
            if track and track.marks:
                return sorted(m.time_ms for m in track.marks)
        return []

    beat_onsets: list[int] = _best_onsets()
    full_mix_onsets: list[int] = (
        sorted(m.time_ms for m in result.events["full_mix"].marks)
        if result.events.get("full_mix") else []
    )

    # ── L2 Bars ───────────────────────────────────────────────────────────────
    if result.bars and result.bars.marks:
        reg = _regularity(result.bars)
        align = _onset_alignment_rate(result.bars, beat_onsets, window_ms=80)
        bar_score = round((reg + align) / 2, 3)
        report["bars"] = {
            "mark_count": len(result.bars.marks),
            "regularity": round(reg, 3),
            "onset_alignment": round(align, 3),
            "score": bar_score,
        }
        for mark in result.bars.marks:
            mark.confidence = bar_score

    # ── L3 Beats ─────────────────────────────────────────────────────────────
    if result.beats and result.beats.marks:
        reg = _regularity(result.beats)
        align = _onset_alignment_rate(result.beats, beat_onsets, window_ms=50)
        beat_score = round((reg + align) / 2, 3)
        report["beats"] = {
            "mark_count": len(result.beats.marks),
            "regularity": round(reg, 3),
            "onset_alignment": round(align, 3),
            "score": beat_score,
        }
        for mark in result.beats.marks:
            mark.confidence = beat_score

    # ── L2↔L3 cross-level consistency ────────────────────────────────────────
    if result.bars and result.beats:
        consistency = _beat_bar_consistency(result.beats, result.bars, window_ms=80)
        report["bar_beat_consistency"] = round(consistency, 3)

    # ── L1 Sections ──────────────────────────────────────────────────────────
    if result.sections:
        if result.bars:
            aligned, total, win = _bar_alignment_rate(result.sections, result.bars)
            rate = round(aligned / total, 3) if total else 0.0
            report["sections"] = {
                "mark_count": total,
                "bar_aligned": aligned,
                "bar_alignment_rate": rate,
                "window_ms": win,
            }
            for mark in result.sections:
                mark.confidence = rate
        else:
            report["sections"] = {"mark_count": len(result.sections), "bar_alignment_rate": None}

    # ── L4 Events ────────────────────────────────────────────────────────────
    # Spectral flux captures rapid spectral changes better than RMS energy for
    # short-attack instruments like drums.  Prefer it for drums stem.
    spectral_flux_curve = getattr(result, "spectral_flux", None)

    report["events"] = {}
    for stem, track in result.events.items():
        if not track.marks:
            continue
        if stem == "drums" and spectral_flux_curve:
            stem_curve = spectral_flux_curve
        else:
            stem_curve = result.energy_curves.get(stem) or full_mix_curve
        tr = _transient_rate(track, stem_curve, window_ms=80) if stem_curve else 0.0
        report["events"][stem] = {
            "mark_count": len(track.marks),
            "transient_rate": round(tr, 3),
        }
        for mark in track.marks:
            mark.confidence = round(tr, 3)

    # ── L0 Energy impacts ────────────────────────────────────────────────────
    if full_mix_curve and result.energy_impacts:
        ratios = [_energy_ratio_at(m, full_mix_curve) for m in result.energy_impacts]
        mean_ratio = round(sum(ratios) / len(ratios), 2)
        above = sum(1 for r in ratios if r >= 1.5)
        report["impacts"] = {
            "mark_count": len(result.energy_impacts),
            "energy_ratio_mean": mean_ratio,
            "above_threshold": above,
        }
        for mark, ratio in zip(result.energy_impacts, ratios):
            mark.confidence = round(min(1.0, max(0.0, (ratio - 1.0) / 2.0)), 3)

    # ── L0 Energy drops ──────────────────────────────────────────────────────
    if full_mix_curve and result.energy_drops:
        ratios = [_energy_ratio_at(m, full_mix_curve) for m in result.energy_drops]
        mean_ratio = round(sum(ratios) / len(ratios), 2)
        below = sum(1 for r in ratios if r <= 0.7)
        report["drops"] = {
            "mark_count": len(result.energy_drops),
            "energy_ratio_mean": mean_ratio,
            "below_threshold": below,
        }
        for mark, ratio in zip(result.energy_drops, ratios):
            mark.confidence = round(min(1.0, max(0.0, 1.0 - ratio)), 3)

    # ── Overall score ─────────────────────────────────────────────────────────
    scores = []
    if "bars" in report:
        scores.append(report["bars"]["score"])
    if "beats" in report:
        scores.append(report["beats"]["score"])
    if "bar_beat_consistency" in report:
        scores.append(report["bar_beat_consistency"])
    if "sections" in report and report["sections"].get("bar_alignment_rate") is not None:
        scores.append(report["sections"]["bar_alignment_rate"])
    if report.get("events"):
        rates = [v["transient_rate"] for v in report["events"].values()]
        if rates:
            scores.append(sum(rates) / len(rates))

    report["overall_score"] = round(sum(scores) / len(scores), 3) if scores else 0.0
    return report


def format_validation_report(report: dict) -> str:
    """Format a validation report for console output."""
    lines = ["Validation:"]

    def _bar(score: float) -> str:
        filled = int(score * 10)
        return "[" + "#" * filled + "." * (10 - filled) + f"] {score:.2f}"

    if "bars" in report:
        r = report["bars"]
        lines.append(
            f"  L2 Bars:    {_bar(r['score'])}  "
            f"regularity={r['regularity']:.2f}  onset_align={r['onset_alignment']:.2f}  "
            f"({r['mark_count']} marks)"
        )
    if "beats" in report:
        r = report["beats"]
        lines.append(
            f"  L3 Beats:   {_bar(r['score'])}  "
            f"regularity={r['regularity']:.2f}  onset_align={r['onset_alignment']:.2f}  "
            f"({r['mark_count']} marks)"
        )
    if "bar_beat_consistency" in report:
        c = report["bar_beat_consistency"]
        lines.append(f"  L2↔L3:      bar/beat consistency={c:.2f}")
    if "sections" in report:
        r = report["sections"]
        rate = r.get("bar_alignment_rate")
        if rate is not None:
            win = r.get("window_ms", 500)
            lines.append(
                f"  L1 Sections:{_bar(rate)}  "
                f"bar_aligned={r.get('bar_aligned', '?')}/{r['mark_count']}  "
                f"(window={win}ms)"
            )
    if report.get("events"):
        for stem, ev in sorted(report["events"].items()):
            tr = ev["transient_rate"]
            lines.append(
                f"  L4 {stem:<8}  {_bar(tr)}  "
                f"transient_rate={tr:.2f}  ({ev['mark_count']} marks)"
            )
    if "impacts" in report:
        r = report["impacts"]
        lines.append(
            f"  L0 Impacts: ratio_mean={r['energy_ratio_mean']:.2f}x  "
            f"above_threshold={r['above_threshold']}/{r['mark_count']}"
        )
    if "drops" in report:
        r = report["drops"]
        lines.append(
            f"  L0 Drops:   ratio_mean={r['energy_ratio_mean']:.2f}x  "
            f"below_threshold={r['below_threshold']}/{r['mark_count']}"
        )

    overall = report.get("overall_score", 0.0)
    lines.append(f"  Overall:    {_bar(overall)}")
    return "\n".join(lines)
