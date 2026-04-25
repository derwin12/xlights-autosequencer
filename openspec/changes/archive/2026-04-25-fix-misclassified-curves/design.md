## Context

The repo's analyzer infrastructure already supports value-curve algorithms:
`src/analyzer/result.py:413-446` defines `ValueCurve` (scalar 0–100 per frame),
`TimingTrack.value_curve: Optional[ValueCurve]` is the field algorithms attach
their curve to, and `src/analyzer/orchestrator.py:472-479` reads `bbc_energy`
tracks and populates `HierarchyResult.energy_curves: dict[str, ValueCurve]`
keyed by stem. `bbc_energy`, `bbc_spectral_flux`, and `bbc_peaks` already
follow this pattern (`src/analyzer/algorithms/vamp_bbc.py:46,73,100`).

Two algorithms still violate the contract:

- **`BBCRhythmAlgorithm`** (`vamp_bbc.py:127`) — `element_type="onset"`. The
  vamp output is a per-frame strength vector (same shape as the other BBC
  curves), but the wrapper converts it to discrete `TimingMark` instances
  rather than attaching a `ValueCurve`. Downstream consumers that read
  `onset` tracks expect timing events; the rhythm output gets dropped.
- **`NNLSChromaAlgorithm`** (`vamp_harmony.py:45`) — `element_type="harmonic"`.
  The vamp output is a per-frame 12-bin chroma vector (one value per pitch
  class). The wrapper currently extracts only `frame["timestamp"]` from each
  frame and discards `frame["values"]` (the 12-bin vector). Even if we kept
  the values, no infrastructure exists to carry multi-dimensional per-frame
  payloads — `ValueCurve.values` is `list[int]` (scalar).

`docs/musical-analysis-design.md §2` ("Algorithms We're Using Wrong") flagged
both of these in March 2026. The BBC fix landed for 3 of 4 wrappers; this
change finishes the work and adds the multi-dim payload support that NNLS
needs.

## Goals / Non-Goals

**Goals:**

- Reclassify both algorithms to `element_type="value_curve"` so their output
  isn't shape-mismatched with their consumers.
- Add multi-dimensional curve support (`ChromaCurve`) without breaking the
  existing scalar `ValueCurve` contract.
- Wire one consumer per signal — proving the reclassification produces
  reachable output, not just shape-correct dead code:
  - `bbc_rhythm` cross-confirms `bbc_energy` via per-frame mean, smoothing
    `HierarchyResult.energy_curves[stem]`.
  - `nnls_chroma` populates `HierarchyResult.chroma_curve` and
    `effect_placer.py` consults it for color modulation between Chordino
    chord events.
- Update `tests/golden/analyzer/baseline.json` to match the new shape.
- Mark the misclassification resolved in `docs/musical-analysis-design.md §2`.

**Non-Goals:**

- Refactoring the existing Chordino → `chord_colors.py` consumer (it stays
  unchanged; the chroma curve is added as an *additional* signal, not a
  replacement).
- Touching any other algorithm's classification (HPSS, frequency-band onsets,
  pitch trackers — separate changes).
- Operationalizing per-section agreement scores from PR #81 (the revised
  Proposal 2; tracked separately).
- Reconciling the rest of `docs/musical-analysis-design.md` against
  post-April-2026 architecture (separate doc-only chore).
- Performance optimization. Both algorithms already run; this only affects
  what happens to their output. Wall-clock impact: negligible (we're
  *retaining* data we currently discard, plus computing one mean curve).

## Decisions

### D1. New `ChromaCurve` dataclass, not extension of `ValueCurve`

`ValueCurve.values: list[int]` is `list[int]`, scalar-per-frame. NNLS Chroma
emits 12 floats per frame (one per pitch class). Three options were
considered:

- **(A) Extend `ValueCurve`** with `multi_values: Optional[list[list[int]]]`.
  Rejected: makes the dataclass dual-shaped, every consumer must check which
  field is populated, and serialization grows ambiguous.
- **(B) Decompose into 12 separate `ValueCurve`s**, one per pitch class.
  Rejected: 12 curves keyed by `"chroma_C"`, `"chroma_C#"`, … pollutes
  `energy_curves` with non-energy data and forces consumers to recombine
  the 12-vector at every read.
- **(C) New `ChromaCurve` dataclass** mirroring `ValueCurve` but with
  `values: list[list[int]]` (12-dim normalized 0–100 per frame). Selected.
  Clean separation, matches the actual data shape, parallel to how
  `spectral_flux` lives as its own field next to `energy_curves`.

`HierarchyResult` gains one new optional field:
`chroma_curve: Optional[ChromaCurve] = None`.

### D2. `bbc_rhythm` consumer: in-place smoothing of `energy_curves[stem]`

Two consumer designs were considered:

- **(A)** Add `rhythm_curves: dict[str, ValueCurve]` to `HierarchyResult` —
  preserves both raw signals separately. Rejected as scope creep: the
  proposal commits to *one* consumer per signal, and a new field with no
  reader downstream is the same dead-output problem we're fixing.
- **(B) Smooth `bbc_energy` against `bbc_rhythm` per-frame**, store the
  result in `energy_curves[stem]`. Selected. The smoothed signal is the
  product the consumer (L0 impacts/drops/gaps detection, L4 event filtering)
  already reads — we're improving its quality, not adding a parallel signal.
  Reproducibility preserved by storing both raw curves on the
  `AnalysisResult` JSON snapshot (where each algorithm's `value_curve` is
  already serialized) so anyone can re-derive.

Smoothing function: per-frame `int(round((energy[i] + rhythm[i]) / 2))`,
frame-aligned. If frame counts differ, truncate to the shorter of the two
(both come from the same audio at the same fps so this should not happen
in practice; the truncation is a defensive guard).

If `bbc_rhythm` is unavailable on a stem (e.g., plugin missing), fall back
to `bbc_energy` unchanged. No exception, no warning loop — just the
existing curve.

### D3. `nnls_chroma` consumer: chord-color fallback in `effect_placer.py`

Today, `effect_placer.py` reads Chordino chord-change events via
`chord_colors.py` to map chord → color. Between two chord events, color is
held constant. With `chroma_curve` available, the placer can interpolate
color along the curve when the gap between chord events exceeds a threshold
(e.g. > 4 seconds), giving slow harmonic drift instead of step changes.

The new helper lives next to the existing chord-color logic
(`src/generator/chord_colors.py` or sibling module — exact placement
deferred to implementation). API shape:

```python
def chord_color_for_time(
    t_ms: int,
    chords: list[TimingMark],          # Chordino chord events (existing)
    chroma_curve: Optional[ChromaCurve], # new
) -> Tuple[int, int, int]:
    """Return RGB. Falls back to chroma-derived color when no Chordino
    event covers t_ms (or the gap exceeds 4 s)."""
```

Chordino remains primary. Chroma is a **fallback / interpolation**, never an
override. This keeps `chord_colors.py` deterministic for songs where
Chordino confidently tracks chords throughout.

### D4. Baseline regeneration is part of this change

`tests/golden/analyzer/baseline.json` will record the new track shapes
(`element_type="value_curve"` for both, `chroma_curve` field present in
`HierarchyResult`). Re-snapshotting is mandatory — the gate fails on shape
mismatch. The regenerated baseline lands in the same PR.

### D5. Doc reconciliation: §2-only, scoped

`docs/musical-analysis-design.md §2` will get a 1–2 paragraph update marking
the misclassification resolved with a back-reference to this change.
Reconciling §5 (the obsolete "drop ensemble" decision) and the rest of the
doc against post-April-2026 architecture is **explicitly out of scope** —
that's a larger doc-only PR with its own review.

## Risks / Trade-offs

**[R1] Baseline regeneration is expensive (~10 min wall) and noisy in diffs.**
→ Mitigation: regenerate once at the end of implementation, after the code
is stable. Re-snapshot only if behavior changes again. The gate's
`skip_check` flag (already in `src/evaluation/analyzer_baseline.py`) covers
qm_segments / segmentino non-determinism but not curve shapes; the
regenerated baseline must be deterministic across runs of the same fixture.
Verified by running it twice locally before committing.

**[R2] `chroma_curve` is multi-dim, ~12× the storage of a scalar curve.**
→ Mitigation: store as `list[list[int]]` with 0–100 normalization (1 byte
per value as JSON int), not floats. For a 4-minute song at 20 fps × 12
classes that's ~57 KB per fixture × 4 fixtures = ~230 KB to the baseline.
Acceptable.

**[R3] Smoothing `bbc_energy` against `bbc_rhythm` could shift downstream
L0 impacts/drops/gaps thresholds.**
→ Mitigation: the L0 thresholds in `orchestrator.py` are tuned against the
current (unsmoothed) `bbc_energy`. After the change, run the gate on the
CC0 corpus and confirm impact/drop counts stay within tolerance; tune
thresholds if not. **This is the test that catches whether this change is a
quality win or a regression** — if smoothed `bbc_energy` produces noticeably
different L0 outcomes on the corpus, we either accept the new outcomes (and
re-snapshot the baseline) or weight the smoothing differently. Decision
deferred to implementation evidence.

**[R4] Consumer in `effect_placer.py` is the first downstream reader of
`chroma_curve` — consumer is untested in production.**
→ Mitigation: keep Chordino as primary; chroma is fallback only. If chroma
produces wrong colors, the worst case is that gaps between chord events
look *different*, not wrong — Chordino-covered moments are unaffected.

**[R5] Shared module change: `src/analyzer/` has 86 importers,
`src/generator/` has 44.**
→ Mitigation: the regression surface section below enumerates every public
symbol modified and grep-confirms callers. Per CLAUDE.md Design-First Gate.

## Regression surface

Per CLAUDE.md "Design-First Gate" — every public symbol modified, with
caller status:

- **`NNLSChromaAlgorithm.element_type`** — class attribute. Read by:
  - `src/analyzer/orchestrator.py` (filtering/routing by element_type) — must
    be updated to route value_curve algorithms to the curve-collection path
  - `src/analyzer/scorer.py` (per-element-type scoring families)
  - `tests/golden/analyzer/baseline.json` (snapshot includes element_type
    per track)
  Verified by `grep -rn 'element_type' src/`.

- **`BBCRhythmAlgorithm.element_type`** — same callers as above.

- **`NNLSChromaAlgorithm._run`** — output shape changes from
  `TimingTrack(marks=[...])` to `TimingTrack(marks=[], value_curve=ChromaCurve(...))`.
  No external caller invokes `_run` directly outside the analyzer runner;
  `grep -rn 'NNLSChromaAlgorithm' src/ tests/` confirms only internal use
  (sweep matrix, runner, tests).

- **`BBCRhythmAlgorithm._run`** — same.

- **`HierarchyResult` fields** — new optional `chroma_curve` field. Strictly
  additive; existing field readers unaffected. JSON serialization adds a key.

- **`TimingTrack.value_curve`** — field type changes from
  `Optional[ValueCurve]` to `Optional[ValueCurve | ChromaCurve]`. Existing
  callers (BBC variants, orchestrator's `_get_value_curve`) only handle
  `ValueCurve`; we add a parallel `_get_chroma_curve` and route by
  `element_type` to avoid type narrowing surprises. The base class union is
  benign because no existing call site `isinstance(track.value_curve, ValueCurve)`-checks.

- **`docs/musical-analysis-design.md`** — §2 doc-only edit.

## Historical echoes

`grep` of `.wolf/buglog.json` for `nnls_chroma`, `bbc_rhythm`, `chroma`,
`element_type`, `value_curve`:

- **bug-139** — *"Wrong reference: TimingTrack should be TimingMark"* in
  `src/analyzer/algorithms/vamp_harmony.py`. This was the NameError fix
  (PR #100, 2026-04-25) that made `NNLSChromaAlgorithm._run` actually run
  to completion. Direct precursor — the algorithm only started producing
  output at all on the day before this proposal was written. Without that
  fix, this change would have nothing to reclassify.
- No other matches.

`.wolf/cerebrum.md` Do-Not-Repeat:
- 2026-04-25 entries on test-isolation conventions and quarantine pairing
  apply to *how* this change is verified (re-snapshot is the test, not
  xfail/skip).
- 2026-04-19 "shipped changes that broke previously-working behavior because
  modified public symbols weren't audited for callers" — applies directly
  to the `element_type` change. Caller audit captured in Regression
  surface above.

## Migration Plan

Pure code change, no live data migration. Steps:

1. Add `ChromaCurve` dataclass to `src/analyzer/result.py`.
2. Add `chroma_curve` optional field to `HierarchyResult`.
3. Reclassify `BBCRhythmAlgorithm` (mirrors the 3 existing BBC curve
   variants). Wall-clock cost in `_run` unchanged (vamp output already
   collected; shape-conversion is the only change).
4. Reclassify `NNLSChromaAlgorithm` and rewrite `_run` to capture
   `frame["values"]` as the per-frame chroma vector.
5. Update orchestrator to: (a) read `bbc_rhythm` curves alongside
   `bbc_energy` and emit smoothed `energy_curves[stem]`; (b) populate
   `HierarchyResult.chroma_curve` from the `nnls_chroma` track's payload.
6. Add `chord_color_for_time` helper that consults `chroma_curve` as
   inter-chord fallback. Wire into `effect_placer.py`.
7. Re-snapshot `tests/golden/analyzer/baseline.json` on the CC0 corpus.
   Run `xlight-evaluate snapshot-analyzer` per CLAUDE.md.
8. Update `docs/musical-analysis-design.md §2`.
9. Run `xlight-evaluate gate` locally (or `gate --quick` for fast loop) to
   confirm no L0 impact/drop/gap regressions from the smoothing.
10. Open PR with the regenerated baseline + code in one commit (or two:
    code-then-baseline) so reviewers can read the code change without
    drowning in the 460k-line baseline diff.

**Rollback strategy:** revert the PR. The baseline regeneration is
deterministic; reverting restores the prior shape. No data on disk relies
on the new fields except the baseline itself (which is regenerated on
revert).

## Open Questions

- **Q1.** Smoothing function for D2: simple per-frame mean vs.
  weighted (e.g., 0.7·energy + 0.3·rhythm) vs. nonlinear (max, geometric
  mean)? Current proposal: simple mean as the v1; revisit if the gate's L0
  metrics shift in unwanted directions.
- **Q2.** The 4-second threshold in D3 for "gap large enough to interpolate
  via chroma" — is 4 s the right value? Reasonable starting heuristic; would
  benefit from tuning against a corpus subjectively. Acceptable to land
  with a constant and refine in a follow-up.
- **Q3.** `effect_placer.py`'s consumer wiring — is the right hook a new
  helper or should chroma-aware modulation flow through the existing value
  curves system in `src/generator/value_curves.py` (currently disabled per
  CLAUDE.md "Future Work")? If chroma-via-value-curves is the future
  architecture, threading the new signal through that machinery may be
  cheaper. Implementation phase decides; either is consistent with the
  proposal's "one consumer" commitment.
