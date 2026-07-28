"""Tests for StemSet, StemSeparator, and StemCache."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# These imports will fail until stems.py is created — that's expected (TDD).
from src.analyzer.stems import StemCache, StemSeparator, StemSet

SR = 22050
STEM_NAMES = ["drums", "bass", "vocals", "guitar", "piano", "other"]


# ── StemSet ───────────────────────────────────────────────────────────────────

class TestStemSet:
    def test_has_all_six_fields(self):
        arrays = {name: np.zeros(SR, dtype=np.float32) for name in STEM_NAMES}
        ss = StemSet(**arrays, sample_rate=SR)
        for name in STEM_NAMES:
            assert hasattr(ss, name)
        assert ss.sample_rate == SR

    def test_get_by_name_known(self):
        arrays = {name: np.ones(SR, dtype=np.float32) * i for i, name in enumerate(STEM_NAMES)}
        ss = StemSet(**arrays, sample_rate=SR)
        assert np.allclose(ss.get("drums"), arrays["drums"])
        assert np.allclose(ss.get("vocals"), arrays["vocals"])

    def test_get_by_name_unknown_returns_none(self):
        arrays = {name: np.zeros(SR, dtype=np.float32) for name in STEM_NAMES}
        ss = StemSet(**arrays, sample_rate=SR)
        assert ss.get("full_mix") is None
        assert ss.get("nonexistent") is None


# ── StemSeparator ─────────────────────────────────────────────────────────────

def _fake_stem_set() -> StemSet:
    return StemSet(
        **{name: np.random.rand(SR * 10).astype(np.float32) for name in STEM_NAMES},
        sample_rate=SR,
    )


class TestStemSeparator:
    def test_separate_returns_stemset_with_six_stems(self, mixed_fixture_path: Path, tmp_path: Path):
        """StemSeparator.separate() must return a StemSet with 6 non-empty arrays."""
        expected = _fake_stem_set()

        with patch.object(StemSeparator, "_run_demucs", return_value=expected):
            sep = StemSeparator(cache_dir=tmp_path / ".stems")
            result = sep.separate(mixed_fixture_path)

        assert isinstance(result, StemSet)
        for name in STEM_NAMES:
            arr = getattr(result, name)
            assert isinstance(arr, np.ndarray)
            assert len(arr) > 0, f"{name} stem array is empty"
        assert result.sample_rate == SR

    def test_separate_uses_htdemucs_6s_model(self, mixed_fixture_path: Path, tmp_path: Path):
        """StemSeparator must invoke _run_demucs (which uses htdemucs_6s internally)."""
        with patch.object(StemSeparator, "_run_demucs", return_value=_fake_stem_set()) as mock_run:
            StemSeparator(cache_dir=tmp_path / ".stems").separate(mixed_fixture_path)

        mock_run.assert_called_once()

    def test_run_demucs_prefers_inprocess_when_importable(self, tmp_path: Path):
        """bug found 2026-07-25: the packaged app bundles demucs/torch directly
        into the single executable (no .venv-vamp sidecar exists), so
        _run_demucs must try an in-process import first instead of always
        shelling out -- previously it always raised ".venv-vamp not found"
        in that environment even though capabilities.py's detection
        correctly reported demucs as available."""
        pytest.importorskip("demucs")
        pytest.importorskip("torch")
        sep = StemSeparator(cache_dir=tmp_path / ".stems")
        with patch.object(sep, "_run_demucs_inprocess", return_value=_fake_stem_set()) as mock_inprocess, \
             patch.object(sep, "_run_demucs_subprocess") as mock_subprocess:
            sep._run_demucs(Path("fake.mp3"), "deadbeef")

        mock_inprocess.assert_called_once()
        mock_subprocess.assert_not_called()

    def test_inprocess_forwards_progress_cb_via_apply_model_callback(self, tmp_path: Path):
        """User report, 2026-07-28: the SSE analysis stream had zero
        intermediate events for the whole 1-2 minute Demucs separation,
        reading as a frozen/stuck progress bar. _run_demucs_inprocess must
        build a callback= for apply_model that forwards a 0.0-1.0 fraction
        to progress_cb on each segment's "end" event."""
        pytest.importorskip("demucs")
        pytest.importorskip("torch")
        import torch

        sep = StemSeparator(cache_dir=tmp_path / ".stems")
        total_samples = 1000
        fake_model = MagicMock()
        fake_model.sources = STEM_NAMES
        fake_model.samplerate = SR
        captured = {}

        def _fake_apply_model(model, mix, **kwargs):
            captured["callback"] = kwargs.get("callback")
            return torch.zeros(1, len(STEM_NAMES), 2, total_samples)

        with patch("librosa.load",
                    return_value=(np.zeros((2, total_samples), dtype=np.float32), SR)), \
             patch("demucs.pretrained.get_model", return_value=fake_model), \
             patch("demucs.apply.apply_model", side_effect=_fake_apply_model):
            progress_values = []
            sep._run_demucs_inprocess(Path("fake.mp3"), progress_cb=progress_values.append)

        assert captured["callback"] is not None
        # Midway and final segment should map to a proportional fraction.
        captured["callback"]({"state": "end", "segment_offset": 500})
        captured["callback"]({"state": "end", "segment_offset": 1000})
        # "start" events (no progress yet) must not report anything.
        captured["callback"]({"state": "start", "segment_offset": 0})
        assert progress_values == [0.5, 1.0]

    def test_inprocess_without_progress_cb_passes_no_callback(self, tmp_path: Path):
        pytest.importorskip("demucs")
        pytest.importorskip("torch")
        import torch

        sep = StemSeparator(cache_dir=tmp_path / ".stems")
        fake_model = MagicMock()
        fake_model.sources = STEM_NAMES
        fake_model.samplerate = SR
        captured = {}

        def _fake_apply_model(model, mix, **kwargs):
            captured["callback"] = kwargs.get("callback")
            return torch.zeros(1, len(STEM_NAMES), 2, 100)

        with patch("librosa.load",
                    return_value=(np.zeros((2, 100), dtype=np.float32), SR)), \
             patch("demucs.pretrained.get_model", return_value=fake_model), \
             patch("demucs.apply.apply_model", side_effect=_fake_apply_model):
            sep._run_demucs_inprocess(Path("fake.mp3"))

        assert captured["callback"] is None

    def test_run_demucs_falls_back_to_subprocess_when_not_importable(self, tmp_path: Path):
        """When demucs/torch aren't importable in-process (dev-mode main
        venv), fall back to the .venv-vamp sidecar subprocess as before."""
        sep = StemSeparator(cache_dir=tmp_path / ".stems")

        real_import = __import__

        def _blocked_import(name, *args, **kwargs):
            if name in ("demucs", "torch"):
                raise ImportError(f"no module named {name}")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_blocked_import), \
             patch.object(sep, "_run_demucs_inprocess") as mock_inprocess, \
             patch.object(sep, "_run_demucs_subprocess", return_value=_fake_stem_set()) as mock_subprocess:
            sep._run_demucs(Path("fake.mp3"), "deadbeef")

        mock_inprocess.assert_not_called()
        mock_subprocess.assert_called_once()


# ── StemCache ─────────────────────────────────────────────────────────────────

class TestStemCache:
    def _make_stem_set(self) -> StemSet:
        return StemSet(
            **{name: np.random.rand(SR * 5).astype(np.float32) for name in STEM_NAMES},
            sample_rate=SR,
        )

    def test_cache_miss_when_no_directory(self, mixed_fixture_path: Path, tmp_path: Path):
        cache = StemCache(mixed_fixture_path, cache_root=tmp_path / ".stems")
        assert not cache.is_valid()

    def test_cache_hit_after_save(self, mixed_fixture_path: Path, tmp_path: Path):
        cache = StemCache(mixed_fixture_path, cache_root=tmp_path / ".stems")
        stem_set = self._make_stem_set()
        cache.save(stem_set)
        assert cache.is_valid()

    def test_cache_load_round_trip(self, mixed_fixture_path: Path, tmp_path: Path):
        cache = StemCache(mixed_fixture_path, cache_root=tmp_path / ".stems")
        stem_set = self._make_stem_set()
        cache.save(stem_set)

        loaded = cache.load()
        assert isinstance(loaded, StemSet)
        assert loaded.sample_rate == SR
        for name in STEM_NAMES:
            orig = getattr(stem_set, name)
            loaded_arr = getattr(loaded, name)
            assert orig.shape == loaded_arr.shape

    def test_stale_cache_detected_on_hash_mismatch(self, tmp_path: Path):
        """If source file content changes, cache must be detected as stale."""
        audio_path = tmp_path / "song.wav"
        audio_path.write_bytes(b"\x00" * 1000)

        cache = StemCache(audio_path, cache_root=tmp_path / ".stems")
        stem_set = self._make_stem_set()
        cache.save(stem_set)
        assert cache.is_valid()

        # Modify the source file to simulate content change
        audio_path.write_bytes(b"\xff" * 1000)

        # Must detect stale — hash no longer matches directory name
        cache2 = StemCache(audio_path, cache_root=tmp_path / ".stems")
        assert not cache2.is_valid()

    def test_manifest_contains_required_fields(self, mixed_fixture_path: Path, tmp_path: Path):
        cache = StemCache(mixed_fixture_path, cache_root=tmp_path / ".stems")
        cache.save(self._make_stem_set())

        manifest_path = cache.stem_dir / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert "source_hash" in data
        assert "source_path" in data
        assert "created_at" in data
        assert "stems" in data
        assert set(data["stems"].keys()) == set(STEM_NAMES)
