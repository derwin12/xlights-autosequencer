# API Contract: Theme Library

**Date**: 2026-03-26
**Branch**: `019-effect-themes`

---

## Programmatic Interface

### Load Library

```
load_theme_library(
    builtin_path: Path | None = None,
    custom_dir: Path | None = None,
    effect_library: EffectLibrary | None = None,
) -> ThemeLibrary
```

Loads built-in themes JSON, scans custom dir for overrides, validates all effect references against the effect library. If effect_library is None, loads it automatically.

**Errors**: Raises if built-in JSON is missing (fatal).

---

### Lookup by Name

```
ThemeLibrary.get(name: str) -> Theme | None
```

Case-insensitive lookup.

---

### Query by Tags

```
ThemeLibrary.by_mood(mood: str) -> list[Theme]
ThemeLibrary.by_occasion(occasion: str) -> list[Theme]
ThemeLibrary.by_genre(genre: str) -> list[Theme]
ThemeLibrary.query(mood: str | None, occasion: str | None, genre: str | None) -> list[Theme]
```

`by_genre` includes themes tagged "any". `query` combines all filters (AND logic).

---

### Validate Theme

```
validate_theme(data: dict, effect_library: EffectLibrary) -> list[str]
```

Returns error messages. Checks: required fields, effect references exist in library, blend modes valid, bottom layer is Normal, modifier effects not on bottom layer, palette has 2+ colors.

---

## JSON File Locations

| File | Path | Purpose |
|------|------|---------|
| Built-in catalog | `src/themes/builtin_themes.json` | Shipped with tool, read-only |
| Custom overrides | `~/.xlight/custom_themes/{name}.json` | User-created, one file per theme |
