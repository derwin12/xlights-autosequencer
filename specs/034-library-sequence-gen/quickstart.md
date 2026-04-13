# Quickstart: Song Library Sequence Generation

**Feature**: 034-library-sequence-gen
**Purpose**: Integration test scenarios and dependency chain

---

## Prerequisites

1. xLights layout XML with props (`xlights_rgbeffects.xml`)
2. At least one analyzed song in the library (`~/.xlight/library.json`)
3. Grouper configuration saved (writes layout path to `~/.xlight/settings.json`)
4. Running review server

---

## Dependency Chain

```
LibraryEntry.source_file (MP3)
  └── hierarchy analysis → *_hierarchy.json (existing)
        └── GenerationConfig(audio_path, layout_path, genre, occasion, transition_mode)
              └── generate_sequence(config) → .xsq file
                    └── send_file() → browser download
```

```
~/.xlight/settings.json (layout_path)
  └── parse_layout(layout_path) → props
        └── generate_groups(props, edits) → PowerGroup[]
              └── build_plan(config, hierarchy, props, groups, ...) → SequencePlan
                    └── write_xsq(plan, output_path)
```

---

## Integration Test Scenarios

### Scenario 1: Happy Path (P1 — Core Generation)

```
Given:
  - settings.json has layout_path set
  - Library has a song with analysis complete

Steps:
  1. Open /library → click song → flyout opens
  2. Click "Generate" tab
  3. Confirm genre/occasion pre-populated from song metadata
  4. Click "Generate Sequence"
  5. UI shows spinner, Generate button disabled
  6. Poll /generate/<hash>/status until status == "complete"
  7. .xsq download begins automatically

Expected: Valid .xsq file downloaded, no terminal involved
```

### Scenario 2: No Layout Configured (FR-003)

```
Given:
  - settings.json missing or layout_path is null

Steps:
  1. Open song detail → Generate tab

Expected:
  - Generate button disabled
  - Message: "No layout groups configured"
  - Link to /grouper
```

### Scenario 3: Unanalyzed Song (FR-002)

```
Given:
  - Library entry exists but analysis_path file is missing

Steps:
  1. Open song detail → Generate tab

Expected:
  - Generate section shows "Analysis required" message
  - Generate button is absent or disabled
```

### Scenario 4: Generation Failure (FR-008)

```
Given:
  - layout_path set but points to invalid/missing XML

Steps:
  1. Click Generate
  2. POST /generate/<hash> returns 202
  3. Status polling reaches status == "failed"

Expected:
  - User sees human-readable error (not raw traceback)
  - No raw Python exception exposed to UI
```

### Scenario 5: Re-download History (P3 — FR-010)

```
Given:
  - Generation completed earlier in this session (job_id in _jobs)

Steps:
  1. Reopen song detail → Generate tab
  2. History section shows prior generation with timestamp
  3. Click re-download link

Expected:
  - GET /generate/<hash>/download/<job_id> returns the same .xsq
```

---

## Test Fixtures Needed

- `tests/fixtures/generate/mock_layout.xml` — minimal xLights layout XML with 2+ props
- `tests/fixtures/generate/mock_settings.json` — `{"layout_path": "<fixture-path>"}`
- Reuse existing hierarchy fixture from `tests/fixtures/` for the song input
