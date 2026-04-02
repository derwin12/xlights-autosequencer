"""Tests for the rotation-report CLI subcommand (T038)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.cli import cli


def _make_plan_json(tmp_path: Path) -> Path:
    """Create a minimal plan JSON file with rotation_plan data."""
    plan_data = {
        "song_profile": {
            "title": "Test Song",
            "artist": "Test Artist",
            "genre": "pop",
            "occasion": "christmas",
            "duration_ms": 180000,
            "estimated_bpm": 120.0,
        },
        "rotation_plan": {
            "sections_count": 2,
            "groups_count": 3,
            "symmetry_pairs": [],
            "entries": [
                {
                    "section_index": 0,
                    "section_label": "verse",
                    "group_name": "Arches",
                    "group_tier": 6,
                    "variant_name": "Fire Blaze High",
                    "base_effect": "Fire",
                    "score": 0.85,
                    "score_breakdown": {"energy": 0.40, "suitability": 0.30, "diversity": 0.15},
                    "source": "library",
                },
                {
                    "section_index": 0,
                    "section_label": "verse",
                    "group_name": "Matrix-Center",
                    "group_tier": 6,
                    "variant_name": "Bars Sweep Left",
                    "base_effect": "Bars",
                    "score": 0.72,
                    "score_breakdown": {"energy": 0.35, "suitability": 0.25, "diversity": 0.12},
                    "source": "library",
                },
                {
                    "section_index": 1,
                    "section_label": "chorus",
                    "group_name": "Arches",
                    "group_tier": 6,
                    "variant_name": "Meteors Gentle Rain",
                    "base_effect": "Meteors",
                    "score": 0.91,
                    "score_breakdown": {"energy": 0.45, "suitability": 0.35, "diversity": 0.11},
                    "source": "library",
                },
            ],
        },
    }
    path = tmp_path / "test_song.plan.json"
    path.write_text(json.dumps(plan_data, indent=2))
    return path


class TestRotationReportTableFormat:
    """Test rotation-report table output."""

    def test_table_output_contains_expected_columns(self, tmp_path):
        plan_path = _make_plan_json(tmp_path)
        result = CliRunner().invoke(cli, ["rotation-report", str(plan_path)])
        assert result.exit_code == 0
        # Header row should contain column names
        assert "Section" in result.output
        assert "Group" in result.output
        assert "Variant" in result.output
        assert "Score" in result.output
        assert "Top Factors" in result.output

    def test_table_output_contains_entry_data(self, tmp_path):
        plan_path = _make_plan_json(tmp_path)
        result = CliRunner().invoke(cli, ["rotation-report", str(plan_path)])
        assert result.exit_code == 0
        assert "Fire Blaze High" in result.output
        assert "Bars Sweep Left" in result.output
        assert "Meteors Gentle Rain" in result.output
        assert "verse" in result.output
        assert "chorus" in result.output
        assert "Arches" in result.output

    def test_table_output_contains_summary(self, tmp_path):
        plan_path = _make_plan_json(tmp_path)
        result = CliRunner().invoke(cli, ["rotation-report", str(plan_path)])
        assert result.exit_code == 0
        assert "Symmetry pairs: 0" in result.output
        assert "Sections: 2" in result.output
        assert "Groups: 3" in result.output
        assert "Unique variants: 3" in result.output

    def test_section_filter(self, tmp_path):
        plan_path = _make_plan_json(tmp_path)
        result = CliRunner().invoke(cli, ["rotation-report", str(plan_path), "--section", "chorus"])
        assert result.exit_code == 0
        assert "Meteors Gentle Rain" in result.output
        # verse entries should be filtered out
        assert "Fire Blaze High" not in result.output
        assert "Bars Sweep Left" not in result.output

    def test_group_filter(self, tmp_path):
        plan_path = _make_plan_json(tmp_path)
        result = CliRunner().invoke(cli, ["rotation-report", str(plan_path), "--group", "Arches"])
        assert result.exit_code == 0
        assert "Fire Blaze High" in result.output
        assert "Meteors Gentle Rain" in result.output
        # Matrix-Center entry should be filtered out
        assert "Bars Sweep Left" not in result.output


class TestRotationReportJsonFormat:
    """Test rotation-report JSON output."""

    def test_json_output_is_valid(self, tmp_path):
        plan_path = _make_plan_json(tmp_path)
        result = CliRunner().invoke(cli, ["rotation-report", str(plan_path), "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "rotation_plan" in data
        assert "entries" in data["rotation_plan"]
        assert len(data["rotation_plan"]["entries"]) == 3

    def test_json_output_preserves_scores(self, tmp_path):
        plan_path = _make_plan_json(tmp_path)
        result = CliRunner().invoke(cli, ["rotation-report", str(plan_path), "--format", "json"])
        data = json.loads(result.output)
        entries = data["rotation_plan"]["entries"]
        scores = {e["variant_name"]: e["score"] for e in entries}
        assert scores["Fire Blaze High"] == pytest.approx(0.85)
        assert scores["Meteors Gentle Rain"] == pytest.approx(0.91)

    def test_json_with_section_filter(self, tmp_path):
        plan_path = _make_plan_json(tmp_path)
        result = CliRunner().invoke(cli, [
            "rotation-report", str(plan_path), "--format", "json", "--section", "verse",
        ])
        data = json.loads(result.output)
        entries = data["rotation_plan"]["entries"]
        assert len(entries) == 2
        assert all(e["section_label"] == "verse" for e in entries)


class TestRotationReportMissingFile:
    """Test rotation-report with invalid inputs."""

    def test_missing_file_exits_nonzero(self):
        result = CliRunner().invoke(cli, ["rotation-report", "/nonexistent/path.json"])
        assert result.exit_code != 0

    def test_no_rotation_plan_in_file(self, tmp_path):
        # File exists but has no rotation_plan key
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"song_profile": {}}))
        result = CliRunner().invoke(cli, ["rotation-report", str(path)])
        assert result.exit_code == 2
        assert "No rotation plan" in result.output
