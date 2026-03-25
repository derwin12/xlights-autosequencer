"""Integration tests: --stems analysis pipeline end-to-end.

SKIPPED: These tests use the old --stems CLI flag. The analyze command was
replaced by the zero-flag orchestrator in feature 016-hierarchy-orchestrator.
"""
from __future__ import annotations

import pytest
pytestmark = pytest.mark.skip(reason="Old --stems flag replaced by auto-stem orchestrator (016)")

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from click.testing import CliRunner

from src.cli import cli
from src.analyzer.stems import StemSeparator, StemSet

SR = 22050
STEM_NAMES = ["drums", "bass", "vocals", "guitar", "piano", "other"]


def _fake_stem_set(sr: int = SR) -> StemSet:
    return StemSet(
        **{name: np.random.rand(sr * 10).astype(np.float32) for name in STEM_NAMES},
        sample_rate=sr,
    )


class TestStemPipeline:
    def test_analyze_with_stems_flag_succeeds(self, mixed_fixture_path: Path, tmp_path: Path):
        """analyze --stems on a fixture produces a JSON output without error."""
        out_path = tmp_path / "out.json"

        with patch.object(StemSeparator, "_run_demucs", return_value=_fake_stem_set()):
            runner = CliRunner()
            result = runner.invoke(cli, [
                "analyze", str(mixed_fixture_path),
                "--stems",
                "--no-vamp", "--no-madmom",
                "--output", str(out_path),
            ])

        assert result.exit_code == 0, result.output
        assert out_path.exists()

    def test_stem_source_set_on_beat_tracks(self, mixed_fixture_path: Path, tmp_path: Path):
        """Beat tracks produced with --stems must have stem_source == 'drums'."""
        out_path = tmp_path / "out.json"

        with patch.object(StemSeparator, "_run_demucs", return_value=_fake_stem_set()):
            runner = CliRunner()
            runner.invoke(cli, [
                "analyze", str(mixed_fixture_path),
                "--stems",
                "--no-vamp", "--no-madmom",
                "--output", str(out_path),
            ])

        data = json.loads(out_path.read_text())
        beat_tracks = [t for t in data["timing_tracks"] if t["element_type"] == "beat"]
        assert len(beat_tracks) > 0, "Expected at least one beat track"
        for track in beat_tracks:
            assert track["stem_source"] == "drums", (
                f"Track {track['name']} should have stem_source='drums', "
                f"got '{track['stem_source']}'"
            )

    def test_stem_separation_metadata_in_json(self, mixed_fixture_path: Path, tmp_path: Path):
        """Output JSON must contain stem_separation=true and stem_cache path."""
        out_path = tmp_path / "out.json"

        with patch.object(StemSeparator, "_run_demucs", return_value=_fake_stem_set()):
            runner = CliRunner()
            runner.invoke(cli, [
                "analyze", str(mixed_fixture_path),
                "--stems",
                "--no-vamp", "--no-madmom",
                "--output", str(out_path),
            ])

        data = json.loads(out_path.read_text())
        assert data.get("stem_separation") is True
        assert data.get("stem_cache") is not None

    def test_no_stems_flag_leaves_stem_source_as_full_mix(
        self, mixed_fixture_path: Path, tmp_path: Path
    ):
        """Without --stems, all tracks must have stem_source == 'full_mix'."""
        out_path = tmp_path / "out.json"

        runner = CliRunner()
        runner.invoke(cli, [
            "analyze", str(mixed_fixture_path),
            "--no-vamp", "--no-madmom",
            "--output", str(out_path),
        ])

        data = json.loads(out_path.read_text())
        for track in data["timing_tracks"]:
            assert track.get("stem_source", "full_mix") == "full_mix", (
                f"Track {track['name']} should have stem_source='full_mix'"
            )
        assert data.get("stem_separation") is False
