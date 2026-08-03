"""Tests for GET /api/v1/themes — T040."""
import json

import pytest

from src.review.storage.assignments import save_session
from src.review.storage.library import save_library


SECTION_KINDS = {"intro", "verse", "chorus", "bridge", "outro", "drop"}


def _seed_song(song_id: str, title: str = "Believer", artist: str = "Imagine Dragons"):
    save_library({
        "schema_version": 1,
        "songs": [{
            "song_id": song_id,
            "title": title,
            "artist": artist,
            "status": "analyzed",
            "source_paths": [],
            "folder_id": "unfiled",
            "imported_at": "2026-04-21T00:00:00Z",
        }],
        "folders": [{"id": "unfiled", "name": "Unfiled", "created_at": "2026-04-21T00:00:00Z"}],
        "preferences": {},
        "layout": None,
    })


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


# ── DELETE /api/v1/themes/<theme_id> ───────────────────────────────────────

@pytest.fixture()
def custom_themes_dir(tmp_path, monkeypatch):
    """Isolate custom-theme file I/O to a temp dir instead of the real
    ~/.xlight/custom_themes/ (module-level constant, unlike the library/
    session storage which already reads XLIGHT_STATE_HOME)."""
    import src.review.api.v1.themes as themes_module

    d = tmp_path / "custom_themes"
    d.mkdir()
    monkeypatch.setattr(themes_module, "_CUSTOM_THEMES_DIR", d)
    return d


def _write_custom_theme(custom_themes_dir, theme_id: str, name: str = "Test Theme"):
    (custom_themes_dir / f"{theme_id}.json").write_text(
        json.dumps({"name": name, "mood": "structural", "occasion": "general",
                    "genre": "any", "intent": "", "palette": ["#111111"] * 4,
                    "accent_palette": []}),
        encoding="utf-8",
    )


def test_delete_builtin_theme_returns_403(client, custom_themes_dir):
    data = client.get("/api/v1/themes").get_json()
    builtin_id = next(t["theme_id"] for t in data["themes"] if not t["editable"])
    resp = client.delete(f"/api/v1/themes/{builtin_id}")
    assert resp.status_code == 403


def test_delete_nonexistent_theme_returns_404(client, custom_themes_dir):
    resp = client.delete("/api/v1/themes/does-not-exist")
    assert resp.status_code == 404


def test_delete_unused_custom_theme_removes_it(client, custom_themes_dir):
    _write_custom_theme(custom_themes_dir, "my-test-theme")
    resp = client.delete("/api/v1/themes/my-test-theme")
    assert resp.status_code == 200
    assert not (custom_themes_dir / "my-test-theme.json").exists()
    data = client.get("/api/v1/themes").get_json()
    assert not any(t["theme_id"] == "my-test-theme" for t in data["themes"])


def test_delete_theme_still_assigned_to_a_song_returns_409(client, custom_themes_dir):
    _write_custom_theme(custom_themes_dir, "my-test-theme")
    _seed_song("themesong0000004")
    save_session(
        "themesong0000004",
        sections=[{"index": 0, "start_ms": 0, "end_ms": 1000, "kind": "verse", "label": "Verse"}],
        assignments=[{"section_index": 0, "theme_id": "my-test-theme", "overrides": {}}],
    )
    resp = client.delete("/api/v1/themes/my-test-theme")
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "theme_in_use"
    # File must survive — the delete must not have happened.
    assert (custom_themes_dir / "my-test-theme.json").exists()


# ── Layers-less custom themes get a working default (user report 2026-08-03) ─
# The Theme screen's New Theme/Edit dialog has no layer/effect picker, so a
# theme saved through it has no `layers` — validate_theme() rejects that,
# and the real generator used to silently drop the theme from its catalog
# entirely (an assigned theme never actually rendered). create_theme/
# update_theme now backfill a working default layer so this can't happen.

def test_create_theme_without_layers_gets_default_layer(client, custom_themes_dir):
    resp = client.post("/api/v1/themes", json={
        "name": "test2", "mood": "structural", "occasion": "general", "genre": "any",
        "palette": ["#1E1B4B", "#7DD3FC"], "accent_palette": [],
    })
    assert resp.status_code == 201
    saved = json.loads((custom_themes_dir / "test2.json").read_text(encoding="utf-8"))
    assert saved["layers"] == [
        {"variant": "Color Wash Smooth", "blend_mode": "Normal", "effect_pool": [], "stem": None},
    ]


def test_update_theme_backfills_default_layer_for_existing_layerless_theme(client, custom_themes_dir):
    _write_custom_theme(custom_themes_dir, "my-test-theme")  # no "layers" key at all
    resp = client.put("/api/v1/themes/my-test-theme", json={"intent": "updated"})
    assert resp.status_code == 200
    saved = json.loads((custom_themes_dir / "my-test-theme.json").read_text(encoding="utf-8"))
    assert saved["layers"] == [
        {"variant": "Color Wash Smooth", "blend_mode": "Normal", "effect_pool": [], "stem": None},
    ]


def test_theme_with_explicit_layers_are_not_overwritten_on_create(client, custom_themes_dir):
    resp = client.post("/api/v1/themes", json={
        "name": "Has Layers", "palette": ["#FFFFFF", "#000000"],
        "layers": [{"variant": "Fire Tall", "blend_mode": "Normal"}],
    })
    assert resp.status_code == 201
    saved = json.loads((custom_themes_dir / "has-layers.json").read_text(encoding="utf-8"))
    assert saved["layers"] == [{"variant": "Fire Tall", "blend_mode": "Normal"}]


def test_themes_list_includes_validation_errors_field(client, custom_themes_dir):
    _write_custom_theme(custom_themes_dir, "my-test-theme")  # no "layers" key -- backfilled at load, should validate clean
    data = client.get("/api/v1/themes").get_json()
    theme = next(t for t in data["themes"] if t["theme_id"] == "my-test-theme")
    assert theme["validation_errors"] == []


def test_genuinely_broken_custom_theme_reports_validation_errors(client, custom_themes_dir):
    # Missing "mood" — a real authoring error the layers backfill can't fix.
    (custom_themes_dir / "broken.json").write_text(json.dumps({
        "name": "Broken", "occasion": "general", "genre": "any", "intent": "",
        "palette": ["#111111", "#222222"],
    }), encoding="utf-8")
    data = client.get("/api/v1/themes").get_json()
    theme = next(t for t in data["themes"] if t["theme_id"] == "broken")
    assert theme["validation_errors"]  # non-empty


def test_builtin_themes_have_no_validation_errors(client, custom_themes_dir):
    data = client.get("/api/v1/themes").get_json()
    for theme in data["themes"]:
        if not theme["editable"]:
            assert theme["validation_errors"] == []
