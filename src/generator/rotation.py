"""Intelligent effect rotation engine — pre-computes variant assignments for tier 5-8 groups."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from src.effects.library import EffectLibrary
from src.variants.library import VariantLibrary
from src.variants.models import EffectVariant
from src.variants.scorer import _score_variant, rank_variants_with_fallback


@dataclass
class RotationEntry:
    """A single variant assignment for one group in one section."""

    section_index: int
    section_label: str
    group_name: str
    group_tier: int
    variant_name: str
    base_effect: str
    score: float
    score_breakdown: dict[str, float] = field(default_factory=dict)
    source: str = "library"  # "pool", "library", or "continuity"

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_index": self.section_index,
            "section_label": self.section_label,
            "group_name": self.group_name,
            "group_tier": self.group_tier,
            "variant_name": self.variant_name,
            "base_effect": self.base_effect,
            "score": self.score,
            "score_breakdown": dict(self.score_breakdown),
            "source": self.source,
        }


@dataclass
class RotationPlan:
    """Complete per-section, per-group variant assignment for a sequence."""

    entries: list[RotationEntry] = field(default_factory=list)
    sections_count: int = 0
    groups_count: int = 0
    symmetry_pairs: list = field(default_factory=list)  # list[SymmetryGroup]

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": [e.to_dict() for e in self.entries],
            "sections_count": self.sections_count,
            "groups_count": self.groups_count,
            "symmetry_pairs": [
                sp.to_dict() if hasattr(sp, "to_dict") else sp
                for sp in self.symmetry_pairs
            ],
        }

    def lookup(self, section_index: int, group_name: str) -> RotationEntry | None:
        """Find the rotation entry for a specific section and group."""
        for entry in self.entries:
            if entry.section_index == section_index and entry.group_name == group_name:
                return entry
        return None


def build_scoring_context(
    section,
    group,
    theme,
) -> "ScoringContext":
    """Map SectionEnergy + PowerGroup + Theme to ScoringContext.

    Mapping per research.md R2:
    - energy_score 0-33 → "low", 34-66 → "medium", 67-100 → "high"
    - group.tier → tier_affinity: 5→"mid", 6→"mid", 7→"foreground", 8→"hero"
    - section.label → section_role
    - theme.genre → genre
    - group.prop_type → prop_type
    """
    from src.variants.scorer import ScoringContext

    energy_score = section.energy_score
    if energy_score <= 33:
        energy_level = "low"
    elif energy_score <= 66:
        energy_level = "medium"
    else:
        energy_level = "high"

    tier_map = {5: "mid", 6: "mid", 7: "foreground", 8: "hero"}
    tier_affinity = tier_map.get(group.tier, "mid")

    return ScoringContext(
        base_effect=None,
        prop_type=group.prop_type,
        energy_level=energy_level,
        tier_affinity=tier_affinity,
        section_role=section.label,
        scope=None,
        genre=getattr(theme, "genre", "any"),
    )


class RotationEngine:
    """Pre-computes variant assignments for tier 5-8 groups across all sections."""

    def __init__(self, variant_library: VariantLibrary, effect_library: EffectLibrary):
        self.variant_library = variant_library
        self.effect_library = effect_library

    def _rank_for_group(
        self, section, group, theme,
    ) -> list[tuple[EffectVariant, float, dict]]:
        """Score all variants against the section/group context and return ranked list."""
        context = build_scoring_context(section, group, theme)
        results, _relaxed = rank_variants_with_fallback(
            context, self.variant_library, self.effect_library,
        )
        return results

    def select_variant_for_group(
        self, section, group, theme, layer,
    ) -> EffectVariant | None:
        """Score all variants against the section/group context and return the best match.

        When the layer defines an ``effect_pool``, only variants named in the pool
        are considered.  If no pool variant scores >= 0.3, falls back to full
        library scoring.

        Returns None if the variant library is empty or no variants score above threshold.
        """
        # Pool filtering (US3)
        if hasattr(layer, "effect_pool") and layer.effect_pool:
            pool_variants = []
            for name in layer.effect_pool:
                v = self.variant_library.get(name)
                if v is not None:
                    pool_variants.append(v)
            if pool_variants:
                context = build_scoring_context(section, group, theme)
                scored = []
                for v in pool_variants:
                    total, breakdown = _score_variant(v, context, self.effect_library)
                    scored.append((v, total, breakdown))
                scored.sort(key=lambda x: x[1], reverse=True)
                if scored[0][1] >= 0.3:
                    return scored[0][0]

        # Full library fallback
        results = self._rank_for_group(section, group, theme)
        if not results:
            return None
        return results[0][0]

    def build_rotation_plan(
        self,
        sections,
        groups,
        theme=None,
        theme_assignments=None,
        symmetry_pairs: list | None = None,
        embrace_repetition: bool = False,
        working_sets: dict | None = None,
    ) -> RotationPlan:
        """Build a complete rotation plan assigning variants to tier 5-8 groups.

        Accepts either a single ``theme`` applied to all sections or a list of
        ``theme_assignments`` (SectionAssignment instances, one per section).

        Intra-section deduplication: within a section, already-selected variants
        are penalized (score * 0.3) so groups get distinct variants when possible.
        Disabled when ``embrace_repetition=True``.

        Cross-section repeat penalty: when two sections share the same label
        (e.g. two verses), variants that were assigned to the same group in the
        previous section of that label are penalized (score * 0.5, or 0.85 when
        ``embrace_repetition=True`` to allow sustained repetition).

        Beat tier (tier 4) is excluded from all rotation plan assignments —
        it is handled by the chase pattern in place_effects regardless of
        ``embrace_repetition``.

        When ``symmetry_pairs`` is provided, group_b in each pair copies the
        variant assignment from group_a (with source="symmetry").

        Transition continuity: at least one group retains its variant from the
        previous section. If not, the lowest-tier group is forced to keep it.

        When ``working_sets`` is provided (dict of theme_name → WorkingSet), variant
        candidates are constrained to only those whose base_effect appears in that
        theme's WorkingSet. This is the T012 focused_vocabulary constraint.
        """
        tier_groups = [g for g in groups if 5 <= g.tier <= 8]
        entries: list[RotationEntry] = []

        # T036: Build symmetry lookup: group_b name → group_a name
        symmetry_map: dict[str, str] = {}
        if symmetry_pairs:
            for sp in symmetry_pairs:
                symmetry_map[sp.group_b] = sp.group_a

        # T026: track previous assignments per label for cross-section penalty
        label_assignments: dict[str, dict[str, str]] = {}  # label → {group_name → variant_name}

        # T037: track previous section's assignments for continuity
        prev_section_variants: dict[str, str] = {}

        for section_index, section_obj in enumerate(sections):
            # Resolve the theme for this section
            if theme_assignments is not None:
                assignment = theme_assignments[section_index]
                section_theme = assignment.theme
                section_energy = assignment.section
            else:
                section_theme = theme
                section_energy = section_obj

            layers = section_theme.layers
            if not layers:
                continue

            # T026: get previous assignments for this label (if any)
            prev_assignments = label_assignments.get(section_energy.label, {})

            # T025: track variants used within this section for deduplication
            used_in_section: set[str] = set()
            # T007 (FR-001): track base effects used per tier within this section
            used_effects_per_tier: dict[int, set[str]] = defaultdict(set)

            section_entries: list[RotationEntry] = []
            section_entry_map: dict[str, RotationEntry] = {}

            for group in tier_groups:
                # T036: skip symmetry group_b — will be filled after group_a
                if group.name in symmetry_map:
                    continue

                # Pick layer: first layer for tiers 5-6, last layer for tiers 7-8
                if group.tier >= 7 and len(layers) > 1:
                    layer = layers[-1]
                else:
                    layer = layers[0]

                # US3: pool filtering — score only pool variants if layer has effect_pool
                pool_results = None
                if hasattr(layer, "effect_pool") and layer.effect_pool:
                    pool_variants = [
                        v for name in layer.effect_pool
                        if (v := self.variant_library.get(name)) is not None
                    ]
                    if pool_variants:
                        context = build_scoring_context(section_energy, group, section_theme)
                        scored = []
                        for v in pool_variants:
                            total, breakdown = _score_variant(v, context, self.effect_library)
                            scored.append((v, total, breakdown))
                        scored.sort(key=lambda x: x[1], reverse=True)
                        if scored[0][1] >= 0.3:
                            pool_results = scored

                if pool_results is not None:
                    results = pool_results
                    source = "pool"
                else:
                    results = self._rank_for_group(section_energy, group, section_theme)
                    source = "library"

                # T012: focused_vocabulary — constrain to variants whose base_effect
                # appears in the theme's WorkingSet (when working_sets provided)
                if working_sets is not None and section_theme is not None:
                    ws = working_sets.get(section_theme.name)
                    if ws and ws.effects:
                        allowed_effects = {e.effect_name for e in ws.effects}
                        ws_results = [(v, s, b) for v, s, b in results if v.base_effect in allowed_effects]
                        if ws_results:
                            results = ws_results

                if not results:
                    continue

                # T026: apply cross-section repeat penalty
                # embrace_repetition=True: relaxed penalty (0.85) — same effect can sustain
                # embrace_repetition=False: aggressive penalty (0.5) — forces cross-section variety
                cross_section_penalty = 0.85 if embrace_repetition else 0.5
                prev_variant = prev_assignments.get(group.name)
                if prev_variant:
                    results = [
                        (v, s * (cross_section_penalty if v.name == prev_variant else 1.0), b)
                        for v, s, b in results
                    ]
                    results.sort(key=lambda x: x[1], reverse=True)

                if embrace_repetition:
                    # T018: No intra-section dedup — same variant can repeat across groups
                    variant, score, breakdown = results[0]
                else:
                    # T025: prefer variants not yet used in this section
                    unused = [(v, s, b) for v, s, b in results if v.name not in used_in_section]
                    if unused:
                        variant, score, breakdown = unused[0]
                    else:
                        # All variants exhausted — fall back to highest-scoring one
                        variant, score, breakdown = results[0]

                # T008/T010 (FR-001, FR-006): within-tier base-effect dedup for tiers 5-8.
                # Independent of embrace_repetition — applies in both modes.
                # If the selected variant's base effect is already used in this tier,
                # find the highest-scoring alternative with an unclaimed base effect and
                # score >= 0.3. Fall back to the current selection if none qualifies.
                if group.tier >= 5 and variant.base_effect in used_effects_per_tier[group.tier]:
                    unclaimed = [
                        (v, s, b) for v, s, b in results
                        if v.base_effect not in used_effects_per_tier[group.tier] and s >= 0.3
                    ]
                    if unclaimed:
                        variant, score, breakdown = unclaimed[0]
                    # else: no suitable alternative — keep current selection (allow duplication)

                used_in_section.add(variant.name)
                # T009: record base effect as used for this tier
                if group.tier >= 5:
                    used_effects_per_tier[group.tier].add(variant.base_effect)

                entry = RotationEntry(
                    section_index=section_index,
                    section_label=section_energy.label,
                    group_name=group.name,
                    group_tier=group.tier,
                    variant_name=variant.name,
                    base_effect=variant.base_effect,
                    score=score,
                    score_breakdown=breakdown,
                    source=source,
                )
                section_entries.append(entry)
                section_entry_map[group.name] = entry

            # T036: fill symmetry group_b entries by copying from group_a
            for group in tier_groups:
                if group.name not in symmetry_map:
                    continue
                primary_name = symmetry_map[group.name]
                primary_entry = section_entry_map.get(primary_name)
                if primary_entry is None:
                    continue

                entry = RotationEntry(
                    section_index=section_index,
                    section_label=section_energy.label,
                    group_name=group.name,
                    group_tier=group.tier,
                    variant_name=primary_entry.variant_name,
                    base_effect=primary_entry.base_effect,
                    score=primary_entry.score,
                    score_breakdown=dict(primary_entry.score_breakdown),
                    source="symmetry",
                )
                section_entries.append(entry)
                section_entry_map[group.name] = entry

            # T037: section transition continuity — ensure at least one group
            # retains its variant from the previous section
            if section_index > 0 and prev_section_variants and section_entries:
                has_continuity = any(
                    e.variant_name == prev_section_variants.get(e.group_name)
                    for e in section_entries
                )
                if not has_continuity:
                    lowest = min(section_entries, key=lambda e: e.group_tier)
                    prev_variant = prev_section_variants.get(lowest.group_name)
                    if prev_variant:
                        lowest.variant_name = prev_variant
                        lowest.source = "continuity"

            # Update tracking for next section
            prev_section_variants = {
                e.group_name: e.variant_name for e in section_entries
            }

            entries.extend(section_entries)

            # T026: record this section's assignments for future same-label sections
            current_assignments = {
                e.group_name: e.variant_name for e in section_entries
            }
            label_assignments[section_energy.label] = current_assignments

        return RotationPlan(
            entries=entries,
            sections_count=len(sections),
            groups_count=len(tier_groups),
            symmetry_pairs=list(symmetry_pairs) if symmetry_pairs else [],
        )
