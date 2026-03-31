"""Stem curve extraction for song story tool.

Downsamples per-stem energy curves from hierarchy (typically 10 fps)
to a 2 Hz output array suitable for value-curve animation.
"""
from __future__ import annotations

import math


_STEM_NAMES = ("drums", "bass", "vocals", "guitar", "piano", "other")


def _downsample(values: list[float], source_rate: float, target_rate: float, n_out: int) -> list[float]:
    """Average source frames into output windows at target_rate Hz.

    Args:
        values: Source frame values.
        source_rate: Frames per second of source data.
        target_rate: Desired output frames per second.
        n_out: Number of output frames to produce.

    Returns:
        List of Python floats of length n_out, clipped to [0.0, 1.0].
    """
    out = []
    frames_per_out = source_rate / target_rate  # e.g. 10 / 2 = 5
    n_src = len(values)

    for i in range(n_out):
        start_f = i * frames_per_out
        end_f = (i + 1) * frames_per_out
        i_start = int(start_f)
        i_end = int(math.ceil(end_f))
        # Clamp to source length
        i_start = max(0, min(i_start, n_src))
        i_end = max(0, min(i_end, n_src))
        if i_start >= i_end:
            out.append(0.0)
        else:
            window = values[i_start:i_end]
            avg = sum(window) / len(window)
            out.append(float(min(1.0, max(0.0, avg))))

    return out


def extract_stem_curves(hierarchy: dict, duration_ms: int) -> dict:
    """Extract and downsample stem energy curves to 2 Hz output arrays.

    Args:
        hierarchy: HierarchyResult dict with 'energy_curves' key.
        duration_ms: Song duration in milliseconds.

    Returns:
        StemCurves dict with 'sample_rate_hz', per-stem 'rms' arrays,
        and 'full_mix' dict with rms/spectral_centroid_hz/harmonic_rms/percussive_rms.
    """
    target_rate: int = 2
    duration_sec = duration_ms / 1000.0
    n_out = math.ceil(duration_sec * target_rate)

    energy_curves: dict = hierarchy.get("energy_curves", {})

    def _get_stem_rms(stem_name: str) -> list[float]:
        if stem_name not in energy_curves:
            return [0.0] * n_out
        curve = energy_curves[stem_name]
        src_rate = float(curve.get("sample_rate") or curve.get("fps") or 10.0)
        values = curve.get("values", [])
        return _downsample(values, src_rate, target_rate, n_out)

    result: dict = {"sample_rate_hz": target_rate}

    # Per-stem arrays
    for stem in _STEM_NAMES:
        result[stem] = {"rms": _get_stem_rms(stem)}

    # Full mix rms
    full_mix_rms = _get_stem_rms("full_mix")

    # Spectral centroid: placeholder if no real data
    if "spectral_centroid" in energy_curves:
        spectral_centroid_hz = _get_stem_rms("spectral_centroid")
    else:
        spectral_centroid_hz = [
            float(v * 4000.0 + 500.0) for v in full_mix_rms
        ]

    # Harmonic RMS: from HPSS if available, else 0.6 * full_mix_rms
    if "harmonic" in energy_curves:
        harmonic_rms = _get_stem_rms("harmonic")
    elif "harmonic_rms" in energy_curves:
        harmonic_rms = _get_stem_rms("harmonic_rms")
    else:
        harmonic_rms = [float(v * 0.6) for v in full_mix_rms]

    # Percussive RMS: from HPSS if available, else 0.4 * full_mix_rms
    if "percussive" in energy_curves:
        percussive_rms = _get_stem_rms("percussive")
    elif "percussive_rms" in energy_curves:
        percussive_rms = _get_stem_rms("percussive_rms")
    else:
        percussive_rms = [float(v * 0.4) for v in full_mix_rms]

    result["full_mix"] = {
        "rms": full_mix_rms,
        "spectral_centroid_hz": spectral_centroid_hz,
        "harmonic_rms": harmonic_rms,
        "percussive_rms": percussive_rms,
    }

    return result
