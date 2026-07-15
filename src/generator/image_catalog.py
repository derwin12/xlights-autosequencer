"""Catalog of user-supplied images for xLights Pictures effects.

Scans ``<show_dir>/Images`` recursively for image/GIF files so the generator
can place Pictures effects using real show-relative paths (see
``effect_placer._place_picture_effects``), and offers lyric-word matching so
the analyze phase can surface advisory "you have an image for this word"
suggestions (see ``src/review/api/v1/analysis.py``).
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from src.paths import get_show_dir

# Words shorter than this are too generic to match meaningfully (the/and/etc.)
_MIN_WORD_LEN = 4
_MIN_MATCH_RATIO = 0.82

_IMAGE_EXTENSIONS = {".gif", ".png", ".bmp", ".jpg", ".jpeg"}
_CATALOG_SUBDIR = "Images"


def catalog_images(show_dir: Path | None = None) -> list[str]:
    """Return sorted show-relative paths of every image under ``<show_dir>/Images``.

    Returns ``[]`` when the show directory is unknown or has no ``Images``
    subdirectory. Paths are POSIX-style and show-relative (e.g.
    ``"Images/snowman.gif"``), suitable for ``Pictures_Filename``.
    """
    if show_dir is None:
        show_dir = get_show_dir()
    if show_dir is None:
        return []

    images_dir = show_dir / _CATALOG_SUBDIR
    if not images_dir.is_dir():
        return []

    paths = [
        p for p in images_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTENSIONS
    ]
    return sorted(
        p.relative_to(show_dir).as_posix() for p in paths
    )


_WORD_RE = re.compile(r"[a-z0-9]+")


def suggest_images_for_words(
    words: list[dict] | None, image_catalog: list[str]
) -> list[dict]:
    """Fuzzy-match lyric words against catalog image filenames.

    Advisory only — used by the analyze phase to surface "you have an image
    for this word" hints; does not influence generation. Matches each word
    (``{"label"/"word", "start_ms", "end_ms"}``) against every catalog file's
    stem (e.g. ``"Images/snowman.gif"`` -> ``"snowman"``) using
    :class:`difflib.SequenceMatcher`, keeping the best match per word when its
    ratio clears ``_MIN_MATCH_RATIO``. Words shorter than ``_MIN_WORD_LEN`` are
    skipped as too generic. Returns ``[]`` for no words or no catalog.
    """
    if not words or not image_catalog:
        return []

    stems = [(path, Path(path).stem.lower()) for path in image_catalog]

    suggestions: list[dict] = []
    for word in words:
        raw = str(word.get("label") or word.get("word") or "")
        match = _WORD_RE.fullmatch(raw.lower())
        token = match.group(0) if match else ""
        if len(token) < _MIN_WORD_LEN:
            continue

        best_path: str | None = None
        best_ratio = 0.0
        for path, stem in stems:
            ratio = 1.0 if token == stem else difflib.SequenceMatcher(None, token, stem).ratio()
            if ratio > best_ratio:
                best_ratio, best_path = ratio, path

        if best_path is not None and best_ratio >= _MIN_MATCH_RATIO:
            suggestions.append({
                "word": raw,
                "start_ms": word.get("start_ms"),
                "end_ms": word.get("end_ms"),
                "matched_file": best_path,
                "score": round(best_ratio, 3),
            })

    return suggestions
