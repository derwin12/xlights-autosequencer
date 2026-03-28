"""Section energy derivation from L5 energy curves and L0 impacts."""
from __future__ import annotations

from src.analyzer.result import TimingMark, ValueCurve
from src.generator.models import SectionEnergy, energy_to_mood

# Reference loudness for normalization (Spotify/YouTube streaming target)
_REFERENCE_LUFS = -14.0


def derive_section_energies(
    sections: list[TimingMark],
    energy_curves: dict[str, ValueCurve],
    energy_impacts: list[TimingMark],
    dynamic_complexity: float | None = None,
    loudness_lufs: float | None = None,
) -> list[SectionEnergy]:
    """Derive energy scores for each section from L5 curves and L0 impacts.

    For each section:
    1. Extract full_mix energy curve frames within the section's time range
    2. Average those frame values -> base_energy (0-100)
    3. Apply LUFS normalization (so quiet and loud songs produce comparable scores)
    4. Count L0 energy_impacts within the section
    5. Boost: final = min(100, base_energy + impact_count * 5)
    6. Apply dynamic range scaling (from essentia dynamic_complexity)
    7. Map to mood tier: 0-33=ethereal, 34-66=structural, 67-100=aggressive
    """
    full_mix = energy_curves.get("full_mix")

    # LUFS normalization multiplier: scales energy so songs at different
    # loudness levels produce comparable brightness.
    # A song at -35 LUFS (quiet) gets boosted; one at -14 LUFS stays 1.0.
    lufs_multiplier = _lufs_normalization_factor(loudness_lufs)

    # Clamp section boundaries so they don't overlap —
    # each section ends at the next section's start time
    clamped: list[tuple[int, int, str]] = []
    for i, section in enumerate(sections):
        start_ms = section.time_ms
        end_ms = start_ms + (section.duration_ms or 0)
        if i + 1 < len(sections):
            next_start = sections[i + 1].time_ms
            end_ms = min(end_ms, next_start)
        clamped.append((start_ms, end_ms, section.label or "unknown"))

    raw_energies: list[tuple[int, int, str, int, int]] = []
    for start_ms, end_ms, label in clamped:
        if end_ms <= start_ms:
            continue
        base_energy = _average_energy_in_range(full_mix, start_ms, end_ms)

        # Apply LUFS normalization
        base_energy = min(100, int(base_energy * lufs_multiplier))

        impact_count = _count_impacts_in_range(energy_impacts, start_ms, end_ms)
        final_energy = min(100, base_energy + impact_count * 5)
        raw_energies.append((start_ms, end_ms, label, final_energy, impact_count))

    # Apply dynamic range scaling if essentia data is available
    if dynamic_complexity is not None and len(raw_energies) >= 2:
        energies = [e for _, _, _, e, _ in raw_energies]
        scaled = _apply_dynamic_scaling(energies, dynamic_complexity)
        raw_energies = [
            (s, e, l, scaled[i], ic)
            for i, (s, e, l, _, ic) in enumerate(raw_energies)
        ]

    result: list[SectionEnergy] = []
    for start_ms, end_ms, label, final_energy, impact_count in raw_energies:
        result.append(SectionEnergy(
            label=label,
            start_ms=start_ms,
            end_ms=end_ms,
            energy_score=final_energy,
            mood_tier=energy_to_mood(final_energy),
            impact_count=impact_count,
        ))

    return result


def _lufs_normalization_factor(loudness_lufs: float | None) -> float:
    """Compute a multiplier to normalize energy relative to reference loudness.

    Songs quieter than -14 LUFS get boosted; louder songs are attenuated.
    The scaling is gentle — we use the dB difference to compute a linear
    gain factor, clamped to [0.5, 2.5] to avoid extreme corrections.

    Examples:
      -14 LUFS (streaming ref)  → 1.0x (no change)
      -24 LUFS (10dB quieter)   → 1.5x boost
      -35 LUFS (21dB quieter)   → 2.1x boost
       -8 LUFS (6dB louder)     → 0.8x attenuation
    """
    if loudness_lufs is None:
        return 1.0

    db_diff = _REFERENCE_LUFS - loudness_lufs  # positive = song is quieter
    # Convert dB difference to a gentle linear multiplier
    # 10dB → ~1.5x, 20dB → ~2.0x (sublinear, not full dB-to-power)
    multiplier = 1.0 + db_diff * 0.05
    return max(0.5, min(2.5, multiplier))


def _apply_dynamic_scaling(
    energies: list[int], dynamic_complexity: float
) -> list[int]:
    """Scale energy scores based on dynamic complexity.

    Dynamic complexity drives how much of the 0-100 brightness range to use:
      < 2 (compressed):  map to 45-85  (narrow range, avoid extremes)
      2-5 (moderate):    map to 25-100 (moderate range)
      > 5 (wide):        map to 10-100 (full range, quiet sections go dim)

    The scaling is relative: the quietest section maps to floor, loudest to ceiling.
    """
    e_min = min(energies)
    e_max = max(energies)
    if e_max == e_min:
        return energies

    # Determine floor and ceiling based on dynamic complexity
    dc = max(0.0, min(10.0, dynamic_complexity))
    if dc < 2:
        floor, ceiling = 45, 85
    elif dc < 5:
        # Linear interpolation: dc=2 -> (45,85), dc=5 -> (10,100)
        t = (dc - 2) / 3.0
        floor = int(45 - 35 * t)
        ceiling = int(85 + 15 * t)
    else:
        floor, ceiling = 10, 100

    result = []
    for e in energies:
        normalized = (e - e_min) / (e_max - e_min)
        scaled = int(floor + normalized * (ceiling - floor))
        result.append(max(0, min(100, scaled)))
    return result


def slice_curve(
    curve: ValueCurve | None, start_ms: int, end_ms: int
) -> list[int]:
    """Extract values from a ValueCurve within a time range.

    Shared utility — also used by value_curves.py.
    """
    if curve is None or not curve.values or curve.fps <= 0:
        return []

    ms_per_frame = 1000 / curve.fps
    start_frame = max(0, int(start_ms / ms_per_frame))
    end_frame = min(len(curve.values), int(end_ms / ms_per_frame))

    if start_frame >= end_frame:
        return []

    return curve.values[start_frame:end_frame]


def _average_energy_in_range(
    curve: ValueCurve | None, start_ms: int, end_ms: int
) -> int:
    """Average the energy curve values within a time range."""
    frames = slice_curve(curve, start_ms, end_ms)
    if not frames:
        return 0
    return round(sum(frames) / len(frames))


def _count_impacts_in_range(
    impacts: list[TimingMark], start_ms: int, end_ms: int
) -> int:
    """Count how many L0 energy impacts fall within a time range."""
    return sum(1 for imp in impacts if start_ms <= imp.time_ms < end_ms)
