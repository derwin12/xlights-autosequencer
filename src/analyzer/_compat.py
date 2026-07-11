"""Compatibility shims for third-party packages that lag behind torchaudio API changes.

torchaudio 2.11 removed several top-level APIs that pyannote.audio 3.3.2 still
uses (AudioMetaData as a return-type hint, list_audio_backends() and info()
called at module load / runtime via Audio(...) construction). Anything that
transitively imports pyannote.audio — whisperx, speechbrain, the analyzer's
phoneme/transcription paths — fails with AttributeError before our code runs.

This module restores the three attributes on ``torchaudio`` with minimal stubs:

* ``AudioMetaData`` — a bare placeholder class; pyannote uses it only as a
  return-type annotation.
* ``list_audio_backends()`` — returns ``["soundfile"]``, the backend pyannote
  prefers when available.
* ``info(path, backend=None)`` — returns an ``AudioMetaData``-shaped object
  populated via soundfile, matching the fields pyannote inspects
  (sample_rate, num_frames, num_channels, bits_per_sample, encoding).

Remove this module once pyannote.audio targets a torchaudio release that
preserves these symbols.
"""
from __future__ import annotations


def install_torchaudio_shims() -> None:
    try:
        import torchaudio
    except Exception:
        return

    if not hasattr(torchaudio, "AudioMetaData"):
        class AudioMetaData:
            __slots__ = ("sample_rate", "num_frames", "num_channels",
                         "bits_per_sample", "encoding")

            def __init__(self, sample_rate: int = 0, num_frames: int = 0,
                         num_channels: int = 0, bits_per_sample: int = 0,
                         encoding: str = "UNKNOWN") -> None:
                self.sample_rate = sample_rate
                self.num_frames = num_frames
                self.num_channels = num_channels
                self.bits_per_sample = bits_per_sample
                self.encoding = encoding

        torchaudio.AudioMetaData = AudioMetaData  # type: ignore[attr-defined]

    if not hasattr(torchaudio, "list_audio_backends"):
        def list_audio_backends() -> list[str]:
            return ["soundfile"]
        torchaudio.list_audio_backends = list_audio_backends  # type: ignore[attr-defined]

    if not hasattr(torchaudio, "info"):
        _BITS_PER_SAMPLE = {
            "PCM_S8": 8, "PCM_U8": 8, "PCM_16": 16, "PCM_24": 24,
            "PCM_32": 32, "FLOAT": 32, "DOUBLE": 64,
        }

        def info(path, backend=None):  # noqa: ARG001
            import soundfile as sf
            with sf.SoundFile(str(path)) as f:
                subtype = str(f.subtype or "UNKNOWN")
                return torchaudio.AudioMetaData(  # type: ignore[attr-defined]
                    sample_rate=int(f.samplerate),
                    num_frames=int(len(f)),
                    num_channels=int(f.channels),
                    bits_per_sample=_BITS_PER_SAMPLE.get(subtype, 0),
                    encoding=subtype,
                )
        torchaudio.info = info  # type: ignore[attr-defined]


install_torchaudio_shims()
