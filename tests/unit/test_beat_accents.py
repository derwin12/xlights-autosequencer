"""Unit tests for beat-synchronized accent effects (spec 042)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.generator.effect_placer import (
    _DRUM_ACCENT_ALTERNATING,
    _DRUM_ACCENT_MIN_SPACING_MS,
    _DRUM_HIT_ENERGY_GATE,
    _DRUM_ONSET_SAMPLE_OFFSET_MS,
    _DRUM_VARIANT_MAP,
    _IMPACT_ACCENT_DURATION_MS,
    _IMPACT_ACCENT_PALETTE,
    _IMPACT_ACCENT_TIERS,
    _IMPACT_ENERGY_GATE,
    _IMPACT_MIN_DURATION_MS,
    _IMPACT_QUALIFYING_ROLES,
    _RADIAL_NAME_KEYWORDS,
    _SMALL_RADIAL_THRESHOLD,
    _place_drum_accents,
    _place_impact_accent,
)
from src.generator.models import AccentPolicy, GenerationConfig, SectionAssignment, SectionEnergy
from src.grouper.grouper import PowerGroup
from src.themes.models import Theme


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_section(
    label: str = "chorus",
    start_ms: int = 0,
    end_ms: int = 10_000,
    energy_score: int = 75,
) -> SectionEnergy:
    return SectionEnergy(
        label=label,
        start_ms=start_ms,
        end_ms=end_ms,
        energy_score=energy_score,
        mood_tier="aggressive",
        impact_count=0,
    )


def _make_theme(palette: list[str] | None = None) -> Theme:
    return Theme(
        name="Test Theme",
        palette=palette or ["#FF0000", "#0000FF", "#00FF00", "#FFFF00"],
        accent_palette=["#FFFFFF"],
        mood="aggressive",
        occasion="general",
        genre="pop",
        intent="test",
        layers=[],
    )


def _make_assignment(
    label: str = "chorus",
    energy_score: int = 75,
    start_ms: int = 0,
    end_ms: int = 10_000,
    drum_hits: bool = True,
    impact: bool = True,
) -> SectionAssignment:
    """Build an assignment for accent-helper tests.

    Per spec 048, the accent helpers read ``assignment.accent_policy`` and skip
    when the corresponding flag is ``False``.  These tests exercise the helpers
    directly, so we default ``drum_hits`` and ``impact`` to ``True`` — the
    helper's per-hit / per-section gates that these tests probe are now
    upstream of the helpers in ``build_plan`` and carried by the policy field.
    """
    return SectionAssignment(
        section=_make_section(label=label, energy_score=energy_score,
                               start_ms=start_ms, end_ms=end_ms),
        theme=_make_theme(),
        accent_policy=AccentPolicy(drum_hits=drum_hits, impact=impact),
    )


def _make_drum_track(hits: list[tuple[int, str]]) -> TimingTrack:
    """Create a drum TimingTrack from (time_ms, label) pairs."""
    marks = [TimingMark(time_ms=t, confidence=0.9, label=lb) for t, lb in hits]
    return TimingTrack(
        name="drums",
        algorithm_name="drum_classifier",
        element_type="onset",
        marks=marks,
        quality_score=0.9,
        stem_source="drums",
    )


def _make_energy_curve(constant_value: int, duration_ms: int = 30_000, fps: float = 47.0) -> Any:
    """Build a mock energy curve (duck-typed ValueCurve) with a constant value."""
    n_frames = int(duration_ms * fps / 1000) + 1
    curve = MagicMock()
    curve.fps = fps
    curve.values = [constant_value] * n_frames
    return curve


def _make_hierarchy(
    drum_hits: list[tuple[int, str]] | None = None,
    drum_curve_value: int | None = None,
    fullmix_curve_value: int | None = None,
) -> HierarchyResult:
    """Build a minimal HierarchyResult, optionally with a drum track and/or energy curves."""
    h = HierarchyResult(
        schema_version="1.0",
        source_file="test.mp3",
        source_hash="abc123",
        duration_ms=30_000,
        estimated_bpm=120.0,
    )
    if drum_hits is not None:
        h.events["drums"] = _make_drum_track(drum_hits)
    if drum_curve_value is not None:
        h.energy_curves["drums"] = _make_energy_curve(drum_curve_value)
    if fullmix_curve_value is not None:
        h.energy_curves["full_mix"] = _make_energy_curve(fullmix_curve_value)
    return h


def _make_radial_group(
    name: str = "06_PROP_Radial",
    tier: int = 6,
    members: list[str] | None = None,
) -> PowerGroup:
    g = PowerGroup(name=name, tier=tier, members=members or ["spinner_01", "spinner_02"])
    g.prop_type = "radial"
    return g


def _make_arch_group(name: str = "06_PROP_Arch") -> PowerGroup:
    g = PowerGroup(name=name, tier=6, members=["arch_01", "arch_02"])
    g.prop_type = "arch"
    return g


def _make_props_by_name(
    names: list[str], pixel_count: int = 50, display_as: str = "Star"
) -> dict[str, Any]:
    """Stub props_by_name dict with .pixel_count and .display_as attributes."""
    props = {}
    for name in names:
        m = MagicMock()
        m.pixel_count = pixel_count
        m.display_as = display_as
        props[name] = m
    return props


def _make_variant_library(overrides: dict[str, dict] | None = None) -> Any:
    """Stub variant library that returns variants with parameter_overrides."""
    overrides = overrides or {}

    def _get(name: str):
        v = MagicMock()
        v.parameter_overrides = overrides.get(name, {})
        return v

    lib = MagicMock()
    lib.get.side_effect = _get
    return lib


# ---------------------------------------------------------------------------
# 042A: _place_drum_accents — per-hit drum energy gate
# ---------------------------------------------------------------------------

class TestDrumAccentHitEnergyGate:
    def test_no_placements_when_drum_energy_below_gate(self):
        """No Shockwave placements when per-hit drum energy < _DRUM_HIT_ENERGY_GATE."""
        hits = [(1000, "kick"), (2000, "snare"), (3000, "kick")]
        # Drum curve is flat at 5 — below threshold
        hierarchy = _make_hierarchy(drum_hits=hits, drum_curve_value=5)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group],
            hierarchy=hierarchy,
            assignment=assignment,
            variant_library=_make_variant_library(),
            props_by_name=props_by_name,
        )
        assert result == {}

    def test_placements_fire_at_threshold(self):
        """Placements fire when drum energy equals _DRUM_HIT_ENERGY_GATE."""
        hits = [(1000, "kick"), (2000, "snare")]
        # Drum curve exactly at threshold
        hierarchy = _make_hierarchy(drum_hits=hits, drum_curve_value=_DRUM_HIT_ENERGY_GATE)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert len(result) > 0
        assert any(len(ps) > 0 for ps in result.values())

    def test_no_curve_allows_all_hits(self):
        """When no energy curves are present, all hits fire (permissive fallback)."""
        hits = [(1000, "kick"), (2000, "snare")]
        hierarchy = _make_hierarchy(drum_hits=hits)  # no energy curves
        assignment = _make_assignment(energy_score=30)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert len(result) > 0
        all_placements = [p for ps in result.values() for p in ps]
        # 2 members × 2 hits = 4 placements; confirm both hits fired (not just 1)
        assert len(all_placements) == 4

    def test_fullmix_fallback_when_no_drum_curve(self):
        """When only full_mix curve exists, it gates hits instead of drums curve."""
        hits = [(1000, "kick"), (2000, "snare")]
        # full_mix at 5 (below gate) — should suppress both hits
        hierarchy = _make_hierarchy(drum_hits=hits, fullmix_curve_value=5)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert result == {}

    def test_drum_curve_takes_priority_over_fullmix(self):
        """When both curves exist, drum curve gates hits (not full_mix)."""
        hits = [(1000, "kick"), (2000, "snare")]
        # drums curve high (50), full_mix curve low (5) — drums should win → hits fire
        hierarchy = _make_hierarchy(drum_hits=hits, drum_curve_value=50, fullmix_curve_value=5)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert len(result) > 0

    def test_sample_offset_constant_is_positive(self):
        """_DRUM_ONSET_SAMPLE_OFFSET_MS is a small positive value (captures ring, not pre-hit)."""
        assert 0 < _DRUM_ONSET_SAMPLE_OFFSET_MS <= 100


# ---------------------------------------------------------------------------
# 042A: missing drum track
# ---------------------------------------------------------------------------

class TestDrumAccentMissingTrack:
    def test_no_drum_track_returns_empty(self):
        """When hierarchy has no 'drums' event track, returns empty dict silently."""
        hierarchy = _make_hierarchy(drum_hits=None)  # no drum track
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert result == {}


# ---------------------------------------------------------------------------
# 042A: small radial threshold
# ---------------------------------------------------------------------------

class TestSmallRadialThreshold:
    def test_small_radials_get_accents(self):
        """Groups with avg pixel_count <= threshold receive drum accents."""
        hits = [(1000, "kick"), (2000, "snare")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=100)  # ≤ 150

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        # Each member model name should appear as a key
        for model_name in group.members:
            assert model_name in result

    def test_large_radials_excluded(self):
        """Radial props with pixel_count > threshold receive no drum accents."""
        hits = [(1000, "kick"), (2000, "snare")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(
            group.members,
            pixel_count=_SMALL_RADIAL_THRESHOLD + 1,
            display_as="Star",
        )

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert result == {}

    def test_non_radial_groups_excluded(self):
        """Non-radial display types (Arches, Single Line, etc.) receive no drum accents."""
        hits = [(1000, "kick"), (2000, "snare")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        arch_group = _make_arch_group()
        # display_as="Arches" maps to prop_type="arch", not "radial"
        props_by_name = _make_props_by_name(arch_group.members, pixel_count=50, display_as="Arches")

        result = _place_drum_accents(
            groups=[arch_group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert result == {}


# ---------------------------------------------------------------------------
# 042A: name-keyword fallback for Custom display_as props
# ---------------------------------------------------------------------------

class TestRadialNameKeywordFallback:
    def test_spinner_name_gets_accents(self):
        """Props named 'Spinner ...' with DisplayAs='Custom' receive drum accents."""
        hits = [(1000, "kick"), (2000, "snare")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group(members=["Spinner 23 inch Right"])
        # DisplayAs='Custom' maps to 'outline', not 'radial' — name keyword must catch it
        props_by_name = _make_props_by_name(
            ["Spinner 23 inch Right"], pixel_count=85, display_as="Custom"
        )

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert "Spinner 23 inch Right" in result
        assert len(result["Spinner 23 inch Right"]) > 0

    def test_flake_name_gets_accents(self):
        """Props named 'GE Flake ...' with DisplayAs='Custom' receive drum accents."""
        hits = [(1000, "kick"), (2000, "snare")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group(members=["GE Flake I"])
        props_by_name = _make_props_by_name(
            ["GE Flake I"], pixel_count=96, display_as="Custom"
        )

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert "GE Flake I" in result

    def test_snowflake_name_gets_accents(self):
        """Props with 'snowflake' in the name get accents via name keyword."""
        hits = [(1000, "kick")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        props_by_name = _make_props_by_name(
            ["Large Snowflake Left"], pixel_count=120, display_as="Custom"
        )

        result = _place_drum_accents(
            groups=[], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert "Large Snowflake Left" in result

    def test_arch_name_not_matched_by_keyword(self):
        """Non-radial prop names (e.g. 'Left Arch') don't get accents via name keyword."""
        hits = [(1000, "kick"), (2000, "snare")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        props_by_name = _make_props_by_name(
            ["Left Arch Section 1"], pixel_count=50, display_as="Arches"
        )

        result = _place_drum_accents(
            groups=[], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert result == {}

    def test_custom_large_prop_excluded_by_threshold(self):
        """Custom-named radial props above pixel threshold are excluded."""
        hits = [(1000, "kick"), (2000, "snare")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        # 'wreath' keyword matches, but pixel_count > threshold
        props_by_name = _make_props_by_name(
            ["Large Wreath"], pixel_count=_SMALL_RADIAL_THRESHOLD + 50, display_as="Custom"
        )

        result = _place_drum_accents(
            groups=[], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert result == {}

    def test_radial_name_keywords_constant_has_expected_entries(self):
        """_RADIAL_NAME_KEYWORDS includes the key terms for spinner/flake detection."""
        assert "spinner" in _RADIAL_NAME_KEYWORDS
        assert "flake" in _RADIAL_NAME_KEYWORDS
        assert "snowflake" in _RADIAL_NAME_KEYWORDS
        assert "star" in _RADIAL_NAME_KEYWORDS


# ---------------------------------------------------------------------------
# 042A: variant selection by drum label
# ---------------------------------------------------------------------------

class TestDrumVariantSelection:
    def test_kick_uses_full_fast_variant(self):
        """Kick hits map to Shockwave Full Fast variant."""
        hits = [(1000, "kick")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)
        var_lib = _make_variant_library()

        _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=var_lib, props_by_name=props_by_name,
        )
        var_lib.get.assert_any_call(_DRUM_VARIANT_MAP["kick"])

    def test_snare_uses_medium_fast_variant(self):
        """Snare hits map to Shockwave Medium Fast variant.

        Uses 2 snares + 1 kick (67% snare) to stay below the 80% bias threshold
        so label-based routing applies rather than the alternating fallback.
        """
        hits = [(0, "kick"), (500, "snare"), (1000, "snare")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)
        var_lib = _make_variant_library()

        _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=var_lib, props_by_name=props_by_name,
        )
        var_lib.get.assert_any_call(_DRUM_VARIANT_MAP["snare"])

    def test_hihat_uses_thin_variant(self):
        """Hihat hits map to a thin/fast variant.

        Uses 2 hihats + 1 kick (67% hihat) to stay below the 80% bias threshold.
        """
        hits = [(0, "kick"), (500, "hihat"), (1000, "hihat")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)
        var_lib = _make_variant_library()

        _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=var_lib, props_by_name=props_by_name,
        )
        var_lib.get.assert_any_call(_DRUM_VARIANT_MAP["hihat"])

    def test_unknown_label_defaults_to_kick_variant(self):
        """Hits with None or unrecognized label fall back to the kick (default) variant."""
        hits = [(1000, None), (2000, "thwump")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)
        var_lib = _make_variant_library()

        _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=var_lib, props_by_name=props_by_name,
        )
        # All calls to get() should resolve to the default variant for unknown labels
        calls = [call.args[0] for call in var_lib.get.call_args_list]
        for c in calls:
            assert c in (_DRUM_VARIANT_MAP["kick"],), f"Expected kick default, got {c!r}"


# ---------------------------------------------------------------------------
# 042A: classifier bias fallback
# ---------------------------------------------------------------------------

class TestClassifierBiasFallback:
    def test_alternating_when_100pct_kick(self):
        """When 100% of labeled hits are kick, alternates kick/snare variants."""
        # 10 kicks in a row → bias > 80% → should alternate
        hits = [(i * 300, "kick") for i in range(10)]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)
        var_lib = _make_variant_library()

        _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=var_lib, props_by_name=props_by_name,
        )
        called_variants = [call.args[0] for call in var_lib.get.call_args_list]
        # Should see both kick and snare alternating variants
        assert _DRUM_ACCENT_ALTERNATING[0] in called_variants
        assert _DRUM_ACCENT_ALTERNATING[1] in called_variants

    def test_no_alternating_with_mixed_labels(self):
        """With balanced kick/snare split (<= 80% single label), uses label-based routing."""
        hits = [(i * 400, "kick" if i % 2 == 0 else "snare") for i in range(6)]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)
        var_lib = _make_variant_library()

        _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=var_lib, props_by_name=props_by_name,
        )
        # With mixed labels no bias — should call both kick and snare variants directly
        called_variants = set(call.args[0] for call in var_lib.get.call_args_list)
        assert _DRUM_VARIANT_MAP["kick"] in called_variants
        assert _DRUM_VARIANT_MAP["snare"] in called_variants


# ---------------------------------------------------------------------------
# 042A: minimum spacing enforcement
# ---------------------------------------------------------------------------

class TestMinimumSpacing:
    def test_hits_too_close_are_skipped(self):
        """Hits within 150ms of the previous placement are dropped."""
        # Three hits: 0ms, 50ms (too close), 300ms (OK)
        hits = [(0, "kick"), (50, "snare"), (300, "kick")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        # Only hits at 0ms and 300ms should make it through (per model)
        placements = result.get(group.members[0], [])
        assert len(placements) == 2

    def test_hits_at_boundary_spacing_pass(self):
        """Hits exactly at the minimum spacing boundary are included."""
        spacing = _DRUM_ACCENT_MIN_SPACING_MS
        hits = [(0, "kick"), (spacing, "snare"), (spacing * 2, "kick")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        placements = result.get(group.members[0], [])
        assert len(placements) == 3


# ---------------------------------------------------------------------------
# 042A: timing precision
# ---------------------------------------------------------------------------

class TestDrumAccentTiming:
    def test_placement_aligns_to_hit_time(self):
        """start_ms of each placement matches the drum hit time (frame-aligned)."""
        hits = [(1000, "kick"), (2500, "snare")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        # Placements keyed by individual model name, not group name
        all_placements = [p for ps in result.values() for p in ps]
        start_times = sorted(p.start_ms for p in all_placements)
        assert 1000 in start_times
        assert 2500 in start_times

    def test_placement_duration_in_range(self):
        """Each placement's duration is between 200ms and 350ms."""
        hits = [(1000, "kick")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        all_placements = [p for ps in result.values() for p in ps]
        for p in all_placements:
            duration = p.end_ms - p.start_ms
            assert 200 <= duration <= 350, f"Duration {duration}ms outside [200, 350]"

    def test_hits_outside_section_not_placed(self):
        """Drum hits outside the section's time range are ignored."""
        # Section is 2000-5000ms, but hits are at 500ms and 6000ms
        hits = [(500, "kick"), (6000, "snare")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80, start_ms=2000, end_ms=5000)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        assert result == {}


# ---------------------------------------------------------------------------
# 042A: palette uses theme colors
# ---------------------------------------------------------------------------

class TestDrumAccentPalette:
    def test_palette_derives_from_theme(self):
        """Drum accent placements use the section theme palette, not white."""
        hits = [(1000, "kick")]
        hierarchy = _make_hierarchy(drum_hits=hits)
        assignment = _make_assignment(energy_score=80)
        group = _make_radial_group()
        props_by_name = _make_props_by_name(group.members, pixel_count=50)

        result = _place_drum_accents(
            groups=[group], hierarchy=hierarchy, assignment=assignment,
            variant_library=_make_variant_library(), props_by_name=props_by_name,
        )
        all_placements = [p for ps in result.values() for p in ps]
        assert len(all_placements) > 0
        for p in all_placements:
            assert p.color_palette != ["#FFFFFF"]
            assert len(p.color_palette) > 0


# ---------------------------------------------------------------------------
# 042B: _place_impact_accent — energy and role gates
# ---------------------------------------------------------------------------

class TestImpactAccentGates:
    """Spec 048: section-level gates (energy, duration, role) now live in
    ``build_plan``'s decision-precompute pass and their outcome is stored on
    ``assignment.accent_policy.impact``.  These tests assert that the helper
    skips when the policy flag is ``False`` — the individual gate rules are
    covered elsewhere via ``_populate_assignment_decisions`` in plan.py.
    """

    def test_no_accent_below_energy_gate(self):
        """Policy computed for below-threshold energy sets impact=False → no accent."""
        assignment = _make_assignment(
            label="chorus", energy_score=_IMPACT_ENERGY_GATE, impact=False,
        )
        groups = [_make_arch_group()]

        result = _place_impact_accent(
            groups=groups, assignment=assignment, variant_library=_make_variant_library()
        )
        assert result == {}

    def test_no_accent_section_too_short(self):
        """Policy computed for too-short section sets impact=False → no accent."""
        assignment = _make_assignment(
            label="chorus", energy_score=85, start_ms=0, end_ms=3999, impact=False,
        )
        groups = [_make_arch_group()]

        result = _place_impact_accent(
            groups=groups, assignment=assignment, variant_library=_make_variant_library()
        )
        assert result == {}

    def test_no_accent_wrong_role(self):
        """Policy computed for non-qualifying role sets impact=False → no accent."""
        for role in ("verse", "bridge", "intro", "outro"):
            assignment = _make_assignment(label=role, energy_score=90, impact=False)
            groups = [_make_arch_group()]

            result = _place_impact_accent(
                groups=groups, assignment=assignment, variant_library=_make_variant_library()
            )
            assert result == {}, f"Expected no accent for role={role!r}"

    def test_accent_fires_for_qualifying_roles(self):
        """Accent fires for all qualifying roles when energy and duration pass."""
        for role in _IMPACT_QUALIFYING_ROLES:
            assignment = _make_assignment(label=role, energy_score=90)
            groups = [_make_arch_group()]

            result = _place_impact_accent(
                groups=groups, assignment=assignment, variant_library=_make_variant_library()
            )
            assert result, f"Expected accent for role={role!r}"

    def test_accent_fires_with_empty_role_at_high_energy(self):
        """When section_role is empty, energy alone gates the impact accent."""
        assignment = _make_assignment(label="", energy_score=90)
        groups = [_make_arch_group()]

        result = _place_impact_accent(
            groups=groups, assignment=assignment, variant_library=_make_variant_library()
        )
        assert result


# ---------------------------------------------------------------------------
# 042B: impact accent placement properties
# ---------------------------------------------------------------------------

class TestImpactAccentPlacement:
    def _qualifying_assignment(self) -> SectionAssignment:
        return _make_assignment(label="chorus", energy_score=90)

    def test_accent_placed_on_all_qualifying_tiers(self):
        """All tier 4-8 groups receive the impact accent."""
        assignment = self._qualifying_assignment()
        groups = [
            PowerGroup(name=f"t{t}_group", tier=t, members=["m1"])
            for t in range(1, 9)
        ]
        for g in groups:
            g.prop_type = "arch"

        result = _place_impact_accent(
            groups=groups, assignment=assignment, variant_library=_make_variant_library()
        )
        placed_names = set(result.keys())
        for t in _IMPACT_ACCENT_TIERS:
            assert f"t{t}_group" in placed_names, f"Tier {t} missing from impact accent"
        # Tiers 1-3 should NOT be included
        for t in (1, 2, 3):
            assert f"t{t}_group" not in placed_names

    def test_accent_palette_is_white(self):
        """Impact accent always uses pure white palette."""
        assignment = self._qualifying_assignment()
        groups = [_make_arch_group()]

        result = _place_impact_accent(
            groups=groups, assignment=assignment, variant_library=_make_variant_library()
        )
        for placements in result.values():
            for p in placements:
                assert p.color_palette == list(_IMPACT_ACCENT_PALETTE)

    def test_accent_starts_at_section_start(self):
        """Impact accent starts at or very near the section start_ms."""
        assignment = _make_assignment(label="chorus", energy_score=90, start_ms=5000)
        groups = [_make_arch_group()]

        result = _place_impact_accent(
            groups=groups, assignment=assignment, variant_library=_make_variant_library()
        )
        for placements in result.values():
            for p in placements:
                assert p.start_ms == 5000, f"Expected start at 5000ms, got {p.start_ms}"

    def test_accent_duration_is_approximately_800ms(self):
        """Impact accent duration matches the 800ms spec."""
        assignment = self._qualifying_assignment()
        groups = [_make_arch_group()]

        result = _place_impact_accent(
            groups=groups, assignment=assignment, variant_library=_make_variant_library()
        )
        for placements in result.values():
            for p in placements:
                duration = p.end_ms - p.start_ms
                # Allow for frame alignment (25ms steps)
                assert abs(duration - _IMPACT_ACCENT_DURATION_MS) <= 25

    def test_accent_effect_name_is_shockwave(self):
        """Impact accent placements are Shockwave effects."""
        assignment = self._qualifying_assignment()
        groups = [_make_arch_group()]

        result = _place_impact_accent(
            groups=groups, assignment=assignment, variant_library=_make_variant_library()
        )
        for placements in result.values():
            for p in placements:
                assert p.effect_name == "Shockwave"


# ---------------------------------------------------------------------------
# beat_accent_effects flag on GenerationConfig
# ---------------------------------------------------------------------------

class TestGenerationConfigFlag:
    def test_flag_defaults_to_true(self):
        """beat_accent_effects defaults to True in GenerationConfig."""
        config = GenerationConfig(
            audio_path=Path("/fake/song.mp3"),
            layout_path=Path("/fake/layout.xml"),
        )
        assert config.beat_accent_effects is True

    def test_flag_can_be_disabled(self):
        """beat_accent_effects can be set to False."""
        config = GenerationConfig(
            audio_path=Path("/fake/song.mp3"),
            layout_path=Path("/fake/layout.xml"),
            beat_accent_effects=False,
        )
        assert config.beat_accent_effects is False
