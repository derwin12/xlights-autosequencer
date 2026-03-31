"""Section role classifier for song story tool.

Classifies each (start_ms, end_ms) section into a named role using three
signals: vocal activity, positional rules, and energy-based ranking.
"""
from __future__ import annotations

VALID_ROLES = frozenset({
    "intro", "verse", "pre_chorus", "chorus", "post_chorus", "bridge",
    "instrumental_break", "climax", "ambient_bridge", "outro", "interlude",
})


def _avg_curve(
    curve: dict,
    start_ms: int,
    end_ms: int,
) -> float:
    """Return the average value of a energy curve dict over [start_ms, end_ms)."""
    sample_rate: float = curve.get("sample_rate") or curve.get("fps") or 10.0
    values: list[float] = curve["values"]
    n = len(values)

    start_idx = int(start_ms / 1000.0 * sample_rate)
    end_idx = int(end_ms / 1000.0 * sample_rate)
    start_idx = max(0, min(start_idx, n))
    end_idx = max(0, min(end_idx, n))

    if start_idx >= end_idx:
        return 0.0
    window = values[start_idx:end_idx]
    return sum(window) / len(window) if window else 0.0


def classify_section_roles(
    sections: list[tuple[int, int]],
    hierarchy: dict,
) -> list[dict]:
    """Classify each section into a named role.

    Args:
        sections:  List of (start_ms, end_ms) tuples.
        hierarchy: HierarchyResult-compatible dict containing energy_curves.

    Returns:
        List of dicts with 'role' (str) and 'confidence' (float) keys,
        one per input section.
    """
    if not sections:
        return []

    energy_curves: dict = hierarchy.get("energy_curves", {})
    vocals_curve: dict | None = energy_curves.get("vocals")
    full_mix_curve: dict | None = energy_curves.get("full_mix")

    n = len(sections)

    # --- Compute per-section signals ---
    vocals_avg: list[float] = []
    energy_avg: list[float] = []

    for start, end in sections:
        v = _avg_curve(vocals_curve, start, end) if vocals_curve else 0.0
        e = _avg_curve(full_mix_curve, start, end) if full_mix_curve else 0.0
        vocals_avg.append(v)
        energy_avg.append(e)

    VOCAL_THRESHOLD = 0.05

    # Determine if this is an instrumental song (no section exceeds threshold)
    has_any_vocal = any(v > VOCAL_THRESHOLD for v in vocals_avg)

    results: list[dict] = [{}] * n

    if not has_any_vocal:
        # --- Instrumental fallback ---
        for i in range(n):
            if i == 0:
                role, conf = "intro", 0.85
            elif i == n - 1:
                role, conf = "outro", 0.85
            else:
                # Alternate based on energy: higher → instrumental_break, lower → interlude
                e = energy_avg[i]
                if e >= 0.4:
                    role, conf = "instrumental_break", 0.60
                else:
                    role, conf = "interlude", 0.55
            results[i] = {"role": role, "confidence": float(conf)}
        return results

    # --- Vocal song: classify each section ---
    # Collect energy values for vocal sections to establish percentile thresholds
    vocal_energies = [
        energy_avg[i]
        for i in range(n)
        if vocals_avg[i] > VOCAL_THRESHOLD
    ]
    if len(vocal_energies) >= 2:
        vocal_energies_sorted = sorted(vocal_energies)
        vocal_median = vocal_energies_sorted[len(vocal_energies_sorted) // 2]
        vocal_max = vocal_energies_sorted[-1]
        # Threshold: top 30% of vocal energy range → chorus
        chorus_threshold = vocal_median + 0.6 * (vocal_max - vocal_median)
    elif len(vocal_energies) == 1:
        # Single vocal section — use absolute threshold: 0.65 → chorus
        vocal_median = vocal_energies[0]
        vocal_max = vocal_energies[0]
        chorus_threshold = 0.65
    else:
        vocal_median = 0.5
        vocal_max = 1.0
        chorus_threshold = 0.65

    for i in range(n):
        is_first = i == 0
        is_last = i == n - 1
        v = vocals_avg[i]
        e = energy_avg[i]
        is_vocal = v > VOCAL_THRESHOLD

        if not is_vocal:
            # Non-vocal section
            if is_first:
                role, conf = "intro", 0.85
            elif is_last and e < 0.3:
                role, conf = "outro", 0.85
            elif is_last:
                role, conf = "outro", 0.80
            else:
                # Short non-vocal surrounded by vocal sections
                prev_vocal = vocals_avg[i - 1] > VOCAL_THRESHOLD if i > 0 else False
                next_vocal = vocals_avg[i + 1] > VOCAL_THRESHOLD if i < n - 1 else False
                if prev_vocal and next_vocal:
                    role, conf = "instrumental_break", 0.65
                else:
                    role, conf = "interlude", 0.60
        else:
            # Vocal section — classify by energy rank
            if e >= chorus_threshold:
                role = "chorus"
                conf = 0.75 + 0.10 * min(1.0, (e - chorus_threshold) / max(0.001, vocal_max - chorus_threshold))
            else:
                role = "verse"
                conf = 0.65 + 0.10 * min(1.0, e / max(0.001, chorus_threshold))

        results[i] = {"role": role, "confidence": float(round(conf, 4))}

    return results
