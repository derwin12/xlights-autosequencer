# Handoff: x-onset — Audio‑reactive Light Sequencer

## Overview

**x-onset** is a desktop-style tool for turning an `.mp3` into a cue-sheet of
musical sections, each assigned a named *theme* that drives an animated light
show (e.g. an xLights holiday display). The north star is a five-step flow:

1. **Library** — pick or drop a song.
2. **Drop** — import mp3.
3. **Analyze** — beat / bar / onset / impact / drop detection.
4. **Timeline** — review detected sections, nudge boundaries, audition.
5. **Theme** — assign one named theme per section (the core screen).
6. **Export** — render to xLights / FSEQ / xsq.

The prototype in this bundle is a single-page React app that mocks the entire
flow with a real audio file, a precomputed analysis fixture, and live mini
light previews.

## About the Design Files

The files in this bundle are **design references created in HTML** — a
high‑fidelity, clickable prototype showing intended look, layout, copy, and
behavior. They are **not production code to copy directly**. The task is to
**recreate these designs in the target codebase's existing environment**
(Electron + React, Tauri + React, native macOS/Windows, web, etc.) using its
established patterns, component libraries, state management, and build system.

If no target codebase exists yet, a reasonable default stack is:

- **Electron** (or **Tauri**) shell so we can talk to local files + xLights.
- **React 18** + **TypeScript**.
- **Zustand** or **Redux Toolkit** for the shared app state shown in
  `prototype/state.jsx` (it's deliberately a single hook — easy to port).
- **Web Audio API** / `<audio>` element for playback; **WaveSurfer.js** or
  a custom canvas waveform renderer.
- A Python/native sidecar for real analysis (librosa, qm-vamp-plugins,
  chordino) — the fixture `assets/highway-data.js` shows the shape the UI
  expects back.

## Fidelity

**High-fidelity.** Colors, typography, spacing, copy, and interactions are
final. Recreate pixel‑perfectly (or as close as the target platform's controls
allow). Typography, the dark/light palettes, and the accent color (`#d97757`)
are the brand — do not swap them for a generic design system.

The **visual language is intentionally pro‑tool/DAW-like**: monospaced meta,
dense information, two‑tone dark surfaces, thin 1px dividers, micro‑caps
labels, tabular numerals for timecodes. Do not "modernize" it into a
rounded/soft SaaS look.

## Files In This Bundle

```
design_handoff_xonset/
├── README.md                         ← this file
├── Prototype.html                    ← open this to run the prototype
├── prototype/                        ← all React/JSX source (10 files)
│   ├── state.jsx                     ← shared state, themes, palette
│   ├── shell.jsx                     ← Chrome, header, tool strip, library rail, status bar, tweaks
│   ├── lights.jsx                    ← light strip preview components
│   ├── theme-picker.jsx              ← THEME screen (north-star)
│   ├── sections-edit.jsx             ← editable section strip + sections-mode panel
│   ├── export-screen.jsx             ← EXPORT screen
│   ├── analyze-screen.jsx            ← ANALYZE screen (progress + detector list)
│   ├── timeline.jsx                  ← TIMELINE screen (waveform, ruler, algo tracks)
│   ├── other-screens.jsx             ← LIBRARY + DROP screens
│   └── app.jsx                       ← top-level router keyed on app.screen
├── assets/
│   ├── highway-data.js               ← analysis fixture (sections, beats, bars, impacts, drops)
│   └── highway.mp3                   ← sample audio
└── reference/                        ← earlier explorations for additional context
    ├── Flow Wireframes.html          ← low-fi storyboard of the whole flow
    ├── Visual Directions.html        ← visual direction explorations
    └── Pro-Tool Flow.html            ← pro-tool visual direction deep-dive
```

**To run locally:** the prototype uses `<script src>` loads, so serve the
folder over http (e.g. `python -m http.server` from inside
`design_handoff_xonset/`) and open `Prototype.html`. Opening via `file://`
will fail due to script-load CORS.

---

## Design Tokens

Defined in [`prototype/state.jsx`](./prototype/state.jsx) as the `PALETTE`
object. There are **two modes**, `dark` (default) and `light`. Both share the
same accent.

### Colors — Dark (default)

| Token        | Hex       | Usage                                              |
|--------------|-----------|----------------------------------------------------|
| `bg0`        | `#111114` | app canvas                                         |
| `bg1`        | `#1a1a20` | header, rails, panels                              |
| `bg2`        | `#22222a` | buttons (idle), inset wells                        |
| `bg3`        | `#2a2a33` | hover / selected row                               |
| `bg4`        | `#33333e` | deepest fills (rarely used)                        |
| `line`       | `#2a2a33` | 1px dividers                                       |
| `line2`      | `#3a3a46` | 1px borders on buttons / emphasized dividers      |
| `ink`        | `#f5f5f0` | primary text (warm off-white)                      |
| `ink2`       | `#a8a8b0` | secondary text                                     |
| `ink3`       | `#6a6a78` | tertiary / meta / monospace captions               |
| `accent`     | `#d97757` | playhead, primary CTAs, active tab underline       |
| `accentInk`  | `#000`    | text on accent                                     |
| `ok`         | `#4ade80` | confirmations ("● connected", "themed")            |
| `warn`       | `#f5a623` | "analyzed", mid confidence                          |
| `err`        | `#d43a2f` | destructive / kick-track                            |

### Colors — Light

| Token   | Hex       |
|---------|-----------|
| `bg0`   | `#f4f4ef` |
| `bg1`   | `#ffffff` |
| `bg2`   | `#ececec` |
| `bg3`   | `#dcdcd4` |
| `bg4`   | `#cac8bf` |
| `line`  | `#dcdcd4` |
| `line2` | `#c4c4bc` |
| `ink`   | `#1a1a20` |
| `ink2`  | `#555560` |
| `ink3`  | `#8a8a90` |
| `accent`| `#d97757` |
| `ok`    | `#2f8f3e` |
| `warn`  | `#b8881a` |
| `err`   | `#c42818` |

### Typography

- **Sans** — Inter (400/500/600/700/800). Body, titles, section labels.
- **Mono** — JetBrains Mono (400/500/600/700). Everything meta: timecodes,
  status bar, micro‑caps labels, parameter values, keyboard hints.

Both are Google Fonts and already preloaded in `Prototype.html`.

**Type scale used:**

| Use                        | Size | Weight | Font  | Tracking     | Transform |
|----------------------------|------|--------|-------|--------------|-----------|
| Screen title / song title  | 20px | 600    | sans  | -0.3px       | —         |
| Section name               | 18px | 600    | sans  | -0.2px       | —         |
| Now‑time (big)             | 22px | 600    | mono  | -0.3px       | tabular‑nums |
| Body                       | 13px | 600    | sans  | -0.1px       | —         |
| Default UI                 | 12px | 400    | sans  | —            | —         |
| Button (primary)           | 11px | 600    | mono  | 0.6px        | lowercase |
| Button (secondary)         | 11px | 400    | mono  | —            | lowercase |
| Micro‑caps label           | 10px | 400    | mono  | 1.0px        | UPPERCASE |
| Status bar                 | 10px | 400    | mono  | —            | —         |
| Tiny meta (track counts)   | 9px  | 400    | mono  | 0.5px        | —         |

All tracking/weight values are load-bearing. `font-variant-numeric:
tabular-nums` is required anywhere a timecode updates during playback.

### Spacing

No 8pt grid — this is a **4px grid** matching DAW conventions.

- Row height library item: 32px
- Row height algorithm track: 28px
- Ruler height: 22px
- Status bar height: 22px
- Tool strip height: 32px
- Header height: 40px
- Transport bar height: 44px
- Waveform pane height: 120px
- Inspector width: 300px
- Library rail width: 220px
- Tweaks panel: 280px, pinned bottom-right at `right: 16, bottom: 32`

### Borders & Corners

- Everything is **1px solid `line` or `line2`**. No elevated shadows in the
  main chrome. One exception: the Tweaks panel uses
  `box-shadow: 0 12px 32px rgba(0,0,0,0.5)`.
- **No border-radius on anything in the app body.** Sharp corners are the
  look. The only rounded elements are:
  - macOS traffic-light dots (pill).
  - The library thumbnail square (2px radius).
  - The playhead dot on the scrubber (2px radius).
  - The ::-webkit-scrollbar-thumb (4px radius).

### Glyphs

Plain unicode, no icon font:

- Play / pause: `▶` / `❚❚`
- Transport: `⏮ ◀ ◀◀ ▶▶ ⏭`
- Section kind: `○` intro, `▮` verse, `▲` chorus, `◆` solo, `◈` bridge, `◌` outro
- Status: `●` on / `○` off
- Misc: `◐` tweaks, `✎` edit, `⇤` jump, `⇧` shift, `⌘` cmd, `◀▶` nudge

Do not replace these with an icon font or SVGs unless the target platform
can't render them.

---

## App Chrome (every screen)

File: [`prototype/shell.jsx`](./prototype/shell.jsx)

Every screen renders inside `<Chrome inspector={...} statusExtra={...}>` which
lays out:

```
┌─ Header (40px) ─────────────────────────────────────────┐
│ ● ● ●   X—ONSET │ project / Halloween 2026    … [tweaks] CPU 12% │ xLights 2024.22 │ ● connected │
├─ Tool strip (32px) ─────────────────────────────────────┤
│ LIB  DROP  ANALYZE  TIMELINE  THEME  EXPORT │ undo redo snap … inspector │
├─ Library rail ──┬─ Main ────────────────────┬─ Inspector ┤
│ 220px           │ (screen content)          │ 300px      │
│                 │                           │ (optional) │
│                 ├───────────────────────────┤            │
│                 │ Status bar (22px)         │            │
└─────────────────┴───────────────────────────┴────────────┘
```

### Header (40px)

- macOS-style traffic lights (decorative on non-macOS) — 11px diameter,
  6px gap, `#ff5f57 / #febc2e / #28c840`.
- Wordmark `X—ONSET`, mono 11px, 600, `letter-spacing: 1`, color `ink2`.
- `|` 1px divider, then project path `project / Halloween 2026` in mono
  11px `ink3`.
- Flex spacer.
- **Tweaks toggle** — button, 4px 10px padding, mono 10px, transparent bg
  when off with `line2` border; `accent` fill + `accentInk` text when on.
- Meta trio separated by `line` 1px verticals, each 4px 10px: `CPU 12%`,
  `xLights 2024.22`, `● connected` (green).

### Tool strip (32px)

Flat button row with bottom-border-activated tabs. Left-aligned tabs:
`LIB DROP ANALYZE TIMELINE THEME EXPORT`. Each tab: 12px horizontal padding,
mono 11px, `ink3` idle → `ink` active. Active has a **2px `accent`
bottom-border**; inactive has `2px solid transparent` (so nothing shifts).

Right side is a faux toolbar — decorative labels `undo · redo · snap ·
grid: 1/4 · zoom · fit` then an actual `▸ inspector` toggle.

### Library rail (220px)

- Section header `LIBRARY · 8` in micro‑caps.
- Collapsible folder headers `▾ HALLOWEEN 2026` / `▸ CHRISTMAS 2025`.
- Song row: 22×22 thumbnail (`bg2` square, `♪` glyph), title (12px sans),
  artist · duration (10px mono `ink3`), status chip (9px mono, color by
  status: `themed` → ok green, `analyzed` → warn orange, `draft` → `ink3`).
- Active song row: `bg3` fill, **2px left-border in `accent`** (inactive rows
  have 2px transparent left-border to prevent shift).
- Bottom dashed-border button `+ drop mp3` — opens the DROP screen.

### Status bar (22px)

Mono 10px `ink3`, 14px gap:
- Playing state + current time: `● playing · 0:52.412` (accent when playing)
  or `○ paused · …` (ink3).
- `statusExtra` slot — screen-specific context.
- Right-aligned meta: `103 BPM`, `4 / 4`, `A major`, `44.1 kHz · 16-bit`, `v0.4.1`.

### Tweaks panel

Floating 280px panel at bottom-right. Title row `TWEAKS` in micro-caps plus
`×` close button. Sections:

- **APPEARANCE** — segmented two-up buttons: `dark | light`.
- **DENSITY** — segmented: `compact | comfortable`.
- **INSPECTOR** — toggle between `● visible` and `○ hidden`.
- **keyboard** — key hint list: `space · play/pause`, `← →  · nudge 1s`,
  `⇧← ⇧→ · jump section`, `1-6 · switch screens`.

Active segmented pill uses `accent` background with `accentInk` text; idle
segments use `bg2` background with `ink2` text.

---

## Screens

### 1. LIBRARY — `other-screens.jsx`

Purpose: triage songs by status, pick one to work on.

Main pane:
- Big title `Library`.
- Grid of song cards, each showing artwork placeholder, title/artist,
  duration, and a `themed|analyzed|draft` status chip.
- Filter pills: `all | themed | analyzed | draft`.

Entering a song takes you to whichever screen matches its status.

### 2. DROP — `other-screens.jsx`

Purpose: import a new mp3.

Main pane:
- A single centered drop target: dashed `line2` border, mono 11px text
  `drop mp3 here · or click to browse`. Hover state fills bg to `bg2`.
- Below: supported formats (`mp3 · wav · flac · aiff`), max size note.
- Once a file is dropped, auto-advance to ANALYZE.

### 3. ANALYZE — `analyze-screen.jsx`

Purpose: show the long-running analysis pipeline, per detector, with a
progress bar + a live log.

Main pane:
- Top: big progress readout (`37%`, mono 48px) + ETA (`~12s remaining`).
- Stepped list of detectors (each row):
  - ● status dot (ok / running pulsing / queued)
  - Algorithm name (mono 12px)
  - Library name, tiny `ink3`
  - Right-aligned: `done`, `0.83 conf`, or a spinner.
- Below: live log pane (mono 11px, `bg1`, one line per event).
- CTA in bottom-right: **`review timeline →`** (disabled until 100%).

### 4. TIMELINE — `timeline.jsx`

Purpose: review the detected beat grid + sections, scrub, nudge, toggle raw
detector tracks on/off, optionally enter **sections edit mode** for
restructuring.

Main pane, top-to-bottom:
1. **Transport bar (44px)** — song title, BPM · key · duration, transport
   buttons (`⏮ ◀◀ ▶/❚❚ ▶▶ ⏭`), right-aligned big timecode
   (mono 20px tabular).
2. **Ruler (22px)** — every 20s tick with timestamp `0:20`, clickable to scrub.
   Playhead label reverses: `accent` background, `accentInk` text,
   mono 9px 600, fixed +6px pad.
3. **Editable section strip** — chips colored by assigned theme; see
   `sections-edit.jsx`. Click to select, double-click to seek+play.
4. **Live lights preview (40px)** — a horizontal strip of 72 cells
   rendering the current theme at the current playhead.
5. **Wave pane (120px)** — SVG waveform on a black canvas, with per-section
   colored background tints at 8% opacity, bar grid as 0.35 stroke `accent`
   lines at 30% opacity, and a 1.2px white playhead with a 3.5r dot on top.
   Drag to scrub.
6. **Raw algorithm tracks** — collapsible drawer. Each row (28px):
   - 220px sidebar: on/off ● button, color chip, algo name (mono 11px),
     event count.
   - Track canvas: vertical ticks per event, color-coded by detector. Live
     events (within ±0.15s of playhead while playing) flash white at full
     opacity.
   - Rows alternate `bg0` / `rgba(255,255,255,0.01)`.

Inspector (300px, right side):
- `PLAYHEAD` section with `NOW` big timecode (mono 22px), `bar N · beat N of 4`.
- `CURRENT SECTION` — theme swatch + name.
- `CONFIDENCE` — four bars (librosa_beats, qm_bars, energy impact, chord
  change) with value + colored progress bar (ok / warn).
- `LIGHTS OUT` — 32-cell preview + technical detail line.
- Footer buttons: `nudge -10ms` / `nudge +10ms`.

Sections edit mode swaps the inspector for the **`SectionsModePanel`**
(see `sections-edit.jsx`) and makes the section strip tall. In that mode
users can split, merge, delete, rename, promote ghost boundaries, or reset
to detected.

### 5. THEME — `theme-picker.jsx` (north star)

Purpose: pick one theme per section; this is where the user spends most of
their time.

Main pane, top-to-bottom:
1. **Header band** — song title (20px 600), meta (mono 11px `ink3`),
   right-aligned actions: `✎ edit sections`, `open in timeline →`,
   **`export ⌘E`** (primary — `accent` fill).
2. **Section strip** (horizontal-scroll) — one chip per section, width
   proportional to duration (min 90px). Each chip:
   - 6px gradient header bar from `theme.accent` → last swatch.
   - Row 1: zero-padded index `01`, kind-glyph + label, optional `▶` if
     playhead is inside.
   - Row 2: mono 9px time range + theme name.
   - Row 3: `<MiniLights>` at 12px tall.
   - Active (selected) chip: `bg3` bg + double border/outline in theme accent.
   - Currently-playing chip also gets a 2px accent strip on its bottom edge.
3. **Theme grid** — 6-column grid of theme cards (see next section).
4. **Live lights preview card** — 1px `line` bordered card on `bg1`, mono
   micro-caps header `LIVE LIGHTS · DRIVING PULSE · ON CHORUS 1`, 80px tall
   64-cell preview, legend of props underneath.
5. **Timeline strip** — compact transport + scrubber with colored section
   bands, visible section labels, hover-time readout.

Inspector (300px):
- `SECTION · 3 / 7` header.
- Big section label (18px 600) + time range.
- `DETECTED` block: 4 rows `kind / confidence / bars / beats`.
- `CURRENT THEME` block: accent swatch + name + description + 4 large
  swatch bars + a 30-cell `<LightsPreview compact>`.
- `PARAMETERS` block: 4 sliders (visual only): brightness / hit strength /
  dwell time / color shift — each a mono label + value + 3px filled bar in
  theme accent.
- Footer: `⇤ jump` (secondary) + `▶ preview` (primary, accent).

#### Theme card

Card sizing: auto-height in 6-col grid, 10px gap. Each card:

- Top: 48px tall swatch bar — 4 equal-flex colored strips, one per
  `theme.swatches[]` entry, no gaps.
- Body (padding `8px 10px 10px`):
  - Row 1: theme name (sans 13px 600, flex:1) + `● ASSIGNED` pill (mono 9px
    in theme.accent, only if active).
  - Row 2: description (sans 11px `ink3`, line-height 1.4, min-height 28px
    so cards stay aligned).
  - Row 3: `<MiniLights themeId kind height=18>` — rendered preview of how
    the theme would animate on a bar of this section's kind.
- Idle: `bg1` background, 1px `line` border.
- Active (assigned to current section): `bg3` background, 1px
  `theme.accent` border **plus** a second 1px `theme.accent` outline at
  `outline-offset: -2` (creates the double-stroke look).
- Hover: 120ms transition on background + border.

### 6. EXPORT — `export-screen.jsx`

Purpose: emit the final light show.

Main pane (two columns):
- Left: destination picker — xLights project, FSEQ file, xsq, CSV. Radio
  rows with mono 11px labels and one-line descriptions.
- Below: per-prop mapping table — prop name, LED count, pixel range,
  theme-driven colors. Disclosure to change prop mapping.
- Right: render preview — a scrubbable compact timeline + lights preview
  that animates an export of the whole song.
- Bottom CTA row: cancel (secondary) + **`render ⌘R`** (primary, accent).

Status bar `statusExtra` shows `output: <project> · 512 px · 45 fps`.

---

## Shared Components

### `<LightsPreview height cells compact label>`

File: `prototype/lights.jsx`. A horizontal strip of `cells` cells, each
filled per the current theme and playhead. The `compact` flag removes the
label bar; `label` overrides the default prop-name header.

### `<MiniLights themeId kind height>`

Small non-interactive preview for a theme card or chip — runs a
theme-specific deterministic animation for one bar worth of the given
section `kind`. Used inside the theme grid cards and section-strip chips.

### Live-ness

Both previews read `app.time`, `app.playing`, `app.energyPulse`, and
`app.curBeat` from the shared hook. When not playing, they render a
static frame representative of the theme at `t = 0` of a bar.

---

## Shared State

One hook, `useAppStateImpl()`, in
[`prototype/state.jsx`](./prototype/state.jsx). Port this to the target's
state library. Keys and their purpose:

| Key                       | Type      | Notes                                                |
|---------------------------|-----------|------------------------------------------------------|
| `screen`                  | string    | `library`/`drop`/`analyze`/`timeline`/`theme`/`export`. Persisted to localStorage key `xo.screen`. |
| `sections`                | Section[] | Editable; persisted to `xo.sections`.                |
| `detectedSections`        | Section[] | Immutable fallback from analysis; `resetSections()` restores this. |
| `altBoundaries`           | Boundary[]| "Ghost" alt cuts the analyzer found but didn't use.  |
| `sectionThemesById`       | {id→themeId}| Per-section theme; persisted to `xo.sectionThemesById`. |
| `sectionsMode`            | boolean   | If true, timeline enters sections edit mode.         |
| `selectedSection`         | number    | Index of section inspected in THEME screen.          |
| `playing`                 | boolean   | Audio playing.                                       |
| `time`                    | number    | Seconds. Driven by `requestAnimationFrame` while playing. Persisted ~2Hz to `xo.time`. |
| `algoStates`              | {id→bool} | Which detector tracks are visible.                   |
| `mode`                    | string    | `dark` or `light`.                                   |
| `density`                 | string    | `compact` or `comfortable`.                          |
| `inspectorOpen`           | boolean   | Right-rail visibility.                               |
| `tweaksOpen`              | boolean   | Floating tweaks panel.                               |
| `curSectionIdx`           | number    | Derived: which section contains `time`.              |
| `curBeat`                 | Beat      | Derived: most recent beat ≤ `time`.                  |
| `energyPulse`             | 0..1      | Decays ~8%/frame, snaps to 1 on each beat while playing. Use for "breathing" UI. |

### Audio driver

A single `Audio()` element is created once and stored in a ref. Playing
triggers a RAF loop that copies `audio.currentTime` into React state each
frame. Seeking updates both React state and `audio.currentTime`.

In production, replace the `Audio` element with a Web Audio graph so
analysis features (waveform, meters) can share buffers.

---

## Analysis Fixture (shape contract)

`assets/highway-data.js` sets `window.HIGHWAY` with this shape — the real
pipeline should emit the same JSON:

```ts
type Song = {
  title: string;
  artist: string;
  duration: number;         // seconds
  bpm: number;
  key: string;              // "A major"
  timeSignature: [4, 4];
  sections: Section[];
  beats:   { t: number; bar: number; beat: number; }[];
  bars:    number[];        // start times
  impacts: { t: number; conf: number; }[];
  drops:   { t: number; conf: number; }[];
  // plus optional: onsets, chords, bass, vocals
};
type Section = {
  start: number;
  end: number;
  kind: 'intro'|'verse'|'chorus'|'solo'|'bridge'|'outro';
  label: string;            // "Chorus 1"
  defaultTheme: string;     // theme id
};
```

---

## Interactions & Behavior

### Keyboard

- `space` — play/pause
- `←` / `→` — nudge `time` by ±1s
- `Shift+←` / `Shift+→` — jump to prev/next section boundary
- `1..6` — switch screen (library/drop/analyze/timeline/theme/export)
- On TIMELINE with sectionsMode on: `S` split at playhead, `M` merge with
  next, `Del` delete selected, `R` rename selected.

### Navigation

- `app.setScreen(id)` is the only router. No URLs in the prototype; in the
  real app wire this to react-router or the platform's navigation stack.

### Transitions

- Most UI is immediate. The two places with animation:
  - Tweaks panel slides in from bottom-right (120ms ease-out; prototype
    currently just appears — add the slide when porting).
  - Theme card selection has a 120ms transition on `background` + `border`.
- The playhead moves continuously via RAF while playing — no CSS transition
  on the playhead itself (that would introduce lag).

### Empty states

- Library empty — big dashed `+ drop mp3` target centered.
- Analyze failed — red row with `retry` action.
- Theme grid never empty (themes are built-in).

### Error/edge cases

- `splitSection` ignores splits within 0.5s of either boundary.
- `deleteSection` on the first section collapses its range into what was
  the second section; deleting the last section does the reverse. At least
  one section must always exist.
- Seek is clamped to `[0, duration]`.

---

## Assets

- **Fonts** — Inter + JetBrains Mono from Google Fonts. Either self-host
  the WOFF2s or keep the `<link>` tag.
- **Audio** — `assets/highway.mp3` is the sample song used by the
  prototype; replace with user-imported audio in production.
- **Analysis fixture** — `assets/highway-data.js`; in production, your
  analyzer produces this shape per imported song.
- **Traffic-light dots** — rendered as plain divs with hex colors.
- **Icons** — plain unicode glyphs (see *Glyphs* above). No icon font.

No illustrations or raster UI assets are used.

---

## Implementation Order Suggestion

1. Port **state** (`state.jsx`) and the **theme/palette** tokens first.
2. Build **`<Chrome>`** shell with header, tool strip, library rail, status
   bar — no screens yet, just the skeleton + dark/light toggle via Tweaks.
3. Port **`<LightsPreview>`** + **`<MiniLights>`** — they're reused across
   every screen.
4. Build **TIMELINE** (most complex; proves waveform, ruler, transport, raw
   tracks).
5. Build **THEME** screen on top of the shared components.
6. Fill in **ANALYZE**, **EXPORT**, **LIBRARY**, **DROP** (straightforward
   once the vocabulary is in place).
7. Wire real audio analysis sidecar matching the `HIGHWAY` fixture shape.
8. Wire real export to xLights/FSEQ/xsq.

---

## Questions For The PM/Designer

When implementing, you'll likely need clarification on:

- The real themes beyond the six built-in (is this user-extensible? Can a
  user create a theme from within the app, or are themes code-defined?).
- Whether section edits should be undoable (prototype has no undo stack).
- Whether the desktop target is Electron or native (affects xLights IPC).
- Whether there's a cloud/sync component (prototype is all localStorage).
- The exact xLights export schema — prototype's export screen is visual
  only.
