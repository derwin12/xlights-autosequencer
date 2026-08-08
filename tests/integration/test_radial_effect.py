"""Integration: tier-6 radial sub-groups produce a per-beat chase across members.

Drives `place_effects` with a synthetic radial PowerGroup whose members are
"Snowflake/Ring 1", "Snowflake/Ring 2", "Snowflake/Ring 3".  Asserts the
resulting placements alternate ``model_or_group`` across the rings on
successive beats — the visible "blooming" behaviour the user wants.
"""
from __future__ import annotations

from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack
from src.effects.library import EffectLibrary
from src.effects.models import EffectDefinition
from src.generator.effect_placer import place_effects
from src.generator.models import SectionAssignment, SectionEnergy
from src.grouper.grouper import PowerGroup
from src.themes.models import EffectLayer, Theme
from src.variants.library import VariantLibrary
from src.variants.models import EffectVariant, VariantTags


def _hierarchy_with_beats(beat_times: list[int], duration_ms: int = 10000) -> HierarchyResult:
    marks = [TimingMark(time_ms=t, confidence=1.0, label=str((i % 4) + 1))
             for i, t in enumerate(beat_times)]
    beats_track = TimingTrack(
        name="beats", algorithm_name="test", element_type="beat",
        marks=marks, quality_score=0.9,
    )
    return HierarchyResult(
        schema_version="2.0.0",
        source_file="test.mp3",
        source_hash="abc123",
        duration_ms=duration_ms,
        estimated_bpm=120.0,
        beats=beats_track,
    )


def _library() -> EffectLibrary:
    eff = EffectDefinition(
        name="Single Strand",
        xlights_id="E_SINGLESTRAND",
        category="chase",
        description="strand chase",
        intent="chase",
        parameters=[],
        # 'radial' suitability so the prop_type filter doesn't drop it.
        prop_suitability={"radial": "ideal", "outline": "good"},
        analysis_mappings=[],
        layer_role="standalone",
        duration_type="section",
    )
    return EffectLibrary(
        schema_version="1.0.0",
        target_xlights_version="2024.15",
        effects={eff.name: eff},
    )


def _variant_library() -> VariantLibrary:
    v = EffectVariant(
        name="Single Strand",
        base_effect="Single Strand",
        description="test variant",
        parameter_overrides={"E_CHOICE_Chase_Type1": "From Middle"},
        tags=VariantTags(),
    )
    return VariantLibrary(
        schema_version="1.0.0",
        variants={"Single Strand": v},
        builtin_names={"Single Strand"},
    )


def _theme() -> Theme:
    return Theme(
        name="Test", mood="structural", occasion="general", genre="any",
        intent="test",
        layers=[EffectLayer(variant="Single Strand")],
        palette=["#ff0000", "#00ff00"],
    )


def _radial_group() -> PowerGroup:
    return PowerGroup(
        name="06_PROP_Snowflake_Rings",
        tier=6,
        members=["Snowflake/Ring 1", "Snowflake/Ring 2", "Snowflake/Ring 3"],
        prop_type="radial",
    )


class TestRadialPlacement:
    def test_each_ring_receives_placements_across_beats(self):
        # 12 beats, 3 rings, energy=95 (≥0.95 density → no decimation).
        beat_times = list(range(0, 6000, 500))
        hierarchy = _hierarchy_with_beats(beat_times)
        section = SectionEnergy(
            label="verse", start_ms=0, end_ms=6000,
            energy_score=95, mood_tier="structural", impact_count=0,
        )
        assignment = SectionAssignment(
            section=section,
            theme=_theme(),
            active_tiers=frozenset({6}),
        )
        result = place_effects(
            assignment=assignment,
            groups=[_radial_group()],
            effect_library=_library(),
            hierarchy=hierarchy,
            variant_library=_variant_library(),
        )

        # Placements are keyed by the addressed model — i.e. each ring.
        assert "Snowflake/Ring 1" in result
        assert "Snowflake/Ring 2" in result
        assert "Snowflake/Ring 3" in result
        # No placement was made on the parent group name — the chase
        # bypasses the parent and fires directly on members.
        assert "06_PROP_Snowflake_Rings" not in result

        ring1 = result["Snowflake/Ring 1"]
        ring2 = result["Snowflake/Ring 2"]
        ring3 = result["Snowflake/Ring 3"]
        # All three rings are exercised, each gets at least 3 hits, and
        # the count is balanced within 1 (ring 1 may pick up the leftover
        # when total hits aren't a multiple of 3).
        counts = sorted([len(ring1), len(ring2), len(ring3)])
        assert counts[0] >= 3
        assert counts[2] - counts[0] <= 1

    def test_first_three_beats_hit_rings_in_declaration_order(self):
        beat_times = [0, 500, 1000, 1500]
        hierarchy = _hierarchy_with_beats(beat_times)
        section = SectionEnergy(
            label="chorus", start_ms=0, end_ms=2000,
            energy_score=80, mood_tier="structural", impact_count=0,
        )
        assignment = SectionAssignment(
            section=section,
            theme=_theme(),
            active_tiers=frozenset({6}),
        )
        result = place_effects(
            assignment=assignment,
            groups=[_radial_group()],
            effect_library=_library(),
            hierarchy=hierarchy,
            variant_library=_variant_library(),
        )

        # Beat 0 → Ring 1, Beat 1 → Ring 2, Beat 2 → Ring 3 — the bloom.
        # Excludes each ring's own section-spanning Off backdrop (start_ms=0
        # for every active ring), which would otherwise flatten this
        # ordering check to a tie.
        def _chase_starts(ring: str) -> list[int]:
            return sorted(p.start_ms for p in result.get(ring, []) if p.effect_name != "Off")

        ring1_starts = _chase_starts("Snowflake/Ring 1")
        ring2_starts = _chase_starts("Snowflake/Ring 2")
        ring3_starts = _chase_starts("Snowflake/Ring 3")

        assert ring1_starts and ring1_starts[0] < (ring2_starts[0] if ring2_starts else 99999)
        assert ring2_starts and ring2_starts[0] < (ring3_starts[0] if ring3_starts else 99999)

    def test_no_beats_falls_back_to_section_placement(self):
        # No beats track → helper falls back to one placement on the parent
        # group name spanning the whole section.  The flake stays lit even
        # when beat detection is unreliable.
        hierarchy = HierarchyResult(
            schema_version="2.0.0", source_file="test.mp3",
            source_hash="abc123", duration_ms=5000, estimated_bpm=120.0,
            beats=None,
        )
        section = SectionEnergy(
            label="verse", start_ms=0, end_ms=5000,
            energy_score=80, mood_tier="structural", impact_count=0,
        )
        assignment = SectionAssignment(
            section=section,
            theme=_theme(),
            active_tiers=frozenset({6}),
        )
        result = place_effects(
            assignment=assignment,
            groups=[_radial_group()],
            effect_library=_library(),
            hierarchy=hierarchy,
            variant_library=_variant_library(),
        )

        # All placements landed on the parent (fallback path).
        assert "06_PROP_Snowflake_Rings" in result
        # No per-ring placements emitted in the fallback.
        for ring in ("Snowflake/Ring 1", "Snowflake/Ring 2", "Snowflake/Ring 3"):
            assert ring not in result


class TestRadialChaseOffBackdrop:
    """Every ring that receives at least one beat this section also gets a
    section-spanning Off behind its own chase placements (user request
    2026-08-07, spotted on the star family's Star 1-4 during verse_3):
    outside its own turn, a ring has nothing placed at all and is
    unprotected from bleed-through -- unlike the corpus-recipe path's own
    off_backdrop idiom, which this beat-chase fallback never had."""

    def test_each_active_ring_gets_a_section_spanning_off(self):
        beat_times = [0, 500, 1000, 1500]
        hierarchy = _hierarchy_with_beats(beat_times)
        section = SectionEnergy(
            label="chorus", start_ms=0, end_ms=2000,
            energy_score=80, mood_tier="structural", impact_count=0,
        )
        assignment = SectionAssignment(
            section=section,
            theme=_theme(),
            active_tiers=frozenset({6}),
        )
        result = place_effects(
            assignment=assignment,
            groups=[_radial_group()],
            effect_library=_library(),
            hierarchy=hierarchy,
            variant_library=_variant_library(),
        )

        for ring in ("Snowflake/Ring 1", "Snowflake/Ring 2", "Snowflake/Ring 3"):
            offs = [p for p in result[ring] if p.effect_name == "Off"]
            assert len(offs) == 1
            assert offs[0].start_ms == 0
            assert offs[0].end_ms == 2000
            # Behind this ring's own chase placements (layer 0 default) AND
            # behind _place_drum_accents' small-radial-prop Shockwave accents
            # (layer 1, same models) -- layer 1 here would put the backdrop
            # level with those accents and get clipped against them by
            # xsq_writer's per-layer overlap trim instead of sitting cleanly
            # behind (user report 2026-08-07, follow-up same session).
            chase = next(p for p in result[ring] if p.effect_name != "Off")
            assert offs[0].layer > chase.layer
            assert offs[0].layer == 5

    def test_no_beats_fallback_gets_no_per_ring_off(self):
        # The fallback path (no beats track) never reaches the per-ring
        # backdrop loop -- it returns a single parent-level placement.
        hierarchy = HierarchyResult(
            schema_version="2.0.0", source_file="test.mp3",
            source_hash="abc123", duration_ms=5000, estimated_bpm=120.0,
            beats=None,
        )
        section = SectionEnergy(
            label="verse", start_ms=0, end_ms=5000,
            energy_score=80, mood_tier="structural", impact_count=0,
        )
        assignment = SectionAssignment(
            section=section,
            theme=_theme(),
            active_tiers=frozenset({6}),
        )
        result = place_effects(
            assignment=assignment,
            groups=[_radial_group()],
            effect_library=_library(),
            hierarchy=hierarchy,
            variant_library=_variant_library(),
        )
        assert not any(p.effect_name == "Off" for p in result["06_PROP_Snowflake_Rings"])
