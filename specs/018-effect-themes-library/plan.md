# Implementation Plan: xLights Effect Library

**Branch**: `018-effect-themes-library` | **Date**: 2026-03-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/018-effect-themes-library/spec.md`

## Summary

Build a JSON catalog of 35+ individual xLights effect definitions with parameters, prop-type suitability ratings, and structured analysis-to-parameter mappings. Effect parameter data is scraped from xLights C++ source code on GitHub, then hand-reviewed. The library is loaded programmatically by downstream modules (themes engine, sequence generator). Custom overrides via JSON files in `~/.xlight/custom_effects/`. No CLI tools in v1.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: `json` (stdlib), `pathlib` (stdlib) — no new dependencies
**Storage**: `src/effects/builtin_effects.json` (built-in catalog), `~/.xlight/custom_effects/*.json` (custom overrides)
**Testing**: pytest (existing)
**Target Platform**: macOS (developer workstation)
**Project Type**: Library module (consumed by downstream features)
**Performance Goals**: Library loads and validates in under 1 second
**Constraints**: No new runtime dependencies; offline operation; xLights parameter names must match source code exactly
**Scale/Scope**: 35+ effect definitions, ~5-20 parameters each, ~150-700 parameter entries total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*
**Constitution version**: 1.0.0

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | ✅ Pass | Effect library is a static data catalog. It does not produce timing data or alter the analysis pipeline. Analysis mappings define how analysis *could* drive parameters — actual wiring happens in the downstream sequence generator. |
| II. xLights Compatibility | ✅ Pass | Parameter names use exact xLights internal naming (`E_SLIDER_Fire_Height`, etc.) extracted from xLights source. The `.xsq` format compatibility is validated by matching storage name conventions. |
| III. Modular Pipeline | ✅ Pass | New `src/effects/` module is independently testable. Communicates via `EffectLibrary` / `EffectDefinition` data structures. No coupling to analysis pipeline or grouper module. |
| IV. Test-First Development | ✅ Pass | Tests written before implementation (Red-Green-Refactor). JSON fixture files included. |
| V. Simplicity First | ✅ Pass | One-time scrape + static JSON. No runtime scraping, no dynamic loading from xLights repo. Python API only — no CLI tools in v1. |

**Post-Design Re-check**: ✅ All gates still pass.

## Project Structure

### Documentation (this feature)

```text
specs/018-effect-themes-library/
├── plan.md              # This file
├── research.md          # xLights parameter naming convention, scraping strategy
├── data-model.md        # EffectDefinition, EffectParameter, AnalysisMapping, PropSuitability
├── quickstart.md        # Usage guide for downstream consumers
├── contracts/
│   └── api-contract.md  # Python API: load, get, for_prop_type, coverage, validate
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code

```text
src/
└── effects/
    ├── __init__.py               # Package marker
    ├── library.py                # EffectLibrary: load, get, for_prop_type, coverage
    ├── models.py                 # Dataclasses: EffectDefinition, EffectParameter, AnalysisMapping
    ├── validator.py              # validate_effect_definition() — schema validation
    ├── builtin_effects.json      # The 35+ effect catalog (shipped, read-only)
    └── effect_schema.json        # JSON schema for validation

scripts/
└── scrape_xlights_effects.py    # One-time scraper: xLights C++ source → raw JSON (not shipped)

tests/
├── fixtures/
│   └── effects/
│       ├── valid_custom_effect.json     # A valid custom effect for testing
│       ├── invalid_custom_effect.json   # An invalid custom effect for testing
│       └── minimal_library.json         # Small library for unit tests
├── unit/
│   ├── test_effects_models.py           # Dataclass construction and validation
│   ├── test_effects_library.py          # Load, get, for_prop_type, coverage
│   └── test_effects_validator.py        # Schema validation
└── integration/
    └── test_effects_integration.py      # Full load of builtin_effects.json + custom override
```

**Structure Decision**: New `src/effects/` module alongside existing `src/analyzer/` and `src/grouper/`. Scraper script in `scripts/` (dev tool, not shipped). Clean separation between the data (JSON), the data model (dataclasses), and the loading/query logic.

## Complexity Tracking

> No constitution violations. No entries required.

---

## Implementation Notes

### Scraping Strategy

The scraper (`scripts/scrape_xlights_effects.py`) is a dev-time tool, not part of the shipped product:
1. Fetches `*Effect.cpp` and `*Effect.h` from the xLights GitHub repo for the 35 target effects
2. Parses `GetValueCurveInt()`, `GetValueCurveDouble()`, `SettingsMap.GetBool()`, `SettingsMap.Get()` calls
3. Extracts `#define` constants for `*_MIN`, `*_MAX`
4. Outputs a raw JSON file that needs hand-review before becoming `builtin_effects.json`

The scraper output needs manual annotation for:
- `intent` descriptions (why to use the effect)
- `prop_suitability` ratings (community knowledge)
- `analysis_mappings` (creative decisions)
- `description` enrichment (the scraper can extract parameter names but not user-friendly descriptions)

### Custom Override Loading

- On `load_effect_library()`, scan `~/.xlight/custom_effects/` if it exists
- Each `{name}.json` file is validated against the schema
- Valid custom definitions override built-in by matching `name` field (case-insensitive)
- Invalid files: log warning, skip, continue loading

### Analysis Mapping Validation

Mappings reference analysis levels (L0–L6) and field paths. The library validates:
- `analysis_level` is one of `L0` through `L6`
- `mapping_type` is one of `direct`, `inverted`, `threshold_trigger`
- `parameter` references an actual parameter name in the same effect definition

Field path validation (`analysis_field`) is deferred to the sequence generator, since the analysis output schema is defined in a separate feature.
