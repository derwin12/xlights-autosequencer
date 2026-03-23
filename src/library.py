"""Global song library index stored at ~/.xlight/library.json."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_LIBRARY_PATH: Path = Path.home() / ".xlight" / "library.json"


@dataclass
class LibraryEntry:
    """One entry in the library index representing a single analyzed song."""

    source_hash: str
    source_file: str
    filename: str
    analysis_path: str
    duration_ms: int
    estimated_tempo_bpm: float
    track_count: int
    stem_separation: bool
    analyzed_at: int  # Unix timestamp in milliseconds


class Library:
    """Read/write wrapper for the flat JSON library index.

    The index lives at *index_path* (default: ``~/.xlight/library.json``).
    It is created automatically on the first write.  There is at most one entry
    per ``source_hash``; upserting replaces the existing entry.
    """

    def __init__(self, index_path: Path | None = None) -> None:
        # Resolve at call time so tests can patch DEFAULT_LIBRARY_PATH after import.
        self._path = index_path if index_path is not None else DEFAULT_LIBRARY_PATH

    # ── Public API ────────────────────────────────────────────────────────────

    def upsert(self, entry: LibraryEntry) -> None:
        """Add or replace the library entry for *entry.source_hash*."""
        data = self._load()
        data["entries"] = [
            e for e in data["entries"] if e.get("source_hash") != entry.source_hash
        ]
        data["entries"].append(asdict(entry))
        self._save(data)

    def all_entries(self) -> list[LibraryEntry]:
        """Return all entries sorted by ``analyzed_at`` descending (newest first)."""
        data = self._load()
        sorted_raw = sorted(
            data["entries"], key=lambda e: e.get("analyzed_at", 0), reverse=True
        )
        return [LibraryEntry(**e) for e in sorted_raw]

    def find_by_hash(self, source_hash: str) -> LibraryEntry | None:
        """Return the entry whose ``source_hash`` matches, or ``None``."""
        data = self._load()
        for raw in data["entries"]:
            if raw.get("source_hash") == source_hash:
                return LibraryEntry(**raw)
        return None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not self._path.exists():
            return {"version": "1.0", "entries": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": "1.0", "entries": []}
        data.setdefault("version", "1.0")
        data.setdefault("entries", [])
        return data

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
