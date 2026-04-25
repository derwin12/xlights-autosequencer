## 1. Frontend surfacing — agreement_score reaches the Analyze screen

- [ ] 1.1 Extend `src/review/api/v1/analysis.py` (around line 320 where the section payload is built) to copy `agreement_score` from the story-source section dict and to set `low_confidence = (agreement_score <= 1)`. Use `sec.get("agreement_score", 0)` so legacy stories default to 0 (per spec scenario "Legacy story without agreement_score defaults to 0"). Verify the same code path covers the SSE-stream `state.push` and the final state payload.
- [ ] 1.2 Update `src/review/frontend/src/screens/Analyze.tsx` (interface `Section` at line 39) to declare `agreement_score: number` and `low_confidence: boolean`. Update the section-list rendering near line 733 to show a visual indicator (e.g., a small dot or icon next to the role label) when `low_confidence` is true. Indicator style is implementation choice — keep it small and color-accessible.
- [ ] 1.3 Decide and document the visual treatment in a 1-paragraph comment in `Analyze.tsx`: what color, what icon (or text marker), what tooltip text. Tooltip: "Low multi-source agreement — verify boundary".
- [ ] 1.4 Audit any UI snapshot / Playwright tests that compare exact section-payload JSON. Update them to assert against the subset of fields they care about, not whole-payload equality. List of tests to check: `src/review/frontend/tests/` and any Python `tests/integration/` test that asserts on the analyze API response shape.
- [ ] 1.5 Add a unit test for `low_confidence` derivation in `analysis.py` covering scores `0`, `1`, `2`, `5`, and missing-field. File: `tests/unit/test_review_api_analysis.py` (create if absent — verify path before writing).

## 2. Library fidelity → shared module → gate suite

- [ ] 2.1 Create `src/evaluation/section_fidelity.py`. Move `summarize_song`, `load_stories`, and `print_report` from `scripts/library_fidelity.py` into it. Keep them pure-functional; no module-level state. Re-export from the new module so the script's existing logic continues to work after refactor.
- [ ] 2.2 Add `compute_library_mean(stories: list[tuple[str, dict]]) -> float` and `compute_per_fixture_breakdown(stories) -> dict[str, dict]` helpers to `section_fidelity.py`. These are what the gate suite consumes.
- [ ] 2.3 Refactor `scripts/library_fidelity.py` to import from the new module. Verify the printed output is byte-identical to current behavior on the same corpus by capturing stdout before and after the refactor (per spec scenario "Script's stdout format is unchanged from PR #84").
- [ ] 2.4 Add a unit test in `tests/unit/test_section_fidelity.py` covering: (a) library-mean of a known corpus, (b) per-fixture breakdown shape, (c) skipping stories under `stems/` (already in load_stories — preserve the behavior).
- [ ] 2.5 In `src/evaluation/acceptance_gate.py`, add a new `run_section_fidelity_suite(corpus: list[CorpusEntry], baseline_path: Path) -> SuiteResult` parallel to `run_analyzer_suite` / `run_generator_suite`. Read the baseline file; compute library-mean against the corpus; compare; populate `SuiteResult.violations` with per-fixture deltas when over tolerance.
- [ ] 2.6 Wire the new suite into `run_gate` (around line 286): add `"section_fidelity"` to the suites dict. Update `_aggregate_exit_code` only if needed (existing rules likely cover it; verify).
- [ ] 2.7 Add `xlight-evaluate snapshot-section-fidelity` CLI subcommand parallel to `snapshot-analyzer`. It writes `tests/golden/section_fidelity/baseline.json`. Implementation lives in `src/evaluation/section_fidelity.py` or a sibling CLI module — match the pattern used by `snapshot-analyzer`.
- [ ] 2.8 **Order-critical:** before any code from §3 below lands, run `xlight-evaluate snapshot-section-fidelity` on current-main and commit the baseline file. This locks in pre-change library-mean per spec scenario "Baseline captured before SSM wiring lands".
- [ ] 2.9 Run `xlight-evaluate gate --skip-ui` and confirm the new suite returns exit code 0 against the just-captured baseline. Three back-to-back runs: confirm the library-mean noise is well within the `0.10` tolerance window. If noise exceeds 0.10, widen the tolerance constant before shipping (with a comment explaining the calibration).

## 3. SSM productionization

- [ ] 3.1 Create `src/analyzer/self_similarity.py`. Port the working core from `scripts/self_similarity_prototype.py`: feature extraction (beat-synced chroma + MFCC), recurrence matrix construction, diagonal-stripe enhancement, repetition-group extraction. Drop the script's matplotlib / PNG output — that is diagnostic only.
- [ ] 3.2 Implement auto-threshold: `threshold = numpy.percentile(off_diagonal_values, 90)`. Document the choice in a docstring referencing design D4. Make the percentile a private module constant for easy tuning, not a public knob.
- [ ] 3.3 Add `RepetitionGroup` dataclass to `src/analyzer/result.py`: `id: int`, `members: list[tuple[int, int]]` (start_ms, end_ms per occurrence). Minimal shape per design Q3. Round-trip via `to_dict` / `from_dict`.
- [ ] 3.4 Add `repetition_groups: Optional[list[RepetitionGroup]] = None` to `HierarchyResult`. Update serialization. Document the `None` vs. `[]` semantic in the field's docstring (spec scenarios "SSM produces zero groups → empty list" and "SSM unavailable or errored → None plus warning").
- [ ] 3.5 In `src/analyzer/orchestrator.py`, invoke `compute_repetition_groups(audio_path)` (or equivalent) within the existing structural-analysis pass. Wrap in try/except like other optional algorithms; on error, set `repetition_groups = None` and append a warning to `HierarchyResult.warnings`. Budget: 30s timeout for the largest acceptance fixture; if exceeded, record warning and continue.
- [ ] 3.6 Add a unit test in `tests/unit/test_self_similarity.py` that builds a synthetic chroma+MFCC matrix with two known repetition blocks, calls the SSM module, and asserts the returned groups contain those blocks. Avoid loading real audio in unit tests.
- [ ] 3.7 Add an integration test in `tests/integration/test_orchestrator_ssm.py` (new file) running the full orchestrator on a small fixture known to have repetitions (e.g., a fixture from `tests/fixtures/`). Assert `HierarchyResult.repetition_groups` is non-None and non-empty. Skip-on-vamp-missing if needed (no `xfail`/`skip` in CI without rationale per cerebrum DNR).
- [ ] 3.8 Re-snapshot `tests/golden/analyzer/baseline.json` to include the new `repetition_groups` field. Run `xlight-evaluate snapshot-analyzer` twice and `git diff` the result; non-determinism in `repetition_groups` must be added to `skip_check` only with a written rationale (per cerebrum DNR on quarantine pairing).

## 4. SSM consumes in the story builder

- [ ] 4.1 In `src/story/builder.py`, after sections are assembled (around the section-dict-build at line 671), iterate sections with role `"chorus"` and compute `chorus_ssm_supported` per spec. Read `hierarchy.repetition_groups` (or default `[]` / `None` per the spec).
- [ ] 4.2 Implement the supported-detection logic: a Chorus is supported iff (a) at least one other Chorus shares its repetition group, OR (b) its time-span overlaps any group with ≥2 members. When `repetition_groups` is `None` or `[]`, default `chorus_ssm_supported = true` for every Chorus.
- [ ] 4.3 Add `chorus_ssm_supported` to non-Chorus sections too? **No.** Per spec the field is set on Chorus sections only. Other sections do not get the field at all (consumers default missing → True).
- [ ] 4.4 Add a unit test in `tests/unit/test_story_builder_ssm_validator.py` covering: two Choruses in same group → both supported; one Chorus alone → unsupported; SSM None → supported (default); SSM empty list → supported (default); Verse + Chorus in same group → Chorus is supported (group has ≥2 members), Verse role unchanged (per spec scenario "SSM does not change role labels").

## 5. Plumbing chorus_ssm_supported through the API + UI

- [ ] 5.1 Update `src/review/api/v1/analysis.py` to copy `chorus_ssm_supported` (defaulting absent → `True`) into the analyze-step section payload. The frontend can decide whether to show a separate hint.
- [ ] 5.2 Decide whether the frontend distinguishes between `low_confidence` (boundary score) and `chorus_ssm_supported = false` (Chorus role validation) in the UI. Recommended: show a single "verify this section" indicator when *either* signal fires; tooltip lists which checks failed. Implementation choice — record the decision in `Analyze.tsx` comment.
- [ ] 5.3 Update the frontend `Section` interface to declare `chorus_ssm_supported?: boolean` (optional; absent on non-Chorus and on legacy stories).
- [ ] 5.4 Add a frontend unit / Vitest test (file: under `src/review/frontend/tests/` matching the existing pattern) that renders the section list with mixed `low_confidence` + `chorus_ssm_supported` values and asserts the indicator behavior.

## 6. Documentation

- [ ] 6.1 Add a one-paragraph entry to `docs/section-confidence-snap-to-cluster-2026-04.md` (or a new sibling doc — match precedent) recording: SSM productionized, library-fidelity gated, agreement_score visible in UI. Cross-reference this change directory.
- [ ] 6.2 Update the project root `CLAUDE.md` "Active Technologies" section if a new top-level dependency is exposed. (Note: this change adds *no* new external dependency — `librosa.segment` is already pulled in. So this task is verify-only; if no entry needs to change, leave CLAUDE.md untouched.)

## 7. Pre-merge gate + PR

- [ ] 7.1 Run `/pre-mortem agreement-score-operationalization` on this design before opening the implementation PR. Address every CRITICAL / HIGH finding from the report. (This task belongs to the implementation PR's session, not the proposal PR's.)
- [ ] 7.2 Run `/review-diff main` against the implementation branch and address every CRITICAL / HIGH finding before opening the PR.
- [ ] 7.3 Run `xlight-evaluate gate` (full Tier B local) and confirm exit code 0. If the new section_fidelity suite fails on first run, diagnose root cause — do NOT raise the tolerance to mask. Acceptable resolutions: fix the regression, regenerate the baseline with a written rationale in the PR description.
- [ ] 7.4 Open implementation PR titled `feat(analyzer/story): operationalize agreement score — UI surfacing, gate suite, SSM Chorus validator`. Body must reference this change directory, link `docs/analysis-pipeline-improvements-2026-04.md`, and explicitly note that PR #84's snap-to-cluster + per-section score are pre-existing (this change does not change them).
- [ ] 7.5 If CI Tier A fails on the implementation PR, fix root causes (no `xfail` / `skip` / `--ignore` per cerebrum 2026-04-25 Do-Not-Repeat).
- [ ] 7.6 After implementation PR merges, run `/opsx:archive agreement-score-operationalization` to fold this change's specs into `openspec/specs/story-section-agreement/`.
