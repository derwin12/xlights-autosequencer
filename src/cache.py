"""Analysis result cache keyed by MD5 of the source audio file."""
from __future__ import annotations

import hashlib
from pathlib import Path

from src import export as export_mod
from src.analyzer.result import AnalysisResult


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
