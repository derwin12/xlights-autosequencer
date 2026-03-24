"""Tests for WizardConfig and related wizard helpers."""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# T005: WizardConfig.to_analyze_kwargs() — must fail until WizardConfig exists
# ---------------------------------------------------------------------------

class TestWizardConfig:
    """WizardConfig dataclass and flag-parity mapping (FR-014)."""

    def _make_config(self, **overrides):
        from src.wizard import WizardConfig
        defaults = dict(
            audio_path="/tmp/song.mp3",
            cache_strategy="regenerate",
            algorithm_groups={"librosa", "vamp", "madmom"},
            use_stems=True,
            use_phonemes=True,
            whisper_model="base",
            use_structure=True,
            use_genius=False,
        )
        defaults.update(overrides)
        return WizardConfig(**defaults)

    def test_to_analyze_kwargs_stems(self):
        cfg = self._make_config(use_stems=True)
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["use_stems"] is True

    def test_to_analyze_kwargs_no_stems(self):
        cfg = self._make_config(use_stems=False)
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["use_stems"] is False

    def test_to_analyze_kwargs_phonemes(self):
        cfg = self._make_config(use_phonemes=True)
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["use_phonemes"] is True

    def test_to_analyze_kwargs_no_phonemes(self):
        cfg = self._make_config(use_phonemes=False)
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["use_phonemes"] is False

    def test_to_analyze_kwargs_whisper_model(self):
        cfg = self._make_config(whisper_model="small")
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["phoneme_model"] == "small"

    def test_to_analyze_kwargs_use_structure(self):
        cfg = self._make_config(use_structure=True)
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["use_structure"] is True

    def test_to_analyze_kwargs_use_genius(self):
        cfg = self._make_config(use_genius=True)
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["genius"] is True

    def test_to_analyze_kwargs_no_genius(self):
        cfg = self._make_config(use_genius=False)
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["genius"] is False

    def test_to_analyze_kwargs_cache_strategy_regenerate(self):
        cfg = self._make_config(cache_strategy="regenerate")
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["no_cache"] is True

    def test_to_analyze_kwargs_cache_strategy_use_existing(self):
        cfg = self._make_config(cache_strategy="use_existing")
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["no_cache"] is False

    def test_to_analyze_kwargs_cache_strategy_skip_write(self):
        cfg = self._make_config(cache_strategy="skip_write")
        kwargs = cfg.to_analyze_kwargs()
        # skip_write runs fresh but doesn't persist; no_cache=True so it bypasses cache read
        assert kwargs["no_cache"] is True
        assert kwargs["skip_cache_write"] is True

    def test_to_analyze_kwargs_algorithm_groups_no_vamp(self):
        cfg = self._make_config(algorithm_groups={"librosa", "madmom"})
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["include_vamp"] is False
        assert kwargs["include_madmom"] is True

    def test_to_analyze_kwargs_algorithm_groups_no_madmom(self):
        cfg = self._make_config(algorithm_groups={"librosa"})
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["include_vamp"] is False
        assert kwargs["include_madmom"] is False

    def test_to_analyze_kwargs_all_groups(self):
        cfg = self._make_config(algorithm_groups={"librosa", "vamp", "madmom"})
        kwargs = cfg.to_analyze_kwargs()
        assert kwargs["include_vamp"] is True
        assert kwargs["include_madmom"] is True


# ---------------------------------------------------------------------------
# WhisperModelInfo tests (T021 — included here since same test file)
# ---------------------------------------------------------------------------

class TestWhisperModelList:
    """whisper_model_list() and WhisperModelInfo."""

    def test_returns_five_models(self):
        from src.wizard import whisper_model_list
        models = whisper_model_list()
        assert len(models) == 5

    def test_model_names(self):
        from src.wizard import whisper_model_list
        names = [m.name for m in whisper_model_list()]
        assert set(names) == {"tiny", "base", "small", "medium", "large-v2"}

    def test_descriptions_non_empty(self):
        from src.wizard import whisper_model_list
        for m in whisper_model_list():
            assert m.description, f"Model {m.name!r} has empty description"

    def test_is_cached_is_boolean(self):
        from src.wizard import whisper_model_list
        with patch("src.wizard._whisper_model_cached", return_value=False):
            for m in whisper_model_list():
                assert isinstance(m.is_cached, bool)

    def test_approximate_size_mb_positive(self):
        from src.wizard import whisper_model_list
        for m in whisper_model_list():
            assert m.approximate_size_mb > 0
