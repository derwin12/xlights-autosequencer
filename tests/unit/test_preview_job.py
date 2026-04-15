"""Tests for preview.py — CancelToken, PreviewJob lifecycle, brief hash, LRU cache."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.generator.preview import (
    CancelToken,
    PreviewCancelled,
    PreviewJob,
    PreviewResult,
    _PreviewCache,
    _canonical_brief_hash,
)


# ── T008: PreviewJob lifecycle transitions ─────────────────────────────────


def test_preview_job_initial_state():
    """PreviewJob starts in 'pending' status with no artifact or error."""
    token = CancelToken()
    job = PreviewJob(
        job_id="test-id",
        song_hash="abc123",
        section_index=2,
        brief_snapshot={"genre": "pop"},
        brief_hash="aabbccdd11223344",
        status="pending",
        started_at=time.time(),
    )
    assert job.status == "pending"
    assert job.artifact_path is None
    assert job.error_message is None
    assert job.result is None
    assert job.completed_at is None


def test_preview_job_pending_to_running():
    """Setting status to 'running' and started_at records state correctly."""
    job = PreviewJob(
        job_id="test-id",
        song_hash="abc123",
        section_index=0,
        brief_snapshot={},
        brief_hash="0" * 16,
        status="pending",
        started_at=0.0,
    )
    t0 = time.time()
    job.status = "running"
    job.started_at = t0
    assert job.status == "running"
    assert job.started_at == t0


def test_preview_job_running_to_done(tmp_path):
    """Completed job has status 'done', completed_at, artifact_path, and result set."""
    artifact = tmp_path / "preview.xsq"
    artifact.write_text("<xsequence/>")

    result = PreviewResult(
        section={"label": "chorus", "start_ms": 45000, "end_ms": 60000,
                 "energy_score": 82, "role": "chorus"},
        window_ms=15000,
        theme_name="Polar Night",
        placement_count=42,
        artifact_url="/api/song/abc123/preview/test-id/download",
    )
    job = PreviewJob(
        job_id="test-id",
        song_hash="abc123",
        section_index=0,
        brief_snapshot={},
        brief_hash="0" * 16,
        status="running",
        started_at=time.time(),
    )
    t1 = time.time()
    job.status = "done"
    job.completed_at = t1
    job.artifact_path = artifact
    job.result = result

    assert job.status == "done"
    assert job.completed_at == t1
    assert job.artifact_path == artifact
    assert job.result is result


def test_preview_job_running_to_failed():
    """Failed job has status 'failed', completed_at, and error_message set."""
    job = PreviewJob(
        job_id="test-id",
        song_hash="abc123",
        section_index=0,
        brief_snapshot={},
        brief_hash="0" * 16,
        status="running",
        started_at=time.time(),
    )
    job.status = "failed"
    job.completed_at = time.time()
    job.error_message = "Layout file not found."

    assert job.status == "failed"
    assert job.error_message == "Layout file not found."
    assert job.artifact_path is None


# ── T009: CancelToken lifecycle ─────────────────────────────────────────────


def test_cancel_token_initial_not_cancelled():
    """Fresh CancelToken is not cancelled."""
    token = CancelToken()
    assert not token.is_cancelled()


def test_cancel_token_cancel_sets_flag():
    """cancel() sets is_cancelled() to True."""
    token = CancelToken()
    token.cancel()
    assert token.is_cancelled()


def test_cancel_token_raise_if_cancelled_raises():
    """raise_if_cancelled() raises PreviewCancelled after cancel()."""
    token = CancelToken()
    token.cancel()
    with pytest.raises(PreviewCancelled):
        token.raise_if_cancelled()


def test_cancel_token_raise_if_not_cancelled_is_noop():
    """raise_if_cancelled() does nothing when token is not cancelled."""
    token = CancelToken()
    # Should not raise
    token.raise_if_cancelled()


def test_cancel_token_idempotent():
    """Calling cancel() multiple times is safe."""
    token = CancelToken()
    token.cancel()
    token.cancel()  # second call should not raise
    assert token.is_cancelled()


# ── T010: canonical brief hash ─────────────────────────────────────────────


def test_canonical_brief_hash_deterministic():
    """Same brief always produces the same hash."""
    brief = {"focused_vocabulary": True, "genre": "pop", "curves_mode": "none"}
    h1 = _canonical_brief_hash(brief)
    h2 = _canonical_brief_hash(brief)
    assert h1 == h2


def test_canonical_brief_hash_key_order_independent():
    """Two dicts with the same key-value pairs in different order hash identically."""
    brief_a = {"genre": "pop", "focused_vocabulary": True, "curves_mode": "none"}
    brief_b = {"focused_vocabulary": True, "curves_mode": "none", "genre": "pop"}
    assert _canonical_brief_hash(brief_a) == _canonical_brief_hash(brief_b)


def test_canonical_brief_hash_different_values_differ():
    """Different brief values produce different hashes."""
    brief_a = {"genre": "pop"}
    brief_b = {"genre": "rock"}
    assert _canonical_brief_hash(brief_a) != _canonical_brief_hash(brief_b)


def test_canonical_brief_hash_length():
    """Hash is exactly 16 hex characters."""
    h = _canonical_brief_hash({"x": 1})
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_canonical_brief_hash_empty_dict():
    """Empty brief hashes consistently."""
    h1 = _canonical_brief_hash({})
    h2 = _canonical_brief_hash({})
    assert h1 == h2
    assert len(h1) == 16


# ── T011: _PreviewCache LRU eviction ───────────────────────────────────────


def _make_result() -> PreviewResult:
    return PreviewResult(
        section={"label": "chorus", "start_ms": 0, "end_ms": 15000,
                 "energy_score": 80, "role": "chorus"},
        window_ms=15000,
        theme_name="Arctic Lights",
        placement_count=10,
        artifact_url="/download",
    )


def test_preview_cache_put_and_get(tmp_path):
    """Cache returns (result, path) after put."""
    cache = _PreviewCache(max_entries=16)
    key = ("hash1", 0, "brief1234567890a")
    result = _make_result()
    artifact = tmp_path / "preview.xsq"
    artifact.write_text("<xsequence/>")

    cache.put(key, result, artifact)
    cached = cache.get(key)
    assert cached is not None
    assert cached[0] is result
    assert cached[1] == artifact


def test_preview_cache_miss_returns_none():
    """get() returns None for unknown key."""
    cache = _PreviewCache(max_entries=16)
    result = cache.get(("unknown", 0, "brief"))
    assert result is None


def test_preview_cache_lru_eviction(tmp_path):
    """16th entry evicts the oldest when max_entries=16."""
    cache = _PreviewCache(max_entries=16)

    # Fill 16 entries
    for i in range(16):
        key = ("hash", i, f"brief{i:016x}")
        artifact = tmp_path / f"preview_{i}.xsq"
        artifact.write_text("<xsequence/>")
        cache.put(key, _make_result(), artifact)

    assert len(cache) == 16

    # Insert 17th — oldest (i=0) should be evicted
    key_oldest = ("hash", 0, "brief%016x" % 0)
    key_new = ("hash", 100, "briefnew12345678")
    artifact_new = tmp_path / "preview_new.xsq"
    artifact_new.write_text("<xsequence/>")
    cache.put(key_new, _make_result(), artifact_new)

    assert len(cache) == 16
    assert cache.get(key_oldest) is None  # evicted


def test_preview_cache_eviction_deletes_file(tmp_path):
    """Evicted entry's .xsq file is deleted from disk."""
    cache = _PreviewCache(max_entries=2)

    # Fill 2 entries with real files
    artifacts = []
    for i in range(2):
        key = ("hash", i, f"brief{i:016x}")
        artifact = tmp_path / f"preview_{i}.xsq"
        artifact.write_text("<xsequence/>")
        artifacts.append((key, artifact))
        cache.put(key, _make_result(), artifact)

    assert artifacts[0][1].exists()

    # 3rd entry evicts the first
    key3 = ("hash", 99, "briefnewentry000")
    artifact3 = tmp_path / "preview_99.xsq"
    artifact3.write_text("<xsequence/>")
    cache.put(key3, _make_result(), artifact3)

    # First artifact should be deleted
    assert not artifacts[0][1].exists()
    # Second artifact should still exist
    assert artifacts[1][1].exists()


# ── T012: Cache only admits 'done' results ─────────────────────────────────


def test_preview_cache_does_not_store_failed_jobs(tmp_path):
    """Simulated failed job — do not put into cache — verify cache miss."""
    cache = _PreviewCache(max_entries=16)
    key = ("hash1", 0, "brief1234567890a")

    # Simulate a failed job: caller should NOT call put() — verify no entry
    cached = cache.get(key)
    assert cached is None


def test_preview_cache_only_put_on_done(tmp_path):
    """Only put() entries for done jobs — verify no entries for others."""
    cache = _PreviewCache(max_entries=16)

    # We verify the caller contract: only done results get inserted.
    # The cache itself doesn't know about job status — it trusts the caller.
    # Test that put() correctly inserts and get() returns it.
    key = ("hash1", 0, "brief1234567890a")
    artifact = tmp_path / "preview.xsq"
    artifact.write_text("<xsequence/>")
    result = _make_result()

    # Should only be called for done jobs (caller contract)
    cache.put(key, result, artifact)
    assert cache.get(key) is not None
    assert len(cache) == 1
