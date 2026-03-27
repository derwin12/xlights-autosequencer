# Implementation Plan: Effect Themes

**Branch**: `019-effect-themes` | **Date**: 2026-03-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/019-effect-themes/spec.md`

## Summary

Build a JSON catalog of 21+ composite effect themes organized by mood (Ethereal, Aggressive, Dark, Structural), tagged with occasion (christmas, halloween, general) and genre affinity (rock, pop, classical, any). Each theme stacks multiple effects from the effect library (018) with color palettes, blend modes, and parameter overrides. Programmatic API for loading, lookup, and tag-based querying. Custom overrides via `~/.xlight/custom_themes/`. No CLI tools in v1.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: `json` (stdlib), `pathlib` (stdlib), `src.effects` (feature 018)
**Storage**: `src/themes/builtin_themes.json` (built-in), `~/.xlight/custom_themes/*.json` (custom)
**Testing**: pytest (existing)
**Target Platform**: macOS (developer workstation)
**Project Type**: Library module (consumed by sequence generator)
**Performance Goals**: Library loads and validates in under 1 second
**Constraints**: No new runtime dependencies; effect references must validate against effect library
**Scale/Scope**: 21+ theme definitions, 2-4 layers each

## Constitution Check

**Constitution version**: 1.0.0

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | ✅ Pass | Themes are a static data catalog. No timing or analysis data is processed. |
| II. xLights Compatibility | ✅ Pass | Blend modes use exact xLights `T_CHOICE_LayerMethod` values. Parameter overrides use `E_SLIDER_*` storage names. Color palettes use `#RRGGBB` hex matching xLights `C_BUTTON_Palette` format. |
| III. Modular Pipeline | ✅ Pass | New `src/themes/` module depends on `src/effects/` but is independently testable. |
| IV. Test-First Development | ✅ Pass | TDD enforced. |
| V. Simplicity First | ✅ Pass | Data catalog + API only. No selection engine, no mood detection, no CLI. |

**Post-Design Re-check**: ✅ All gates pass.

## Project Structure

### Documentation (this feature)

```text
specs/019-effect-themes/
├── plan.md
├── research.md          # Blend modes, palette format, layer overrides
├── data-model.md        # Theme, EffectLayer, ColorPalette, ThemeLibrary
├── quickstart.md        # Usage guide
├── contracts/
│   └── api-contract.md  # Python API: load, get, by_mood, by_occasion, query
└── tasks.md
```

### Source Code

```text
src/
└── themes/
    ├── __init__.py
    ├── models.py               # Dataclasses: Theme, EffectLayer, ThemeLibrary
    ├── library.py              # load_theme_library(), ThemeLibrary query methods
    ├── validator.py            # validate_theme() — checks effect refs, blend modes, layers
    └── builtin_themes.json     # The 21+ theme catalog

tests/
├── fixtures/
│   └── themes/
│       ├── minimal_themes.json       # 3 themes for unit tests
│       ├── valid_custom_theme.json   # A valid custom theme
│       └── invalid_custom_theme.json # Invalid custom theme
├── unit/
│   ├── test_themes_models.py
│   ├── test_themes_library.py
│   └── test_themes_validator.py
└── integration/
    └── test_themes_integration.py
```

**Structure Decision**: Mirrors `src/effects/` exactly — same patterns for loading, validation, custom overrides, and testing. The only new dependency is importing `EffectLibrary` from `src/effects/` for validation.

## Complexity Tracking

> No constitution violations. No entries required.

---

## Implementation Notes

### Theme Authoring

The 21 built-in themes are hand-authored JSON based on:
- 12 themes from `docs/effect-themes-library.md` (design doc) — effect stacks and model logic already defined
- 6 Christmas themes — new, using winter/holiday effect combinations with red/green/gold/blue palettes
- 3 Halloween themes — new, using dark/aggressive effects with orange/purple/black palettes

Each theme translates the design doc's prose descriptions into concrete JSON:
- "Slow Butterfly → Twinkle → Meteors" becomes 3 layers with specific parameter overrides
- "Map Meteor Count to piano onsets" becomes a note in the intent (actual wiring is sequence generator's job)

### Effect Reference Validation

On load, every effect name in every theme layer is checked against the loaded effect library. Additionally:
- Modifier effects (`layer_role=modifier` in effect library) cannot be on layer 0 (bottom)
- If an effect is missing from the library, the theme is loaded but flagged with a warning

### Blend Mode Storage

The 24 xLights blend modes are stored as string values matching `T_CHOICE_LayerMethod`. We store them as a constant list in `models.py` for validation. The sequence generator will emit them as `T_CHOICE_LayerMethod={value}` in the effect settings string.
