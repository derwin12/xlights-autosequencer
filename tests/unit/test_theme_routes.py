"""Tests for src/review/theme_routes.py — theme editor API endpoints."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.effects.library import load_effect_library
from src.themes.library import load_theme_library

THEMES_FIXTURE = Path(__file__).parent.parent / "fixtures" / "themes" / "minimal_themes.json"
EFFECTS_FIXTURE = Path(__file__).parent.parent / "fixtures" / "effects" / "minimal_library.json"
CUSTOM_THEME_FIXTURE = Path(__file__).parent.parent / "fixtures" / "themes" / "valid_custom_theme.json"


@pytest.fixture
def app(tmp_path):
    """Create a Flask test app with theme routes using fixture data."""
    import src.review.theme_routes as tr

    # Pre-load libraries from fixtures
    effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE)
    theme_lib = load_theme_library(
        builtin_path=THEMES_FIXTURE,
        custom_dir=tmp_path,
        effect_library=effect_lib,
    )

    # Inject into module-level state
    tr._library = theme_lib
    tr._effect_library = effect_lib
    tr._custom_dir = tmp_path
    tr._builtin_path = THEMES_FIXTURE

    from src.review.server import create_app
    flask_app = create_app()
    flask_app.config["TESTING"] = True
    yield flask_app

    # Cleanup
    tr._library = None
    tr._effect_library = None
    tr._custom_dir = None
    tr._builtin_path = None
    tr._builtin_names_cache = None


@pytest.fixture
def client(app):
    return app.test_client()


class TestListEndpoint:
    def test_returns_200(self, client):
        resp = client.get("/themes/api/list")
        assert resp.status_code == 200

    def test_returns_themes_array(self, client):
        resp = client.get("/themes/api/list")
        data = resp.get_json()
        assert "themes" in data
        assert isinstance(data["themes"], list)
        assert len(data["themes"]) > 0

    def test_themes_have_required_fields(self, client):
        resp = client.get("/themes/api/list")
        data = resp.get_json()
        theme = data["themes"][0]
        for field in ("name", "mood", "occasion", "genre", "intent",
                      "layers", "palette", "is_custom", "has_builtin_override"):
            assert field in theme, f"Missing field: {field}"

    def test_returns_enum_arrays(self, client):
        resp = client.get("/themes/api/list")
        data = resp.get_json()
        assert "moods" in data
        assert "occasions" in data
        assert "genres" in data
        assert "ethereal" in data["moods"]

    def test_is_custom_flag_false_for_builtins(self, client):
        resp = client.get("/themes/api/list")
        data = resp.get_json()
        for theme in data["themes"]:
            assert theme["is_custom"] is False


class TestEffectsEndpoint:
    def test_returns_200(self, client):
        resp = client.get("/themes/api/effects")
        assert resp.status_code == 200

    def test_returns_effects_array(self, client):
        resp = client.get("/themes/api/effects")
        data = resp.get_json()
        assert "effects" in data
        assert isinstance(data["effects"], list)
        assert len(data["effects"]) > 0

    def test_effects_have_parameters(self, client):
        resp = client.get("/themes/api/effects")
        data = resp.get_json()
        effect = data["effects"][0]
        assert "name" in effect
        assert "parameters" in effect
        assert "category" in effect
        assert "layer_role" in effect

    def test_parameters_have_required_fields(self, client):
        resp = client.get("/themes/api/effects")
        data = resp.get_json()
        # Find an effect with parameters
        for effect in data["effects"]:
            if effect["parameters"]:
                param = effect["parameters"][0]
                for field in ("name", "storage_name", "widget_type",
                              "value_type", "default"):
                    assert field in param, f"Missing param field: {field}"
                break

    def test_returns_blend_modes(self, client):
        resp = client.get("/themes/api/effects")
        data = resp.get_json()
        assert "blend_modes" in data
        assert "Normal" in data["blend_modes"]
        assert "Additive" in data["blend_modes"]


VALID_THEME = {
    "name": "My New Theme",
    "mood": "ethereal",
    "occasion": "general",
    "genre": "any",
    "intent": "Test theme for save",
    "layers": [{"effect": "On", "blend_mode": "Normal", "parameter_overrides": {}}],
    "palette": ["#FF0000", "#00FF00"],
    "accent_palette": [],
    "variants": [],
}


class TestSaveEndpoint:
    def test_save_valid_returns_200(self, client, tmp_path):
        resp = client.post("/themes/api/save",
                           json={"theme": VALID_THEME})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["theme_name"] == "My New Theme"

    def test_save_creates_file(self, client, tmp_path):
        client.post("/themes/api/save", json={"theme": VALID_THEME})
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 1
        assert "my-new-theme" in files[0].name

    def test_save_duplicate_name_returns_400(self, client):
        # "Test Aggressive" exists in fixture
        theme = {**VALID_THEME, "name": "Test Aggressive"}
        resp = client.post("/themes/api/save", json={"theme": theme})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "already exists" in data["error"]

    def test_save_invalid_palette_returns_400(self, client):
        theme = {**VALID_THEME, "palette": ["#FF0000"]}
        resp = client.post("/themes/api/save", json={"theme": theme})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "validation_errors" in data
        assert any("Palette" in e or "palette" in e for e in data["validation_errors"])

    def test_rename_allows_own_name(self, client, tmp_path):
        # Save first
        client.post("/themes/api/save", json={"theme": VALID_THEME})
        # Reload so it knows about the theme
        import src.review.theme_routes as tr
        tr._reload_library()
        # Save again with original_name (edit in place)
        resp = client.post("/themes/api/save",
                           json={"theme": VALID_THEME, "original_name": "My New Theme"})
        assert resp.status_code == 200


class TestValidateEndpoint:
    def test_valid_theme_returns_valid(self, client):
        resp = client.post("/themes/api/validate",
                           json={"theme": VALID_THEME})
        data = resp.get_json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_invalid_theme_returns_errors(self, client):
        theme = {**VALID_THEME, "palette": ["#FF0000"]}
        resp = client.post("/themes/api/validate",
                           json={"theme": theme})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_does_not_write(self, client, tmp_path):
        client.post("/themes/api/validate", json={"theme": VALID_THEME})
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 0


class TestDeleteEndpoint:
    def test_delete_custom_succeeds(self, client, tmp_path):
        # Save a theme first
        client.post("/themes/api/save", json={"theme": VALID_THEME})
        import src.review.theme_routes as tr
        tr._reload_library()
        # Delete it
        resp = client.post("/themes/api/delete", json={"name": "My New Theme"})
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
        assert not list(tmp_path.glob("*.json"))

    def test_delete_builtin_returns_400(self, client):
        resp = client.post("/themes/api/delete", json={"name": "Test Aggressive"})
        assert resp.status_code == 400
        assert "built-in" in resp.get_json()["error"].lower() or "Cannot" in resp.get_json()["error"]

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.post("/themes/api/delete", json={"name": "Nonexistent"})
        assert resp.status_code == 404


class TestRestoreEndpoint:
    def test_restore_removes_override(self, client, tmp_path):
        # Create an override of a built-in
        override = {**VALID_THEME, "name": "Test Aggressive"}
        # Need to bypass uniqueness for this — save directly
        import json
        (tmp_path / "test-aggressive.json").write_text(json.dumps(override))
        import src.review.theme_routes as tr
        tr._reload_library()
        # Restore
        resp = client.post("/themes/api/restore", json={"name": "Test Aggressive"})
        assert resp.status_code == 200
        assert not (tmp_path / "test-aggressive.json").exists()

    def test_restore_without_override_returns_400(self, client):
        resp = client.post("/themes/api/restore", json={"name": "Test Aggressive"})
        assert resp.status_code == 400
        assert "No custom override" in resp.get_json()["error"]

    def test_restore_non_builtin_returns_400(self, client):
        resp = client.post("/themes/api/restore", json={"name": "My Custom Only"})
        assert resp.status_code == 400
        assert "not a built-in" in resp.get_json()["error"]


class TestScaleValidation:
    def test_100_custom_themes_loads_under_2s(self, tmp_path):
        """SC-007: 100 custom themes without performance degradation."""
        import json
        import time
        from src.effects.library import load_effect_library
        from src.themes.library import load_theme_library

        effect_lib = load_effect_library(builtin_path=EFFECTS_FIXTURE)

        # Create 100 custom theme files
        for i in range(100):
            theme = {
                "name": f"Scale Test Theme {i:03d}",
                "mood": ["ethereal", "aggressive", "dark", "structural"][i % 4],
                "occasion": "general",
                "genre": "any",
                "intent": f"Scale test theme number {i}",
                "layers": [{"effect": "On", "blend_mode": "Normal", "parameter_overrides": {}}],
                "palette": ["#FF0000", "#00FF00", "#0000FF"],
            }
            (tmp_path / f"scale-test-{i:03d}.json").write_text(json.dumps(theme))

        start = time.monotonic()
        lib = load_theme_library(
            builtin_path=THEMES_FIXTURE,
            custom_dir=tmp_path,
            effect_library=effect_lib,
        )
        elapsed = time.monotonic() - start

        # Verify all loaded
        custom_count = sum(1 for t in lib.themes.values() if t.name.startswith("Scale Test"))
        assert custom_count == 100
        assert elapsed < 2.0, f"Loading 100 themes took {elapsed:.2f}s (limit: 2s)"
