"""Free-transcription wrapper around WhisperX.

Reusable WhisperX transcribe+align pass that returns per-word timestamps as
``WordMark`` instances. Used by the Genius alignment path to discover vocal
regions, and by the boundary-refinement step (OpenSpec change
``lyric-anchored-boundary-refinement``) as ground-truth ``is anyone audibly
singing here`` evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.analyzer.phonemes import WordMark
from src.log import get_logger

log = get_logger("xlight.free_transcription")

_HF_ALIGN_FALLBACK = "jonatasgrosman/wav2vec2-large-xlsr-53-english"


def _load_align_model(language: str, device: str) -> tuple:
    """Load whisperx alignment model, falling back to HF if torchaudio download fails."""
    import whisperx as _wx
    try:
        return _wx.load_align_model(language_code=language, device=device)
    except Exception as _e:
        log.warning("torchaudio align model failed (%s), trying HF fallback", _e)
        return _wx.load_align_model(
            language_code=language,
            device=device,
            model_name=_HF_ALIGN_FALLBACK,
        )


def transcribe_free(
    audio_path: str,
    *,
    language: str = "en",
    device: str = "cpu",
    duration_s: Optional[float] = None,
) -> list[WordMark]:
    """Run a free WhisperX transcription pass on ``audio_path``.

    No lyrics are passed in — the model transcribes whatever it hears. Used as
    a ground-truth signal for ``did the singer audibly enter here.``

    Returns a list of ``WordMark`` instances ordered by ``start_ms``. Raises
    ``FileNotFoundError`` if ``audio_path`` does not exist.
    """
    p = Path(audio_path)
    if not p.exists():
        raise FileNotFoundError(f"audio path does not exist: {audio_path}")

    try:
        import whisperx
    except ImportError as e:
        raise RuntimeError(
            "whisperx is not installed; free transcription requires whisperx"
        ) from e

    audio = whisperx.load_audio(str(p))

    log.info("transcribe_free: loading whisper model (device=%s, language=%s)", device, language)
    model = whisperx.load_model("base", device, compute_type="float32", language=language)
    transcribed = model.transcribe(audio, batch_size=8)
    raw_segments = transcribed.get("segments", [])
    log.info("transcribe_free: %d raw segments", len(raw_segments))

    if not raw_segments:
        return []

    if duration_s is None:
        try:
            import librosa
            duration_s = float(librosa.get_duration(path=str(p)))
        except Exception:
            duration_s = max((s.get("end", 0.0) for s in raw_segments), default=0.0)

    align_model, metadata = _load_align_model(language, device)
    aligned = whisperx.align(raw_segments, align_model, metadata, audio, device)
    word_segments = aligned.get("word_segments", [])
    log.info("transcribe_free: alignment returned %d word_segments", len(word_segments))

    word_marks: list[WordMark] = []
    for ws in word_segments:
        word = (ws.get("word") or "").strip()
        start = ws.get("start")
        end = ws.get("end")
        if not word or start is None or end is None:
            continue
        word_marks.append(
            WordMark(
                label=word.upper(),
                start_ms=int(round(start * 1000)),
                end_ms=int(round(end * 1000)),
            )
        )

    word_marks.sort(key=lambda w: w.start_ms)
    return word_marks


def derive_vocal_regions(
    word_marks: list[WordMark],
    *,
    gap_s: float = 4.0,
) -> list[tuple[float, float]]:
    """Group word marks into contiguous vocal regions.

    A region break is inserted whenever the gap between consecutive words
    exceeds ``gap_s`` seconds. Returns a list of ``(start_s, end_s)`` tuples.
    """
    if not word_marks:
        return []

    gap_ms = int(round(gap_s * 1000))
    regions: list[tuple[float, float]] = []
    r_start_ms = word_marks[0].start_ms
    r_end_ms = word_marks[0].end_ms

    for wm in word_marks[1:]:
        if wm.start_ms - r_end_ms > gap_ms:
            regions.append((r_start_ms / 1000.0, r_end_ms / 1000.0))
            r_start_ms = wm.start_ms
        r_end_ms = max(r_end_ms, wm.end_ms)

    regions.append((r_start_ms / 1000.0, r_end_ms / 1000.0))
    return regions
