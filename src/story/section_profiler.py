"""Section profiler for song story tool.

Computes SectionCharacter and SectionStems dicts for a given time range
by reading from a HierarchyResult-compatible dict.
"""
from __future__ import annotations

import math


_STEM_NAMES = ("drums", "bass", "vocals", "guitar", "piano", "other")

# Stems considered harmonic (for H/P ratio estimation when no explicit HPSS data)
_HARMONIC_STEMS = ("guitar", "piano", "bass", "vocals")
# Stems considered percussive
_PERCUSSIVE_STEMS = ("drums",)

_FREQUENCY_BAND_NAMES = (
    "sub_bass", "bass", "low_mid", "mid", "upper_mid", "presence", "brilliance"
)

# Approximate relative weights for each band (proportional energy distribution)
_BAND_WEIGHTS_BY_ENERGY_LEVEL = {
    "low":    [0.10, 0.20, 0.20, 0.25, 0.15, 0.05, 0.05],
    "medium": [0.08, 0.15, 0.18, 0.28, 0.18, 0.08, 0.05],
    "high":   [0.07, 0.12, 0.15, 0.28, 0.22, 0.10, 0.06],
}


def _get_frames_in_range(values: list[float], sample_rate: float,
                          start_ms: int, end_ms: int) -> list[float]:
    """Return the source frames whose timestamps fall in [start_ms, end_ms).

    Values are returned on their original scale (0–100 for energy curves).
    """
    start_sec = start_ms / 1000.0
    end_sec = end_ms / 1000.0
    start_idx = max(0, int(start_sec * sample_rate))
    end_idx = min(len(values), int(end_sec * sample_rate))
    return values[start_idx:end_idx] if start_idx < end_idx else []


def _mean(vals: list[float]) -> float:
    if not vals:
        return 0.0
    return sum(vals) / len(vals)


def _variance(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _mean(vals)
    return sum((v - m) ** 2 for v in vals) / len(vals)


def _linear_regression_slope(vals: list[float]) -> float:
    """Compute slope of least-squares linear fit."""
    n = len(vals)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = (n - 1) / 2.0
    mean_y = _mean(vals)
    num = sum((xs[i] - mean_x) * (vals[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if den == 0:
        return 0.0
    return num / den


def _stddev(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    return math.sqrt(_variance(vals))


def profile_section(start_ms: int, end_ms: int, hierarchy: dict) -> dict:
    """Profile a section of a song by computing character and stem properties.

    Args:
        start_ms: Section start time in milliseconds (inclusive).
        end_ms: Section end time in milliseconds (exclusive).
        hierarchy: HierarchyResult-compatible dict.

    Returns:
        Dict with 'character' and 'stems' sub-dicts.
    """
    duration_sec = (end_ms - start_ms) / 1000.0
    energy_curves: dict = hierarchy.get("energy_curves", {})

    # ── Energy frames ────────────────────────────────────────────────────────
    full_mix_curve = energy_curves.get("full_mix", {})
    full_mix_values = full_mix_curve.get("values", [])
    full_mix_rate = float(full_mix_curve.get("sample_rate") or full_mix_curve.get("fps") or 10.0)

    energy_frames = _get_frames_in_range(
        full_mix_values, full_mix_rate, start_ms, end_ms
    )
    if not energy_frames:
        energy_frames = [0.0]

    mean_energy = _mean(energy_frames)
    # Energy curve values are already 0–100 integers (normalised by the BBC/librosa
    # generators). Do NOT multiply by 100 again.
    energy_score = int(min(100, max(0, round(mean_energy))))
    energy_peak = int(min(100, max(0, round(max(energy_frames)))))
    # Variance on a 0–100 scale; normalise to 0.0–1.0 by dividing by max possible (2500)
    raw_var = _variance(energy_frames)
    energy_variance = float(min(1.0, max(0.0, raw_var / 2500.0)))

    # energy_score is now 0–100 (mean of 0–100 curve values)
    if energy_score <= 33:
        energy_level = "low"
    elif energy_score <= 66:
        energy_level = "medium"
    else:
        energy_level = "high"

    # Energy trajectory via linear regression
    # Normalise slope to be per-second so threshold is independent of frame count.
    raw_slope = _linear_regression_slope(energy_frames)
    # raw_slope is per-frame; convert to per-second using source sample rate
    slope_per_sec = raw_slope * full_mix_rate
    std = _stddev(energy_frames)
    if slope_per_sec > 0.005:
        energy_trajectory = "rising"
    elif slope_per_sec < -0.005:
        energy_trajectory = "falling"
    elif std > 0.1:
        energy_trajectory = "oscillating"
    else:
        energy_trajectory = "stable"

    # ── Texture / H-P ratio ──────────────────────────────────────────────────
    # Use per-stem energy curves to compute harmonic vs percussive energy
    def _stem_mean_in_range(stem_name: str) -> float:
        curve = energy_curves.get(stem_name, {})
        vals = curve.get("values", [])
        rate = float(curve.get("sample_rate") or curve.get("fps") or 10.0)
        frames = _get_frames_in_range(vals, rate, start_ms, end_ms)
        return _mean(frames) if frames else 0.0

    # Average the harmonic stems (not sum) so the ratio compares equivalent
    # single-stem levels. Summing 4 harmonic stems vs 1 drums made it impossible
    # for drums to ever win (would need 8× the energy of each harmonic stem).
    harmonic_stems = [_stem_mean_in_range(s) for s in _HARMONIC_STEMS]
    harmonic_energy = sum(harmonic_stems) / len(harmonic_stems) if harmonic_stems else 0.0
    percussive_energy = _stem_mean_in_range("drums")

    if percussive_energy > 0:
        hp_ratio = float(harmonic_energy / percussive_energy)
    else:
        hp_ratio = float(harmonic_energy * 2.0) if harmonic_energy > 0 else 1.0

    if hp_ratio > 1.5:
        texture = "harmonic"
    elif hp_ratio < 0.7:
        texture = "percussive"
    else:
        texture = "balanced"

    # ── Spectral brightness ──────────────────────────────────────────────────
    spectral_brightness_map = {"high": "bright", "medium": "neutral", "low": "dark"}
    spectral_brightness = spectral_brightness_map[energy_level]

    # ── Spectral centroid and flatness ───────────────────────────────────────
    spectral_centroid_hz_map = {"high": 3500, "medium": 2000, "low": 800}
    spectral_centroid_hz = spectral_centroid_hz_map[energy_level]

    spectral_flatness_map = {"percussive": 0.6, "harmonic": 0.2, "balanced": 0.4}
    spectral_flatness = float(spectral_flatness_map[texture])

    # ── Onset density ────────────────────────────────────────────────────────
    events: dict = hierarchy.get("events", {})
    total_onsets = 0
    for stem_events in events.values():
        marks = stem_events.get("marks", []) if isinstance(stem_events, dict) else []
        for m in marks:
            t = m.get("time_ms", -1)
            if start_ms <= t < end_ms:
                total_onsets += 1
    onset_density = float(total_onsets / duration_sec) if duration_sec > 0 else 0.0

    # ── Local tempo ──────────────────────────────────────────────────────────
    beats_track = hierarchy.get("beats") or {}
    beat_marks = beats_track.get("marks", []) if isinstance(beats_track, dict) else []
    section_beat_times = [
        m["time_ms"] for m in beat_marks
        if start_ms <= m.get("time_ms", -1) < end_ms
    ]
    if len(section_beat_times) >= 2:
        intervals = [
            section_beat_times[i + 1] - section_beat_times[i]
            for i in range(len(section_beat_times) - 1)
        ]
        mean_interval_ms = _mean(intervals)
        local_tempo_bpm = float(60_000.0 / mean_interval_ms) if mean_interval_ms > 0 else float(hierarchy.get("estimated_bpm", 120.0))
    else:
        local_tempo_bpm = float(hierarchy.get("estimated_bpm", 120.0))

    # ── Dominant note ────────────────────────────────────────────────────────
    chords_track = hierarchy.get("chords") or {}
    chord_marks = chords_track.get("marks", []) if isinstance(chords_track, dict) else []
    section_chords = [
        m.get("label", "C") for m in chord_marks
        if start_ms <= m.get("time_ms", -1) < end_ms
    ]
    if section_chords:
        # Extract root note from chord label
        root_counts: dict[str, int] = {}
        for chord in section_chords:
            root = chord[0] if chord else "C"
            if len(chord) > 1 and chord[1] in ("#", "b"):
                root = chord[:2]
            root_counts[root] = root_counts.get(root, 0) + 1
        dominant_note = max(root_counts, key=lambda r: root_counts[r])
    else:
        dominant_note = "C"

    # ── Frequency bands ──────────────────────────────────────────────────────
    band_weights = _BAND_WEIGHTS_BY_ENERGY_LEVEL[energy_level]
    frequency_bands: dict = {}
    for band_name, weight in zip(_FREQUENCY_BAND_NAMES, band_weights):
        band_mean = float(mean_energy * weight)
        band_relative = float(weight)
        frequency_bands[band_name] = {"mean": band_mean, "relative": band_relative}

    # ── Per-stem averages ────────────────────────────────────────────────────
    stem_avgs: dict[str, float] = {s: _stem_mean_in_range(s) for s in _STEM_NAMES}
    max_stem_rms = max(stem_avgs.values()) if stem_avgs else 0.0

    dominant_stem = max(stem_avgs, key=lambda s: stem_avgs[s]) if stem_avgs else "full_mix"

    if max_stem_rms > 0:
        stem_levels = {
            s: float(min(1.0, max(0.0, stem_avgs[s] / max_stem_rms)))
            for s in _STEM_NAMES
        }
        active_stems = [s for s in _STEM_NAMES if stem_avgs[s] > 0.1 * max_stem_rms]
    else:
        stem_levels = {s: 0.0 for s in _STEM_NAMES}
        active_stems = []

    vocals_active: bool = bool(stem_avgs.get("vocals", 0.0) > 0.05)

    # ── Per-stem onset counts ────────────────────────────────────────────────
    onset_counts: dict[str, int] = {}
    for stem_name in _STEM_NAMES:
        stem_events = events.get(stem_name)
        if stem_events and isinstance(stem_events, dict):
            marks = stem_events.get("marks", [])
            count = sum(1 for m in marks if start_ms <= m.get("time_ms", -1) < end_ms)
        else:
            count = 0
        onset_counts[stem_name] = count

    # ── Leader stem ─────────────────────────────────────────────────────────
    max_onsets = max(onset_counts.values()) if onset_counts else 0
    leader_stem = dominant_stem
    if max_onsets > 0:
        for s in _STEM_NAMES:
            if onset_counts[s] == max_onsets:
                leader_stem = s
                break

    # ── Drum pattern ─────────────────────────────────────────────────────────
    drum_events = events.get("drums")
    drum_pattern = None
    if drum_events and isinstance(drum_events, dict):
        drum_marks = drum_events.get("marks", [])
        section_drum_marks = [
            m for m in drum_marks if start_ms <= m.get("time_ms", -1) < end_ms
        ]
        if section_drum_marks:
            kick_count = sum(1 for m in section_drum_marks if m.get("label") == "kick")
            snare_count = sum(1 for m in section_drum_marks if m.get("label") == "snare")
            hihat_count = sum(1 for m in section_drum_marks if m.get("label") == "hihat")
            total_count = len(section_drum_marks)
            total_density = float(total_count / duration_sec) if duration_sec > 0 else 0.0

            # Dominant element
            element_counts = {"kick": kick_count, "snare": snare_count, "hihat": hihat_count}
            dominant_element = max(element_counts, key=lambda e: element_counts[e])

            # Style
            if total_density < 1.0:
                style = "sparse"
            elif total_count > 0 and kick_count / total_count > 0.5:
                style = "driving"
            elif total_count > 0 and snare_count / total_count > 0.4:
                style = "fills"
            elif total_count > 0 and hihat_count / total_count > 0.6:
                style = "riding"
            else:
                style = "balanced"

            drum_pattern = {
                "kick_count": kick_count,
                "snare_count": snare_count,
                "hihat_count": hihat_count,
                "total_density": total_density,
                "dominant_element": dominant_element,
                "style": style,
            }

    # ── Tightness ─────────────────────────────────────────────────────────────
    drums_active = "drums" in active_stems
    bass_active = "bass" in active_stems
    tightness: str | None = "unison" if (drums_active and bass_active) else None

    character = {
        "energy_score": energy_score,
        "energy_peak": energy_peak,
        "energy_variance": energy_variance,
        "energy_level": energy_level,
        "energy_trajectory": energy_trajectory,
        "texture": texture,
        "hp_ratio": hp_ratio,
        "onset_density": onset_density,
        "spectral_brightness": spectral_brightness,
        "spectral_centroid_hz": spectral_centroid_hz,
        "spectral_flatness": spectral_flatness,
        "local_tempo_bpm": local_tempo_bpm,
        "dominant_note": dominant_note,
        "frequency_bands": frequency_bands,
    }

    stems = {
        "dominant_stem": dominant_stem,
        "active_stems": active_stems,
        "stem_levels": stem_levels,
        "vocals_active": vocals_active,
        "onset_counts": onset_counts,
        "leader_stem": leader_stem,
        "leader_transitions": [],
        "solos": [],
        "drum_pattern": drum_pattern,
        "tightness": tightness,
        "handoffs": [],
        "chords": [],
        "other_stem_class": None,
    }

    return {"character": character, "stems": stems}
