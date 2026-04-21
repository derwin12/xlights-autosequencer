"""Corpus manifest loader and skip categorization."""
from __future__ import annotations

import hashlib
import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ManifestEntry:
    song_id: str
    pro_id: str
    xsq_path: Path
    mp3_path: Path | None
    audio_hash: str          # "md5:<32-hex>" as stored in manifest
    tags: list[str]
    notes_ref: str
    master_may_differ: bool


@dataclass
class SkipEntry:
    song_id: str
    pro_id: str
    reason: str              # e.g. "mp3_missing", "xsq_missing"
    category: str            # "corpus-side" or "our-side"


def _compute_md5(path: Path) -> str:
    return f"md5:{hashlib.md5(path.read_bytes()).hexdigest()}"


class Corpus:
    def __init__(self, manifest_path: Path) -> None:
        self._entries: list[ManifestEntry] = []
        self._skips: list[SkipEntry] = []

        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        seen_keys: set[tuple[str, str]] = set()

        for item in raw["entries"]:
            song_id: str = item["song_id"]
            pro_id: str = item["pro_id"]
            composite_key = (song_id, pro_id)

            if composite_key in seen_keys:
                raise ValueError(
                    f"Duplicate (song_id, pro_id) composite key: ({song_id!r}, {pro_id!r})"
                )
            seen_keys.add(composite_key)

            xsq_path = Path(item["xsq_path"])
            mp3_raw = item.get("mp3_path")
            mp3_path: Path | None = Path(mp3_raw) if mp3_raw else None
            audio_hash: str = item.get("audio_hash", "")
            tags: list[str] = item.get("tags", [])
            notes_ref: str = item.get("notes_ref", "")
            master_may_differ: bool = bool(item.get("master_may_differ", False))

            # --- file-existence checks (corpus-side skips) ---
            if mp3_path is None or not mp3_path.exists():
                self._skips.append(SkipEntry(
                    song_id=song_id,
                    pro_id=pro_id,
                    reason="mp3_missing",
                    category="corpus-side",
                ))
                continue

            if not xsq_path.exists():
                self._skips.append(SkipEntry(
                    song_id=song_id,
                    pro_id=pro_id,
                    reason="xsq_missing",
                    category="corpus-side",
                ))
                continue

            # --- audio hash check (warning only, not a skip) ---
            actual_hash = _compute_md5(mp3_path)
            if audio_hash and actual_hash != audio_hash:
                warnings.warn(
                    f"Audio hash mismatch for danger-zone/{pro_id} "
                    f"(song_id={song_id!r}): manifest has {audio_hash!r}, "
                    f"on-disk is {actual_hash!r}. Entry will still be measured.",
                    UserWarning,
                    stacklevel=2,
                )

            self._entries.append(ManifestEntry(
                song_id=song_id,
                pro_id=pro_id,
                xsq_path=xsq_path,
                mp3_path=mp3_path,
                audio_hash=audio_hash,
                tags=tags,
                notes_ref=notes_ref,
                master_may_differ=master_may_differ,
            ))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def all_entries(self) -> list[ManifestEntry]:
        """All successfully loaded manifest entries (not skipped)."""
        return list(self._entries)

    def measurable_songs(self) -> list[str]:
        """Unique song_ids that have at least one non-skipped entry with a valid mp3."""
        seen: dict[str, None] = {}  # ordered set via insertion order
        for entry in self._entries:
            seen[entry.song_id] = None
        return list(seen)

    def entries_for_song(self, song_id: str) -> list[ManifestEntry]:
        """All non-skipped pro entries for a given song_id."""
        return [e for e in self._entries if e.song_id == song_id]

    def skips(self) -> list[SkipEntry]:
        """All skip entries collected during manifest loading."""
        return list(self._skips)

    def mp3_path_for_song(self, song_id: str) -> Path | None:
        """Return the mp3_path from any non-skipped entry for the song."""
        for entry in self._entries:
            if entry.song_id == song_id and entry.mp3_path is not None:
                return entry.mp3_path
        return None

    def audio_hash_for_song(self, song_id: str) -> str:
        """Return audio_hash from the manifest for a song (first non-skipped entry)."""
        for entry in self._entries:
            if entry.song_id == song_id:
                return entry.audio_hash
        return ""
