# Feature Specification: Theme Data Endpoint

**Feature Branch**: `025-theme-data-endpoint`
**Created**: 2026-04-01
**Status**: RETIRED — Superseded by [026-theme-editor](../026-theme-editor/spec.md)
**Input**: User description: "Theme data API endpoint for serving theme library data to the review UI frontend"

> **This spec has been retired.** Its scope (theme listing, validation, and data endpoints) has been absorbed into [026-theme-editor](../026-theme-editor/spec.md), which covers a full theme editor UI including all data endpoints as prerequisites. Any dependencies on 025 (e.g., from spec 024) should now reference 026 instead.

## Summary

The story review UI needs access to theme library data (names, moods, occasions, intents, color palettes) to power the Themes flyout tab, drag-and-drop assignment, and theme recommendations. Currently, themes are only loaded server-side by `src/themes/library.py` and consumed by the sequence generator. No endpoint exposes theme data to the frontend.

This feature will provide:

1. **Theme listing endpoint** — serve all available themes with filterable metadata (mood, occasion, genre) and color palettes, usable by the review UI frontend.
2. **Theme recommendation endpoint** — given a section's character (energy, mood, role) and the song's occasion preference, return 2-3 ranked theme suggestions. Builds on existing logic in `src/generator/theme_selector.py`.
3. **Theme name validation** — when a theme is assigned to a section via overrides, validate that the theme name exists in the loaded library.

## Scope Notes

- Exposes existing theme library data — does NOT create new themes or modify the theme data model.
- Recommendation logic should be reusable from `theme_selector.py`, adapted for single-section queries.
- Validation should cover both per-section override assignments and song-wide preference theme field.

## Dependencies

- Depends on: existing `src/themes/library.py`, `src/themes/builtin_themes.json`, `src/generator/theme_selector.py`
- Depended on by: [024-story-review-flyouts](../024-story-review-flyouts/spec.md) (P2 and P3 stories)
