"""White-first corpus-color themes — validation against the real libraries.

These six themes encode the dominant color structure observed in the local
reference corpus: white carries most of the lit time, with one or two
saturated accents defining the song's identity. accent_palette therefore
leads with white (tiers 3+ read from it), while `palette` holds the
colored wash for the background tiers.
"""
from __future__ import annotations

import pytest

from src.effects.library import load_effect_library
from src.themes.library import load_theme_library
from src.variants.library import load_variant_library

NEW_THEMES = (
    "White Heat", "Ice Crystal", "Violet Night",
    "Scarlet Ribbon", "Solar Gold", "Ember White",
)


@pytest.fixture(scope="module")
def libraries():
    effect_library = load_effect_library()
    variant_library = load_variant_library(effect_library=effect_library)
    theme_library = load_theme_library(
        effect_library=effect_library, variant_library=variant_library,
    )
    return effect_library, variant_library, theme_library


def _iter_variant_names(theme):
    for layer_set in [theme.layers] + [a.layers for a in getattr(theme, "alternates", [])]:
        for layer in layer_set:
            yield layer.variant
            for pool_name in getattr(layer, "effect_pool", None) or []:
                yield pool_name
    bav = getattr(theme, "background_accent_variant", None)
    if bav:
        yield bav


def test_new_themes_present(libraries):
    _, _, theme_library = libraries
    for name in NEW_THEMES:
        assert name in theme_library.themes, f"missing builtin theme {name!r}"


def test_new_themes_are_white_first(libraries):
    """Tiers 3+ draw from accent_palette — white must lead so props render
    predominantly white with the accent as the secondary color."""
    _, _, theme_library = libraries
    for name in NEW_THEMES:
        theme = theme_library.themes[name]
        assert theme.accent_palette[0] == "#FFFFFF", (
            f"{name}: accent_palette must lead with white, got {theme.accent_palette}"
        )
        def _is_near_white(hex_color: str) -> bool:
            r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
            return min(r, g, b) >= 0xE0

        assert any(_is_near_white(c) for c in theme.palette), (
            f"{name}: background palette must include a (near-)white, "
            f"got {theme.palette}"
        )


def test_new_themes_cover_all_mood_tiers(libraries):
    """The selector queries by mood_tier — the set must span all four so
    every section type can land on a white-first theme."""
    _, _, theme_library = libraries
    moods = {theme_library.themes[n].mood for n in NEW_THEMES}
    assert moods == {"ethereal", "aggressive", "dark", "structural"}


def test_every_builtin_theme_variant_resolves(libraries):
    """Guard for ALL builtin themes (not just the new six): every layer,
    alternate, effect_pool entry, and background accent must name a real
    variant — a typo here silently drops the layer at generation time."""
    _, variant_library, theme_library = libraries
    unresolved = [
        (theme_name, variant_name)
        for theme_name, theme in theme_library.themes.items()
        for variant_name in _iter_variant_names(theme)
        if variant_library.get(variant_name) is None
    ]
    assert unresolved == [], f"themes reference unknown variants: {unresolved}"
