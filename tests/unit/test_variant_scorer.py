"""Unit tests for the variant scorer (rank_variants, rank_variants_with_fallback)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.effects.library import load_effect_library
from src.variants.library import load_variant_library
from src.variants.models import EffectVariant, VariantTags
from src.variants.scorer import ScoringContext, rank_variants, rank_variants_with_fallback

FIXTURES = Path(__file__).parent.parent / "fixtures"
EFFECTS_FIXTURE = FIXTURES / "effects" / "minimal_library_with_meteors.json"
VARIANTS_FIXTURE = FIXTURES / "variants" / "builtin_variants_minimal.json"


@pytest.fixture
def effect_library():
    return load_effect_library(builtin_path=EFFECTS_FIXTURE)


@pytest.fixture
def variant_library(effect_library):
    return load_variant_library(
        builtin_path=VARIANTS_FIXTURE,
        custom_dir=Path("/tmp/nonexistent_custom_dir_scorer_test"),
        effect_library=effect_library,
    )


class TestRankVariantsReturnShape:
    def test_returns_list(self, variant_library, effect_library):
        ctx = ScoringContext()
        results = rank_variants(ctx, variant_library, effect_library)
        assert isinstance(results, list)

    def test_each_result_is_three_tuple(self, variant_library, effect_library):
        ctx = ScoringContext()
        results = rank_variants(ctx, variant_library, effect_library)
        assert len(results) > 0
        for item in results:
            assert len(item) == 3

    def test_first_element_is_effect_variant(self, variant_library, effect_library):
        ctx = ScoringContext()
        results = rank_variants(ctx, variant_library, effect_library)
        for variant, score, breakdown in results:
            assert isinstance(variant, EffectVariant)

    def test_second_element_is_float(self, variant_library, effect_library):
        ctx = ScoringContext()
        results = rank_variants(ctx, variant_library, effect_library)
        for variant, score, breakdown in results:
            assert isinstance(score, float)

    def test_third_element_is_dict(self, variant_library, effect_library):
        ctx = ScoringContext()
        results = rank_variants(ctx, variant_library, effect_library)
        for variant, score, breakdown in results:
            assert isinstance(breakdown, dict)

    def test_breakdown_contains_all_dimensions(self, variant_library, effect_library):
        ctx = ScoringContext()
        results = rank_variants(ctx, variant_library, effect_library)
        expected_keys = {"prop_type", "energy_level", "tier_affinity", "section_role", "scope", "genre"}
        for variant, score, breakdown in results:
            assert expected_keys <= breakdown.keys(), f"Missing keys: {expected_keys - breakdown.keys()}"

    def test_sorted_by_score_descending(self, variant_library, effect_library):
        ctx = ScoringContext(energy_level="high")
        results = rank_variants(ctx, variant_library, effect_library)
        scores = [s for _, s, _ in results]
        assert scores == sorted(scores, reverse=True)


class TestRankVariantsScoring:
    def test_exact_match_on_energy_scores_higher_than_adjacent(self, variant_library, effect_library):
        # Fire Blaze High has energy_level=high, tier_affinity=foreground, section_roles=[chorus,build,drop]
        ctx_exact = ScoringContext(energy_level="high")
        ctx_adjacent = ScoringContext(energy_level="medium")

        results_exact = {v.name: s for v, s, _ in rank_variants(ctx_exact, variant_library, effect_library)}
        results_adjacent = {v.name: s for v, s, _ in rank_variants(ctx_adjacent, variant_library, effect_library)}

        assert results_exact["Fire Blaze High"] > results_adjacent["Fire Blaze High"]

    def test_mismatched_energy_scores_lower_than_adjacent(self, variant_library, effect_library):
        # low vs high is a mismatch (0.0), medium vs high is adjacent (0.5)
        ctx_mismatch = ScoringContext(energy_level="low")   # Fire Blaze High has high
        ctx_adjacent = ScoringContext(energy_level="medium")

        results_mismatch = {v.name: s for v, s, _ in rank_variants(ctx_mismatch, variant_library, effect_library)}
        results_adjacent = {v.name: s for v, s, _ in rank_variants(ctx_adjacent, variant_library, effect_library)}

        assert results_mismatch["Fire Blaze High"] < results_adjacent["Fire Blaze High"]

    def test_mismatch_dimension_scores_zero(self, variant_library, effect_library):
        # Energy: low vs high = 0.0 (mismatch)
        ctx = ScoringContext(energy_level="low")
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        _, breakdown = results["Fire Blaze High"]
        assert breakdown["energy_level"] == 0.0

    def test_exact_match_dimension_scores_one(self, variant_library, effect_library):
        ctx = ScoringContext(energy_level="high")
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        _, breakdown = results["Fire Blaze High"]
        assert breakdown["energy_level"] == 1.0

    def test_adjacent_energy_scores_half(self, variant_library, effect_library):
        # Fire Blaze High has energy_level=high, medium is adjacent
        ctx = ScoringContext(energy_level="medium")
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        _, breakdown = results["Fire Blaze High"]
        assert breakdown["energy_level"] == 0.5

    def test_adjacent_tier_scores_half(self, variant_library, effect_library):
        # Fire Blaze High has tier_affinity=foreground, hero is adjacent to foreground
        ctx = ScoringContext(tier_affinity="hero")
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        _, breakdown = results["Fire Blaze High"]
        assert breakdown["tier_affinity"] == 0.5

    def test_none_context_field_scores_half_neutral(self, variant_library, effect_library):
        # No energy specified → neutral 0.5 for all variants
        ctx = ScoringContext()
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        for vname, (_, breakdown) in results.items():
            assert breakdown["energy_level"] == 0.5, f"Expected 0.5 for {vname}"

    def test_section_role_match_scores_one(self, variant_library, effect_library):
        ctx = ScoringContext(section_role="chorus")
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        # Fire Blaze High has chorus in section_roles
        _, breakdown = results["Fire Blaze High"]
        assert breakdown["section_role"] == 1.0

    def test_section_role_mismatch_scores_zero(self, variant_library, effect_library):
        # Fire Blaze High has section_roles=[chorus, build, drop] — not outro
        ctx = ScoringContext(section_role="outro")
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        _, breakdown = results["Fire Blaze High"]
        assert breakdown["section_role"] == 0.0

    def test_section_roles_empty_on_variant_scores_half(self, effect_library):
        """A variant with empty section_roles should score 0.5 (neutral) for any queried role."""
        from src.variants.library import VariantLibrary
        v = EffectVariant(
            name="No Roles",
            base_effect="Fire",
            description="test",
            parameter_overrides={},
            tags=VariantTags(section_roles=[]),
        )
        lib = VariantLibrary(schema_version="1.0.0", variants={"No Roles": v})
        ctx = ScoringContext(section_role="chorus")
        results = rank_variants(ctx, lib, effect_library)
        assert len(results) == 1
        _, _, breakdown = results[0]
        assert breakdown["section_role"] == 0.5

    def test_genre_affinity_any_scores_one_for_any_genre(self, variant_library, effect_library):
        # All fixture variants have genre_affinity="any"
        ctx = ScoringContext(genre="pop")
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        for vname, (_, breakdown) in results.items():
            assert breakdown["genre"] == 1.0, f"Expected 1.0 for {vname}"

    def test_genre_affinity_specific_match_scores_one(self, effect_library):
        from src.variants.library import VariantLibrary
        v = EffectVariant(
            name="Rock Fire",
            base_effect="Fire",
            description="test",
            parameter_overrides={},
            tags=VariantTags(genre_affinity="rock"),
        )
        lib = VariantLibrary(schema_version="1.0.0", variants={"Rock Fire": v})
        ctx = ScoringContext(genre="rock")
        results = rank_variants(ctx, lib, effect_library)
        _, _, breakdown = results[0]
        assert breakdown["genre"] == 1.0

    def test_genre_affinity_specific_mismatch_scores_zero(self, effect_library):
        from src.variants.library import VariantLibrary
        v = EffectVariant(
            name="Rock Fire",
            base_effect="Fire",
            description="test",
            parameter_overrides={},
            tags=VariantTags(genre_affinity="rock"),
        )
        lib = VariantLibrary(schema_version="1.0.0", variants={"Rock Fire": v})
        ctx = ScoringContext(genre="pop")
        results = rank_variants(ctx, lib, effect_library)
        _, _, breakdown = results[0]
        assert breakdown["genre"] == 0.0

    def test_prop_type_match_scores_one(self, variant_library, effect_library):
        # Fire Blaze High → base_effect=Fire; Fire has prop_suitability with "matrix": "ideal"
        ctx = ScoringContext(prop_type="matrix")
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        _, breakdown = results["Fire Blaze High"]
        assert breakdown["prop_type"] == 1.0

    def test_prop_type_not_in_suitability_scores_zero(self, variant_library, effect_library):
        # Fire's prop_suitability doesn't have "custom_string"
        ctx = ScoringContext(prop_type="custom_string")
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        _, breakdown = results["Fire Blaze High"]
        assert breakdown["prop_type"] == 0.0

    def test_unknown_base_effect_prop_type_scores_half(self, effect_library):
        """If effect_library doesn't know the base_effect, prop_type score → 0.5 neutral."""
        from src.variants.library import VariantLibrary
        v = EffectVariant(
            name="Unknown Effect",
            base_effect="NonExistentEffect",
            description="test",
            parameter_overrides={},
            tags=VariantTags(),
        )
        lib = VariantLibrary(schema_version="1.0.0", variants={"Unknown Effect": v})
        ctx = ScoringContext(prop_type="matrix")
        results = rank_variants(ctx, lib, effect_library)
        assert len(results) == 1
        _, _, breakdown = results[0]
        assert breakdown["prop_type"] == 0.5

    def test_scope_exact_match_scores_one(self, variant_library, effect_library):
        # Meteors Gentle Rain has scope=single-prop
        ctx = ScoringContext(scope="single-prop")
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        _, breakdown = results["Meteors Gentle Rain"]
        assert breakdown["scope"] == 1.0

    def test_scope_mismatch_scores_zero(self, variant_library, effect_library):
        ctx = ScoringContext(scope="group")
        results = {v.name: (s, bd) for v, s, bd in rank_variants(ctx, variant_library, effect_library)}
        _, breakdown = results["Meteors Gentle Rain"]
        assert breakdown["scope"] == 0.0


class TestRankVariantsEdgeCases:
    def test_empty_library_returns_empty_list(self, effect_library):
        from src.variants.library import VariantLibrary
        lib = VariantLibrary(schema_version="1.0.0", variants={})
        ctx = ScoringContext(energy_level="high")
        results = rank_variants(ctx, lib, effect_library)
        assert results == []

    def test_base_effect_filter_limits_results(self, variant_library, effect_library):
        ctx = ScoringContext(base_effect="Fire")
        results = rank_variants(ctx, variant_library, effect_library)
        assert len(results) == 1
        assert results[0][0].name == "Fire Blaze High"

    def test_base_effect_filter_unknown_returns_empty(self, variant_library, effect_library):
        ctx = ScoringContext(base_effect="NonExistentEffect")
        results = rank_variants(ctx, variant_library, effect_library)
        assert results == []

    def test_total_score_is_weighted_sum(self, variant_library, effect_library):
        ctx = ScoringContext(energy_level="high")
        for variant, total_score, breakdown in rank_variants(ctx, variant_library, effect_library):
            from src.variants.scorer import WEIGHTS
            expected = sum(WEIGHTS[k] * breakdown[k] for k in WEIGHTS)
            assert abs(total_score - expected) < 1e-9, f"Score mismatch for {variant.name}"


class TestRankVariantsWithFallback:
    def test_returns_tuple_of_results_and_relaxed_filters(self, variant_library, effect_library):
        ctx = ScoringContext(energy_level="high")
        result = rank_variants_with_fallback(ctx, variant_library, effect_library)
        assert isinstance(result, tuple)
        assert len(result) == 2
        results, relaxed = result
        assert isinstance(results, list)
        assert isinstance(relaxed, list)

    def test_no_fallback_when_above_threshold(self, variant_library, effect_library):
        # energy=high matches Fire Blaze High exactly → above default threshold 0.5
        ctx = ScoringContext(energy_level="high")
        results, relaxed = rank_variants_with_fallback(ctx, variant_library, effect_library)
        assert relaxed == []
        assert len(results) > 0

    def test_fallback_triggered_when_all_below_threshold(self, effect_library):
        """Force a scenario where nothing scores above threshold."""
        from src.variants.library import VariantLibrary
        v = EffectVariant(
            name="Niche Variant",
            base_effect="Fire",
            description="test",
            parameter_overrides={},
            tags=VariantTags(
                energy_level="low",
                tier_affinity="background",
                section_roles=["intro"],
                scope="single-prop",
                genre_affinity="classical",
            ),
        )
        lib = VariantLibrary(schema_version="1.0.0", variants={"Niche Variant": v})
        # Request the opposite of everything
        ctx = ScoringContext(
            energy_level="high",
            tier_affinity="hero",
            section_role="drop",
            scope="group",
            genre="metal",
        )
        results, relaxed = rank_variants_with_fallback(ctx, lib, effect_library)
        # Should still return something (fallback kicks in)
        assert len(results) > 0
        # At least one filter should have been relaxed
        assert len(relaxed) > 0

    def test_fallback_results_still_sorted_descending(self, variant_library, effect_library):
        ctx = ScoringContext(energy_level="high", section_role="outro")
        results, relaxed = rank_variants_with_fallback(ctx, variant_library, effect_library)
        scores = [s for _, s, _ in results]
        assert scores == sorted(scores, reverse=True)

    def test_relaxed_filters_names_are_strings(self, variant_library, effect_library):
        ctx = ScoringContext()
        _, relaxed = rank_variants_with_fallback(ctx, variant_library, effect_library)
        for item in relaxed:
            assert isinstance(item, str)


class TestGraduatedPropScoring:
    """Tests for graduated _score_prop_type() scoring.

    The NEW graduated behavior maps prop_suitability rating strings to scores:
      ideal → 1.0, good → 0.75, possible → 0.25, not_recommended → 0.0
    Unknown prop types (not in suitability dict) → 0.0.
    No context (prop_type=None) → 0.5.

    Fire effect fixture ratings: matrix=ideal, outline=good, arch=possible,
    vertical=good, tree=good, radial=good.
    No fixture effect has a "not_recommended" rating — that case uses a
    synthetic effect to ensure coverage.
    """

    def test_ideal_prop_type_scores_one(self, variant_library, effect_library):
        """Fire has matrix rated 'ideal' → prop_type score should be 1.0."""
        ctx = ScoringContext(prop_type="matrix")
        results = {v.name: bd for v, _, bd in rank_variants(ctx, variant_library, effect_library)}
        assert results["Fire Blaze High"]["prop_type"] == 1.0

    def test_good_prop_type_scores_075(self, variant_library, effect_library):
        """Fire has outline rated 'good' → prop_type score should be 0.75."""
        ctx = ScoringContext(prop_type="outline")
        results = {v.name: bd for v, _, bd in rank_variants(ctx, variant_library, effect_library)}
        assert results["Fire Blaze High"]["prop_type"] == 0.75

    def test_possible_prop_type_scores_025(self, variant_library, effect_library):
        """Fire has arch rated 'possible' → prop_type score should be 0.25."""
        ctx = ScoringContext(prop_type="arch")
        results = {v.name: bd for v, _, bd in rank_variants(ctx, variant_library, effect_library)}
        assert results["Fire Blaze High"]["prop_type"] == 0.25

    def test_not_recommended_prop_type_scores_zero(self, effect_library):
        """A prop_suitability rating of 'not_recommended' → prop_type score should be 0.0.

        No fixture effect has this rating, so we patch in a synthetic effect.
        """
        from src.effects.library import EffectDefinition, EffectLibrary
        from src.variants.library import VariantLibrary

        patched_lib = EffectLibrary(
            schema_version="1.0.0",
            target_xlights_version="2024.x",
            effects={
                "TestEffect": EffectDefinition(
                    name="TestEffect",
                    xlights_id="eff_TEST",
                    category="test",
                    description="test",
                    intent="test",
                    parameters=[],
                    prop_suitability={"matrix": "not_recommended"},
                    analysis_mappings=[],
                ),
            },
        )
        v = EffectVariant(
            name="Test Variant",
            base_effect="TestEffect",
            description="test",
            parameter_overrides={},
            tags=VariantTags(),
        )
        vlib = VariantLibrary(schema_version="1.0.0", variants={"Test Variant": v})
        ctx = ScoringContext(prop_type="matrix")
        results = rank_variants(ctx, vlib, patched_lib)
        assert len(results) == 1
        _, _, breakdown = results[0]
        assert breakdown["prop_type"] == 0.0

    def test_unknown_prop_type_scores_zero(self, variant_library, effect_library):
        """A prop_type not present in the effect's suitability dict → 0.0."""
        ctx = ScoringContext(prop_type="custom_string")
        results = {v.name: bd for v, _, bd in rank_variants(ctx, variant_library, effect_library)}
        assert results["Fire Blaze High"]["prop_type"] == 0.0

    def test_none_prop_type_scores_half(self, variant_library, effect_library):
        """No prop_type context (None) → neutral 0.5."""
        ctx = ScoringContext(prop_type=None)
        results = {v.name: bd for v, _, bd in rank_variants(ctx, variant_library, effect_library)}
        assert results["Fire Blaze High"]["prop_type"] == 0.5
