"""Essentia-based audio feature extraction.

Extracts high-level descriptors not available from Vamp/librosa:
danceability, dynamic complexity, key (with mode), and EBU R128 loudness.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class EssentiaFeatures:
    """High-level audio features from essentia."""

    key: str                      # e.g. "E"
    scale: str                    # "minor" or "major"
    key_strength: float           # 0.0–1.0 confidence
    danceability: float           # 0.0–~3.0 (higher = more danceable)
    dynamic_complexity: float     # higher = more dynamic contrast
    loudness_lufs: float          # integrated loudness (EBU R128)
    loudness_range_lu: float      # loudness range in LU
    true_peak_dbtp: float         # true peak in dBTP
    bpm_essentia: float           # essentia's BPM estimate
    bpm_confidence: float         # essentia's BPM confidence

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "scale": self.scale,
            "key_strength": round(self.key_strength, 4),
            "danceability": round(self.danceability, 4),
            "dynamic_complexity": round(self.dynamic_complexity, 4),
            "loudness_lufs": round(self.loudness_lufs, 1),
            "loudness_range_lu": round(self.loudness_range_lu, 1),
            "true_peak_dbtp": round(self.true_peak_dbtp, 1),
            "bpm_essentia": round(self.bpm_essentia, 1),
            "bpm_confidence": round(self.bpm_confidence, 4),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EssentiaFeatures":
        return cls(
            key=d["key"],
            scale=d["scale"],
            key_strength=d["key_strength"],
            danceability=d["danceability"],
            dynamic_complexity=d["dynamic_complexity"],
            loudness_lufs=d["loudness_lufs"],
            loudness_range_lu=d["loudness_range_lu"],
            true_peak_dbtp=d["true_peak_dbtp"],
            bpm_essentia=d["bpm_essentia"],
            bpm_confidence=d["bpm_confidence"],
        )


def extract_essentia_features(
    audio: np.ndarray,
    sr: int,
    audio_stereo: Optional[np.ndarray] = None,
) -> EssentiaFeatures:
    """Run essentia analysis on audio and return high-level features.

    Args:
        audio: Mono audio as float32 numpy array.
        sr: Sample rate (will resample to 44100 if different).
        audio_stereo: Optional stereo audio for EBU R128 loudness.
                      Shape: (samples, 2). If None, mono is duplicated.
    """
    import essentia.standard as es

    # Essentia expects 44100Hz float32
    if sr != 44100:
        import librosa
        audio = librosa.resample(audio, orig_sr=sr, target_sr=44100).astype(np.float32)
    else:
        audio = audio.astype(np.float32)

    # Key detection
    key_algo = es.KeyExtractor()
    key, scale, key_strength = key_algo(audio)

    # Danceability
    danceability, _ = es.Danceability()(audio)

    # Dynamic complexity
    dynamic_complexity, _ = es.DynamicComplexity()(audio)

    # Rhythm / BPM
    bpm, _, bpm_confidence, _, _ = es.RhythmExtractor2013()(audio)

    # EBU R128 Loudness (needs stereo)
    if audio_stereo is not None:
        if audio_stereo.shape[0] == 2:
            # (2, samples) -> (samples, 2)
            stereo = audio_stereo.T.astype(np.float32)
        else:
            stereo = audio_stereo.astype(np.float32)
    else:
        stereo = np.column_stack([audio, audio]).astype(np.float32)

    loud_algo = es.LoudnessEBUR128(sampleRate=44100)
    il, lra, tp, _ = loud_algo(stereo)
    loudness_lufs = float(np.asarray(il).flat[0])
    loudness_range_lu = float(np.asarray(lra).flat[0])
    true_peak_dbtp = float(np.asarray(tp).flat[0])

    return EssentiaFeatures(
        key=key,
        scale=scale,
        key_strength=float(key_strength),
        danceability=float(danceability),
        dynamic_complexity=float(dynamic_complexity),
        loudness_lufs=loudness_lufs,
        loudness_range_lu=loudness_range_lu,
        true_peak_dbtp=true_peak_dbtp,
        bpm_essentia=float(bpm),
        bpm_confidence=float(bpm_confidence),
    )
