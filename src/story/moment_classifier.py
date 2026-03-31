"""Moment classifier for the song story tool.

Detects and classifies musical moments from a HierarchyResult-compatible dict.
"""
from __future__ import annotations


# ── Type weights ───────────────────────────────────────────────────────────────

_TYPE_WEIGHTS: dict[str, float] = {
    "silence": 1.0,
    "energy_drop": 0.9,
    "vocal_entry": 0.85,
    "energy_surge": 0.8,
    "percussive_impact": 0.7,
    "handoff": 0.6,
    "brightness_spike": 0.5,
    "texture_shift": 0.4,
    "tempo_change": 0.3,
    "vocal_exit": 0.3,
}

_VOCAL_THRESHOLD = 0.05
_PERSISTENCE_FRAMES = 5  # consecutive frames required to confirm a crossing


def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS.mmm."""
    total_ms = round(seconds * 1000)
    minutes = total_ms // 60_000
    remaining = total_ms % 60_000
    secs = remaining // 1000
    millis = remaining % 1000
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def _assign_section(time_ms: float, sections: list[tuple[int, int]]) -> str:
    """Return section id (s01, s02, ...) for the given time_ms."""
    for idx, (start, end) in enumerate(sections, start=1):
        if start <= time_ms < end:
            return f"s{idx:02d}"
    return "s01"


def _classify_patterns(raw_moments: list[dict]) -> dict[int, str]:
    """Classify temporal patterns per moment index.

    Returns a dict mapping list-index → pattern string.
    """
    n = len(raw_moments)
    patterns = ["isolated"] * n

    # Group indices by type
    by_type: dict[str, list[int]] = {}
    for i, m in enumerate(raw_moments):
        by_type.setdefault(m["type"], []).append(i)

    for typ, indices in by_type.items():
        times = [raw_moments[i]["time"] for i in indices]

        for i_pos, idx in enumerate(indices):
            t = times[i_pos]

            # Gather nearby same-type moments (within 30s window)
            nearby_times = [tt for tt in times if abs(tt - t) <= 30]
            within_5s = [tt for tt in times if abs(tt - t) <= 5]
            within_1s = [tt for tt in times if abs(tt - t) <= 1]

            # double_tap: two moments of same type within 1 second
            if len(within_1s) >= 2:
                patterns[idx] = "double_tap"
                continue

            # plateau: 3+ moments of same type within 5 seconds
            if len(within_5s) >= 3:
                patterns[idx] = "plateau"
                continue

            # cascade: moments within 3 seconds where each is higher energy than previous
            # Check if this moment is part of a rising-energy sequence within 3s
            within_3s_indices = [
                j for j, (jidx, tt) in enumerate(zip(indices, times))
                if abs(tt - t) <= 3
            ]
            if len(within_3s_indices) >= 2:
                # Check if the sequence is monotonically increasing in intensity
                seq_intensities = [raw_moments[indices[j]]["intensity"] for j in within_3s_indices]
                seq_times = [times[j] for j in within_3s_indices]
                # Sort by time
                sorted_pairs = sorted(zip(seq_times, seq_intensities))
                is_cascade = all(
                    sorted_pairs[k + 1][1] > sorted_pairs[k][1]
                    for k in range(len(sorted_pairs) - 1)
                )
                if is_cascade:
                    patterns[idx] = "cascade"
                    continue

            # scattered: 2+ moments of same type spread across 5-30 seconds
            spread = [tt for tt in nearby_times if 5 < abs(tt - t) <= 30]
            if len(spread) >= 1:
                patterns[idx] = "scattered"
                continue

    return {i: patterns[i] for i in range(n)}


def classify_moments(
    hierarchy: dict,
    sections: list[tuple[int, int]],
) -> list[dict]:
    """Classify musical moments from a hierarchy dict.

    Args:
        hierarchy: HierarchyResult-compatible dict (from HierarchyResult.to_dict()).
        sections: List of (start_ms, end_ms) tuples defining section boundaries.

    Returns:
        List of moment dicts sorted by time ascending, with sequential IDs m001, m002, ...
    """
    raw: list[dict] = []

    # ── 1. Energy surges ───────────────────────────────────────────────────────
    for mark in hierarchy.get("energy_impacts") or []:
        time_ms = mark["time_ms"]
        intensity = float(mark.get("confidence", 0.5))
        time_sec = time_ms / 1000.0
        raw.append({
            "time": time_sec,
            "time_fmt": _fmt_time(time_sec),
            "section_id": _assign_section(time_ms, sections),
            "type": "energy_surge",
            "stem": "full_mix",
            "intensity": intensity,
            "description": f"Energy surge at {_fmt_time(time_sec)}",
            "dismissed": False,
        })

    # ── 2. Energy drops ────────────────────────────────────────────────────────
    for mark in hierarchy.get("energy_drops") or []:
        time_ms = mark["time_ms"]
        intensity = float(mark.get("confidence", 0.5))
        time_sec = time_ms / 1000.0
        raw.append({
            "time": time_sec,
            "time_fmt": _fmt_time(time_sec),
            "section_id": _assign_section(time_ms, sections),
            "type": "energy_drop",
            "stem": "full_mix",
            "intensity": intensity,
            "description": f"Energy drop at {_fmt_time(time_sec)}",
            "dismissed": False,
        })

    # ── 3. Silence / gaps ─────────────────────────────────────────────────────
    for gap in hierarchy.get("gaps") or []:
        time_ms = gap["time_ms"]
        intensity = float(gap.get("confidence", 0.5))
        time_sec = time_ms / 1000.0
        raw.append({
            "time": time_sec,
            "time_fmt": _fmt_time(time_sec),
            "section_id": _assign_section(time_ms, sections),
            "type": "silence",
            "stem": "full_mix",
            "intensity": intensity,
            "description": f"Silence/gap at {_fmt_time(time_sec)}",
            "dismissed": False,
        })

    # ── 4. Vocal entry / exit ─────────────────────────────────────────────────
    energy_curves = hierarchy.get("energy_curves") or {}
    vocals_curve = energy_curves.get("vocals")
    if vocals_curve:
        values: list[float] = vocals_curve["values"]
        sample_rate: float = vocals_curve.get("sample_rate") or vocals_curve.get("fps") or 10.0
        n_frames = len(values)

        def _check_persistence(start_idx: int, is_entry: bool, window: int = _PERSISTENCE_FRAMES) -> bool:
            """Return True if the crossing persists for `window` consecutive frames."""
            for k in range(1, window + 1):
                check_idx = start_idx + k
                if check_idx >= n_frames:
                    return False
                v = values[check_idx]
                if is_entry and v < _VOCAL_THRESHOLD:
                    return False
                if not is_entry and v >= _VOCAL_THRESHOLD:
                    return False
            return True

        for i in range(1, n_frames):
            prev = values[i - 1]
            curr = values[i]

            # Vocal entry: rising edge crossing 0.05
            if prev < _VOCAL_THRESHOLD <= curr:
                if _check_persistence(i, is_entry=True):
                    time_sec = i / sample_rate
                    time_ms = time_sec * 1000.0
                    intensity = float(abs(curr - prev))
                    # Ensure intensity > 0
                    if intensity == 0.0:
                        intensity = float(curr)
                    raw.append({
                        "time": time_sec,
                        "time_fmt": _fmt_time(time_sec),
                        "section_id": _assign_section(time_ms, sections),
                        "type": "vocal_entry",
                        "stem": "vocals",
                        "intensity": intensity,
                        "description": f"Vocals enter at {_fmt_time(time_sec)}",
                        "dismissed": False,
                    })

            # Vocal exit: falling edge crossing 0.05
            elif prev >= _VOCAL_THRESHOLD > curr:
                if _check_persistence(i, is_entry=False):
                    time_sec = i / sample_rate
                    time_ms = time_sec * 1000.0
                    intensity = float(abs(curr - prev))
                    if intensity == 0.0:
                        intensity = float(prev)
                    raw.append({
                        "time": time_sec,
                        "time_fmt": _fmt_time(time_sec),
                        "section_id": _assign_section(time_ms, sections),
                        "type": "vocal_exit",
                        "stem": "vocals",
                        "intensity": intensity,
                        "description": f"Vocals fade at {_fmt_time(time_sec)}",
                        "dismissed": False,
                    })

    # ── Deduplicate: same (type, time) ────────────────────────────────────────
    seen: set[tuple[float, str]] = set()
    deduped: list[dict] = []
    for m in raw:
        key = (round(m["time"], 3), m["type"])
        if key not in seen:
            seen.add(key)
            deduped.append(m)
    raw = deduped

    # ── Sort by time ──────────────────────────────────────────────────────────
    raw.sort(key=lambda m: m["time"])

    # ── Pattern classification ────────────────────────────────────────────────
    idx_to_pattern = _classify_patterns(raw)
    for i, m in enumerate(raw):
        m["pattern"] = idx_to_pattern[i]

    # ── Compute section boundaries set for boundary_multiplier ───────────────
    boundary_times_sec: set[float] = set()
    for start_ms, end_ms in sections:
        boundary_times_sec.add(start_ms / 1000.0)
        boundary_times_sec.add(end_ms / 1000.0)

    def _boundary_multiplier(time_sec: float) -> float:
        for bt in boundary_times_sec:
            if abs(time_sec - bt) <= 0.5:
                return 1.3
        return 1.0

    # ── Compute raw scores for ranking ────────────────────────────────────────
    _PATTERN_MULTIPLIERS = {
        "isolated": 1.5,
        "double_tap": 1.0,
        "plateau": 1.0,
        "cascade": 1.0,
        "scattered": 1.0,
    }

    scored: list[tuple[float, float, dict]] = []  # (raw_score, intensity, moment)
    for m in raw:
        type_weight = _TYPE_WEIGHTS.get(m["type"], 0.5)
        pattern_mult = _PATTERN_MULTIPLIERS.get(m["pattern"], 1.0)
        boundary_mult = _boundary_multiplier(m["time"])
        raw_score = m["intensity"] * type_weight * pattern_mult * boundary_mult
        scored.append((raw_score, m["intensity"], m))

    # Sort descending: intensity is primary (ensures rank 1 = highest intensity),
    # raw_score is secondary for tie-breaking within same intensity level.
    scored.sort(key=lambda x: (x[1], x[0]), reverse=True)

    # Assign ranks
    for rank, (_, _, m) in enumerate(scored, start=1):
        m["rank"] = rank

    # ── Assign sequential IDs (sorted by time) ────────────────────────────────
    for i, m in enumerate(raw, start=1):
        m["id"] = f"m{i:03d}"

    return raw
