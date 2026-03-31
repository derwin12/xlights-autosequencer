"""Minimal HierarchyResult-like fixture for song story unit tests.

All values are hand-crafted to produce deterministic, predictable outputs.
The fixture represents a 60-second song with 4 distinct sections.

Usage:
    from tests.fixtures.story_fixture import make_hierarchy_dict, FIXTURE_DURATION_MS
"""
from __future__ import annotations

FIXTURE_DURATION_MS = 60_000
FIXTURE_BPM = 120.0
FIXTURE_HASH = "abcdef1234567890abcdef1234567890"

# 4 sections: intro (0-12s), verse (12-36s), chorus (36-54s), outro (54-60s)
FIXTURE_SECTIONS = [
    {"time_ms": 0, "label": "seg0"},
    {"time_ms": 12_000, "label": "seg1"},
    {"time_ms": 36_000, "label": "seg2"},
    {"time_ms": 54_000, "label": "seg3"},
    {"time_ms": 60_000, "label": "seg_end"},   # sentinel end boundary
]

# Beats at 120 BPM = every 500ms, 120 beats over 60 seconds
FIXTURE_BEATS = [
    {"time_ms": i * 500, "label": str((i % 4) + 1), "confidence": 0.9}
    for i in range(120)
]

# Energy impacts (L0)
FIXTURE_ENERGY_IMPACTS = [
    {"time_ms": 36_000, "confidence": 0.9, "label": "energy_impact"},
    {"time_ms": 48_000, "confidence": 0.7, "label": "energy_impact"},
]

FIXTURE_ENERGY_DROPS = [
    {"time_ms": 54_000, "confidence": 0.8, "label": "energy_drop"},
]

FIXTURE_GAPS = []

# Energy curves at 10 fps over 60 seconds = 600 frames
# Intro: low (0.2), Verse: medium (0.5), Chorus: high (0.8), Outro: low (0.2)
def _energy_at(t_sec: float) -> float:
    if t_sec < 12:
        return 0.2
    elif t_sec < 36:
        return 0.5
    elif t_sec < 54:
        return 0.8
    else:
        return 0.2


FIXTURE_ENERGY_CURVE_FULL_MIX = {
    "sample_rate": 10.0,
    "values": [round(_energy_at(i / 10), 3) for i in range(600)],
}

# Per-stem curves (vocals active only in verse + chorus)
def _vocals_energy(t_sec: float) -> float:
    return 0.6 if 12 <= t_sec < 54 else 0.0


def _drums_energy(t_sec: float) -> float:
    return 0.7 if t_sec >= 12 else 0.1


def _bass_energy(t_sec: float) -> float:
    return 0.5 if t_sec >= 12 else 0.05


FIXTURE_ENERGY_CURVES = {
    "full_mix": FIXTURE_ENERGY_CURVE_FULL_MIX,
    "vocals": {
        "sample_rate": 10.0,
        "values": [round(_vocals_energy(i / 10), 3) for i in range(600)],
    },
    "drums": {
        "sample_rate": 10.0,
        "values": [round(_drums_energy(i / 10), 3) for i in range(600)],
    },
    "bass": {
        "sample_rate": 10.0,
        "values": [round(_bass_energy(i / 10), 3) for i in range(600)],
    },
    "guitar": {
        "sample_rate": 10.0,
        "values": [0.3] * 600,
    },
    "piano": {
        "sample_rate": 10.0,
        "values": [0.1] * 600,
    },
    "other": {
        "sample_rate": 10.0,
        "values": [0.1] * 600,
    },
}

# L4 events (onset tracks per stem)
# Drums: kick on beats 1 and 3, snare on beats 2 and 4, hihat every beat (from bar 2 onwards)
FIXTURE_EVENTS = {
    "drums": {
        "name": "drums",
        "marks": [
            # kick on beats 1,3 from 12s onward
            *[{"time_ms": ms, "label": "kick", "confidence": 0.9}
              for ms in range(12_000, 54_000, 1000)],  # every 1s = every 2 beats
            # snare on beats 2,4
            *[{"time_ms": ms, "label": "snare", "confidence": 0.8}
              for ms in range(12_500, 54_000, 1000)],
            # hihat every beat
            *[{"time_ms": ms, "label": "hihat", "confidence": 0.7}
              for ms in range(12_000, 54_000, 500)],
        ],
    },
    "bass": {
        "name": "bass",
        "marks": [
            {"time_ms": ms, "label": "onset", "confidence": 0.8}
            for ms in range(12_000, 54_000, 1000)
        ],
    },
    "vocals": {
        "name": "vocals",
        "marks": [
            {"time_ms": ms, "label": "onset", "confidence": 0.7}
            for ms in range(12_000, 54_000, 750)
        ],
    },
    "guitar": {
        "name": "guitar",
        "marks": [
            {"time_ms": ms, "label": "onset", "confidence": 0.6}
            for ms in range(0, 60_000, 2000)
        ],
    },
}

# L6 chords
FIXTURE_CHORDS = {
    "name": "chords",
    "marks": [
        {"time_ms": 0, "label": "C"},
        {"time_ms": 12_000, "label": "Am"},
        {"time_ms": 24_000, "label": "F"},
        {"time_ms": 36_000, "label": "G"},
        {"time_ms": 48_000, "label": "Cmaj7"},
        {"time_ms": 54_000, "label": "C"},
    ],
}

# Solos: guitar solo in chorus
FIXTURE_SOLOS = {
    "guitar": [{"time_ms": 40_000, "duration_ms": 10_000, "label": "solo", "confidence": 0.8}],
}

# Essentia features
FIXTURE_ESSENTIA = {
    "key": "C",
    "key_scale": "major",
    "key_strength": 0.85,
    "danceability": 0.7,
    "loudness": -8.0,
}


def make_hierarchy_dict(
    duration_ms: int = FIXTURE_DURATION_MS,
    bpm: float = FIXTURE_BPM,
    source_hash: str = FIXTURE_HASH,
    stems_available: list[str] | None = None,
) -> dict:
    """Return a minimal HierarchyResult-compatible dict for story tests.

    Args:
        duration_ms: Song duration in milliseconds.
        bpm: Estimated tempo.
        source_hash: Simulated MD5 hash.
        stems_available: List of available stems; defaults to all 6.

    Returns:
        A dict matching the HierarchyResult.to_dict() structure.
    """
    if stems_available is None:
        stems_available = ["drums", "bass", "vocals", "guitar", "piano", "other"]

    return {
        "schema_version": "2.0.0",
        "source_file": "/tmp/fixture_song.mp3",
        "source_hash": source_hash,
        "duration_ms": duration_ms,
        "estimated_bpm": bpm,
        "energy_impacts": FIXTURE_ENERGY_IMPACTS,
        "energy_drops": FIXTURE_ENERGY_DROPS,
        "gaps": FIXTURE_GAPS,
        "sections": FIXTURE_SECTIONS,
        "bars": None,
        "beats": {"name": "beats", "marks": FIXTURE_BEATS},
        "half_bars": None,
        "eighth_notes": None,
        "events": FIXTURE_EVENTS,
        "solos": FIXTURE_SOLOS,
        "energy_curves": FIXTURE_ENERGY_CURVES,
        "spectral_flux": None,
        "chords": FIXTURE_CHORDS,
        "key_changes": None,
        "interactions": None,
        "essentia_features": FIXTURE_ESSENTIA,
        "stems_available": stems_available,
        "capabilities": {
            "has_stems": True,
            "has_beats": True,
            "has_harmony": True,
            "has_essentia": True,
        },
        "algorithms_run": ["qm_structure", "librosa_beats", "librosa_hpss"],
        "warnings": [],
        "validation": {},
    }


def make_hierarchy_dict_no_stems() -> dict:
    """Fixture without any stem data — simulates full-mix-only analysis."""
    d = make_hierarchy_dict(stems_available=[])
    d["energy_curves"] = {"full_mix": FIXTURE_ENERGY_CURVE_FULL_MIX}
    d["events"] = {}
    d["solos"] = {}
    d["capabilities"]["has_stems"] = False
    return d


def make_hierarchy_dict_instrumental() -> dict:
    """Fixture with zero vocal activity — simulates instrumental music."""
    import copy
    d = make_hierarchy_dict()
    # Deep-copy energy_curves so we don't mutate the module-level FIXTURE_ENERGY_CURVES
    d["energy_curves"] = copy.deepcopy(d["energy_curves"])
    d["energy_curves"]["vocals"] = {
        "sample_rate": 10.0,
        "values": [0.0] * 600,
    }
    d["events"] = {k: v for k, v in d["events"].items() if k != "vocals"}
    return d
