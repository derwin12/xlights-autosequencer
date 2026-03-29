"""T028: Librosa frequency band energy peak algorithms."""
from __future__ import annotations

import numpy as np

from src.analyzer.algorithms.base import Algorithm
from src.analyzer.result import TimingMark, TimingTrack

_HOP_LENGTH = 512
_N_FFT = 2048

# Module-level STFT cache to avoid recomputing the same STFT 3 times
# (once per band). Keyed by (id(audio), sample_rate) so it auto-invalidates
# when a different audio array is passed.
_stft_cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}


def _get_stft_and_freqs(
    audio: np.ndarray, sample_rate: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (magnitude_stft, freq_bins), computing once and caching."""
    key = (id(audio), sample_rate)
    cached = _stft_cache.get(key)
    if cached is not None:
        return cached

    import librosa

    stft = np.abs(librosa.stft(audio, n_fft=_N_FFT, hop_length=_HOP_LENGTH))
    freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=_N_FFT)
    # Keep only one entry to bound memory
    _stft_cache.clear()
    _stft_cache[key] = (stft, freqs)
    return stft, freqs


def _band_onsets(
    audio: np.ndarray,
    sample_rate: int,
    fmin: float,
    fmax: float,
) -> np.ndarray:
    """Return onset times (seconds) for energy peaks in a frequency band."""
    import librosa

    stft, freqs = _get_stft_and_freqs(audio, sample_rate)
    mask = (freqs >= fmin) & (freqs <= fmax)
    band_stft = stft[mask, :]

    # Novelty / onset envelope from band energy
    onset_env = librosa.onset.onset_strength(
        S=librosa.amplitude_to_db(band_stft, ref=np.max),
        sr=sample_rate,
        hop_length=_HOP_LENGTH,
    )
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env,
        sr=sample_rate,
        hop_length=_HOP_LENGTH,
        backtrack=True,
    )
    return librosa.frames_to_time(onset_frames, sr=sample_rate, hop_length=_HOP_LENGTH)


class LibrosaBassAlgorithm(Algorithm):
    """Bass band (20-250 Hz) onset detection."""

    name = "bass"
    element_type = "frequency"
    library = "librosa"
    plugin_key = None
    parameters = {"fmin": 20, "fmax": 250}
    depends_on = ["audio_load"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        times = _band_onsets(audio, sample_rate, fmin=20.0, fmax=250.0)
        marks = [
            TimingMark(time_ms=int(round(t * 1000)), confidence=None) for t in times
        ]
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )


class LibrosaMidAlgorithm(Algorithm):
    """Mid band (250-4000 Hz) onset detection."""

    name = "mid"
    element_type = "frequency"
    library = "librosa"
    plugin_key = None
    parameters = {"fmin": 250, "fmax": 4000}
    depends_on = ["audio_load"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        times = _band_onsets(audio, sample_rate, fmin=250.0, fmax=4000.0)
        marks = [
            TimingMark(time_ms=int(round(t * 1000)), confidence=None) for t in times
        ]
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )


class LibrosaTrebleAlgorithm(Algorithm):
    """Treble band (4000-20000 Hz) onset detection."""

    name = "treble"
    element_type = "frequency"
    library = "librosa"
    plugin_key = None
    parameters = {"fmin": 4000, "fmax": 20000}
    depends_on = ["audio_load"]

    def _run(self, audio: np.ndarray, sample_rate: int) -> TimingTrack:
        times = _band_onsets(audio, sample_rate, fmin=4000.0, fmax=20000.0)
        marks = [
            TimingMark(time_ms=int(round(t * 1000)), confidence=None) for t in times
        ]
        return TimingTrack(
            name=self.name,
            algorithm_name=self.name,
            element_type=self.element_type,
            marks=marks,
            quality_score=0.0,
        )
