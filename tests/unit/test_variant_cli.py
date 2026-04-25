"""Tests for variant CLI subcommands: list, show, coverage."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.cli import cli
from src.effects.library import load_effect_library
from src.variants.library import load_variant_library

FIXTURES = Path(__file__).parent.parent / "fixtures"
EFFECTS_FIXTURE = FIXTURES / "effects" / "minimal_library_with_meteors.json"
VARIANTS_FIXTURE = FIXTURES / "variants" / "builtin_variants_minimal.json"


@pytest.fixture(autouse=True)
def inject_variant_lib(tmp_path, monkeypatch):
    """Inject fixture-based libraries into the CLI module.

    The variant CLI commands live in src.cli_old (re-exported through
    src.cli for backward compat). _get_variant_lib() reads the override
    from src.cli_old, so we must patch there. Patching src.cli only
    updates the re-exported reference, which the actual command function
    doesn't see.
    """
    import src.cli_old as cli_module

    effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE)
    lib = load_variant_library(
        builtin_path=VARIANTS_FIXTURE,
        custom_dir=tmp_path,
        effect_library=effect_lib,
    )
    monkeypatch.setattr(cli_module, "_variant_library_override", lib)
    monkeypatch.setattr(cli_module, "_variant_effect_library_override", effect_lib)
    monkeypatch.setattr(cli_module, "_variant_custom_dir_override", tmp_path)


class TestVariantList:
    def test_exit_code_zero(self):
        result = CliRunner().invoke(cli, ["variant", "list"])
        assert result.exit_code == 0

    def test_shows_all_variant_names(self):
        result = CliRunner().invoke(cli, ["variant", "list"])
        assert "Fire Blaze High" in result.output
        assert "Bars Sweep Left" in result.output
        assert "Meteors Gentle Rain" in result.output

    def test_filter_by_effect(self):
        result = CliRunner().invoke(cli, ["variant", "list", "--effect", "Meteors"])
        assert "Meteors Gentle Rain" in result.output
        assert "Fire Blaze High" not in result.output

    def test_filter_by_energy(self):
        result = CliRunner().invoke(cli, ["variant", "list", "--energy", "high"])
        assert "Fire Blaze High" in result.output
        assert "Meteors Gentle Rain" not in result.output

    def test_filter_by_tier(self):
        result = CliRunner().invoke(cli, ["variant", "list", "--tier", "background"])
        assert "Meteors Gentle Rain" in result.output
        assert "Fire Blaze High" not in result.output

    def test_filter_by_scope(self):
        result = CliRunner().invoke(cli, ["variant", "list", "--scope", "single-prop"])
        assert "Meteors Gentle Rain" in result.output
        assert "Bars Sweep Left" not in result.output

    def test_filter_no_matches_exits_zero(self):
        result = CliRunner().invoke(cli, ["variant", "list", "--energy", "low", "--tier", "hero"])
        assert result.exit_code == 0

    def test_filter_no_matches_says_no_results(self):
        result = CliRunner().invoke(cli, ["variant", "list", "--energy", "low", "--tier", "hero"])
        assert "no variants" in result.output.lower() or "0" in result.output

    def test_json_format_is_valid(self):
        result = CliRunner().invoke(cli, ["variant", "list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "variants" in data
        assert len(data["variants"]) == 3

    def test_json_format_has_variant_fields(self):
        result = CliRunner().invoke(cli, ["variant", "list", "--format", "json"])
        v = json.loads(result.output)["variants"][0]
        for field in ("name", "base_effect", "description", "parameter_overrides", "tags"):
            assert field in v


class TestVariantShow:
    def test_exit_code_zero(self):
        result = CliRunner().invoke(cli, ["variant", "show", "Fire Blaze High"])
        assert result.exit_code == 0

    def test_shows_variant_name(self):
        result = CliRunner().invoke(cli, ["variant", "show", "Fire Blaze High"])
        assert "Fire Blaze High" in result.output

    def test_shows_base_effect(self):
        result = CliRunner().invoke(cli, ["variant", "show", "Fire Blaze High"])
        assert "Fire" in result.output

    def test_shows_parameter_overrides(self):
        result = CliRunner().invoke(cli, ["variant", "show", "Fire Blaze High"])
        assert "E_SLIDER_Fire_Height" in result.output

    def test_shows_energy_tag(self):
        result = CliRunner().invoke(cli, ["variant", "show", "Fire Blaze High"])
        assert "high" in result.output

    def test_shows_tier_tag(self):
        result = CliRunner().invoke(cli, ["variant", "show", "Fire Blaze High"])
        assert "foreground" in result.output

    def test_case_insensitive_lookup(self):
        result = CliRunner().invoke(cli, ["variant", "show", "fire blaze high"])
        assert result.exit_code == 0
        assert "Fire Blaze High" in result.output

    def test_shows_inherited_base_effect_category(self):
        result = CliRunner().invoke(cli, ["variant", "show", "Fire Blaze High"])
        assert "nature" in result.output  # Fire is category=nature

    def test_not_found_exits_nonzero(self):
        result = CliRunner().invoke(cli, ["variant", "show", "No Such Variant"])
        assert result.exit_code != 0

    def test_not_found_prints_error(self):
        result = CliRunner().invoke(cli, ["variant", "show", "No Such Variant"])
        assert "not found" in result.output.lower() or "error" in result.output.lower()


class TestVariantCoverage:
    def test_exit_code_zero(self):
        result = CliRunner().invoke(cli, ["variant", "coverage"])
        assert result.exit_code == 0

    def test_shows_effects_with_variants(self):
        result = CliRunner().invoke(cli, ["variant", "coverage"])
        assert "Fire" in result.output
        assert "Bars" in result.output
        assert "Meteors" in result.output

    def test_shows_variant_count(self):
        result = CliRunner().invoke(cli, ["variant", "coverage"])
        # Each fixture effect has 1 variant
        assert "1" in result.output

    def test_shows_total(self):
        result = CliRunner().invoke(cli, ["variant", "coverage"])
        assert "3" in result.output  # 3 total variants

    def test_json_format_valid(self):
        result = CliRunner().invoke(cli, ["variant", "coverage", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "coverage" in data
        assert "total_variants" in data
        assert data["total_variants"] == 3

    def test_json_coverage_has_required_fields(self):
        result = CliRunner().invoke(cli, ["variant", "coverage", "--format", "json"])
        entry = json.loads(result.output)["coverage"][0]
        for field in ("effect", "category", "variant_count", "tag_completeness"):
            assert field in entry
