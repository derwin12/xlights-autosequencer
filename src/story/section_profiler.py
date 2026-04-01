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

def _detect_accents(
    energy_curves: dict,
    stem_name: str,
    start_ms: int,
    end_ms: int,
    floor: int = 20,
) -> list[dict]:
    """Detect dramatic accent peaks on a stem's energy curve.

    Finds all local peaks, computes median intensity, keeps only outliers
    that significantly exceed the normal level. Timestamps are snapped to
    the **onset** (rising edge) of each peak so they align with the
    visible waveform transient rather than the smoothed envelope peak.

    Returns list of {"time_ms": int, "intensity": int} dicts, sorted by time.
    """
    curve = energy_curves.get(stem_name, {})
    vals = curve.get("values", [])
    fps = float(curve.get("fps") or curve.get("sample_rate") or 10.0)
    if not vals:
        return []

    si = int(start_ms / 1000 * fps)
    ei = int(end_ms / 1000 * fps)
    section_vals = vals[si:ei]
    if not section_vals or max(section_vals) < floor:
        return []

    # Step 1: Find all local peaks above the noise floor
    window = max(1, int(fps * 0.15))   # ~150ms peak window
    min_gap = int(fps * 0.3)           # ~300ms between peaks
    all_peaks: list[tuple[int, int]] = []  # (onset_ms, peak_intensity)

    i = si
    while i < min(ei, len(vals)):
        chunk = vals[i:i + window]
        peak = max(chunk) if chunk else 0
        if peak >= floor:
            # Find the actual peak position within the chunk
            peak_offset = chunk.index(peak)
            peak_idx = i + peak_offset

            # Snap to onset: scan backwards from peak to find where the
            # energy started rising (crossed below 40% of peak value).
            # This aligns the marker with the transient attack, not the
            # smoothed envelope peak which lags behind.
            onset_threshold = peak * 0.4
            onset_idx = peak_idx
            lookback = max(1, int(fps * 0.15))  # up to ~150ms back
            for j in range(peak_idx - 1, max(si, peak_idx - lookback) - 1, -1):
                if j < len(vals) and vals[j] <= onset_threshold:
                    onset_idx = j + 1
                    break

            onset_ms = int(onset_idx / fps * 1000)
            all_peaks.append((onset_ms, int(peak)))
            i += max(window, min_gap)
        else:
            i += 1

    if len(all_peaks) < 3:
        return []

    # Step 2: Keep only outlier peaks above the normal level
    sorted_intensities = sorted(p[1] for p in all_peaks)
    n_peaks = len(sorted_intensities)
    median_intensity = sorted_intensities[n_peaks // 2]
    p75 = sorted_intensities[int(n_peaks * 0.75)]
    p90 = sorted_intensities[int(n_peaks * 0.90)]
    section_max = sorted_intensities[-1]

    # Threshold: top ~10% of peaks, but never higher than 90% of max.
    # The cap prevents the threshold from exceeding 100 when median is high
    # (e.g. songs with uniformly sharp drum transients).
    big_threshold = min(
        max(p75 * 1.3, median_intensity * 1.8, 50),
        section_max * 0.90,
    )
    # Only flag accents if there's meaningful dynamic range (P90 > median * 1.2).
    # If all peaks are nearly the same intensity, there are no standout accents.
    if p90 <= median_intensity * 1.2:
        return []

    return [
        {"time_ms": t, "intensity": v}
        for t, v in all_peaks if v >= big_threshold
    ]


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
    # Compute from actual stem balance: high-frequency stems (guitar, piano,
    # vocals) vs low-frequency stems (bass, drums). A section dominated by
    # treble instruments is "bright" regardless of overall energy level.
    treble_stems = ["guitar", "piano", "vocals"]
    low_stems = ["bass", "drums"]
    treble_energy = sum(_stem_mean_in_range(s) for s in treble_stems)
    low_energy = sum(_stem_mean_in_range(s) for s in low_stems)
    total_stem_energy = treble_energy + low_energy

    if total_stem_energy > 0:
        treble_ratio = treble_energy / total_stem_energy
    else:
        treble_ratio = 0.5  # no data → neutral

    if treble_ratio > 0.65:
        spectral_brightness = "bright"
    elif treble_ratio < 0.35:
        spectral_brightness = "dark"
    else:
        spectral_brightness = "neutral"

    # ── Spectral centroid (estimated from stem balance) ──────────────────────
    # Map treble_ratio (0–1) to approximate centroid Hz range (300–5000)
    spectral_centroid_hz = int(300 + treble_ratio * 4700)

    # ── Spectral flatness (from spectral flux variation) ────────────────────
    # High spectral flux variance → tonal (peaky spectrum) → low flatness
    # Low variance → noise-like (flat spectrum) → high flatness
    sf_curve = hierarchy.get("spectral_flux", {})
    sf_vals = sf_curve.get("values", [])
    sf_fps = float(sf_curve.get("fps") or sf_curve.get("sample_rate") or 10.0)
    sf_frames = _get_frames_in_range(sf_vals, sf_fps, start_ms, end_ms)
    if sf_frames:
        sf_mean = _mean(sf_frames)
        sf_std = _stddev(sf_frames)
        # Coefficient of variation: high CV → tonal, low CV → flat/noisy
        sf_cv = sf_std / sf_mean if sf_mean > 0 else 0.0
        spectral_flatness = float(max(0.0, min(1.0, 1.0 - sf_cv)))
    else:
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
    # Demucs routes some bass drum energy to the "bass" stem, so include bass
    # onset count as a proxy for low-frequency percussive hits.
    drum_events = events.get("drums")
    bass_events = events.get("bass")
    drum_pattern = None

    def _count_marks_in_section(evt, label_filter=None):
        if not evt or not isinstance(evt, dict):
            return 0
        marks = evt.get("marks", [])
        return sum(1 for m in marks
                   if start_ms <= m.get("time_ms", -1) < end_ms
                   and (label_filter is None or m.get("label") == label_filter))

    if drum_events and isinstance(drum_events, dict):
        drum_marks = drum_events.get("marks", [])
        section_drum_marks = [
            m for m in drum_marks if start_ms <= m.get("time_ms", -1) < end_ms
        ]

        kick_count = sum(1 for m in section_drum_marks if m.get("label") == "kick")
        snare_count = sum(1 for m in section_drum_marks if m.get("label") == "snare")
        hihat_count = sum(1 for m in section_drum_marks if m.get("label") == "hihat")
        total_drum_count = len(section_drum_marks)

        # Bass onsets as proxy for sub-bass kick hits (demucs routes bass drums here)
        bass_onset_count = _count_marks_in_section(bass_events)

        # Combined percussion = drum onsets + bass onsets (deduplicated by density)
        combined_count = total_drum_count + bass_onset_count
        combined_density = float(combined_count / duration_sec) if duration_sec > 0 else 0.0
        drum_density = float(total_drum_count / duration_sec) if duration_sec > 0 else 0.0

        # Drum energy from the curves (for intensity measure)
        drum_energy = _stem_mean_in_range("drums")
        bass_energy = _stem_mean_in_range("bass")

        # Dominant element
        element_counts = {"kick": kick_count, "snare": snare_count, "hihat": hihat_count}
        dominant_element = max(element_counts, key=lambda e: element_counts[e])

        # Style classification
        kick_ratio = kick_count / total_drum_count if total_drum_count > 0 else 0
        snare_ratio = snare_count / total_drum_count if total_drum_count > 0 else 0
        hihat_ratio = hihat_count / total_drum_count if total_drum_count > 0 else 0

        # "kick_heavy": pronounced bass drum — either high kick ratio with
        # strong drum/bass energy, or very few onsets but high bass energy
        # (sub-bass drops that demucs puts in bass stem)
        bass_dominant = bass_energy > drum_energy * 1.5
        kick_dominant = kick_ratio > 0.6

        if combined_density < 0.3:
            style = "sparse"
        elif kick_dominant and (drum_energy > 20 or bass_energy > 20):
            style = "kick_heavy"
        elif bass_dominant and combined_density > 0.5:
            style = "kick_heavy"  # sub-bass hits via bass stem
        elif kick_ratio > 0.5:
            style = "driving"
        elif snare_ratio > 0.4:
            style = "fills"
        elif hihat_ratio > 0.6:
            style = "riding"
        else:
            style = "balanced"

        # ── Detect big hits on drums ──
        big_hits = _detect_accents(energy_curves, "drums", start_ms, end_ms)

        drum_pattern = {
            "kick_count": kick_count,
            "snare_count": snare_count,
            "hihat_count": hihat_count,
            "bass_onset_count": bass_onset_count,
            "total_density": drum_density,
            "combined_density": combined_density,
            "drum_energy": round(drum_energy, 1),
            "bass_energy": round(bass_energy, 1),
            "dominant_element": dominant_element,
            "style": style,
            "big_hits": big_hits,
            "big_hit_count": len(big_hits),
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

    # ── Per-stem accents (outlier peaks on each stem's energy curve) ────────
    stem_accents: dict[str, list[dict]] = {}
    for sn in _STEM_NAMES:
        accents = _detect_accents(energy_curves, sn, start_ms, end_ms)
        if accents:
            stem_accents[sn] = accents

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
        "accents": stem_accents,
    }

    return {"character": character, "stems": stems}
