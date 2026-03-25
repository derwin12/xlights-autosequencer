"""Stem affinity table: maps each algorithm to its preferred stems with rationale.

See docs/stem-affinity-rationale.md for full audio engineering reasoning.
"""
from __future__ import annotations

__all__ = [
    "StemAffinity",
    "AFFINITY_TABLE",
]

# Each entry: stems (preference order), output_type, tunable_params
AFFINITY_TABLE: dict[str, dict] = {
    # ── Beat & Tempo ─────────────────────────────────────────────────────────
    "qm_beats":          {"stems": ["drums", "bass", "full_mix"], "output_type": "timing", "params": ["inputtempo", "constraintempo"]},
    "qm_bars":           {"stems": ["drums", "bass", "full_mix"], "output_type": "timing", "params": ["inputtempo", "constraintempo"]},
    "qm_tempo":          {"stems": ["drums", "bass", "full_mix"], "output_type": "timing", "params": []},
    "beatroot_beats":    {"stems": ["drums", "bass", "full_mix"], "output_type": "timing", "params": []},
    "librosa_beats":     {"stems": ["drums", "bass", "full_mix"], "output_type": "timing", "params": []},
    "librosa_bars":      {"stems": ["drums", "bass", "full_mix"], "output_type": "timing", "params": []},
    "aubio_tempo":       {"stems": ["drums", "bass", "full_mix"], "output_type": "timing", "params": []},
    "madmom_beats":      {"stems": ["drums", "bass", "full_mix"], "output_type": "timing", "params": []},
    "madmom_downbeats":  {"stems": ["drums", "bass", "full_mix"], "output_type": "timing", "params": []},

    # ── Onset Detection ──────────────────────────────────────────────────────
    "qm_onsets_complex": {"stems": ["drums", "guitar", "bass", "vocals", "full_mix"], "output_type": "timing", "params": ["sensitivity"]},
    "qm_onsets_hfc":     {"stems": ["drums", "guitar", "full_mix"], "output_type": "timing", "params": ["sensitivity"]},
    "qm_onsets_phase":   {"stems": ["bass", "vocals", "guitar", "full_mix"], "output_type": "timing", "params": ["sensitivity"]},
    "librosa_onsets":    {"stems": ["drums", "guitar", "bass", "vocals", "full_mix"], "output_type": "timing", "params": []},
    "aubio_onset":       {"stems": ["drums", "guitar", "bass", "vocals", "full_mix"], "output_type": "timing", "params": ["threshold", "silence", "minioi"]},
    "percussion_onsets": {"stems": ["drums", "full_mix"], "output_type": "timing", "params": ["threshold", "sensitivity"]},
    "bbc_rhythm":        {"stems": ["drums", "bass", "full_mix"], "output_type": "timing", "params": []},

    # ── Pitch & Melody ───────────────────────────────────────────────────────
    "pyin_notes":        {"stems": ["vocals", "guitar", "piano", "full_mix"], "output_type": "timing", "params": ["threshdistr", "outputunvoiced"]},
    "pyin_pitch_changes":{"stems": ["vocals", "guitar", "piano", "full_mix"], "output_type": "timing", "params": ["threshdistr", "outputunvoiced"]},
    "aubio_notes":       {"stems": ["vocals", "guitar", "piano", "full_mix"], "output_type": "timing", "params": []},

    # ── Harmony & Key ────────────────────────────────────────────────────────
    "chordino_chords":   {"stems": ["guitar", "piano", "full_mix"], "output_type": "timing", "params": []},
    "nnls_chroma":       {"stems": ["guitar", "piano", "full_mix"], "output_type": "timing", "params": []},
    "qm_key":            {"stems": ["guitar", "piano", "full_mix"], "output_type": "timing", "params": []},

    # ── Segmentation ─────────────────────────────────────────────────────────
    "qm_segments":       {"stems": ["full_mix", "vocals", "drums"], "output_type": "timing", "params": []},
    "segmentino":        {"stems": ["full_mix", "vocals", "drums"], "output_type": "timing", "params": []},

    # ── Polyphonic Transcription ─────────────────────────────────────────────
    "qm_transcription":  {"stems": ["piano", "guitar", "full_mix"], "output_type": "timing", "params": []},
    "silvet_notes":      {"stems": ["piano", "guitar", "full_mix"], "output_type": "timing", "params": []},

    # ── Energy & Spectral (Value Curves) ─────────────────────────────────────
    "bbc_energy":        {"stems": ["drums", "bass", "vocals", "guitar", "piano", "other", "full_mix"], "output_type": "value_curve", "params": []},
    "bbc_spectral_flux": {"stems": ["drums", "bass", "vocals", "guitar", "piano", "other", "full_mix"], "output_type": "value_curve", "params": []},
    "bbc_peaks":         {"stems": ["drums", "bass", "guitar", "full_mix"], "output_type": "value_curve", "params": []},
    "amplitude_follower":{"stems": ["drums", "bass", "vocals", "guitar", "piano", "other", "full_mix"], "output_type": "value_curve", "params": ["attack", "release"]},
    "tempogram":         {"stems": ["drums", "bass", "full_mix"], "output_type": "value_curve", "params": []},

    # ── Frequency Bands (librosa) ────────────────────────────────────────────
    "bass":              {"stems": ["bass", "drums", "full_mix"], "output_type": "timing", "params": []},
    "mid":               {"stems": ["vocals", "guitar", "piano", "full_mix"], "output_type": "timing", "params": []},
    "treble":            {"stems": ["drums", "guitar", "full_mix"], "output_type": "timing", "params": []},

    # ── HPSS (librosa) ───────────────────────────────────────────────────────
    "drums":             {"stems": ["full_mix"], "output_type": "timing", "params": []},
    "harmonic_peaks":    {"stems": ["full_mix"], "output_type": "timing", "params": []},
}


class StemAffinity:
    """Query the stem affinity table."""

    @staticmethod
    def get_stems(algorithm: str, available_stems: set[str]) -> list[str]:
        """Return preferred stems for *algorithm* filtered by *available_stems*.

        Always includes full_mix. No artificial cap on count.
        Returns ["full_mix"] for unknown algorithms.
        """
        entry = AFFINITY_TABLE.get(algorithm)
        if entry is None:
            return ["full_mix"]

        result = [s for s in entry["stems"] if s in available_stems]
        if "full_mix" not in result:
            result.append("full_mix")
        return result

    @staticmethod
    def get_output_type(algorithm: str) -> str:
        """Return 'timing' or 'value_curve' for the algorithm."""
        entry = AFFINITY_TABLE.get(algorithm)
        return entry["output_type"] if entry else "timing"

    @staticmethod
    def get_tunable_params(algorithm: str) -> list[str]:
        """Return list of tunable parameter names for the algorithm."""
        entry = AFFINITY_TABLE.get(algorithm)
        return list(entry["params"]) if entry else []
