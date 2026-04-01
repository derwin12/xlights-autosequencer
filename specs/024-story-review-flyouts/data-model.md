# Data Model: 024-story-review-flyouts

**Date**: 2026-04-01 | **Branch**: `024-story-review-flyouts`

## Entities

### Flyout State (frontend only — added to JS `state` object)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| flyoutOpen | boolean | false | Whether the flyout panel is visible |
| activeTab | string | "details" | Currently active tab: "details", "moments", or "themes" |
| themePalettes | object | {} | Cache of theme name → palette colors (loaded from 026 endpoint) |
| themeList | array | [] | Full list of available themes (loaded from 026 endpoint) |
| themeFilters | object | {mood: null, occasion: null} | Active theme tab filters |

### Existing Entities (no changes)

#### SectionOverrides (already exists in models.py)

| Field | Type | Notes |
|-------|------|-------|
| role | Optional[str] | Override auto-classified role |
| energy_level | Optional[str] | Override energy classification |
| mood | Optional[str] | "ethereal", "structural", "aggressive", "dark" |
| **theme** | **Optional[str]** | **Theme name — used by this feature for assignment storage** |
| focus_stem | Optional[str] | Which stem to emphasize |
| intensity | Optional[float] | 0.0-2.0 multiplier |
| notes | Optional[str] | User review notes |
| is_highlight | bool | Star as important section |

No new fields needed. The `theme` field already exists and is persisted through save/export.

#### Theme (read-only, served by 026-theme-editor)

| Field | Type | Notes |
|-------|------|-------|
| name | str | Display name, used as the assignment key |
| mood | str | "ethereal", "aggressive", "dark", "structural" |
| occasion | str | "general", "christmas", "halloween" |
| genre | str | "any", "rock", "pop", "classical" |
| intent | str | Human-readable creative description |
| palette | list[str] | Primary colors (hex codes, 3-4 entries) |
| accent_palette | list[str] | Accent colors (hex codes, 3-4 entries) |

Only the fields relevant to the flyout UI are listed. Full theme data (layers, variants, blend modes) is not needed for browsing/assignment.

## State Transitions

### Flyout Panel

```
CLOSED → OPEN (user clicks a section on timeline)
OPEN → OPEN (user clicks a different section — content updates, no transition)
OPEN → CLOSED (user clicks close button or empty timeline space)
CLOSED → OPEN (user clicks a section — opens to last active tab)
```

### Theme Assignment (per section)

```
UNASSIGNED → ASSIGNED (user drops theme or clicks Apply)
ASSIGNED → REASSIGNED (user drops a different theme on same section)
ASSIGNED → UNASSIGNED (user clicks remove/clear on theme badge)
```

## Data Flow

### P1: Flyout open/close + Details/Moments tabs

```
Timeline click → selectSection(idx) → state.flyoutOpen = true
  → renderFlyout() → renders active tab content
  → updateGridLayout() → CSS grid transitions to show flyout column
  → renderTimeline() + renderStemTracks() → canvas redraws at new width

Close button click → state.flyoutOpen = false
  → updateGridLayout() → CSS grid transitions to hide flyout column
  → renderTimeline() + renderStemTracks() → canvas redraws at full width
```

### P2: Theme assignment (requires 026)

```
Themes tab render → fetch /story/themes → cache in state.themeList
  → render theme cards with palette swatches

Drag theme card → dragstart event with theme name
  → timeline sections show drop-target highlight
  → drop event → POST /story/section/overrides {theme: name}
  → update state.story section overrides
  → renderTimeline() → palette strip appears on section bar
```
