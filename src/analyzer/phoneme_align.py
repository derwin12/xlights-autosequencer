"""Word/phoneme alignment for singing faces — session-friendly wrapper.

Runs :class:`src.analyzer.phonemes.PhonemeAnalyzer` (WhisperX forced
alignment + cmudict decomposition) and returns plain mark dicts ready to
persist in an X-Onset session (``words`` / ``phonemes`` keys) and to embed
as .xsq timing tracks.

WhisperX may live in the main venv (Windows host) or in the ``.venv-vamp``
sidecar (devcontainer). This module tries an in-process run first and falls
back to a sidecar subprocess — the same pattern as
``src.story.builder._try_free_transcription``.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.log import get_logger

log = get_logger("xlight.phoneme_align")

_SUBPROCESS_TIMEOUT_S = 600


def _discover_vocals_stem(audio_path: str) -> Path | None:
    """Find a cached vocals stem next to ``audio_path``, or None if absent.

    Mirrors ``src.story.builder._discover_vocals_stem`` (kept private there).
    """
    audio_p = Path(audio_path)
    for stem_dir in (
        audio_p.parent / "stems",
        audio_p.parent / ".stems",
        audio_p.parent / audio_p.stem / "stems",
        audio_p.parent / audio_p.stem / ".stems",
    ):
        for ext in ("mp3", "wav"):
            candidate = stem_dir / f"vocals.{ext}"
            if candidate.exists():
                return candidate
    return None


def _sidecar_python() -> Path | None:
    """Resolve the .venv-vamp interpreter, or None when no sidecar exists."""
    override = os.environ.get("XLIGHT_VENV_VAMP")
    if override:
        p = Path(override)
        return p if p.exists() else None
    repo_root = Path(__file__).resolve().parents[2]
    for rel in ("bin/python", "Scripts/python.exe"):
        candidate = repo_root / ".venv-vamp" / rel
        if candidate.exists():
            return candidate
    return None


def _lyric_lines_to_text(lyric_lines: list[dict]) -> str:
    """Flatten session lyric lines (``{t_ms, duration_ms, text}``) to plain text."""
    return "\n".join(line.get("text", "") for line in lyric_lines if line.get("text"))


def _run_in_process(
    audio_path: str, lyrics_path: Optional[str],
) -> tuple[list[dict], list[dict], list[str]]:
    from src.analyzer.phonemes import PhonemeAnalyzer

    analyzer = PhonemeAnalyzer(model_name="base", device="cpu", language="en")
    result = analyzer.analyze(audio_path, source_file=audio_path, lyrics_path=lyrics_path)
    warnings = list(getattr(analyzer, "warnings", []) or [])
    if result is None:
        return [], [], warnings
    words = [m.to_dict() for m in result.word_track.marks]
    phonemes = [m.to_dict() for m in result.phoneme_track.marks]
    return words, phonemes, warnings


def _run_in_sidecar(
    sidecar: Path, audio_path: str, lyrics_path: Optional[str],
) -> tuple[list[dict], list[dict], list[str]]:
    repo_root = Path(__file__).resolve().parents[2]
    script = f'''
import json, sys
sys.path.insert(0, {str(repo_root)!r})
try:
    import torch
    _orig_torch_load = torch.load
    def _torch_load_compat(*args, **kwargs):
        kwargs["weights_only"] = False
        return _orig_torch_load(*args, **kwargs)
    torch.load = _torch_load_compat
except Exception:
    pass
from src.analyzer.phonemes import PhonemeAnalyzer
analyzer = PhonemeAnalyzer(model_name="base", device="cpu", language="en")
result = analyzer.analyze({audio_path!r}, source_file={audio_path!r}, lyrics_path={lyrics_path!r})
warnings = list(getattr(analyzer, "warnings", []) or [])
if result is None:
    print(json.dumps({{"words": [], "phonemes": [], "warnings": warnings}}))
else:
    print(json.dumps({{
        "words": [m.to_dict() for m in result.word_track.marks],
        "phonemes": [m.to_dict() for m in result.phoneme_track.marks],
        "warnings": warnings,
    }}))
'''
    proc = subprocess.run(
        [str(sidecar), "-c", script],
        capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_S,
    )
    if proc.returncode != 0:
        log.warning("phoneme sidecar subprocess failed:\n%s", proc.stderr[:800])
        return [], [], []
    payload = json.loads(proc.stdout.strip().split("\n")[-1])
    return payload.get("words", []), payload.get("phonemes", []), payload.get("warnings", [])


def align_words_and_phonemes(
    audio_path: str,
    lyric_lines: Optional[list[dict]] = None,
    lyrics_text: Optional[str] = None,
) -> tuple[list[dict], list[dict], list[str]]:
    """Return ``(words, phonemes, warnings)`` for the song's vocals.

    Each word mark is ``{"label": str, "start_ms": int, "end_ms": int,
    "speaker": int}`` — word labels are uppercased words; ``speaker`` is 0
    (lead) or 1 (featured/backup), from :func:`diarize_words
    <src.analyzer.vocal_diarization.diarize_words>` — always 0 when no
    second voice is confidently detected. Phoneme labels are Papagayo mouth
    shapes (AI/E/O/U/WQ/L/MBP/FV/etc/rest) matching xLights face
    definitions.

    When ``lyric_lines`` (session ``lyrics`` — ``{t_ms, duration_ms,
    text}``, i.e. real LRC timestamps) is provided, WhisperX force-aligns
    that known lyric text. Otherwise, when ``lyrics_text`` (raw plain text —
    e.g. a user-pasted lyrics fallback, or an untimed provider result) is
    provided, WhisperX force-aligns THAT instead. Both produce far more
    accurate word text than free transcription, which only guesses words
    from audio alone (user-confirmed 2026-07-21: free transcription on a
    pasted-but-untimed song produced garbage words). Only when NEITHER is
    available does it fall back to free transcription. Prefers the cached
    demucs vocals stem over the full mix when one exists.

    ``warnings`` includes, notably, the case where lyric text was provided
    but fewer than 50% of its words aligned to the audio — the analyzer
    discards the provided text entirely and falls back to free
    transcription for the WHOLE song in that case (see
    ``PhonemeAnalyzer._align_with_lyrics``), so the returned words can look
    like "made up" text even though real lyrics were supplied. Surface this
    warning to the user rather than silently returning different words than
    what they pasted.

    Never raises: returns ``([], [], [])`` when WhisperX is unavailable in
    both the main venv and the ``.venv-vamp`` sidecar, or when alignment
    fails.
    """
    vocals = _discover_vocals_stem(audio_path)
    align_audio = str(vocals) if vocals is not None else str(audio_path)

    words, phonemes, warnings = _run_alignment(align_audio, lyric_lines, lyrics_text)

    if words and vocals is not None:
        from src.analyzer.vocal_diarization import diarize_words
        words = diarize_words(str(vocals), words)
    else:
        words = [{**w, "speaker": 0} for w in words]

    return words, phonemes, warnings


def _run_alignment(
    align_audio: str,
    lyric_lines: Optional[list[dict]],
    lyrics_text: Optional[str],
) -> tuple[list[dict], list[dict], list[str]]:
    lyrics_path: Optional[str] = None
    tmp_file: Optional[str] = None
    try:
        reference_text: str = ""
        if lyric_lines:
            reference_text = _lyric_lines_to_text(lyric_lines)
        elif lyrics_text:
            reference_text = lyrics_text
        if reference_text.strip():
            fd, tmp_file = tempfile.mkstemp(suffix=".txt", text=True)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(reference_text)
            lyrics_path = tmp_file

        try:
            return _run_in_process(align_audio, lyrics_path)
        except RuntimeError:
            # PhonemeAnalyzer raises RuntimeError when whisperx isn't
            # importable in this venv — try the sidecar interpreter.
            sidecar = _sidecar_python()
            if sidecar is None:
                log.warning(
                    "phoneme alignment skipped: whisperx unavailable and no "
                    ".venv-vamp sidecar found"
                )
                return [], [], []
            return _run_in_sidecar(sidecar, align_audio, lyrics_path)
        except Exception as exc:
            log.warning("phoneme alignment failed: %s", exc, exc_info=True)
            return [], [], []
    finally:
        if tmp_file is not None:
            try:
                os.unlink(tmp_file)
            except OSError:
                pass
