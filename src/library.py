"""Global song library index stored at ~/.xlight/library.json."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

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
    relative_source_file: Optional[str] = None   # show-dir-relative (cross-env portable)
    relative_analysis_path: Optional[str] = None  # show-dir-relative (cross-env portable)
    title: Optional[str] = None
    artist: Optional[str] = None


def _entry_from_dict(d: dict) -> LibraryEntry:
    """Deserialise a raw dict to LibraryEntry, tolerating missing optional fields.

    ``source_file`` and ``analysis_path`` are resolved to absolute paths for
    the current environment: relative fields take priority (cross-env portable),
    falling back to the stored absolute path (translated if from another env).
    """
    from src.paths import resolve_show_path

    rel_src = d.get("relative_source_file")
    rel_ana = d.get("relative_analysis_path")

    # Prefer relative (portable) over absolute (may be stale/foreign)
    source_file = str(resolve_show_path(rel_src if rel_src else d["source_file"]))
    analysis_path = str(resolve_show_path(rel_ana if rel_ana else d["analysis_path"]))

    return LibraryEntry(
        source_hash=d["source_hash"],
        source_file=source_file,
        filename=d["filename"],
        analysis_path=analysis_path,
        duration_ms=d["duration_ms"],
        estimated_tempo_bpm=d["estimated_tempo_bpm"],
        track_count=d["track_count"],
        stem_separation=d["stem_separation"],
        analyzed_at=d["analyzed_at"],
        relative_source_file=rel_src,
        relative_analysis_path=rel_ana,
        title=d.get("title"),
        artist=d.get("artist"),
    )


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
        return [_entry_from_dict(e) for e in sorted_raw]

    def remove_entry(self, source_hash: str) -> bool:
        """Remove the entry with *source_hash* from the index. Returns True if found."""
        data = self._load()
        original_count = len(data["entries"])
        data["entries"] = [
            e for e in data["entries"] if e.get("source_hash") != source_hash
        ]
        if len(data["entries"]) < original_count:
            self._save(data)
            return True
        return False

    def find_by_hash(self, source_hash: str) -> LibraryEntry | None:
        """Return the entry whose ``source_hash`` matches, or ``None``."""
        data = self._load()
        for raw in data["entries"]:
            if raw.get("source_hash") == source_hash:
                return _entry_from_dict(raw)
        return None

    # ── Internal helpers ──────────────────────────────────────────────────────

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


def delete_files_for_entry(entry: LibraryEntry) -> list[str]:
    """Delete analysis artifacts from disk for a library entry.

    Removes: analysis JSON, hierarchy JSON, story JSON, and stems directory.
    Returns list of paths that were deleted.
    """
    import shutil

    deleted: list[str] = []
    mp3 = Path(entry.source_file)

    # Analysis / hierarchy JSON
    for path_str in [entry.analysis_path]:
        p = Path(path_str)
        if p.exists():
            p.unlink()
            deleted.append(str(p))

    # Story JSON (adjacent to source MP3)
    story_path = mp3.parent / (mp3.stem + "_story.json")
    if story_path.exists():
        story_path.unlink()
        deleted.append(str(story_path))

    # Story edits JSON
    story_edits = mp3.parent / (mp3.stem + "_story_edits.json")
    if story_edits.exists():
        story_edits.unlink()
        deleted.append(str(story_edits))

    # Stems directory — only delete if the MP3 lives in its own dedicated
    # song directory (songs/<stem>/<file>.mp3) to avoid nuking shared stems.
    # Safety check: the parent directory name should match the MP3 stem.
    stems_dir = mp3.parent / "stems"
    if stems_dir.is_dir() and mp3.parent.name == mp3.stem:
        shutil.rmtree(stems_dir)
        deleted.append(str(stems_dir))

    return deleted
