"""Tests for GET /api/v1/themes — T040."""
import pytest


SECTION_KINDS = {"intro", "verse", "chorus", "bridge", "outro", "drop"}


def test_themes_returns_200(client):
    resp = client.get("/api/v1/themes")
    assert resp.status_code == 200


def test_themes_schema_version(client):
    data = client.get("/api/v1/themes").get_json()
    assert data["schema_version"] == 1


def test_themes_list_nonempty(client):
    data = client.get("/api/v1/themes").get_json()
    assert isinstance(data["themes"], list)
    assert len(data["themes"]) > 0


def test_themes_required_fields(client):
    data = client.get("/api/v1/themes").get_json()
    for theme in data["themes"]:
        assert "theme_id" in theme
        assert "name" in theme
        assert "description" in theme
        assert "accent" in theme
        assert "swatches" in theme
        assert "default_for_kinds" in theme
        assert isinstance(theme["swatches"], list)
        # Themes have 4 base palette colors plus an optional accent — accept
        # 4-or-more so a future palette-restraint expansion doesn't break this.
        assert len(theme["swatches"]) >= 4
        assert isinstance(theme["default_for_kinds"], list)


def test_themes_every_section_kind_covered(client):
    """FR-012a: every Section kind must have at least one theme."""
    data = client.get("/api/v1/themes").get_json()
    covered = set()
    for theme in data["themes"]:
        for kind in theme["default_for_kinds"]:
            covered.add(kind)
    for kind in SECTION_KINDS:
        assert kind in covered, f"Section kind '{kind}' has no default theme"


def test_themes_accent_is_hex(client):
    data = client.get("/api/v1/themes").get_json()
    for theme in data["themes"]:
        assert theme["accent"].startswith("#"), f"{theme['theme_id']} accent not a hex color"


def test_themes_swatches_are_hex(client):
    data = client.get("/api/v1/themes").get_json()
    for theme in data["themes"]:
        for swatch in theme["swatches"]:
            assert swatch.startswith("#"), f"swatch {swatch} not hex"


def test_themes_swatches_include_every_accent_color(client):
    """Bug found 2026-07-28 (user report): swatches used to be capped at
    (palette + accent_palette)[:5], so a theme with a 4-color palette only
    ever showed accent_palette[0] -- the remaining accent colors were fully
    active in generated sequences but invisible in the theme browser. Every
    theme's swatches must now include its complete accent_palette (minus
    any color duplicated from its own palette)."""
    import json as _json
    from src.review.api.v1.themes import _BUILTIN_THEMES_PATH

    raw_themes = _json.loads(_BUILTIN_THEMES_PATH.read_text(encoding="utf-8"))["themes"]
    data = client.get("/api/v1/themes").get_json()
    by_id = {t["theme_id"]: t for t in data["themes"]}

    for name, raw in raw_themes.items():
        theme_id = next((t for t in by_id if by_id[t]["name"] == name), None)
        assert theme_id is not None, f"{name} missing from API response"
        swatches = set(by_id[theme_id]["swatches"])
        for accent_color in raw.get("accent_palette", []):
            assert accent_color in swatches, (
                f"{name}: accent color {accent_color} missing from swatches"
            )
