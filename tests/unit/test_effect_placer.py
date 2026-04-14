"""Tests for src/generator/effect_placer — _build_effect_pool prop_type filtering (spec 041).

T017: _build_effect_pool(lib, prop_type="arch") excludes not_recommended effects for arch
T018: _build_effect_pool(lib, prop_type=None) returns full pool (backward compat)
T019: When all pool effects are not_recommended, pool relaxes to include possible-rated effects
"""
from __future__ import annotations

import pytest

from src.effects.library import EffectLibrary
from src.effects.models import EffectDefinition
from src.generator.effect_placer import _build_effect_pool, _PROP_EFFECT_POOL


def _make_effect_lib(ratings: dict[str, dict[str, str]]) -> EffectLibrary:
    """Create a mock EffectLibrary where each entry maps effect name → prop_suitability dict."""
    effects = {}
    for name, prop_suitability in ratings.items():
        effects[name] = EffectDefinition(
            name=name,
            xlights_id=name.lower().replace(" ", "_"),
            category="pattern",
            description="test effect",
            intent="test",
            parameters=[],
            prop_suitability=prop_suitability,
        )
    return EffectLibrary(
        schema_version="1.0.0",
        target_xlights_version="2024.x",
        effects=effects,
    )


class TestBuildEffectPool:
    """T017-T019: prop_type filtering in _build_effect_pool."""

    def test_t017_excludes_not_recommended_effects_for_prop_type(self):
        """T017: _build_effect_pool(lib, prop_type="arch") omits not_recommended effects.

        Bars is not_recommended for arch; Spirals and Ripple are not. The returned pool
        should contain Spirals and Ripple but NOT Bars.
        """
        lib = _make_effect_lib({
            "Bars": {"arch": "not_recommended", "tree": "good"},
            "Spirals": {"arch": "good", "tree": "ideal"},
            "Ripple": {"arch": "good", "tree": "ideal"},
        })

        pool = _build_effect_pool(lib, prop_type="arch")
        pool_names = {e.name for e in pool}

        assert "Bars" not in pool_names, "Bars (not_recommended for arch) should be excluded"
        assert "Spirals" in pool_names, "Spirals (good for arch) should be included"
        assert "Ripple" in pool_names, "Ripple (good for arch) should be included"

    def test_t017_missing_prop_type_key_treated_as_possible(self):
        """T017: When prop_suitability has no entry for the prop_type, treat as 'possible' (included)."""
        lib = _make_effect_lib({
            "Bars": {"tree": "good"},        # no "arch" key
            "Spirals": {"arch": "good"},
        })

        pool = _build_effect_pool(lib, prop_type="arch")
        pool_names = {e.name for e in pool}

        # Bars has no arch rating → defaults to "possible" → NOT excluded (only not_recommended is)
        assert "Bars" in pool_names, "Bars (no arch key, defaults to possible) should be included"
        assert "Spirals" in pool_names

    def test_t018_no_prop_type_returns_full_pool(self):
        """T018: _build_effect_pool(lib, prop_type=None) returns full pool — backward compat."""
        lib = _make_effect_lib({
            "Bars": {"arch": "not_recommended"},
            "Spirals": {"arch": "good"},
            "Ripple": {"arch": "ideal"},
            "Meteors": {"arch": "good"},
        })

        pool_with_filter = _build_effect_pool(lib, prop_type="arch")
        pool_without_filter = _build_effect_pool(lib, prop_type=None)

        # Without filter: all 4 effects present
        pool_names = {e.name for e in pool_without_filter}
        assert pool_names == {"Bars", "Spirals", "Ripple", "Meteors"}

        # With filter: Bars excluded
        filtered_names = {e.name for e in pool_with_filter}
        assert "Bars" not in filtered_names
        assert len(filtered_names) == 3

    def test_t018_no_prop_type_arg_returns_full_pool(self):
        """T018: Calling _build_effect_pool without prop_type kwarg returns full pool."""
        lib = _make_effect_lib({
            "Bars": {"arch": "not_recommended"},
            "Spirals": {"arch": "good"},
        })

        # Call without prop_type (default should be None → no filtering)
        pool = _build_effect_pool(lib)
        pool_names = {e.name for e in pool}
        assert "Bars" in pool_names, "Without prop_type, not_recommended effects are included"

    def test_t019_all_not_recommended_relaxes_to_full_pool(self):
        """T019: When all pool effects are not_recommended, relax to include all effects.

        The pool should not return empty — it falls back to prop_type=None (no filtering).
        """
        # All effects in the mock lib are not_recommended for "test_type"
        lib = _make_effect_lib({
            "Bars": {"test_type": "not_recommended"},
            "Spirals": {"test_type": "not_recommended"},
            "Ripple": {"test_type": "not_recommended"},
        })

        pool = _build_effect_pool(lib, prop_type="test_type")
        pool_names = {e.name for e in pool}

        # Must not be empty — falls back to unfiltered pool
        assert len(pool) > 0, "Pool must not be empty after filter relaxation"
        assert pool_names == {"Bars", "Spirals", "Ripple"}, (
            f"After fallback, full pool should be returned, got {pool_names}"
        )

    def test_t019_mixed_ratings_does_not_relax(self):
        """T019: If at least one effect passes the filter, no relaxation occurs."""
        lib = _make_effect_lib({
            "Bars": {"test_type": "not_recommended"},
            "Spirals": {"test_type": "possible"},  # passes the filter
        })

        pool = _build_effect_pool(lib, prop_type="test_type")
        pool_names = {e.name for e in pool}

        # Spirals passes (possible is not not_recommended), so no relaxation
        assert "Bars" not in pool_names
        assert "Spirals" in pool_names

    def test_exclude_and_prop_type_both_apply(self):
        """Both exclude and prop_type filtering work together."""
        lib = _make_effect_lib({
            "Bars": {"arch": "good"},
            "Spirals": {"arch": "good"},
            "Ripple": {"arch": "not_recommended"},
        })

        pool = _build_effect_pool(lib, exclude={"Bars"}, prop_type="arch")
        pool_names = {e.name for e in pool}

        assert "Bars" not in pool_names, "Bars excluded by exclude set"
        assert "Ripple" not in pool_names, "Ripple excluded by not_recommended for arch"
        assert "Spirals" in pool_names, "Spirals should be in pool"
        assert len(pool) == 1
