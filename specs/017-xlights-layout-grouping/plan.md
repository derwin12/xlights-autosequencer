# Implementation Plan: xLights Layout Grouping

**Branch**: `017-xlights-layout-grouping` | **Date**: 2026-03-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/017-xlights-layout-grouping/spec.md`

## Summary

Parse any `xlights_rgbeffects.xml` layout, normalize prop coordinates, classify props by geometry and density, and generate hierarchical "Power Groups" (8 tiers) compatible with the xLights sequence editor. Output is injected back into the XML file. A `--profile` option filters which tiers to generate. A `--dry-run` flag previews output without writing. Supports `--hero` for explicit hero designation and `--no-auto-heroes` to disable pixel-outlier detection. Uses stdlib `xml.etree.ElementTree` — no new dependencies.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: `xml.etree.ElementTree` (stdlib), `click` 8+ (existing)
**Storage**: `xlights_rgbeffects.xml` — read and rewritten in-place (backup optional)
**Testing**: pytest (existing)
**Target Platform**: macOS (developer workstation)
**Project Type**: CLI tool (new subcommand added to existing `xlight-analyze` CLI)
**Performance Goals**: Complete in under 5 seconds for any residential layout (< 500 props)
**Constraints**: No new runtime dependencies; output XML must load in xLights without errors
**Scale/Scope**: Typical residential display: 10–100 props; largest holiday shows: ~500 props

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*
**Constitution version**: 1.0.0

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Audio-First Pipeline | ✅ Pass | Layout grouping is a *pre-sequencing* setup step, not part of the audio analysis pipeline. It does not produce timing data, so the audio-first constraint does not apply. |
| II. xLights Compatibility | ✅ Pass | Output is `<ModelGroup>` elements injected into `xlights_rgbeffects.xml`, the native xLights layout format. Group names use only alphanumeric/underscore/hyphen characters. |
| III. Modular Pipeline | ✅ Pass | New `src/grouper/` module is independently testable with no coupling to the audio analysis pipeline. Communicates via `Layout` / `PowerGroup` data structures. |
| IV. Test-First Development | ✅ Pass | Tests written before implementation (Red-Green-Refactor). Fixture XML files included in test suite. |
| V. Simplicity First | ✅ Pass | No speculative abstraction. Stdlib XML only. Single new CLI command. No new dependencies. |

**Post-Design Re-check**: ✅ All gates still pass after Phase 1 design.

## Project Structure

### Documentation (this feature)

```text
specs/017-xlights-layout-grouping/
├── plan.md              # This file
├── research.md          # Phase 0 — xLights XML format, coordinate decisions
├── data-model.md        # Phase 1 — Prop, PowerGroup, Layout, ShowProfile entities
├── quickstart.md        # Phase 1 — end-user usage guide
├── contracts/
│   └── cli-contract.md  # CLI signature, exit codes, output format, XML contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code

```text
src/
└── grouper/
    ├── __init__.py          # Package marker
    ├── layout.py            # parse_layout() → Layout
    ├── classifier.py        # normalize_coords(), classify_props(), detect_heroes()
    ├── grouper.py           # generate_groups(props, profile) → list[PowerGroup]
    └── writer.py            # inject_groups(raw_tree, groups) → ET.ElementTree; write_layout()

src/cli.py                   # Add group_layout_cmd (@cli.command("group-layout"))

tests/
├── fixtures/
│   └── grouper/
│       ├── simple_layout.xml          # 8 props, varied positions
│       ├── hero_layout.xml            # includes SingingFace with subModels
│       └── minimal_layout.xml         # 1 prop edge case
├── unit/
│   ├── test_grouper_layout.py         # parse_layout, write_layout
│   ├── test_grouper_classifier.py     # normalize, aspect ratio, hero detection
│   ├── test_grouper_groups.py         # beat groups, spatial bins, profiles
│   └── test_grouper_writer.py         # inject/remove groups in XML tree
└── integration/
    └── test_grouper_integration.py    # full round-trip: XML in → XML out, load validation
```

**Structure Decision**: New `src/grouper/` module alongside existing `src/analyzer/`. Four focused files keep each concern testable in isolation (Constitution III). No shared state with the audio pipeline.

## Complexity Tracking

> No constitution violations. No entries required.

---

## Implementation Notes

### XML Round-Trip Strategy
- Parse with `ET.parse(path)` → preserve all existing elements/attributes/ordering
- Remove auto-groups: iterate `root.findall("ModelGroup")`, remove those whose `name` starts with any auto prefix
- Append new `<ModelGroup>` elements at end of root
- Write back with `ET.indent()` + `ET.ElementTree.write()` (same pattern as `src/analyzer/xtiming.py`)

### Coordinate Edge Cases
- If `x_max == x_min` (all props at same X): normalize all to 0.5 (center bin)
- If `y_max == y_min`: normalize all to 0.5 (mid bin)
- Missing `WorldPosX`/`WorldPosY`: treat as 0.0

### Beat Group Remainder Handling
- If `len(props) % 4 != 0`: last group gets 1–3 props — still created, not discarded
- Both LR and CO algorithms applied independently; they produce different groupings over the same prop set

### Hero Detection Keywords
- Name contains (case-insensitive): `"face"`, `"megatree"`, `"mega_tree"`, `"mega tree"`, `"tree"`
- Each detected hero prop becomes one `08_HERO_<PropName>` group containing its sub-models
- If a hero prop has no sub-models, it is placed alone in the hero group

### Backup Strategy (implementation decision)
- Write to `<source>.bak` before overwriting, only when not using `--output`
- Silently skip backup if `.bak` already exists (idempotent re-runs)
