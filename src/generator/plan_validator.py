"""Pre-write plan diagnostics — catches known monotony failure shapes in a
built SequencePlan before it's written to .xsq.

See openspec/changes/plan-variety-validator for the design rationale. V1
implements exactly one check (corpus_recipe_monotony): a corpus-recipe
family with alt_effect_name set is supposed to show two effects across a
song's qualifying occurrences. If every occurrence renders the SAME one,
that's the exact "one effect the whole song" bug class that has recurred
multiple times in this codebase (bug-197, the 2026-07-28 Shockwave bounce
reroll, the mirror-overlay aliasing bug) -- always caught before now by a
human noticing a bad render, never by the pipeline itself.

Deliberately narrow: this is one specific, already-proven failure shape,
not a general variety-score heuristic (which would need its own calibration
before being trustworthy -- see the design's "Alternatives considered").
motion_rotation families (megatree, matrix) are out of scope for V1; they
have their own occurrence-counter reachability guarantee already and would
need a differently-shaped check.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from src.generator.corpus_recipes import recipe_for_group
from src.generator.models import PlanWarning, SectionAssignment
from src.grouper.grouper import PowerGroup

# Fewer occurrences than this can't demonstrate variety by construction --
# not flagging a family that only qualified once in a short song.
_MIN_OCCURRENCES_TO_FLAG = 2


def validate_plan(
    assignments: list[SectionAssignment], groups: list[PowerGroup],
) -> list[PlanWarning]:
    """Run all V1 pre-write checks against a built plan. Read-only."""
    warnings: list[PlanWarning] = []
    warnings.extend(_check_corpus_recipe_monotony(assignments, groups))
    return warnings


def _check_corpus_recipe_monotony(
    assignments: list[SectionAssignment], groups: list[PowerGroup],
) -> list[PlanWarning]:
    warnings: list[PlanWarning] = []
    for group in groups:
        recipe = recipe_for_group(group)
        if recipe is None or recipe.alt_effect_name is None:
            continue
        # V1 scope: only the plain primary/alt families. motion_rotation
        # families already have a reachability-guaranteed occurrence
        # counter and would need a differently-shaped check (see module
        # docstring).
        if recipe.motion_rotation:
            continue

        recipe_effects = {recipe.effect_name, recipe.alt_effect_name}
        effect_counts: Counter[str] = Counter()
        for assignment in assignments:
            for placement in assignment.group_effects.get(group.name, []):
                if placement.effect_name in recipe_effects:
                    effect_counts[placement.effect_name] += 1

        if not effect_counts:
            continue
        occurrences = sum(effect_counts.values())
        if occurrences < _MIN_OCCURRENCES_TO_FLAG:
            continue
        if len(effect_counts) == 1:
            only_effect = next(iter(effect_counts))
            warnings.append(PlanWarning(
                severity="warning",
                code="corpus_recipe_monotony",
                group_name=group.name,
                message=(
                    f"{group.name}: every placement across {occurrences} "
                    f"qualifying occurrence(s) used '{only_effect}' — "
                    f"'{recipe.alt_effect_name if only_effect == recipe.effect_name else recipe.effect_name}' "
                    f"never appeared despite being part of the {recipe.family} recipe."
                ),
            ))
    return warnings
