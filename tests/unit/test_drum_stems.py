"""Unit tests for src/analyzer/drum_stems.py — cymbal + snare separation.

Never touches the network or the real model: every test exercises the
cache and graceful-degradation paths, which is what the orchestrator
depends on (any failure must mean "no marks", never an exception).

_run_drumsep_inprocess/_run_drumsep_sidecar return every drumsep source as
a dict (2026-07-18: generalized from cymbals-only so separate_snare can
share one inference run with separate_cymbals) -- mocks below reflect that.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.analyzer import drum_stems


def _drums(duration_s: float = 2.0, sr: int = 22050) -> np.ndarray:
    rng = np.random.default_rng(7)
    return (0.1 * rng.standard_normal(int(sr * duration_s))).astype(np.float32)


class TestSeparateCymbals:
    def test_empty_audio_returns_none(self):
        assert drum_stems.separate_cymbals(np.array([]), 22050) is None

    def test_silent_audio_returns_none(self):
        silent = np.zeros(22050, dtype=np.float32)
        assert drum_stems.separate_cymbals(silent, 22050) is None

    def test_missing_checkpoint_returns_none(self, monkeypatch):
        monkeypatch.setattr(drum_stems, "ensure_checkpoint", lambda: None)
        assert drum_stems.separate_cymbals(_drums(), 22050) is None

    def test_separation_failure_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(drum_stems, "ensure_checkpoint",
                            lambda: tmp_path / "49469ca8.th")
        def _boom(*a, **k):
            raise RuntimeError("model exploded")
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess", _boom)
        assert drum_stems.separate_cymbals(_drums(), 22050) is None

    def test_import_error_falls_back_to_sidecar(self, monkeypatch, tmp_path):
        monkeypatch.setattr(drum_stems, "ensure_checkpoint",
                            lambda: tmp_path / "49469ca8.th")
        def _no_torch(*a, **k):
            raise ImportError("no torch here")
        sentinel = ({"platillos": np.ones(100, dtype=np.float32)}, 44100)
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess", _no_torch)
        monkeypatch.setattr(drum_stems, "_run_drumsep_sidecar",
                            lambda *a, **k: sentinel)
        result = drum_stems.separate_cymbals(_drums(), 22050)
        assert result is not None
        arr, sr = result
        assert sr == 44100
        assert np.array_equal(arr, sentinel[0]["platillos"])

    def test_sidecar_failure_after_import_error_returns_none(
            self, monkeypatch, tmp_path):
        monkeypatch.setattr(drum_stems, "ensure_checkpoint",
                            lambda: tmp_path / "49469ca8.th")
        def _no_torch(*a, **k):
            raise ImportError("no torch here")
        def _no_sidecar(*a, **k):
            raise RuntimeError(".venv-vamp not found")
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess", _no_torch)
        monkeypatch.setattr(drum_stems, "_run_drumsep_sidecar", _no_sidecar)
        assert drum_stems.separate_cymbals(_drums(), 22050) is None

    def test_missing_source_in_model_output_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(drum_stems, "ensure_checkpoint",
                            lambda: tmp_path / "49469ca8.th")
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess",
                            lambda *a, **k: ({"bombo": np.ones(10, dtype=np.float32)}, 44100))
        assert drum_stems.separate_cymbals(_drums(), 22050) is None

    def test_cache_hit_skips_model_entirely(self, monkeypatch, tmp_path):
        # Write a real cached cymbals file, then make everything model-
        # related explode: the cache path must not touch any of it.
        sr = 22050
        cached = _drums(1.0, sr)
        try:
            from src.analyzer.stems import _write_mp3
            _write_mp3(cached, sr, tmp_path / "drums_cymbals.mp3")
        except Exception:
            pytest.skip("ffmpeg unavailable — cache write not testable here")

        def _boom(*a, **k):
            raise AssertionError("model path must not run on cache hit")
        monkeypatch.setattr(drum_stems, "ensure_checkpoint", _boom)
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess", _boom)
        monkeypatch.setattr(drum_stems, "_run_drumsep_sidecar", _boom)

        result = drum_stems.separate_cymbals(_drums(), sr, cache_dir=tmp_path)
        assert result is not None
        arr, out_sr = result
        assert out_sr == sr
        assert arr.size > 0

    def test_successful_separation_writes_cache(self, monkeypatch, tmp_path):
        monkeypatch.setattr(drum_stems, "ensure_checkpoint",
                            lambda: tmp_path / "49469ca8.th")
        cym = (0.2 * np.ones(22050, dtype=np.float32))
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess",
                            lambda *a, **k: ({"platillos": cym}, 22050))
        result = drum_stems.separate_cymbals(_drums(), 22050,
                                             cache_dir=tmp_path)
        assert result is not None
        cache_file = tmp_path / "drums_cymbals.mp3"
        # Cache write may be skipped if ffmpeg is missing; when present the
        # file must exist and be non-empty.
        if cache_file.exists():
            assert cache_file.stat().st_size > 0


class TestSeparateSnare:
    def test_empty_audio_returns_none(self):
        assert drum_stems.separate_snare(np.array([]), 22050) is None

    def test_missing_source_in_model_output_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(drum_stems, "ensure_checkpoint",
                            lambda: tmp_path / "49469ca8.th")
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess",
                            lambda *a, **k: ({"platillos": np.ones(10, dtype=np.float32)}, 44100))
        assert drum_stems.separate_snare(_drums(), 22050) is None

    def test_successful_separation_returns_snare_source(self, monkeypatch, tmp_path):
        monkeypatch.setattr(drum_stems, "ensure_checkpoint",
                            lambda: tmp_path / "49469ca8.th")
        snare = (0.3 * np.ones(22050, dtype=np.float32))
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess",
                            lambda *a, **k: ({"redoblante": snare}, 22050))
        result = drum_stems.separate_snare(_drums(), 22050)
        assert result is not None
        arr, sr = result
        assert sr == 22050
        assert np.array_equal(arr, snare)

    def test_cache_hit_skips_model_entirely(self, monkeypatch, tmp_path):
        sr = 22050
        cached = _drums(1.0, sr)
        try:
            from src.analyzer.stems import _write_mp3
            _write_mp3(cached, sr, tmp_path / "drums_snare.mp3")
        except Exception:
            pytest.skip("ffmpeg unavailable — cache write not testable here")

        def _boom(*a, **k):
            raise AssertionError("model path must not run on cache hit")
        monkeypatch.setattr(drum_stems, "ensure_checkpoint", _boom)
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess", _boom)

        result = drum_stems.separate_snare(_drums(), sr, cache_dir=tmp_path)
        assert result is not None

    def test_one_inference_run_caches_both_cymbals_and_snare(self, monkeypatch, tmp_path):
        # Calling separate_snare first must also opportunistically cache
        # cymbals from the same run, so a later separate_cymbals call hits
        # cache instead of re-running the model (and vice versa).
        monkeypatch.setattr(drum_stems, "ensure_checkpoint",
                            lambda: tmp_path / "49469ca8.th")
        cym = (0.2 * np.ones(22050, dtype=np.float32))
        snare = (0.3 * np.ones(22050, dtype=np.float32))
        call_count = {"n": 0}
        def _run(*a, **k):
            call_count["n"] += 1
            return {"platillos": cym, "redoblante": snare}, 22050
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess", _run)

        snare_result = drum_stems.separate_snare(_drums(), 22050, cache_dir=tmp_path)
        assert snare_result is not None
        assert call_count["n"] == 1

        if not (tmp_path / "drums_cymbals.mp3").exists():
            pytest.skip("ffmpeg unavailable — cross-cache write not testable here")

        def _boom(*a, **k):
            raise AssertionError("model path must not run on cache hit")
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess", _boom)
        cym_result = drum_stems.separate_cymbals(_drums(), 22050, cache_dir=tmp_path)
        assert cym_result is not None
        assert call_count["n"] == 1


class TestSeparateKick:
    def test_empty_audio_returns_none(self):
        assert drum_stems.separate_kick(np.array([]), 22050) is None

    def test_missing_source_in_model_output_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(drum_stems, "ensure_checkpoint",
                            lambda: tmp_path / "49469ca8.th")
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess",
                            lambda *a, **k: ({"platillos": np.ones(10, dtype=np.float32)}, 44100))
        assert drum_stems.separate_kick(_drums(), 22050) is None

    def test_successful_separation_returns_kick_source(self, monkeypatch, tmp_path):
        monkeypatch.setattr(drum_stems, "ensure_checkpoint",
                            lambda: tmp_path / "49469ca8.th")
        kick = (0.4 * np.ones(22050, dtype=np.float32))
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess",
                            lambda *a, **k: ({"bombo": kick}, 22050))
        result = drum_stems.separate_kick(_drums(), 22050)
        assert result is not None
        arr, sr = result
        assert sr == 22050
        assert np.array_equal(arr, kick)

    def test_one_inference_run_caches_all_three(self, monkeypatch, tmp_path):
        monkeypatch.setattr(drum_stems, "ensure_checkpoint",
                            lambda: tmp_path / "49469ca8.th")
        cym = (0.2 * np.ones(22050, dtype=np.float32))
        snare = (0.3 * np.ones(22050, dtype=np.float32))
        kick = (0.4 * np.ones(22050, dtype=np.float32))
        call_count = {"n": 0}
        def _run(*a, **k):
            call_count["n"] += 1
            return {"platillos": cym, "redoblante": snare, "bombo": kick}, 22050
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess", _run)

        kick_result = drum_stems.separate_kick(_drums(), 22050, cache_dir=tmp_path)
        assert kick_result is not None
        assert call_count["n"] == 1

        if not (tmp_path / "drums_cymbals.mp3").exists():
            pytest.skip("ffmpeg unavailable — cross-cache write not testable here")

        def _boom(*a, **k):
            raise AssertionError("model path must not run on cache hit")
        monkeypatch.setattr(drum_stems, "_run_drumsep_inprocess", _boom)
        cym_result = drum_stems.separate_cymbals(_drums(), 22050, cache_dir=tmp_path)
        assert cym_result is not None
        assert call_count["n"] == 1


class TestEnsureCheckpoint:
    def test_existing_checkpoint_returned_without_download(self, monkeypatch, tmp_path):
        ckpt = tmp_path / "49469ca8.th"
        ckpt.write_bytes(b"x" * 10)
        monkeypatch.setattr(drum_stems, "checkpoint_path", lambda: ckpt)
        def _no_net(*a, **k):
            raise AssertionError("must not download when checkpoint exists")
        monkeypatch.setattr(drum_stems, "_download_from_gdrive", _no_net)
        assert drum_stems.ensure_checkpoint() == ckpt

    def test_download_failure_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(drum_stems, "checkpoint_path",
                            lambda: tmp_path / "49469ca8.th")
        def _offline(*a, **k):
            raise OSError("network unreachable")
        monkeypatch.setattr(drum_stems, "_download_from_gdrive", _offline)
        assert drum_stems.ensure_checkpoint() is None
