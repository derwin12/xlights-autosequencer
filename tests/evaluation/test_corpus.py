"""Tests for the corpus manifest loader (src/evaluation/corpus.py)."""
from __future__ import annotations

import hashlib
import json
import warnings
from pathlib import Path

import pytest

from src.evaluation.corpus import Corpus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_manifest(tmp_path: Path, entries: list[dict]) -> Path:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return manifest


def _fake_file(tmp_path: Path, name: str, content: bytes = b"fake") -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def _md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# ---------------------------------------------------------------------------
# T010-1: basic load
# ---------------------------------------------------------------------------

def test_load_manifest_basic(tmp_path: Path) -> None:
    xsq1 = _fake_file(tmp_path, "a.xsq")
    xsq2 = _fake_file(tmp_path, "b.xsq")
    mp3 = _fake_file(tmp_path, "song.mp3")
    correct_hash = f"md5:{_md5_hex(mp3.read_bytes())}"

    manifest = _write_manifest(tmp_path, [
        {
            "song_id": "danger-zone",
            "pro_id": "xatw",
            "xsq_path": str(xsq1),
            "mp3_path": str(mp3),
            "audio_hash": correct_hash,
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        },
        {
            "song_id": "danger-zone",
            "pro_id": "poling",
            "xsq_path": str(xsq2),
            "mp3_path": str(mp3),
            "audio_hash": correct_hash,
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        },
    ])

    corpus = Corpus(manifest)
    assert len(corpus.all_entries()) == 2


# ---------------------------------------------------------------------------
# T010-2: correct audio hash → not a skip
# ---------------------------------------------------------------------------

def test_audio_hash_match(tmp_path: Path) -> None:
    content = b"this is a fake mp3 file"
    mp3 = _fake_file(tmp_path, "song.mp3", content)
    xsq = _fake_file(tmp_path, "song.xsq")
    correct_hash = f"md5:{_md5_hex(content)}"

    manifest = _write_manifest(tmp_path, [
        {
            "song_id": "danger-zone",
            "pro_id": "xatw",
            "xsq_path": str(xsq),
            "mp3_path": str(mp3),
            "audio_hash": correct_hash,
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        },
    ])

    corpus = Corpus(manifest)
    skip_ids = {s.song_id for s in corpus.skips()}
    assert "danger-zone" not in skip_ids


# ---------------------------------------------------------------------------
# T010-3: wrong audio hash → warning, but still measurable
# ---------------------------------------------------------------------------

def test_audio_hash_mismatch_warns(tmp_path: Path) -> None:
    content = b"some audio bytes"
    mp3 = _fake_file(tmp_path, "song.mp3", content)
    xsq = _fake_file(tmp_path, "song.xsq")

    manifest = _write_manifest(tmp_path, [
        {
            "song_id": "danger-zone",
            "pro_id": "xatw",
            "xsq_path": str(xsq),
            "mp3_path": str(mp3),
            "audio_hash": "md5:00000000000000000000000000000000",
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        },
    ])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        corpus = Corpus(manifest)

    # Still measurable (not skipped)
    assert "danger-zone" in corpus.measurable_songs()

    # A warning was issued
    assert any("danger-zone" in str(w.message) or "hash" in str(w.message).lower()
               for w in caught), f"Expected a hash-mismatch warning; got: {[str(w.message) for w in caught]}"


# ---------------------------------------------------------------------------
# T010-4: missing mp3 → corpus-side skip
# ---------------------------------------------------------------------------

def test_missing_mp3_is_corpus_side_skip(tmp_path: Path) -> None:
    xsq = _fake_file(tmp_path, "song.xsq")

    manifest = _write_manifest(tmp_path, [
        {
            "song_id": "uptown-funk",
            "pro_id": "xatw",
            "xsq_path": str(xsq),
            "mp3_path": str(tmp_path / "nonexistent.mp3"),
            "audio_hash": "md5:00000000000000000000000000000000",
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        },
    ])

    corpus = Corpus(manifest)
    skips = corpus.skips()
    matching = [s for s in skips if s.song_id == "uptown-funk"]
    assert matching, "Expected a skip entry for uptown-funk"
    assert matching[0].category == "corpus-side"
    assert "mp3_missing" in matching[0].reason


# ---------------------------------------------------------------------------
# T010-5: missing xsq → corpus-side skip
# ---------------------------------------------------------------------------

def test_missing_xsq_is_corpus_side_skip(tmp_path: Path) -> None:
    content = b"audio"
    mp3 = _fake_file(tmp_path, "song.mp3", content)

    manifest = _write_manifest(tmp_path, [
        {
            "song_id": "bad-romance",
            "pro_id": "xatw",
            "xsq_path": str(tmp_path / "nonexistent.xsq"),
            "mp3_path": str(mp3),
            "audio_hash": f"md5:{_md5_hex(content)}",
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        },
    ])

    corpus = Corpus(manifest)
    skips = corpus.skips()
    matching = [s for s in skips if s.song_id == "bad-romance"]
    assert matching, "Expected a skip entry for bad-romance"
    assert matching[0].category == "corpus-side"
    assert "xsq_missing" in matching[0].reason


# ---------------------------------------------------------------------------
# T010-6: master_may_differ propagation
# ---------------------------------------------------------------------------

def test_master_may_differ_propagation(tmp_path: Path) -> None:
    content = b"audio data"
    mp3 = _fake_file(tmp_path, "song.mp3", content)
    xsq = _fake_file(tmp_path, "song.xsq")
    correct_hash = f"md5:{_md5_hex(content)}"

    manifest = _write_manifest(tmp_path, [
        {
            "song_id": "light-of-christmas",
            "pro_id": "xatw",
            "xsq_path": str(xsq),
            "mp3_path": str(mp3),
            "audio_hash": correct_hash,
            "tags": ["christmas"],
            "notes_ref": "",
            "master_may_differ": True,
        },
    ])

    corpus = Corpus(manifest)
    assert "light-of-christmas" in corpus.measurable_songs()
    entries = corpus.entries_for_song("light-of-christmas")
    assert len(entries) == 1
    assert entries[0].master_may_differ is True


# ---------------------------------------------------------------------------
# T010-7: duplicate composite key raises ValueError
# ---------------------------------------------------------------------------

def test_duplicate_composite_key_raises(tmp_path: Path) -> None:
    xsq = _fake_file(tmp_path, "song.xsq")
    mp3 = _fake_file(tmp_path, "song.mp3")
    h = f"md5:{_md5_hex(mp3.read_bytes())}"

    manifest = _write_manifest(tmp_path, [
        {
            "song_id": "danger-zone",
            "pro_id": "xatw",
            "xsq_path": str(xsq),
            "mp3_path": str(mp3),
            "audio_hash": h,
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        },
        {
            "song_id": "danger-zone",
            "pro_id": "xatw",   # same composite key
            "xsq_path": str(xsq),
            "mp3_path": str(mp3),
            "audio_hash": h,
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        },
    ])

    with pytest.raises(ValueError, match=r"(?i)duplicate"):
        Corpus(manifest)


# ---------------------------------------------------------------------------
# T010-8: measurable_songs unique by song_id
# ---------------------------------------------------------------------------

def test_measurable_songs_unique_by_song_id(tmp_path: Path) -> None:
    content = b"audio"
    mp3 = _fake_file(tmp_path, "song.mp3", content)
    xsq1 = _fake_file(tmp_path, "a.xsq")
    xsq2 = _fake_file(tmp_path, "b.xsq")
    xsq3 = _fake_file(tmp_path, "c.xsq")
    h = f"md5:{_md5_hex(content)}"

    manifest = _write_manifest(tmp_path, [
        {
            "song_id": "danger-zone",
            "pro_id": "xatw",
            "xsq_path": str(xsq1),
            "mp3_path": str(mp3),
            "audio_hash": h,
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        },
        {
            "song_id": "danger-zone",
            "pro_id": "poling",
            "xsq_path": str(xsq2),
            "mp3_path": str(mp3),
            "audio_hash": h,
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        },
        {
            "song_id": "baby-shark",
            "pro_id": "xatw",
            "xsq_path": str(xsq3),
            "mp3_path": str(mp3),
            "audio_hash": h,
            "tags": [],
            "notes_ref": "",
            "master_may_differ": False,
        },
    ])

    corpus = Corpus(manifest)
    measurable = corpus.measurable_songs()
    assert sorted(measurable) == ["baby-shark", "danger-zone"]
    assert len(measurable) == len(set(measurable)), "measurable_songs() must not contain duplicates"
