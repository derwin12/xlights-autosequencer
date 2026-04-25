## 1. Data model

- [x] 1.1 Add `ChromaCurve` dataclass to `src/analyzer/result.py` mirroring `ValueCurve` but with `values: list[list[int]]` (12 ints per frame, 0–100). Implement `to_dict` / `from_dict` round-trip; add `duration_ms` property. Place near the existing `ValueCurve` definition (~line 414).
- [x] 1.2 Add `chroma_curve: Optional[ChromaCurve] = None` field to `HierarchyResult` in the L6 Harmony block (next to `chords` and `key_changes`, ~line 497).
- [x] 1.3 Add unit tests for `ChromaCurve` round-trip serialization and `duration_ms` math in `tests/unit/test_analysis_result.py` (or whichever file currently tests `ValueCurve` — verify path before writing).

## 2. BBC Rhythm reclassification

- [x] 2.1 In `src/analyzer/algorithms/vamp_bbc.py:127`, change `BBCRhythmAlgorithm.element_type` from `"onset"` to `"value_curve"`.
- [x] 2.2 Rewrite `BBCRhythmAlgorithm._run` to follow the same pattern as `bbc_energy` / `bbc_spectral_flux` / `bbc_peaks` (lines 46-119): collect vamp output as a vector, normalize via `_vamp_vector_to_curve`, attach a `ValueCurve` to `track.value_curve`, return `TimingTrack` with empty `marks`.
- [x] 2.3 Add a unit test in `tests/unit/test_vamp_bbc.py` (create file if absent) that mocks `vamp.collect` to return a synthetic vector and asserts the algorithm returns `element_type="value_curve"` with a populated `value_curve` and empty `marks`. Test must not require the real vamp plugin (CI doesn't have it).

## 3. NNLS Chroma reclassification

- [x] 3.1 In `src/analyzer/algorithms/vamp_harmony.py:45`, change `NNLSChromaAlgorithm.element_type` from `"harmonic"` to `"value_curve"`.
- [x] 3.2 Rewrite `NNLSChromaAlgorithm._run` to capture `frame["values"]` (the 12-bin chroma vector, currently discarded). Determine fps from frame timestamps (vamp typically returns at fixed fps; compute from first two timestamps). Normalize floats to 0–100 ints (multiply by 100, round, clamp). Build a `ChromaCurve(name=self.name, stem_source=stem, fps=fps, values=values)` and attach to `track.value_curve`. Return `TimingTrack` with empty `marks`.
- [x] 3.3 Note: `TimingTrack.value_curve` field type widens from `Optional[ValueCurve]` to `Optional[ValueCurve | ChromaCurve]`. Update the type annotation in `src/analyzer/result.py` (~line 145 area) and verify mypy / runtime doesn't break.
- [x] 3.4 Add a unit test in `tests/unit/test_vamp_harmony.py` mocking `vamp.process_audio` to return synthetic chroma frames and asserting the algorithm returns `element_type="value_curve"`, populated `value_curve` of type `ChromaCurve`, empty `marks`. Add the regression assertion that `NameError` cannot recur (importing the algorithm class succeeds — the bug-139 echo).

## 4. Orchestrator wiring — energy smoothing

- [x] 4.1 In `src/analyzer/orchestrator.py` after line 479 (where `energy_curves[stem]` is populated from `bbc_energy`), add a sibling loop that reads `bbc_rhythm` tracks via `_get_value_curve`. For each stem present in *both* dicts, replace `energy_curves[stem]` with a per-frame mean `ValueCurve`. Keep stems present in only one of the two unchanged.
- [x] 4.2 If frame counts differ, use `min(len(energy), len(rhythm))` and append a warning to `warnings`. Cite spec scenario "Frame count mismatch falls back to shorter length".
- [x] 4.3 Add `bbc_rhythm` to the algorithm inclusion list in `_build_algorithm_list` (around line 154 where `bbc_energy` is added) for the same stems that get `bbc_energy`. Verify `bbc_rhythm` is registered in the algorithm registry.
- [x] 4.4 Add an integration test in `tests/integration/test_orchestrator_energy_smoothing.py` (new file) that constructs synthetic `bbc_energy` and `bbc_rhythm` ValueCurves, runs the smoothing logic in isolation, and asserts the per-frame mean is correct.

## 5. Orchestrator wiring — chroma curve population

- [x] 5.1 In `src/analyzer/orchestrator.py` near the L6 Harmony assembly, read `nnls_chroma` track via `tracks_by_name.get("nnls_chroma", [])`. If a track exists and its `value_curve` is a `ChromaCurve`, assign to `HierarchyResult.chroma_curve`.
- [x] 5.2 Add `nnls_chroma` to the algorithm inclusion list in `_build_algorithm_list`. Verify it routes to the appropriate stem (probably `full_mix` per the existing stem affinity table).
- [x] 5.3 If `nnls_chroma` is unavailable, append a warning to `HierarchyResult.warnings` ("L6 Chroma: skipped — NNLS Chroma vamp plugin not available") and leave `chroma_curve = None`.

## 6. Generator consumer — chroma-aware chord color

- [x] 6.1 Add `chord_color_for_time(t_ms, chords, chroma_curve)` helper to `src/generator/chord_colors.py` (or a new sibling module — implementation choice). Implement Chordino-primary / chroma-fallback logic per spec: Chordino color when within 4000 ms of a chord event; chroma-derived color from the dominant pitch class when gap > 4000 ms AND `chroma_curve` is not None; held Chordino color otherwise.
- [x] 6.2 Implement chroma → color: pick the pitch class with the maximum value at the frame nearest `t_ms`, map through the existing `CIRCLE_OF_FIFTHS` hue table.
- [x] 6.3 Wire the new helper into `src/generator/effect_placer.py` at the call site that currently does step-change chord color lookup. Old behavior (no chroma) preserved when `chroma_curve` is None.
- [x] 6.4 Add a unit test in `tests/unit/test_chord_colors.py` covering all three scenarios from the spec: Chordino covers timestamp, long gap with chroma, long gap without chroma.

## 7. Baseline + gate

- [x] 7.1 Run `xlight-evaluate snapshot-analyzer` against the CC0 corpus to regenerate `tests/golden/analyzer/baseline.json`. Verify nnls_chroma and bbc_rhythm appear with `element_type="value_curve"` and the new `chroma_curve` field is present.
- [x] 7.2 Run `xlight-evaluate snapshot-analyzer` a second time and `git diff` the result against the first regeneration. Any non-skip_check field that differs is non-determinism that must be tracked down before this change ships. Acceptable to add specific algorithm names to `skip_check` only if they were already non-deterministic before this change (verify via git blame on existing skip_check entries).
- [x] 7.3 Run `xlight-evaluate gate` (full Tier B local) and confirm exit code 0. Pay attention to L0 impact / drop / gap counts on the corpus — significant drift indicates the smoothing changed downstream behavior. If counts shift outside acceptable tolerance, decide: accept (re-snapshot) or revisit smoothing (D2 weight).
- [x] 7.4 Update `src/evaluation/analyzer_baseline.py` if the curve algorithms need new tolerance entries (likely already covered by the existing curve-algorithm path, but verify).

## 8. Documentation

- [x] 8.1 Update `docs/musical-analysis-design.md §2` to mark the misclassification of `bbc_rhythm` and `nnls_chroma` as resolved, with a back-reference to this change. Keep the historical context (the original §2 finding); add a "Resolved 2026-04-25 in change `fix-misclassified-curves`" note. Do NOT touch §5 or other sections.
- [x] 8.2 Confirm the `docs/analyzer-coverage.md` audit doc does not exist yet (it was a hypothetical Proposal A artifact); if a session creates it later, it should reference this change.

## 9. PR + ship

- [x] 9.1 Run `/review-diff main` against the branch and address every CRITICAL / HIGH finding before opening the PR.
- [x] 9.2 Open PR with title `feat(analyzer): reclassify nnls_chroma and bbc_rhythm as value curves`. Body should reference `docs/musical-analysis-design.md §2` (the finding) and link this change directory. Include "Test plan" with the gate exit-code expectation and the L0 metric check.
- [ ] 9.3 If CI Tier A fails, fix root causes (no xfail / skip / --ignore — per cerebrum 2026-04-25 Do-Not-Repeat).
- [ ] 9.4 After merge, run `/opsx:archive fix-misclassified-curves` to fold this change's specs into `openspec/specs/analyzer-value-curves/`.
