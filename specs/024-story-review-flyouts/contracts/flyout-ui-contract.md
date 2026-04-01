# UI Contract: Flyout Panel

**Date**: 2026-04-01

## Flyout HTML Structure

```html
<div id="flyout" class="flyout flyout--closed">
  <div class="flyout-header">
    <div class="flyout-tabs">
      <button class="flyout-tab active" data-tab="details">Details</button>
      <button class="flyout-tab" data-tab="moments">Moments</button>
      <button class="flyout-tab" data-tab="themes">Themes</button>
    </div>
    <button class="flyout-close" aria-label="Close panel">&times;</button>
  </div>
  <div class="flyout-body">
    <div class="flyout-content" data-tab-content="details">
      <!-- Section detail + stems bars (migrated from #section-detail + #stems-panel) -->
    </div>
    <div class="flyout-content" data-tab-content="moments" hidden>
      <!-- Moments list (migrated from #moments-panel) -->
    </div>
    <div class="flyout-content" data-tab-content="themes" hidden>
      <!-- Theme cards + filters (new, depends on 026) -->
    </div>
  </div>
</div>
```

## CSS Layout Contract

```css
/* Flyout closed: timeline takes full width */
#main.flyout-closed {
  grid-template-columns: 1fr;
}

/* Flyout open: push layout with animated transition */
#main.flyout-open {
  grid-template-columns: 1fr 360px;
}

#main {
  transition: grid-template-columns 0.25s ease;
}
```

## JavaScript API Contract

### State additions
```javascript
state.flyoutOpen    // boolean — flyout visibility
state.activeTab     // "details" | "moments" | "themes"
state.themeList     // Theme[] — cached from /story/themes (P2)
state.themePalettes // {[themeName]: string[]} — palette lookup (P2)
state.themeFilters  // {mood: string|null, occasion: string|null} (P2)
```

### Functions (new or modified)

| Function | Action | Replaces |
|----------|--------|----------|
| `openFlyout()` | Sets state.flyoutOpen=true, updates grid class, re-renders canvas | — |
| `closeFlyout()` | Sets state.flyoutOpen=false, updates grid class, re-renders canvas | — |
| `switchTab(tabName)` | Sets state.activeTab, shows/hides content, re-renders active tab | — |
| `renderDetailsTab(idx)` | Renders section details + stems into flyout | `renderSectionDetail()` + `renderStemsPanel()` |
| `renderMomentsTab(section, moments)` | Renders moments list into flyout | `renderMomentsPanel()` |
| `renderThemesTab(section)` | Renders theme cards with filters (P2) | — (new) |
| `selectSection(idx)` | Modified: calls openFlyout() + renders active tab only | Current: renders all 3 panels |

### Events

| Event | Source | Handler |
|-------|--------|---------|
| click .flyout-tab | Tab button | `switchTab(e.target.dataset.tab)` |
| click .flyout-close | Close button | `closeFlyout()` |
| click timeline (no section hit) | Canvas | `closeFlyout()` |
| click timeline (section hit) | Canvas | `selectSection(idx)` → opens flyout |
| transitionend #main | Grid | Re-render canvases at new width |

## Theme Card Contract (P2 — depends on 026)

```html
<div class="theme-card" draggable="true" data-theme-name="Inferno">
  <div class="theme-card-header">
    <span class="theme-name">Inferno</span>
    <span class="theme-mood-badge mood-aggressive">aggressive</span>
  </div>
  <p class="theme-intent">Raw power — house looks like it is on fire</p>
  <div class="theme-palette">
    <span class="palette-swatch" style="background: #ff4400"></span>
    <span class="palette-swatch" style="background: #ff8800"></span>
    <span class="palette-swatch" style="background: #ffcc00"></span>
  </div>
  <div class="theme-accent-palette">
    <span class="palette-swatch" style="background: #ff0000"></span>
    <span class="palette-swatch" style="background: #ff6600"></span>
    <span class="palette-swatch" style="background: #ffaa00"></span>
  </div>
</div>
```

## Drag and Drop Contract (P2)

| Event | Element | Behavior |
|-------|---------|----------|
| dragstart | .theme-card | Set `dataTransfer` with theme name; add `.dragging` class |
| dragover | .section-bar (canvas) | Highlight section as valid drop target |
| dragleave | .section-bar (canvas) | Remove highlight |
| drop | .section-bar (canvas) | POST `/story/section/overrides` with `{theme: name}`; re-render |
| dragend | .theme-card | Remove `.dragging` class; clear highlights |

Note: Since sections are canvas-drawn (not DOM elements), drag-over detection uses mouse coordinates mapped to section time ranges via `xToTime()`, with a transparent overlay div for drop target events.
