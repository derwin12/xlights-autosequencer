"""Tests for src/generator/effect_placer — _build_effect_pool prop_type filtering (spec 041).

T017: _build_effect_pool(lib, prop_type="arch") excludes not_recommended effects for arch
T018: _build_effect_pool(lib, prop_type=None) returns full pool (backward compat)
T019: When all pool effects are not_recommended, pool relaxes to include possible-rated effects
"""
from __future__ import annotations

import pytest

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.effects.library import EffectLibrary
from src.effects.models import EffectDefinition
from src.generator.effect_placer import (
    _BEAT_PUNCH_DURATION_MS,
    _build_effect_pool,
    _PROP_EFFECT_POOL,
    _place_per_beat,
)
from src.generator.models import SectionEnergy


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

class TestPlacePerBeatConfidenceBranching:
    """Per-mark confidence routing: high confidence → punch, None/low → wash.

    Regression coverage for ``_place_per_beat`` after the
    ``beat-confidence-annotation`` change. The pre-change behavior is the
    full-beat ``wash`` placement (``end_ms == next_mark.time_ms``); the
    post-change punch behavior shortens to ``_BEAT_PUNCH_DURATION_MS``.
    """

    def _hierarchy_with_beats(self, beat_specs: list[tuple[int, float | None]]) -> HierarchyResult:
        """Build a stub HierarchyResult whose .beats track has the given (time_ms, confidence) marks."""
        marks = [TimingMark(time_ms=t, confidence=c) for t, c in beat_specs]
        beats_track = TimingTrack(
            name="beats",
            algorithm_name="stub_beats",
            element_type="beat",
            marks=marks,
            quality_score=1.0,
        )
        return HierarchyResult(
            schema_version="2.0.0",
            source_file="stub.mp3",
            source_hash="0" * 32,
            duration_ms=10_000,
            estimated_bpm=120.0,
            beats=beats_track,
        )

    def _section(self) -> SectionEnergy:
        # Energy 100 so the density filter keeps all marks — see _apply_density_filter.
        return SectionEnergy(
            label="chorus",
            start_ms=0,
            end_ms=10_000,
            energy_score=100,
            mood_tier="HIGH",
            impact_count=0,
        )

    def _effect_def(self) -> EffectDefinition:
        return EffectDefinition(
            name="On",
            xlights_id="On",
            category="basic",
            description="solid on",
            intent="test",
            parameters=[],
            prop_suitability={},
        )

    def test_high_and_low_confidence_yield_distinguishable_durations(self):
        """T7.1: A 0.9-confidence beat punches; a 0.3-confidence beat washes.

        Use 10 beats with high danceability to bypass the density filter so
        every mark survives into placement.
        """
        beat_specs = [(1000 + i * 1000, 0.9 if i % 2 == 0 else 0.3) for i in range(8)]
        hierarchy = self._hierarchy_with_beats(beat_specs)
        # Pre-filter: the density step keeps roughly 90% of marks at energy 100;
        # with 8 marks that yields 7 placements, plenty for the assertions.
        placements = _place_per_beat(
            self._effect_def(), "G", self._section(), hierarchy,
            params={}, palette=["#FFFFFF"], blend_mode="Normal",
        )
        # Map placements back to the originating beat by start_ms (frame-aligned).
        by_start = {p.start_ms: p for p in placements}
        # Find at least one high-confidence and one low-confidence beat in the
        # placements (allowing for whichever the density filter dropped).
        punch_durations = [
            p.end_ms - p.start_ms
            for t, c in beat_specs
            if c == 0.9 and any(abs(p.start_ms - t) < 50 for p in placements)
            for p in [next(pp for pp in placements if abs(pp.start_ms - t) < 50)]
        ]
        wash_durations = [
            p.end_ms - p.start_ms
            for t, c in beat_specs
            if c == 0.3 and any(abs(p.start_ms - t) < 50 for p in placements)
            for p in [next(pp for pp in placements if abs(pp.start_ms - t) < 50)]
        ]
        assert punch_durations and wash_durations, (
            f"need both punch and wash placements; got punch={punch_durations}, "
            f"wash={wash_durations}, all_starts={list(by_start.keys())}"
        )
        # Every punch placement is at most one frame past the punch duration cap.
        assert all(d <= _BEAT_PUNCH_DURATION_MS + 50 for d in punch_durations), (
            f"punch durations exceed cap: {punch_durations}"
        )
        # Every wash placement spans well beyond the punch cap.
        assert all(d > _BEAT_PUNCH_DURATION_MS + 200 for d in wash_durations), (
            f"wash durations should be long: {wash_durations}"
        )

    def test_none_confidence_preserves_pre_change_wash_behavior(self):
        """T7.2: confidence=None on every beat → wash placements (pre-change behavior)."""
        beat_specs = [(1000 + i * 1000, None) for i in range(8)]
        hierarchy = self._hierarchy_with_beats(beat_specs)
        placements = _place_per_beat(
            self._effect_def(), "G", self._section(), hierarchy,
            params={}, palette=["#FFFFFF"], blend_mode="Normal",
        )
        assert placements, "density filter should keep at least one beat"
        for p in placements:
            assert p.end_ms - p.start_ms > _BEAT_PUNCH_DURATION_MS + 200, (
                f"None-confidence beat must use the wash path "
                f"(duration {p.end_ms - p.start_ms} ms ≤ punch duration)"
            )

    def test_threshold_boundary_confidence_07_punches(self):
        """At exactly 0.7 (the threshold), the placement punches; 0.69 washes."""
        beat_specs = [(1000 + i * 1000, 0.7 if i % 2 == 0 else 0.69) for i in range(8)]
        hierarchy = self._hierarchy_with_beats(beat_specs)
        placements = _place_per_beat(
            self._effect_def(), "G", self._section(), hierarchy,
            params={}, palette=["#FFFFFF"], blend_mode="Normal",
        )
        for p in placements:
            # Find the source mark by nearest start_ms.
            mark_t, mark_c = min(beat_specs, key=lambda s: abs(s[0] - p.start_ms))
            duration = p.end_ms - p.start_ms
            if mark_c == 0.7:
                assert duration <= _BEAT_PUNCH_DURATION_MS + 50, (
                    f"0.7 threshold should punch; got duration {duration}"
                )
            else:
                assert duration > _BEAT_PUNCH_DURATION_MS + 200, (
                    f"0.69 below threshold should wash; got duration {duration}"
                )


class TestEffectPoolFiltering:
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
