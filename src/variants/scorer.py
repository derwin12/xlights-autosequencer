"""Weighted multi-dimensional scorer for automated variant selection."""
from __future__ import annotations

from dataclasses import dataclass

from src.effects.library import EffectLibrary
from src.variants.library import VariantLibrary
from src.variants.models import EffectVariant

# --------------------------------------------------------------------------- #
# Scoring context                                                              #
# --------------------------------------------------------------------------- #

@dataclass
class ScoringContext:
    base_effect: str | None = None
    prop_type: str | None = None
    energy_level: str | None = None
    tier_affinity: str | None = None
    section_role: str | None = None
    scope: str | None = None
    genre: str | None = None


# --------------------------------------------------------------------------- #
# Dimension weights                                                            #
# --------------------------------------------------------------------------- #

WEIGHTS: dict[str, float] = {
    "prop_type": 0.30,
    "energy_level": 0.25,
    "tier_affinity": 0.20,
    "section_role": 0.15,
    "scope": 0.05,
    "genre": 0.05,
}

# Adjacency tables — each tuple lists neighbours that score 0.5 instead of 0.0
_ENERGY_ADJACENT: dict[str, set[str]] = {
    "low":    {"medium"},
    "medium": {"low", "high"},
    "high":   {"medium"},
}

_TIER_ADJACENT: dict[str, set[str]] = {
    "background": {"mid"},
    "mid":        {"background", "foreground"},
    "foreground": {"mid", "hero"},
    "hero":       {"foreground"},
}

_SUITABILITY_SCORES: dict[str, float] = {
    "ideal": 1.0,
    "good": 0.75,
    "possible": 0.25,
    "not_recommended": 0.0,
}


# --------------------------------------------------------------------------- #
# Per-dimension scorers                                                        #
# --------------------------------------------------------------------------- #

def _score_energy(context_val: str | None, variant_val: str | None) -> float:
    if context_val is None or variant_val is None:
        return 0.5
    if context_val == variant_val:
        return 1.0
    if context_val in _ENERGY_ADJACENT and variant_val in _ENERGY_ADJACENT[context_val]:
        return 0.5
    return 0.0


def _score_tier(context_val: str | None, variant_val: str | None) -> float:
    if context_val is None or variant_val is None:
        return 0.5
    if context_val == variant_val:
        return 1.0
    if context_val in _TIER_ADJACENT and variant_val in _TIER_ADJACENT[context_val]:
        return 0.5
    return 0.0


def _score_section_role(context_val: str | None, variant_roles: list[str]) -> float:
    if context_val is None:
        return 0.5
    if not variant_roles:
        return 0.5
    return 1.0 if context_val in variant_roles else 0.0


def _score_genre(context_val: str | None, variant_val: str) -> float:
    if context_val is None:
        return 0.5
    if variant_val == "any":
        return 1.0
    return 1.0 if context_val == variant_val else 0.0


def _score_scope(context_val: str | None, variant_val: str | None) -> float:
    if context_val is None or variant_val is None:
        return 0.5
    return 1.0 if context_val == variant_val else 0.0


def _score_prop_type(
    context_val: str | None,
    variant: EffectVariant,
    effect_library: EffectLibrary,
) -> float:
    if context_val is None:
        return 0.5
    effect_def = effect_library.get(variant.base_effect)
    if effect_def is None:
        return 0.5
    rating = effect_def.prop_suitability.get(context_val)
    if rating is None:
        return 0.0
    return _SUITABILITY_SCORES.get(rating, 0.0)


# --------------------------------------------------------------------------- #
# Core scoring function                                                        #
# --------------------------------------------------------------------------- #

def _score_variant(
    variant: EffectVariant,
    context: ScoringContext,
    effect_library: EffectLibrary,
) -> tuple[float, dict[str, float]]:
    """Compute weighted total score and per-dimension breakdown for one variant."""
    breakdown: dict[str, float] = {
        "prop_type":    _score_prop_type(context.prop_type, variant, effect_library),
        "energy_level": _score_energy(context.energy_level, variant.tags.energy_level),
        "tier_affinity": _score_tier(context.tier_affinity, variant.tags.tier_affinity),
        "section_role": _score_section_role(context.section_role, variant.tags.section_roles),
        "scope":        _score_scope(context.scope, variant.tags.scope),
        "genre":        _score_genre(context.genre, variant.tags.genre_affinity),
    }
    total = sum(WEIGHTS[k] * v for k, v in breakdown.items())
    return total, breakdown


def rank_variants(
    context: ScoringContext,
    variant_library: VariantLibrary,
    effect_library: EffectLibrary,
    threshold: float = 0.5,
) -> list[tuple[EffectVariant, float, dict]]:
    """Return variants sorted by score descending.

    Each entry is (EffectVariant, total_score, breakdown_dict).
    If context.base_effect is set, only variants for that base effect are scored.
    The threshold parameter is accepted for API consistency but does not filter
    results here — filtering is the responsibility of the fallback wrapper.
    """
    candidates = _get_candidates(context, variant_library)
    scored = []
    for variant in candidates:
        total, breakdown = _score_variant(variant, context, effect_library)
        scored.append((variant, total, breakdown))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def _get_candidates(context: ScoringContext, variant_library: VariantLibrary) -> list[EffectVariant]:
    """Return the candidate variant list, optionally filtered by base_effect."""
    if context.base_effect is None:
        return list(variant_library.variants.values())
    base_lower = context.base_effect.lower()
    return [
        v for v in variant_library.variants.values()
        if v.base_effect.lower() == base_lower
    ]


# --------------------------------------------------------------------------- #
# Progressive fallback                                                         #
# --------------------------------------------------------------------------- #

def rank_variants_with_fallback(
    context: ScoringContext,
    variant_library: VariantLibrary,
    effect_library: EffectLibrary,
    threshold: float = 0.5,
) -> tuple[list[tuple[EffectVariant, float, dict]], list[str]]:
    """Score variants with progressive constraint relaxation.

    Returns (results, relaxed_filters) where relaxed_filters lists the
    dimensions that were dropped/widened to obtain a result above threshold.

    Fallback order:
    1. Full context
    2. Drop section_role
    3. Drop genre
    4. Widen energy (adjacent levels acceptable via _score_energy already)
       — implemented by dropping the energy constraint from the context so
         even adjacent matches (0.5) count toward threshold
    5. Widen tier — same approach
    6. Drop scope
    7. Return all variants for base_effect (prop suitability preserved)
    """
    relaxed: list[str] = []

    # Step 1: full context
    results = rank_variants(context, variant_library, effect_library, threshold)
    if _any_above(results, threshold):
        return results, relaxed

    # Step 2: drop section_role
    ctx2 = _copy_context(context, section_role=None)
    results = rank_variants(ctx2, variant_library, effect_library, threshold)
    if _any_above(results, threshold):
        return results, ["section_role"]

    relaxed.append("section_role")

    # Step 3: drop genre
    ctx3 = _copy_context(ctx2, genre=None)
    results = rank_variants(ctx3, variant_library, effect_library, threshold)
    if _any_above(results, threshold):
        return results, relaxed + ["genre"]

    relaxed.append("genre")

    # Step 4: widen energy (drop constraint — adjacent already scores 0.5, exact 1.0;
    #         by setting energy_level=None we let both adjacent and exact both become
    #         neutral 0.5, but variants that matched are now not penalised)
    # Actually to widen: we allow adjacent by keeping energy but we already do that.
    # The intent here is to drop the energy constraint so *any* energy passes.
    ctx4 = _copy_context(ctx3, energy_level=None)
    results = rank_variants(ctx4, variant_library, effect_library, threshold)
    if _any_above(results, threshold):
        return results, relaxed + ["energy_level"]

    relaxed.append("energy_level")

    # Step 5: widen tier — drop tier constraint
    ctx5 = _copy_context(ctx4, tier_affinity=None)
    results = rank_variants(ctx5, variant_library, effect_library, threshold)
    if _any_above(results, threshold):
        return results, relaxed + ["tier_affinity"]

    relaxed.append("tier_affinity")

    # Step 6: drop scope
    ctx6 = _copy_context(ctx5, scope=None)
    results = rank_variants(ctx6, variant_library, effect_library, threshold)
    if _any_above(results, threshold):
        return results, relaxed + ["scope"]

    relaxed.append("scope")

    # Step 7: return all for base_effect (no context constraints except base_effect)
    ctx7 = ScoringContext(base_effect=context.base_effect)
    results = rank_variants(ctx7, variant_library, effect_library, threshold)
    return results, relaxed


def _any_above(results: list[tuple[EffectVariant, float, dict]], threshold: float) -> bool:
    return any(score >= threshold for _, score, _ in results)


def _copy_context(ctx: ScoringContext, **overrides) -> ScoringContext:
    """Return a shallow copy of ctx with specified fields replaced."""
    return ScoringContext(
        base_effect=overrides.get("base_effect", ctx.base_effect),
        prop_type=overrides.get("prop_type", ctx.prop_type),
        energy_level=overrides.get("energy_level", ctx.energy_level),
        tier_affinity=overrides.get("tier_affinity", ctx.tier_affinity),
        section_role=overrides.get("section_role", ctx.section_role),
        scope=overrides.get("scope", ctx.scope),
        genre=overrides.get("genre", ctx.genre),
    )
