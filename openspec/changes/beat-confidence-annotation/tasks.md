## 1. Selector — agreement annotation

- [x] 1.1 Add `annotate_agreement_confidence(winner, losers, window_ms=35)` to `src/analyzer/selector.py`. Mutates `winner.marks[i].confidence` in place. Use `numpy.searchsorted` against each loser's pre-sorted mark times to count agreement in O(N log M) per loser. Round to 3 decimal places.
- [x] 1.2 Add `select_best_beat_track_with_candidates(candidates, onset_times_ms) -> tuple[TimingTrack | None, list[TimingTrack]]`. Reuse the existing `select_best_track` for the winner; build losers as `[c for c in candidates if c is not winner]`.
- [x] 1.3 Add `select_best_bar_track_with_candidates` (parallel implementation).
- [x] 1.4 Keep `select_best_beat_track` and `select_best_bar_track` unchanged (thin wrappers around `select_best_track`).

## 2. Selector tests

- [x] 2.1 Create `tests/unit/test_selector.py` (verify file does not already exist; if it does, append).
- [x] 2.2 Test: three losers all within ±35 ms → confidence = 1.0.
- [x] 2.3 Test: zero losers within ±35 ms → confidence = 0.0.
- [x] 2.4 Test: one of three losers within ±35 ms → confidence ≈ 0.333.
- [x] 2.5 Test: empty losers list → confidence remains None.
- [x] 2.6 Test: window boundary — loser at exactly 35 ms counts; loser at 36 ms does not.
- [x] 2.7 Test: a loser with multiple marks inside the window counts as one (the closest mark).
- [x] 2.8 Test: `select_best_beat_track_with_candidates` returns `(winner, losers)` with `len(losers) == len(candidates) - 1`.
- [x] 2.9 Test: `select_best_beat_track_with_candidates` with a single candidate returns `(candidate, [])`.

## 3. Orchestrator wiring

- [x] 3.1 In `src/analyzer/orchestrator.py:240`, update the import line to add `select_best_beat_track_with_candidates`, `select_best_bar_track_with_candidates`, `annotate_agreement_confidence`.
- [x] 3.2 At the L2 bar selection site (~line 412), replace `bars = select_best_bar_track(...)` with `bars, bar_losers = select_best_bar_track_with_candidates(...)`. After the existing `_snap_sections_to_bars` block, call `if bars and bar_losers: annotate_agreement_confidence(bars, bar_losers, window_ms=35)`.
- [x] 3.3 At the L3 beat selection site (~line 425), update `_select_beat_with_bpm_check` to return `(winner, losers)`. After the call, `if beats and beat_losers: annotate_agreement_confidence(beats, beat_losers, window_ms=35)`.
- [x] 3.4 Update `_select_beat_with_bpm_check` body (~line 1229) to thread candidates through and return the tuple. The BPM-check fallback (which may pick a different track than the default selector) should also produce a coherent loser list relative to its chosen winner.
- [x] 3.5 Confirm by grep that `select_best_beat_track` and `select_best_bar_track` (the legacy entry points) have no remaining callers in `src/analyzer/orchestrator.py`. Leave them defined for any out-of-tree callers.

## 4. Validator guard

- [x] 4.1 In `src/analyzer/validator.py:229-230`, change the bar mark-confidence assignment from `for mark in result.bars.marks: mark.confidence = bar_score` to guard with `if mark.confidence is None: mark.confidence = bar_score`.
- [x] 4.2 Same change at lines 243-244 for L3 beats.
- [x] 4.3 Do **not** change L1 sections (line 263), L4 events (line 286), L0 impacts (line 299), or L0 drops (line 312) — those are out of scope.
- [x] 4.4 Update `src/analyzer/validator.py` module docstring (lines 1-10) to note that the bar/beat confidence write is conditional.

## 5. Generator consumer — `_place_per_beat`

- [x] 5.1 In `src/generator/effect_placer.py::_place_per_beat` (~line 1099), inside the `for i, mark in enumerate(marks)` loop, branch on `mark.confidence`. Define `is_high_confidence = mark.confidence is not None and mark.confidence >= 0.7`.
- [x] 5.2 When `is_high_confidence` is True, route the placement to the existing accent path (Strobe / Shockwave). When False or None, fall through to the default path (preserves pre-change behavior bit-for-bit).
- [x] 5.3 Audit-trace the existing function: identify exactly which params dict / effect_def is the punch path vs the wash path. Implementation choice is internal but must not change the function's signature or its callers.

## 6. Integration test

- [x] 6.1 Create `tests/integration/test_orchestrator_beat_confidence.py`.
- [x] 6.2 Test: run the hierarchy on the existing analyzer fixture (`tests/fixtures/...`); assert at least one L3 beat mark has `confidence != report['beats']['score']` (proves per-mark annotation took effect, not just track-level fallback).
- [x] 6.3 Test: run with `profile="quick"`; assert every L3 beat mark has `confidence == report['beats']['score']` (single-tracker fallback path).
- [x] 6.4 Test: assert `report['beats']['score']` value is unchanged from the pre-change value on the same fixture (regression guard for the validator change).

## 7. Generator regression test

- [x] 7.1 In the existing effect-placer tests (path TBD; verify against `tests/`), add: stub a `HierarchyResult` with one beat at `confidence=0.9` and one at `confidence=0.3`; call `_place_per_beat`; assert the two placements have distinguishable effect types.
- [x] 7.2 Add: stub all beats with `confidence=None`; assert placements are bit-for-bit identical to a control run on the pre-change implementation (use a recorded snapshot).

## 8. Golden baseline + acceptance gate

- [x] 8.1 Run `xlight-evaluate snapshot-analyzer` to regenerate `tests/golden/analyzer/baseline.json`.
- [x] 8.2 Manually inspect the diff to confirm changes are confined to per-mark `confidence` values on L2 / L3 tracks. Flag any other field changes for investigation.
- [ ] 8.3 Run `xlight-evaluate gate` (full mode) and confirm exit code 0.
- [x] 8.4 If the analyzer baseline gate fails with exit code 6 (regression), inspect whether the regression is the intended confidence-value change or an unrelated drift.

## 9. Docs

- [x] 9.1 Update `docs/musical-analysis-design.md:77` to mark the cross-tracker agreement annotation as shipped (small doc-only diff bundled in the same PR).
- [x] 9.2 Append a one-line changelog entry to `docs/segment-classification-changelog.md` only if the change touches segment / section classification — verify it does not (this proposal is L2/L3 only) and skip if so.

## 10. Cerebrum + buglog hygiene

- [x] 10.1 Append a `Key Learnings` entry to `.wolf/cerebrum.md` documenting that `validator.py` now respects pre-existing per-mark confidence values, so future writers (e.g. an L4 event-confidence proposal) follow the same `if confidence is None` guard pattern.
- [x] 10.2 No buglog entry expected at proposal time; add one only if implementation surfaces an unexpected regression.
