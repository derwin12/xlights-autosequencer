# API Contract: Effect Library

**Date**: 2026-03-26
**Branch**: `018-effect-themes-library`

---

## Programmatic Interface

The effect library is consumed by downstream modules (themes engine, sequence generator) via a Python API. No CLI commands in v1.

### Load Library

```
load_effect_library() -> EffectLibrary
```

Loads the built-in JSON catalog, scans `~/.xlight/custom_effects/` for overrides, validates, and returns the merged library. Logs warnings for invalid custom files.

**Errors**: Raises if built-in JSON is missing or unparseable (fatal).

---

### Lookup by Name

```
EffectLibrary.get(name: str) -> EffectDefinition | None
```

Returns the full definition for an effect by its xLights name (case-insensitive match), or `None` if not found.

---

### Query by Prop Type

```
EffectLibrary.for_prop_type(prop_type: str) -> list[EffectDefinition]
```

Returns all effects rated `ideal` or `good` for the given prop type. Valid prop types: `matrix`, `outline`, `arch`, `vertical`, `tree`.

---

### Coverage Stats

```
EffectLibrary.coverage() -> CoverageResult
```

Returns:
- `cataloged: list[str]` — effect names in the library
- `uncatalogued: list[str]` — known xLights effect names not in the library
- `total_xlights: int` — total known effects (56)

---

### Validate Definition

```
validate_effect_definition(data: dict) -> list[str]
```

Validates a parsed JSON dict against the effect schema. Returns a list of error messages (empty = valid).

---

## JSON File Locations

| File | Path | Purpose |
|------|------|---------|
| Built-in catalog | `src/effects/builtin_effects.json` | Shipped with tool, read-only |
| Custom overrides | `~/.xlight/custom_effects/{name}.json` | User-created, one file per effect |
| JSON schema | `src/effects/effect_schema.json` | Schema definition for validation |
