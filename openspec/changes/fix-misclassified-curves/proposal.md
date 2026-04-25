## Why

`docs/musical-analysis-design.md §2` ("Algorithms We're Using Wrong") identified
in March 2026 that two analyzer algorithms produce frame-level continuous values
but were registered as timing-mark types, which caused their output to be
silently dropped by every downstream consumer:

- `NNLSChromaAlgorithm` (`element_type="harmonic"`) — produces a 12-bin chroma
  vector per frame; consumers that read `harmonic` tracks expect discrete
  chord-change events (which Chordino correctly produces).
- `BBCRhythmAlgorithm` (`element_type="onset"`) — produces a frame-level rhythm
  strength curve; consumers that read `onset` tracks expect discrete event
  timestamps.

A partial fix shipped (3 of 4 BBC variants — `bbc_energy`, `bbc_spectral_flux`,
`bbc_peaks` — were correctly reclassified to `value_curve`), but `bbc_rhythm`
and `nnls_chroma` were left misclassified. Their wall-clock cost is paid on
every analysis run while their output goes nowhere.

Fixing this gives us two latent quality signals: (1) a continuous chroma curve
suitable for chord-aware effect parameter modulation in `effect_placer.py`,
and (2) a second rhythm-strength curve that cross-confirms `bbc_energy` and
can smooth its noise.

## What Changes

- Reclassify `NNLSChromaAlgorithm.element_type` from `harmonic` to `value_curve`
  and emit its per-frame chroma vector through a new `TimingTrack.values`
  payload (frame-level data, not timing marks).
- Reclassify `BBCRhythmAlgorithm.element_type` from `onset` to `value_curve`
  and emit its per-frame rhythm strength via the same payload.
- Extend `HierarchyResult` with a `chroma_curve` field (per-frame chroma) and
  store `bbc_rhythm` alongside the existing energy curves in
  `HierarchyResult.energy_curves` (under a distinct stem-key suffix to keep
  `bbc_energy` separate).
- Wire one initial consumer per signal:
  - **BBC Rhythm**: in the orchestrator's L5 energy assembly, produce a
    smoothed energy curve when both `bbc_energy` and `bbc_rhythm` are
    available (mean of the two, frame-aligned).
  - **NNLS Chroma**: extend `src/generator/chord_colors.py` (or a sibling
    module) with a `chord_color_for_time(t_ms)` helper that consults the
    chroma curve when Chordino has no chord at that timestamp; this gives
    `effect_placer.py` finer-grained color modulation between chord events.
- Update analyzer baseline (`tests/golden/analyzer/baseline.json`) for the
  new track shapes and new `chroma_curve` field.
- Update `docs/musical-analysis-design.md §2` to mark the misclassification
  as resolved (small doc-only diff bundled in the same PR).

**Out of scope (tracked separately):**

- Refactoring the existing Chordino → `chord_colors.py` consumer
- Deleting any other algorithm (HPSS, frequency-band onsets, pitch trackers)
- Operationalizing per-section agreement scores (the revised Proposal 2)
- Reconciling the rest of `docs/musical-analysis-design.md` against
  post-April-2026 architecture

## Capabilities

### New Capabilities

- `analyzer-value-curves`: Defines the contract for analyzer algorithms that
  produce frame-level continuous values rather than discrete timing marks —
  the `value_curve` element type, its `TimingTrack.values` payload shape,
  the `HierarchyResult` fields it populates (`energy_curves`, `chroma_curve`),
  and the rule that no curve algorithm may be registered with a timing-mark
  element type.

### Modified Capabilities

<!-- No existing specs at openspec/specs/ govern analyzer element-type
     classification or curve emission, so no delta files are required. -->

## Impact

**Code changes:**

- `src/analyzer/algorithms/vamp_harmony.py` — `NNLSChromaAlgorithm`
  reclassification + frame collection rewrite
- `src/analyzer/algorithms/vamp_bbc.py` — `BBCRhythmAlgorithm`
  reclassification (line 127 area)
- `src/analyzer/result.py` — `TimingTrack.values: list[list[float]] | None`
  field for per-frame multi-dim payload (chroma); already supports scalar
  curves via existing `marks` semantics for `value_curve`
- `src/analyzer/orchestrator.py` — L5 energy assembly: read `bbc_rhythm`
  when present, emit smoothed curve; new L6 path: populate
  `HierarchyResult.chroma_curve`
- `src/generator/chord_colors.py` (or sibling) — chroma-aware color
  fallback consumer
- `tests/golden/analyzer/baseline.json` — re-snapshot after reclassification
- `src/evaluation/analyzer_baseline.py` — add tolerance entry for
  `chroma_curve` if not already covered by the curve-algorithm path
- `docs/musical-analysis-design.md` §2 — mark resolved

**Shared modules touched:** `src/analyzer/` (86 importers), `src/generator/`
(44 importers). Full Design-First Gate applies; regression surface listed
in `design.md`.

**No new dependencies.**

**Backward compatibility:** Pre-change, `nnls_chroma` and `bbc_rhythm` tracks
appear in `AnalysisResult` with `element_type` matching their old values and
typically empty `marks` (the misclassification caused frames to be discarded
during conversion). Post-change, the same algorithm names exist with
`element_type="value_curve"` and populated `values`. No external consumers
read these tracks today (verified by grep across `src/generator/`,
`src/story/`, `src/themes/`, `src/effects/`, `src/review/`), so the schema
change is observable only in the JSON snapshot. Baseline regeneration
captures it.
