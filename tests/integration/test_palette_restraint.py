"""Integration tests for palette restraint across the generator pipeline."""
from __future__ import annotations

import pytest

from src.generator.effect_placer import (
    _TIER_PALETTE_CAP,
    restrain_palette,
)
from src.generator.models import EffectPlacement, GenerationConfig
from src.generator.xsq_writer import _serialize_palette


FULL_PALETTE = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF", "#FFFFFF", "#000000"]


# ---------------------------------------------------------------------------
# T033: XSQ serialization round-trip for MusicSparkles
# ---------------------------------------------------------------------------

class TestMusicSparklesXsqSerialization:
    """Verify MusicSparkles appears in serialized palette strings."""

    def test_sparkles_zero_not_in_palette_string(self):
        pal_str = _serialize_palette(["#FF0000", "#00FF00"], music_sparkles=0)
        assert "SparkleFrequency" not in pal_str
        assert "MusicSparkles" not in pal_str

    def test_sparkles_nonzero_in_palette_string(self):
        # bug (2026-07-15): the checkbox is what actually enables sparkles in
        # xLights -- the slider value alone did nothing without it, so every
        # prior sparkle placement silently rendered with sparkles off.
        pal_str = _serialize_palette(["#FF0000", "#00FF00"], music_sparkles=50)
        assert "C_CHECKBOX_MusicSparkles=1" in pal_str
        assert "C_SLIDER_SparkleFrequency=50" in pal_str

    def test_sparkles_at_end_of_palette(self):
        pal_str = _serialize_palette(["#FF0000"], music_sparkles=80)
        parts = pal_str.split(",")
        assert parts[-2] == "C_CHECKBOX_MusicSparkles=1"
        assert parts[-1] == "C_SLIDER_SparkleFrequency=80"

    def test_sparkles_100_max(self):
        pal_str = _serialize_palette(["#FF0000"], music_sparkles=100)
        assert "C_CHECKBOX_MusicSparkles=1" in pal_str
        assert "C_SLIDER_SparkleFrequency=100" in pal_str


# ---------------------------------------------------------------------------
# T034: Palette restraint dedup: same colors+sparkles = same palette index
# ---------------------------------------------------------------------------

class TestPaletteDedup:
    """Different sparkle values produce different palette entries."""

    def test_same_sparkles_deduplicates(self):
        from src.generator.xsq_writer import _ensure_palette

        index: dict[str, int] = {}
        pal_list: list[str] = []
        idx1 = _ensure_palette(["#FF0000"], index, pal_list, music_sparkles=50)
        idx2 = _ensure_palette(["#FF0000"], index, pal_list, music_sparkles=50)
        assert idx1 == idx2
        assert len(pal_list) == 1

    def test_different_sparkles_creates_separate_entries(self):
        from src.generator.xsq_writer import _ensure_palette

        index: dict[str, int] = {}
        pal_list: list[str] = []
        idx1 = _ensure_palette(["#FF0000"], index, pal_list, music_sparkles=0)
        idx2 = _ensure_palette(["#FF0000"], index, pal_list, music_sparkles=50)
        assert idx1 != idx2
        assert len(pal_list) == 2


# ---------------------------------------------------------------------------
# T035: End-to-end palette color count verification
# ---------------------------------------------------------------------------

class TestEndToEndPaletteRestraint:
    """Verify that palette restraint reduces color count across all tiers."""

    @pytest.mark.parametrize("tier", [1, 2, 3, 4, 5, 6, 7, 8])
    def test_restrained_palette_never_exceeds_tier_cap(self, tier):
        for energy in range(0, 101, 10):
            result = restrain_palette(FULL_PALETTE, energy, tier)
            cap = _TIER_PALETTE_CAP[tier]
            assert len(result) <= cap, (
                f"tier={tier} energy={energy}: got {len(result)} colors, cap={cap}"
            )

    def test_restrained_palette_monotonically_increases_with_energy(self):
        for tier in range(1, 9):
            prev_len = 0
            for energy in range(0, 101, 5):
                result = restrain_palette(FULL_PALETTE, energy, tier)
                assert len(result) >= prev_len, (
                    f"tier={tier} energy={energy}: got {len(result)} < prev {prev_len}"
                )
                prev_len = len(result)

    def test_palette_restraint_toggle_off_preserves_full_palette(self):
        """When palette_restraint=False, GenerationConfig has the flag off."""
        from pathlib import Path

        config = GenerationConfig(
            audio_path=Path("/dummy.mp3"),
            layout_path=Path("/dummy.xrgb"),
            palette_restraint=False,
        )
        assert config.palette_restraint is False

    def test_palette_restraint_toggle_on_by_default(self):
        from pathlib import Path

        config = GenerationConfig(
            audio_path=Path("/dummy.mp3"),
            layout_path=Path("/dummy.xrgb"),
        )
        assert config.palette_restraint is True

    def test_effect_placement_music_sparkles_default_zero(self):
        p = EffectPlacement(
            effect_name="Bars",
            xlights_id="bars",
            model_or_group="test",
            start_ms=0,
            end_ms=1000,
        )
        assert p.music_sparkles == 0
