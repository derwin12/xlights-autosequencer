"""Tests for the 'generate' CLI subcommand's --variation-seed/--reroll options."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli import cli


@pytest.fixture()
def audio_and_layout(tmp_path):
    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"fake")
    layout_path = tmp_path / "layout.xml"
    layout_path.write_text("<xlightsproject/>")
    return audio_path, layout_path


def _fake_metadata():
    profile = MagicMock()
    profile.genre = "pop"
    return profile


class TestVariationSeedOption:
    def test_defaults_to_zero(self, audio_and_layout):
        audio_path, layout_path = audio_and_layout
        captured = {}

        def fake_generate(config):
            captured["variation_seed"] = config.variation_seed
            return Path("/fake/out.xsq")

        with patch("src.generator.plan.read_song_metadata", return_value=_fake_metadata()), \
             patch("src.generator.plan.generate_sequence", side_effect=fake_generate), \
             patch("src.generator.xsq_writer.fseq_guidance", return_value=""):
            result = CliRunner().invoke(
                cli, ["generate", str(audio_path), str(layout_path)]
            )
        assert result.exit_code == 0, result.output
        assert captured["variation_seed"] == 0

    def test_explicit_seed_passed_through(self, audio_and_layout):
        audio_path, layout_path = audio_and_layout
        captured = {}

        def fake_generate(config):
            captured["variation_seed"] = config.variation_seed
            return Path("/fake/out.xsq")

        with patch("src.generator.plan.read_song_metadata", return_value=_fake_metadata()), \
             patch("src.generator.plan.generate_sequence", side_effect=fake_generate), \
             patch("src.generator.xsq_writer.fseq_guidance", return_value=""):
            result = CliRunner().invoke(
                cli, ["generate", str(audio_path), str(layout_path), "--variation-seed", "42"]
            )
        assert result.exit_code == 0, result.output
        assert captured["variation_seed"] == 42
        assert "Variation seed: 42" in result.output

    def test_reroll_picks_a_random_seed(self, audio_and_layout):
        audio_path, layout_path = audio_and_layout
        captured = {}

        def fake_generate(config):
            captured["variation_seed"] = config.variation_seed
            return Path("/fake/out.xsq")

        with patch("src.generator.plan.read_song_metadata", return_value=_fake_metadata()), \
             patch("src.generator.plan.generate_sequence", side_effect=fake_generate), \
             patch("src.generator.xsq_writer.fseq_guidance", return_value=""), \
             patch("random.randint", return_value=999):
            result = CliRunner().invoke(
                cli, ["generate", str(audio_path), str(layout_path), "--reroll"]
            )
        assert result.exit_code == 0, result.output
        assert captured["variation_seed"] == 999
        assert "Rerolled variation seed: 999" in result.output

    def test_reroll_and_explicit_seed_are_mutually_exclusive(self, audio_and_layout):
        audio_path, layout_path = audio_and_layout
        with patch("src.generator.plan.read_song_metadata", return_value=_fake_metadata()):
            result = CliRunner().invoke(
                cli, ["generate", str(audio_path), str(layout_path),
                      "--reroll", "--variation-seed", "5"]
            )
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output
