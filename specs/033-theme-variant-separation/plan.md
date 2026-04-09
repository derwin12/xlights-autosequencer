# Implementation Plan: Theme and Effect Variant Separation

**Branch**: `033-theme-variant-separation` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/033-theme-variant-separation/spec.md`

## Summary

Refactor theme layers to reference effect variants by name instead of containing inline parameter overrides. Themes become purely compositional (variant + blend_mode + palette), while variants exclusively own effect parameter configuration. ThemeVariant is renamed to ThemeAlternate to avoid terminology collision. All 87 theme layers across 21 built-in themes are migrated, creating ~60-70 new variants. The runtime parameter variation tweak is removed. The theme editor UI is updated to use a variant picker instead of parameter editing.

## Technical Context

**Language/Version**: Python 3.11+ (backend), Vanilla JavaScript ES2020+ (frontend)
**Primary Dependencies**: Flask 3+ (web server), click 8+ (CLI), existing analysis pipeline
**Storage**: JSON files (builtin_themes.json, variant builtins/*.json, custom themes/variants)
**Testing**: pytest
**Target Platform**: Linux/macOS (local development tool)
**Project Type**: CLI + web-service (local review UI)
**Performance Goals**: N/A (refactor, no new performance requirements)
**Constraints**: Zero visual output regression — migrated themes must produce identical sequences
**Scale/Scope**: 21 themes, 87 layers, ~60-70 new variants, ~50 files touched

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | PASS | No changes to audio analysis pipeline |
| II. xLights Compatibility | PASS | No changes to XSQ output format |
| III. Modular Pipeline | PASS | Strengthens modularity — themes and variants have cleaner separation of concerns |
| IV. Test-First Development | PASS | Tests will be written for new model before implementation |
| V. Simplicity First | PASS | Removes complexity (parameter_overrides, _apply_variation, variant_ref) rather than adding it |

**Post-Phase 1 Re-check**: All gates still pass. Data model simplifies EffectLayer from 5 fields to 3 fields. No new abstractions introduced.

## Project Structure

### Documentation (this feature)

```text
specs/033-theme-variant-separation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── theme-api.md     # API contract changes
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (files to modify)

```text
src/
├── themes/
│   ├── models.py              # EffectLayer simplification, ThemeVariant → ThemeAlternate
│   ├── builtin_themes.json    # All 21 themes rewritten to variant references
│   ├── validator.py           # Variant existence validation (required, not warning)
│   ├── library.py             # variant_library becomes required parameter
│   └── writer.py              # Save format updated (no parameter_overrides)
├── variants/
│   └── builtins/              # ~60-70 new variant JSON files
├── generator/
│   ├── effect_placer.py       # Parameter resolution, _apply_variation removal
│   ├── rotation.py            # Minor — layer.effect_pool access unchanged
│   └── plan.py                # variant_library loading becomes required
└── review/
    ├── theme_routes.py        # API serialization updates
    └── static/
        └── theme-editor.js    # Variant picker replaces parameter editor

tests/
├── unit/
│   ├── test_themes_models.py
│   ├── test_themes_validator.py
│   ├── test_themes_library.py
│   ├── test_theme_routes.py
│   ├── test_theme_writer.py
│   ├── test_variant_theme_models.py
│   └── test_generator/
│       ├── test_effect_placer.py
│       └── test_theme_selector.py
└── integration/
    ├── test_variant_theme_integration.py
    ├── test_theme_variant_picker.py
    ├── test_themes_integration.py
    └── test_rotation_integration.py
```

**Structure Decision**: No new directories or modules. All changes modify existing files. New variant JSON files added to existing `src/variants/builtins/` directory.

## Implementation Phases

### Phase A: Core Model Changes (P1 — Story 1)

**Goal**: EffectLayer references variants only, ThemeVariant → ThemeAlternate rename.

1. **EffectLayer model** (`src/themes/models.py`):
   - Remove `effect`, `parameter_overrides`, `variant_ref` fields
   - Add required `variant: str` field
   - Update `from_dict()` and `to_dict()`
   - Rename `ThemeVariant` class to `ThemeAlternate`
   - Rename `Theme.variants` field to `Theme.alternates`
   - Update `Theme.from_dict()` and `Theme.to_dict()`

2. **Validator** (`src/themes/validator.py`):
   - `variant_library` parameter becomes required (not optional)
   - Validate `layer.variant` exists in variant library (error, not warning)
   - Derive effect from variant's `base_effect` for modifier/blend checks
   - Remove `parameter_overrides` validation
   - Update ThemeVariant → ThemeAlternate references

3. **Library loader** (`src/themes/library.py`):
   - `variant_library` parameter becomes required in `load_theme_library()`
   - Error on missing variant library instead of proceeding without it
   - Update `save_custom_theme()` to use new format

4. **Generator plan** (`src/generator/plan.py`):
   - Remove try/except around variant library loading — make it a required call
   - Pass variant_library to load_theme_library()

5. **Effect placer** (`src/generator/effect_placer.py`):
   - Update `_place_effect_on_group()`: resolve variant from library to get effect_def and params
   - Remove `_apply_variation()` function and its call site
   - Update `_flat_model_fallback()`: resolve variant
   - Update `_place_chase_across_groups()`: resolve variant params
   - Update `theme.variants` → `theme.alternates` references
   - Variant library must be passed to all paths that need parameter resolution

6. **Theme writer** (`src/themes/writer.py`):
   - No structural changes needed (writes raw dicts), but verify save_theme produces new format

7. **Theme routes** (`src/review/theme_routes.py`):
   - Update API serialization to return new EffectLayer format
   - Update effect-pools endpoint

### Phase B: Variant Migration (P2 — Story 2)

**Goal**: Create new variants for all theme layers, rewrite builtin_themes.json.

1. **Analyze and deduplicate**: Compare all 87 theme layer parameter sets. Group identical sets (same base_effect + same params) to avoid creating duplicate variants.

2. **Create new variant files**: For each unique parameter set:
   - Name using effect-descriptive convention (e.g., "Plasma Slow Pattern6")
   - Add to appropriate effect file in `src/variants/builtins/`
   - Fill tags based on theme context (see research.md R7)
   - Include direction_cycle where the theme layer had alternating direction params

3. **Rewrite builtin_themes.json**: Replace every layer's `effect` + `parameter_overrides` with `variant` reference. Rename `variants` key to `alternates`.

4. **Validation pass**: Load the migrated themes and variant library together. Verify zero validation errors and that resolved parameters match the pre-migration values exactly.

### Phase C: Theme Editor UI (P2 — Story 3)

**Goal**: Replace parameter editing with variant picker in the theme editor.

1. **Variant picker component** (`theme-editor.js`):
   - Replace effect selector + parameter controls with variant picker dropdown
   - Group variants by base_effect in the dropdown
   - Show variant name and description
   - Layer creation produces `{ variant: '', blend_mode: 'Normal' }`

2. **Layer serialization** (`getLayerData()`, `getLayerDataFromContainer()`):
   - Serialize layers as `{ variant, blend_mode, effect_pool }` — no effect or parameter_overrides

3. **Alternates editor**:
   - Update variant/alternate section to use "alternates" terminology
   - Same variant picker for alternate layers

4. **API endpoint** (optional):
   - Add `GET /variants/api/list-grouped` for efficient variant picker population

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Visual regression after migration | Snapshot test: capture pre-migration params per theme, compare post-migration resolved params |
| New variants pollute rotation scoring | Careful tagging per research.md R7; run existing rotation tests |
| Theme editor breakage | Test save/load round-trip for new format |
| Missing variant causes hard failure | Validator produces clear error with theme name, layer index, variant name |

## Complexity Tracking

No constitution violations to justify. The refactor removes complexity:
- EffectLayer: 5 fields → 3 fields
- Parameter resolution: 3-level chain → 2-level chain
- `_apply_variation` function: removed
- Terminology: "variant" means one thing (EffectVariant), not two
