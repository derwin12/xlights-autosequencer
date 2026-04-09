# Research: Theme and Effect Variant Separation

**Feature**: 033-theme-variant-separation
**Date**: 2026-04-09

## R1: Existing Variant Match Rate for Theme Layers

**Decision**: All 87 theme layers need new variants — zero exact matches exist.

**Rationale**: Compared every theme layer's `parameter_overrides` against all 125 existing variants using the `identity_key()` logic (base_effect + sorted parameter_overrides). Theme layers use custom parameter combinations not captured in the variant catalog. The existing variants were created for rotation scoring, not for theme composition.

**Implications**: The migration will create ~87 new variants across 19 effect types. The heaviest effects are Plasma (12), Color Wash (7), Ripple (6), Liquid (6). Some theme layers share identical parameter sets — deduplication during migration will reduce the count (estimated 60-70 unique variants needed).

## R2: EffectLayer Consumer Inventory

**Decision**: 8-10 core source files, 2 JS files, and ~24 test files need changes.

**Rationale**: Full codebase scan for all `EffectLayer`, `parameter_overrides`, `variant_ref`, and `ThemeVariant` references.

**Core source files requiring changes**:
- `src/themes/models.py` — EffectLayer dataclass, ThemeVariant → ThemeAlternate rename
- `src/themes/validator.py` — validation logic (variant lookup replaces param validation)
- `src/themes/library.py` — loading (variant_library becomes required)
- `src/themes/builtin_themes.json` — all 21 themes rewritten
- `src/generator/effect_placer.py` — parameter resolution chain, _apply_variation removal, _flat_model_fallback, chase placement
- `src/generator/rotation.py` — layer.effect_pool access (minor, stays)
- `src/generator/plan.py` — variant_library loading changes from try/except to required
- `src/review/theme_routes.py` — API serialization
- `src/review/static/theme-editor.js` — variant picker replaces parameter editor

**Test files** (24+): unit and integration tests for models, validator, library, effect_placer, rotation, theme routes, variant integration.

## R3: Parameter Resolution Chain Changes

**Decision**: Simplify from 3-level (base → variant → layer overrides) to 2-level (base → variant).

**Rationale**: Current chain in `_place_effect_on_group` (effect_placer.py:437-452):
1. Start with empty params
2. Apply variant overrides (if variant_ref set)
3. Apply layer.parameter_overrides on top

New chain:
1. Start with empty params
2. Apply variant overrides (always — variant is required)

No layer overrides. `_apply_variation` (±5% random tweaks) also removed per spec FR-013.

**Alternatives considered**: Keep parameter_overrides as optional override layer. Rejected — user wants clean separation; final tweaks happen in xLights.

## R4: ThemeAlternate Rename Scope

**Decision**: Rename `ThemeVariant` class to `ThemeAlternate`, JSON key `variants` to `alternates`.

**Rationale**: Avoids confusion with `EffectVariant`. Affects:
- `src/themes/models.py` — class rename + Theme field rename
- `src/themes/builtin_themes.json` — JSON key rename
- `src/themes/validator.py` — validation loop variable names
- `src/generator/effect_placer.py` — `theme.variants` → `theme.alternates`
- `src/review/static/theme-editor.js` — UI references to variants/alternates
- All related test files

## R5: Variant Library as Required Dependency

**Decision**: Make variant library loading a hard failure instead of try/except fallback.

**Rationale**: Currently `build_plan()` in plan.py wraps variant loading in try/except and falls back to pool rotation. After refactor, themes cannot resolve their layers without the variant library. The try/except block must become a direct call that raises on failure.

**Impact**: The `_PROP_EFFECT_POOL` fallback path in effect_placer.py (tier 6-7 pool rotation when no rotation plan) also needs updating since it doesn't go through variants. This path should use the rotation plan's variant assignments instead.

## R6: Theme Editor UI Transformation

**Decision**: Replace per-layer parameter editing with variant picker dropdown.

**Rationale**: The theme-editor.js currently:
- Creates layers with `{ effect: '', blend_mode: 'Normal', parameter_overrides: {} }`
- Has an effect selector dropdown that populates parameter controls
- Loads variants per-effect into `variantCache` for optional variant_ref selection
- Serializes layers with effect + parameter_overrides + variant_ref

New model:
- Creates layers with `{ variant: '', blend_mode: 'Normal' }`
- Has a variant picker (grouped by effect) that is the primary control
- No parameter editing on the theme layer at all
- Serializes layers with variant + blend_mode + effect_pool

## R7: New Variant Tag Strategy

**Decision**: Derive tags from theme context during migration.

**Rationale**: Each new variant needs meaningful VariantTags to avoid polluting rotation scoring. Strategy:
- `tier_affinity`: "background" for bottom layers (tiers 1-2), "mid" for middle layers (tiers 3-6), "hero" for top layers (tiers 7-8)
- `energy_level`: derived from theme mood — "ethereal" → "low", "structural" → "medium", "aggressive"/"dark" → "high"
- `speed_feel`: derived from speed parameter values — low speed → "slow", mid → "moderate", high → "fast"
- `section_roles`: derived from theme mood — ethereal → ["verse", "bridge", "intro"], aggressive → ["chorus", "drop"]
- `scope`: "single-prop" for most; "group" for wash/background effects
- `genre_affinity`: from theme genre field, or "any" if generic
