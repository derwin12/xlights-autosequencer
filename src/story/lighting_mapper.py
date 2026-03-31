"""Map a song section role + energy level to a SectionLighting configuration."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Role definitions: base tiers, theme_layer_mode, transition_in
# ---------------------------------------------------------------------------

_ROLE_CONFIG: dict[str, dict] = {
    "intro": {
        "base_tiers": [1, 2],
        "mode": "base_only",
        "transition_in": "quick_build",
    },
    "verse": {
        "base_tiers": [1, 2, 3],
        "mode": "base_only",
        "transition_in": "hard_cut",
    },
    "pre_chorus": {
        "base_tiers": [1, 2, 3, 4],
        "mode": "base_mid",
        "transition_in": "quick_build",
    },
    "chorus": {
        "base_tiers": [1, 2, 3, 4, 5, 6],
        "mode": "full",
        "transition_in": "hard_cut",
    },
    "post_chorus": {
        "base_tiers": [1, 2, 3, 4, 5],
        "mode": "base_mid",
        "transition_in": "quick_fade",
    },
    "bridge": {
        "base_tiers": [1, 2, 3],
        "mode": "base_mid",
        "transition_in": "crossfade",
    },
    "instrumental_break": {
        "base_tiers": [1, 2, 3, 4],
        "mode": "base_mid",
        "transition_in": "hard_cut",
    },
    "climax": {
        "base_tiers": [1, 2, 3, 4, 5, 6, 7, 8],
        "mode": "full",
        "transition_in": "hard_cut",
    },
    "ambient_bridge": {
        "base_tiers": [1, 2],
        "mode": "base_only",
        "transition_in": "crossfade",
    },
    "outro": {
        "base_tiers": [1, 2],
        "mode": "base_only",
        "transition_in": "quick_fade",
    },
    "interlude": {
        "base_tiers": [1, 2, 3],
        "mode": "base_mid",
        "transition_in": "crossfade",
    },
}

# ---------------------------------------------------------------------------
# Energy level adjustments
# ---------------------------------------------------------------------------

_ENERGY_CONFIG: dict[str, dict] = {
    "high": {
        "extra_tiers": 2,        # add 2 tiers above base (cap at 8)
        "brightness_ceiling": 0.9,
        "beat_effect_density": 0.8,
    },
    "medium": {
        "extra_tiers": 0,        # keep base tiers
        "brightness_ceiling": 0.7,
        "beat_effect_density": 0.5,
    },
    "low": {
        "extra_tiers": None,     # use only lowest 2 base tiers
        "brightness_ceiling": 0.45,
        "beat_effect_density": 0.25,
    },
}


def map_lighting(role: str, energy_level: str) -> dict:
    """Map a song section role and energy level to a SectionLighting dict.

    Parameters
    ----------
    role:
        Section role, e.g. "chorus", "verse", "intro".
    energy_level:
        One of "low", "medium", "high".

    Returns
    -------
    dict with keys: active_tiers, brightness_ceiling, theme_layer_mode,
    use_secondary_theme, transition_in, moment_count, moment_pattern,
    beat_effect_density.
    """
    role_cfg = _ROLE_CONFIG[role]
    energy_cfg = _ENERGY_CONFIG[energy_level]

    base_tiers: list[int] = list(role_cfg["base_tiers"])
    mode: str = role_cfg["mode"]
    transition_in: str = role_cfg["transition_in"]

    # Compute active_tiers based on energy
    if energy_level == "high":
        extra = energy_cfg["extra_tiers"]
        max_base = max(base_tiers)
        additional = list(range(max_base + 1, min(max_base + extra + 1, 9)))
        active_tiers = sorted(set(base_tiers + additional))
    elif energy_level == "low":
        # Use only the lowest 3 base tiers (but at least 1)
        active_tiers = sorted(base_tiers)[:3]
        if not active_tiers:
            active_tiers = [1]
    else:
        # medium: keep base tiers
        active_tiers = list(base_tiers)

    brightness_ceiling: float = energy_cfg["brightness_ceiling"]
    beat_effect_density: float = energy_cfg["beat_effect_density"]

    return {
        "active_tiers": active_tiers,
        "brightness_ceiling": brightness_ceiling,
        "theme_layer_mode": mode,
        "use_secondary_theme": False,
        "transition_in": transition_in,
        "moment_count": 0,
        "moment_pattern": "isolated",
        "beat_effect_density": beat_effect_density,
    }
