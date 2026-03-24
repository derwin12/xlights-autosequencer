"""Analysis result cache keyed by MD5 of the source audio file."""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src import export as export_mod
from src.analyzer.result import AnalysisResult


@dataclass
class CacheStatus:
    """Snapshot of cache state for a given audio file, used by the wizard UI."""

    exists: bool
    is_valid: bool
    age_seconds: Optional[float]
    cache_path: Optional[Path]
    track_count: int

    @classmethod
    def from_audio_path(
        cls,
        audio_path: Path,
        output_path: Optional[Path] = None,
    ) -> "CacheStatus":
        """Return a CacheStatus snapshot for *audio_path*.

        If *output_path* is omitted the default cache path is derived the same
        way as :class:`AnalysisCache` (``<audio_dir>/analysis/<stem>_analysis.json``
        or ``<audio_dir>/<stem>_analysis.json``).
        """
        if output_path is None:
            # Mirror the default output path used by analyze_cmd
            analysis_dir = audio_path.parent / "analysis"
            if analysis_dir.is_dir():
                candidate = analysis_dir / f"{audio_path.stem}_analysis.json"
            else:
                candidate = audio_path.parent / f"{audio_path.stem}_analysis.json"
            output_path = candidate

        if not output_path.exists():
            return cls(
                exists=False,
                is_valid=False,
                age_seconds=None,
                cache_path=None,
                track_count=0,
            )

        age = time.time() - output_path.stat().st_mtime
        cache = AnalysisCache(audio_path, output_path)
        valid = cache.is_valid()
        track_count = 0
        if valid:
            try:
                result = cache.load()
                track_count = len(result.timing_tracks)
            except Exception:
                pass

        return cls(
            exists=True,
            is_valid=valid,
            age_seconds=age,
            cache_path=output_path,
            track_count=track_count,
        )


class AnalysisCache:
    """Cache wrapper around the existing _analysis.json output file.

    A cache hit requires:
    - The output JSON file exists.
    - Its ``source_hash`` field matches the MD5 hex digest of the source audio.
    """

    def __init__(self, audio_path: Path, output_path: Path) -> None:
        self._audio_path = audio_path
        self._output_path = output_path
        self._md5: str | None = None  # computed lazily and cached

    # ── Public API ────────────────────────────────────────────────────────────

    def is_valid(self) -> bool:
        """Return True if the output JSON exists and its source_hash matches the audio MD5."""
        if not self._output_path.exists():
            return False
        try:
            result = export_mod.read(str(self._output_path))
        except Exception:
            return False
        if result.source_hash is None:
            return False
        return result.source_hash == self._compute_md5()

    def load(self) -> AnalysisResult:
        """Deserialise and return the cached AnalysisResult."""
        return export_mod.read(str(self._output_path))

    def save(self, result: AnalysisResult) -> None:
        """Stamp ``source_hash`` onto *result* and write it to the output path."""
        result.source_hash = self._compute_md5()
        export_mod.write(result, str(self._output_path))

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _compute_md5(self) -> str:
        """Return the MD5 hex digest of the source audio file (computed once)."""
        if self._md5 is None:
            h = hashlib.md5()
            with open(self._audio_path, "rb") as fh:
                for chunk in iter(lambda: fh.read(65536), b""):
                    h.update(chunk)
            self._md5 = h.hexdigest()
        return self._md5
