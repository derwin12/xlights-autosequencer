"""Global image library for xLights Pictures effects.

Images are uploaded through the review UI (mirroring
``src/review/api/v1/import_video.py``) and stored in a container-local
library — not scanned from a host-mounted directory, since the devcontainer
running generation has no reliable access to the user's real show folder
(see cerebrum.md 2026-07-15). The library is global, not per-song: an image
tagged "snowman" uploaded once is suggested for every future song whose
lyrics mention "snowman" (``suggest_images_for_words``), driving
``effect_placer._place_picture_effects``'s lyric-matched Pictures bursts.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import tempfile
import uuid
from pathlib import Path

# Words shorter than this are too generic to match meaningfully (the/and/etc.)
_MIN_WORD_LEN = 4
_MIN_MATCH_RATIO = 0.82


def _state_home() -> Path:
    override = os.environ.get("XLIGHT_STATE_HOME")
    if override:
        return Path(override)
    return Path.home() / ".xlight"


def _images_root() -> Path:
    return _state_home() / "library" / "images"


def _manifest_path() -> Path:
    return _images_root() / "manifest.json"


def load_image_library() -> list[dict]:
    """Return every uploaded image's library entry.

    Each entry is ``{"id", "tag", "filename", "stored_path", "uploaded_at"}``.
    Returns ``[]`` when no images have been uploaded yet.
    """
    p = _manifest_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data.get("images", [])


def _save_manifest(images: list[dict]) -> None:
    root = _images_root()
    root.mkdir(parents=True, exist_ok=True)
    p = _manifest_path()
    data = json.dumps({"images": images}, indent=2, ensure_ascii=False)
    fd, tmp_path = tempfile.mkstemp(dir=root, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp_path, str(p))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def save_image_to_library(tag: str, filename: str, data: bytes, uploaded_at: str) -> dict:
    """Store an uploaded image file and append it to the library manifest.

    Returns the new entry. ``filename``'s extension is preserved; the stored
    file is named ``<id>_<filename>`` to avoid collisions between uploads
    that share a filename.
    """
    files_dir = _images_root() / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    entry_id = uuid.uuid4().hex[:16]
    stored_name = f"{entry_id}_{filename}"
    stored_path = files_dir / stored_name
    stored_path.write_bytes(data)

    entry = {
        "id": entry_id,
        "tag": tag,
        "filename": filename,
        "stored_path": str(stored_path),
        "uploaded_at": uploaded_at,
    }
    images = load_image_library()
    images.append(entry)
    _save_manifest(images)
    return entry


def catalog_images() -> list[str]:
    """Return the stored absolute path of every uploaded library image."""
    return [e["stored_path"] for e in load_image_library() if e.get("stored_path")]


_WORD_RE = re.compile(r"[a-z0-9]+")


def suggest_images_for_words(
    words: list[dict] | None,
    library: list[dict] | None = None,
    ignored_words: list[str] | None = None,
) -> list[dict]:
    """Fuzzy-match lyric words against the image library's tags.

    Used both by the analyze phase to surface "you have an image for this
    word" hints, and by ``effect_placer._place_picture_effects`` (via
    ``plan.py``) to prefer a lyric-matched image over the random rotation
    when a placement's time window overlaps the match. Matches each word
    (``{"label"/"word", "start_ms", "end_ms"}``) against every library
    entry's ``tag`` using :class:`difflib.SequenceMatcher`, keeping the best
    match per word when its ratio clears ``_MIN_MATCH_RATIO``. Words shorter
    than ``_MIN_WORD_LEN`` are skipped as too generic. ``library`` defaults
    to :func:`load_image_library` when not supplied (tests pass a fixed list
    for determinism). ``ignored_words`` (case-insensitive) suppresses matches
    for words the user unmapped on the review UI's Pictures screen — a
    per-song ignore, so the library entry itself stays available to other
    songs. Returns ``[]`` for no words or an empty library. Each
    suggestion includes ``stored_path`` (the matched entry's absolute file
    path) so callers can resolve straight to the image file.
    """
    if library is None:
        library = load_image_library()
    if not words or not library:
        return []

    tags = [(entry, entry.get("tag", "").lower()) for entry in library if entry.get("tag")]
    ignored = {w.lower() for w in (ignored_words or [])}

    suggestions: list[dict] = []
    for word in words:
        raw = str(word.get("label") or word.get("word") or "")
        match = _WORD_RE.fullmatch(raw.lower())
        token = match.group(0) if match else ""
        if len(token) < _MIN_WORD_LEN or token in ignored:
            continue

        best_entry: dict | None = None
        best_ratio = 0.0
        for entry, tag in tags:
            ratio = 1.0 if token == tag else difflib.SequenceMatcher(None, token, tag).ratio()
            if ratio > best_ratio:
                best_ratio, best_entry = ratio, entry

        if best_entry is not None and best_ratio >= _MIN_MATCH_RATIO:
            suggestions.append({
                "word": raw,
                "start_ms": word.get("start_ms"),
                "end_ms": word.get("end_ms"),
                "matched_file": best_entry["filename"],
                "matched_tag": best_entry["tag"],
                "stored_path": best_entry.get("stored_path"),
                "score": round(best_ratio, 3),
            })

    return suggestions


# Common function/filler words excluded from unmatched-topic suggestions —
# without this, every song surfaces "with"/"that"/"your" as an image topic,
# drowning out words that actually name something concrete enough to
# illustrate. Not exhaustive, just the highest-frequency English filler words.
_STOPWORDS = frozenset({
    "that", "this", "with", "your", "have", "from", "they", "will", "just",
    "when", "what", "there", "their", "then", "them", "these", "those",
    "into", "than", "were", "been", "being", "would", "could", "should",
    "about", "cause", "gonna", "wanna", "gotta", "yeah", "okay", "cant",
    "dont", "wont", "aint", "never", "always", "still", "again", "only",
    "even", "over", "under", "here", "where", "which", "while",
})


def find_unmatched_topics(words: list[dict] | None, library: list[dict] | None = None) -> list[dict]:
    """Return unique lyric words with no matching image-library tag yet.

    Candidates for the "suggested topics" upload flow: real words (see
    :func:`suggest_images_for_words` for the length/regex filter), excluding
    common filler words (``_STOPWORDS``) and anything already matched to an
    existing library entry. Deduped by lowercase token, keeping each word's
    first occurrence timestamp. Returns ``[]`` for no words.
    """
    if not words:
        return []
    if library is None:
        library = load_image_library()

    matched_tokens = {
        s["word"].lower() for s in suggest_images_for_words(words, library)
    }

    seen: dict[str, dict] = {}
    for word in words:
        raw = str(word.get("label") or word.get("word") or "")
        match = _WORD_RE.fullmatch(raw.lower())
        token = match.group(0) if match else ""
        if len(token) < _MIN_WORD_LEN or token in _STOPWORDS or token in matched_tokens:
            continue
        if token not in seen:
            seen[token] = {
                "word": raw,
                "start_ms": word.get("start_ms"),
                "end_ms": word.get("end_ms"),
            }

    return list(seen.values())
