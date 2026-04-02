# Research: Intelligent Effect Rotation

## R1: How should the rotation engine integrate with the existing effect placer?

**Decision**: Create a new `RotationEngine` class in `src/generator/rotation.py` that pre-computes a `RotationPlan` before effect placement begins. The plan maps (section_index, group_name) → selected EffectVariant. The effect placer consults this plan instead of using `_PROP_EFFECT_POOL` round-robin.

**Rationale**: Pre-computing the full rotation plan allows the engine to enforce cross-group uniqueness (FR-002), cross-section variety (FR-003), and section transition continuity (FR-007) — all of which require global visibility across the whole sequence. The current per-tier/per-group placement loop cannot enforce these constraints locally.

**Alternatives considered**:
- **Inline in effect_placer.py**: Would bloat the file and make variety constraints hard to enforce since placement is per-section/per-layer.
- **Lazy per-section computation**: Loses the ability to enforce cross-section variety and transition continuity since we can't look ahead.

## R2: How should the variant scorer map to section energy and theme mood?

**Decision**: Map SectionEnergy fields to ScoringContext as follows:
- `energy_score 0-33` → `energy_level="low"`, `34-66` → `"medium"`, `67-100` → `"high"`
- `mood_tier` ("ethereal"/"structural"/"aggressive") → `tier_affinity` mapping: ethereal→"background", structural→"mid", aggressive→"foreground"
- `section.label` → `section_role` (verse, chorus, bridge, intro, outro, drop)
- `theme.genre` → `genre`
- `theme.mood` → used for EffectPool filtering, not directly in scorer
- `group.prop_type` → `prop_type` (from feature 029)
- `group.tier` → `tier_affinity` override: tier 5→"mid", tier 6→"mid", tier 7→"foreground", tier 8→"hero"

**Rationale**: This mapping uses existing ScoringContext dimensions without inventing new ones. The tier-based tier_affinity override ensures variants tagged for foreground use end up on hero/compound groups.

**Alternatives considered**:
- **New scoring dimensions**: Adding "speed" or "complexity" dimensions. Rejected — YAGNI. The existing 6 dimensions with 0.30 prop weight cover the use cases.

## R3: How should intra-section variety be enforced (FR-002)?

**Decision**: The RotationEngine scores all candidate variants for each group in a section, then uses a greedy assignment algorithm:
1. Score all variants for all groups in the section
2. Assign the top-scoring variant to the first group
3. For subsequent groups, exclude already-assigned variants from the candidate set (if sufficient alternatives exist)
4. If fewer variants than groups: allow reuse but prefer highest-scoring unused variants first

**Rationale**: Greedy assignment is simple, deterministic, and produces good variety with O(groups × variants) complexity. A full combinatorial optimization would be overkill for typical layouts (4-8 groups at a tier).

**Alternatives considered**:
- **Hungarian algorithm**: Optimal assignment but adds complexity for marginal gain.
- **Random shuffling**: Not deterministic (FR-009 violated).

## R4: How should cross-section variety be enforced (FR-003)?

**Decision**: The RotationEngine tracks a `previous_assignments` map per group. When scoring for a new section, variants that were used in the immediately preceding section of the same type receive a 0.5× penalty multiplier on their score. This discourages but doesn't prevent repeats.

**Rationale**: A hard exclusion could leave sections with no valid variants if the library is small. A penalty achieves 50%+ difference naturally while gracefully degrading when options are limited. The penalty is seeded by section index for determinism.

**Alternatives considered**:
- **Hard exclusion**: Fails with small variant libraries.
- **Random re-roll**: Not deterministic.

## R5: How should symmetry pair detection work (FR-006)?

**Decision**: New module `src/grouper/symmetry.py` with `detect_symmetry_pairs(groups, props)`:
1. **Name-based**: Match groups whose names differ only by Left/Right, L/R, 1/2, A/B suffixes (case-insensitive).
2. **Position-based**: For groups not matched by name, check if two groups of the same tier have members whose average norm_x values are on opposite sides of center (one < 0.35, other > 0.65) and similar norm_y (within 0.15).
3. **Manual override**: Accept an optional `symmetry_overrides` list of `(group_a, group_b)` tuples from the generation config.

Returns: `list[SymmetryGroup]` where each SymmetryGroup holds two group names and a `mirror_direction: bool` flag.

**Rationale**: Name-based matching covers the most common case (explicit Left/Right naming). Position-based catches layouts where names don't follow conventions. Manual override handles edge cases.

**Alternatives considered**:
- **Name-only**: Misses spatial symmetry in layouts with numbered props.
- **Full spatial clustering**: Over-engineered for typical layouts.

## R6: How should theme effect pools be stored and loaded?

**Decision**: Add an optional `effect_pool: list[str]` field to `EffectLayer` in `src/themes/models.py`. Each entry is a variant name. When `effect_pool` is set, the rotation engine uses the pool as the candidate set (scored by context); when no pool variant scores above threshold, it falls back to full library scoring. The existing `effect` field remains as the base effect and is used for tiers 1-4 (unchanged behavior).

**Rationale**: Minimal schema change. The `effect` field provides backward compatibility — existing themes with no `effect_pool` work identically. The pool is just a preference list; the scorer still handles ranking.

**Alternatives considered**:
- **Separate pool definition file**: Unnecessary indirection for a list of strings.
- **Query-based pool** (e.g., `{"energy": "high"}`): More complex to author and validate; the scorer already handles context matching.

## R7: How should section transition continuity work (FR-007)?

**Decision**: When building the RotationPlan, after assigning all groups in a section, the engine checks if at least one group at tier 5-8 retained the same variant as the previous section. If not, it forces the lowest-tier group (tier 5 if present, else tier 6) to keep its previous variant, re-scoring only the remaining groups.

**Rationale**: The lowest tier is the most background-like and least noticeable to change — forcing it to stay consistent provides visual anchoring while allowing higher tiers to change freely. Since tiers 1-4 are unchanged by this feature, they already provide some continuity; this rule adds one more shared element in the active tiers.

**Alternatives considered**:
- **Force continuity on a random tier**: Not deterministic.
- **Skip continuity enforcement**: Makes transitions too jarring between sections with different themes.

## R8: How should the rotation report be structured?

**Decision**: The RotationPlan data structure includes per-entry scoring metadata. The report is rendered as:
- **CLI**: `xlight-analyze rotation-report <plan.json>` outputs a table: Section | Group | Effect Variant | Score | Top Factors
- **Web dashboard**: New GET `/rotation-report/<plan_hash>` endpoint returns JSON consumed by the existing dashboard UI

**Rationale**: Reuses existing CLI and Flask patterns. The data is already in the RotationPlan — the report is just a view.

**Alternatives considered**:
- **Standalone HTML report**: Unnecessary when the dashboard already exists.
