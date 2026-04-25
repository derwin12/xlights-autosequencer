"""Tests for variant CLI CRUD subcommands: create, edit, delete."""
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

_CUSTOM_VARIANT = {
    "name": "My Test Fire",
    "base_effect": "Fire",
    "description": "custom test variant",
    "parameter_overrides": {},
    "tags": {},
}


@pytest.fixture
def tmp_custom_dir(tmp_path):
    return tmp_path / "custom_variants"


@pytest.fixture(autouse=True)
def inject_libs(tmp_custom_dir, monkeypatch):
    """Inject fixture-based libraries into the CLI module."""
    import src.cli_old as cli_module

    effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE)
    lib = load_variant_library(
        builtin_path=VARIANTS_FIXTURE,
        custom_dir=tmp_custom_dir,
        effect_library=effect_lib,
    )
    monkeypatch.setattr(cli_module, "_variant_library_override", lib)
    monkeypatch.setattr(cli_module, "_variant_effect_library_override", effect_lib)
    monkeypatch.setattr(cli_module, "_variant_custom_dir_override", tmp_custom_dir)


class TestVariantCreate:
    def test_create_basic(self, tmp_path):
        result = CliRunner().invoke(
            cli,
            ["variant", "create", "--name", "My Bars", "--effect", "Bars",
             "--description", "test bars variant"],
        )
        assert result.exit_code == 0
        assert "My Bars" in result.output

    def test_create_missing_name_shows_error(self):
        result = CliRunner().invoke(cli, ["variant", "create", "--effect", "Fire"])
        assert result.exit_code != 0

    def test_create_from_file(self, tmp_path):
        json_file = tmp_path / "variant.json"
        json_file.write_text(json.dumps(_CUSTOM_VARIANT), encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            ["variant", "create", "--name", "My Test Fire", "--from-file", str(json_file)],
        )
        assert result.exit_code == 0
        assert "My Test Fire" in result.output

    def test_create_from_file_name_override(self, tmp_path):
        """CLI --name flag overrides the name in the file."""
        json_file = tmp_path / "variant.json"
        data = dict(_CUSTOM_VARIANT)
        data["name"] = "File Name"
        json_file.write_text(json.dumps(data), encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            ["variant", "create", "--name", "CLI Name", "--from-file", str(json_file)],
        )
        assert result.exit_code == 0
        assert "CLI Name" in result.output

    def test_create_duplicate_name_fails(self, tmp_path):
        """Creating a variant with an existing name should fail."""
        result = CliRunner().invoke(
            cli,
            ["variant", "create", "--name", "Fire Blaze High", "--effect", "Fire"],
        )
        assert result.exit_code != 0

    def test_create_unknown_effect_fails(self, tmp_path):
        result = CliRunner().invoke(
            cli,
            ["variant", "create", "--name", "Unknown Effect", "--effect", "NonExistentEffect"],
        )
        assert result.exit_code != 0


class TestVariantEdit:
    def test_edit_builtin_fails(self, tmp_path):
        json_file = tmp_path / "edit.json"
        json_file.write_text(json.dumps({
            "name": "Fire Blaze High",
            "base_effect": "Fire",
            "description": "updated",
            "parameter_overrides": {},
            "tags": {},
        }), encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            ["variant", "edit", "Fire Blaze High", "--from-file", str(json_file)],
        )
        assert result.exit_code != 0
        assert "built-in" in result.output.lower() or "cannot" in result.output.lower()

    def test_edit_nonexistent_fails(self, tmp_path):
        json_file = tmp_path / "edit.json"
        json_file.write_text(json.dumps(_CUSTOM_VARIANT), encoding="utf-8")
        result = CliRunner().invoke(
            cli,
            ["variant", "edit", "Totally Fake Variant", "--from-file", str(json_file)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_edit_custom_variant_succeeds(self, tmp_path, tmp_custom_dir):
        import src.cli_old as cli_module
        from src.variants.models import EffectVariant, VariantTags

        # Add custom variant to the library
        custom = EffectVariant(
            name="My Custom Fire",
            base_effect="Fire",
            description="original",
            parameter_overrides={},
            tags=VariantTags(),
        )
        cli_module._variant_library_override.save_custom_variant(custom, tmp_custom_dir)

        json_file = tmp_path / "edit.json"
        json_file.write_text(json.dumps({
            "name": "My Custom Fire",
            "base_effect": "Fire",
            "description": "updated description",
            "parameter_overrides": {"E_SLIDER_Fire_Height": 50},
            "tags": {},
        }), encoding="utf-8")

        result = CliRunner().invoke(
            cli,
            ["variant", "edit", "My Custom Fire", "--from-file", str(json_file)],
        )
        assert result.exit_code == 0
        assert "Updated" in result.output or "My Custom Fire" in result.output


class TestVariantDelete:
    def test_delete_builtin_fails(self):
        result = CliRunner().invoke(
            cli,
            ["variant", "delete", "Fire Blaze High", "--yes"],
        )
        assert result.exit_code != 0
        assert "built-in" in result.output.lower() or "cannot" in result.output.lower()

    def test_delete_nonexistent_fails(self):
        result = CliRunner().invoke(
            cli,
            ["variant", "delete", "Does Not Exist", "--yes"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_delete_custom_variant_succeeds(self, tmp_custom_dir):
        import src.cli_old as cli_module
        from src.variants.models import EffectVariant, VariantTags

        custom = EffectVariant(
            name="Deletable Variant",
            base_effect="Fire",
            description="to be deleted",
            parameter_overrides={},
            tags=VariantTags(),
        )
        cli_module._variant_library_override.save_custom_variant(custom, tmp_custom_dir)

        result = CliRunner().invoke(
            cli,
            ["variant", "delete", "Deletable Variant", "--yes"],
        )
        assert result.exit_code == 0
        assert "Deleted" in result.output or "Deletable Variant" in result.output

    def test_delete_without_yes_prompts(self, tmp_custom_dir):
        import src.cli_old as cli_module
        from src.variants.models import EffectVariant, VariantTags

        custom = EffectVariant(
            name="Prompt Test Variant",
            base_effect="Fire",
            description="prompts",
            parameter_overrides={},
            tags=VariantTags(),
        )
        cli_module._variant_library_override.save_custom_variant(custom, tmp_custom_dir)

        # Supply 'n' to cancel deletion
        result = CliRunner().invoke(
            cli,
            ["variant", "delete", "Prompt Test Variant"],
            input="n\n",
        )
        # Abort should not succeed
        assert result.exit_code != 0 or "Deleted" not in result.output
