"""Tests for src/themes/writer.py — save, delete, rename custom themes."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.themes.writer import delete_theme, rename_theme, save_theme


class TestSaveTheme:
    def test_creates_json_file(self, tmp_path):
        theme_data = {
            "name": "My Cool Theme",
            "mood": "ethereal",
            "occasion": "general",
            "genre": "any",
            "intent": "Test theme",
            "layers": [{"effect": "On", "blend_mode": "Normal", "parameter_overrides": {}}],
            "palette": ["#FF0000", "#00FF00"],
        }
        result = save_theme(theme_data, custom_dir=tmp_path)
        assert result["success"] is True
        assert result["theme_name"] == "My Cool Theme"
        assert Path(result["file_path"]).exists()

    def test_slugifies_filename(self, tmp_path):
        theme_data = {
            "name": "My Cool Theme",
            "mood": "ethereal",
            "occasion": "general",
            "genre": "any",
            "intent": "Test",
            "layers": [{"effect": "On", "blend_mode": "Normal", "parameter_overrides": {}}],
            "palette": ["#FF0000", "#00FF00"],
        }
        result = save_theme(theme_data, custom_dir=tmp_path)
        assert Path(result["file_path"]).name == "my-cool-theme.json"

    def test_file_content_matches(self, tmp_path):
        theme_data = {
            "name": "Test Theme",
            "mood": "dark",
            "occasion": "halloween",
            "genre": "rock",
            "intent": "Spooky",
            "layers": [{"effect": "Fire", "blend_mode": "Normal", "parameter_overrides": {}}],
            "palette": ["#000000", "#FF0000"],
            "accent_palette": ["#440000", "#880000"],
            "variants": [],
        }
        result = save_theme(theme_data, custom_dir=tmp_path)
        with open(result["file_path"], "r") as f:
            written = json.load(f)
        assert written["name"] == "Test Theme"
        assert written["mood"] == "dark"
        assert written["palette"] == ["#000000", "#FF0000"]

    def test_creates_directory_if_missing(self, tmp_path):
        target = tmp_path / "subdir" / "themes"
        theme_data = {
            "name": "Test",
            "mood": "ethereal",
            "occasion": "general",
            "genre": "any",
            "intent": "Test",
            "layers": [{"effect": "On", "blend_mode": "Normal", "parameter_overrides": {}}],
            "palette": ["#FF0000", "#00FF00"],
        }
        result = save_theme(theme_data, custom_dir=target)
        assert result["success"] is True
        assert target.is_dir()

    def test_overwrites_existing(self, tmp_path):
        theme_data = {
            "name": "Test",
            "mood": "ethereal",
            "occasion": "general",
            "genre": "any",
            "intent": "Version 1",
            "layers": [{"effect": "On", "blend_mode": "Normal", "parameter_overrides": {}}],
            "palette": ["#FF0000", "#00FF00"],
        }
        save_theme(theme_data, custom_dir=tmp_path)
        theme_data["intent"] = "Version 2"
        save_theme(theme_data, custom_dir=tmp_path)
        with open(tmp_path / "test.json", "r") as f:
            written = json.load(f)
        assert written["intent"] == "Version 2"

    def test_special_chars_in_name(self, tmp_path):
        theme_data = {
            "name": "Fire & Ice! (v2)",
            "mood": "aggressive",
            "occasion": "general",
            "genre": "rock",
            "intent": "Test",
            "layers": [{"effect": "Fire", "blend_mode": "Normal", "parameter_overrides": {}}],
            "palette": ["#FF0000", "#0000FF"],
        }
        result = save_theme(theme_data, custom_dir=tmp_path)
        assert result["success"] is True
        assert "fire" in Path(result["file_path"]).name.lower()


class TestDeleteTheme:
    def test_deletes_existing(self, tmp_path):
        # Create a theme file first
        theme_file = tmp_path / "my-theme.json"
        theme_file.write_text('{"name": "My Theme"}')
        result = delete_theme("My Theme", custom_dir=tmp_path)
        assert result["success"] is True
        assert not theme_file.exists()

    def test_delete_nonexistent_returns_error(self, tmp_path):
        result = delete_theme("Nonexistent", custom_dir=tmp_path)
        assert result["success"] is False
        assert result["error"] is not None


class TestRenameTheme:
    def test_renames_file(self, tmp_path):
        # Create original
        old_file = tmp_path / "old-name.json"
        old_file.write_text(json.dumps({"name": "Old Name", "mood": "ethereal"}))
        new_data = {"name": "New Name", "mood": "ethereal",
                    "occasion": "general", "genre": "any", "intent": "Renamed",
                    "layers": [{"effect": "On", "blend_mode": "Normal", "parameter_overrides": {}}],
                    "palette": ["#FF0000", "#00FF00"]}
        result = rename_theme("Old Name", new_data, custom_dir=tmp_path)
        assert result["success"] is True
        assert not old_file.exists()
        assert (tmp_path / "new-name.json").exists()
