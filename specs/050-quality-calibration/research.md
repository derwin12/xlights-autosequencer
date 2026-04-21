# Phase 0 Research: Quality Calibration Harness

All topics listed here were unknowns or deferred decisions at the end of `/speckit.specify` + `/speckit.clarify`. Each entry resolves one question with a chosen approach, rationale, and alternatives.

## 1. `.xsq` and `.xsqz` file format

**Decision**: Parse `.xsq` with `xml.etree.ElementTree` (stdlib). For `.xsqz`, open with `zipfile.ZipFile` and extract the single `.xsq` member in memory; parse identically.

**Rationale**: Confirmed by inspecting an actual pro `.xsq` (`baseline-sequences/Light of Christmas.xsq`) — it is plain XML. Confirmed `.xsqz` is a zip archive (`Uptown Funk ... .xsqz` → `file` reports `Zip archive data, compression method=store`). Both are stdlib-resolvable; no `lxml`/`defusedxml` needed for local-only read. The `.xsq` root is `<xsequence>` with `<head>` metadata (mediaFile, sequenceDuration, sequenceTiming in ms), `<ColorPalettes>` (ordered pool), `<EffectDB>` (ordered effect-settings pool), and `<ElementEffects>` containing `<Element type="model" name="...">` → `<EffectLayer>` → `<Effect startTime="..." endTime="..." label="..." ref="..." palette="...">`.

**Alternatives considered**:
- `lxml` for faster parsing — rejected: unnecessary for 10s-of-MB files; adds a dep.
- `xmltodict` for ergonomic nested dicts — rejected: the sax-like streaming we may want later is simpler with ElementTree.

## 2. Identifying effect type from `<Effect>` elements

**Decision**: Effect type is derived from the referenced `<EffectDB>` entry's settings string. Each entry contains a `E_NOTEBOOK_<Name>=Settings` token (e.g. `E_NOTEBOOK_Marquee=Settings`, `E_NOTEBOOK_Plasma=Settings`); the effect name is the token between `E_NOTEBOOK_` and `=`. If multiple tokens match, the first one wins. Entries with no match are labeled `Unknown` and counted toward `unknown_effect_fraction`.

**Rationale**: Inspecting the real `.xsq` shows every effect definition carries exactly one `E_NOTEBOOK_<EffectName>` key. This is how xLights itself identifies the effect. No separate effect-name field exists on `<Effect>` — the `label` attribute is human-authored lyric text, not a type tag.

**Alternatives considered**:
- Inferring from prefixed param keys (`E_CHECKBOX_Marquee_*`) — rejected: noisier, same root info.
- Maintaining our own effect catalog for recognition — rejected: duplicates xLights' own convention and would drift.

## 3. Reusing existing audio analysis cache

**Decision**: Compute beats, energy curves, and section boundaries via the existing `src.analyzer` pipeline keyed by MD5 of the source MP3 (same hash as `src.cache`). The harness calls the existing entry points (`analyze` → cached `AnalysisResult` with timing tracks) and pulls madmom beats, the L5 energy curve, and QM-segmenter section boundaries directly. No re-analysis on repeat runs.

**Rationale**: Per constitution I (Audio-First Pipeline) and CLAUDE.md, analysis is already cached by audio hash. Re-running the full 22-algorithm pipeline on every comparison would blow the 5-minute SC-001 budget. The cache is the correct abstraction boundary.

**Alternatives considered**:
- Independent audio analysis in the evaluation module — rejected: duplicates pipeline, violates modularity.
- Reading only persisted `_analysis.json` files — rejected: couples to file format; using the Python API keeps us future-proof against cache format changes.

## 4. Deterministic generator invocation

**Decision**: Call the existing generator pipeline via a thin wrapper (`src.evaluation.generator_runner`) that sets the random seed (via existing `variation_seed` parameter where present, plus `random.seed()` / `numpy.random.seed()`) derived from a hash of the audio ID. The wrapper runs end-to-end (analysis → plan → `.xsq` in memory via existing `xsq_writer`) and returns the written bytes, which `xsq_reader` then parses. No file persisted to disk.

**Rationale**: Spec FR-019 requires deterministic output given fixed seed. Existing generator already accepts seeds; we just centralize seed construction in one wrapper so corpus entries are reproducible across runs and machines. Routing everything through the same `xsq_reader` as pro inputs guarantees apples-to-apples metric extraction.

**Alternatives considered**:
- Having metrics read directly from the in-memory `Plan` object — rejected: two code paths (pro reads XML, ours reads Plan) mean metrics diverge subtly; one format for both is simpler.
- Writing to a tempfile — rejected: disk I/O per song for no benefit; bytes-in-memory is adequate and faster.

## 5. Baseline update detection ("intentional" vs accidental)

**Decision**: The check command treats any same-diff commit that modifies `tests/golden/baseline.json` as an intentional update. In CI, the gate compares baseline-at-HEAD against the metrics produced by the current code. If baseline-at-HEAD matches current metrics within tolerance, pass. If not, fail with a diff — and suggest running `xlight-evaluate snapshot` to regenerate the baseline. No separate approval flag; the reviewer's job is to confirm the baseline update is intentional in code review.

**Rationale**: Keeps the mechanism simple and PR-review-based. No hidden flags, no state outside git. An accidental regression produces a failing gate; an intentional change produces a gate that passes only after the author deliberately committed the new baseline. This is the standard golden-file pattern.

**Alternatives considered**:
- Explicit `--accept-baseline-change` CLI flag that writes a marker file — rejected: just another thing to forget; doesn't add safety.
- Require a specific commit-message tag (`[baseline-update]`) — rejected: brittle, relies on text convention not enforced by any tool.

## 6. Report output format

**Decision**: Persisted JSON (`tests/golden/reports/<iso>.json`) is the authoritative format. Terminal output is a human-readable summary rendered from the same JSON in memory — per-song tables via simple text alignment, cross-song trends as a bulleted list. A `--json` flag on compare emits only JSON (for CI/scripts); without it, both JSON is written and human summary is printed.

**Rationale**: One source of truth for every report; the rendering is a pure function of the JSON. CI pipelines can parse JSON without ANSI stripping; humans can scan the terminal output without jq.

**Alternatives considered**:
- HTML report — rejected: v0 scope, overkill for a dev tool, violates Simplicity First.
- CSV — rejected: nested structures (per-section metrics, skip reasons) serialize poorly.

## 7. Corpus entry identity

**Decision**: Each manifest entry has a `song_id` (short stable slug like `light-of-christmas`) and a `pro_id` (short stable slug like `xatw` or `bill-jenkins`). The composite key `(song_id, pro_id)` uniquely identifies a corpus entry. Multiple entries may share a `song_id` (intra-pro variance cases). Our-side generated output is keyed only by `song_id` — one generation per unique song, compared against every pro entry for that song.

**Rationale**: Cleanly separates "which song" from "which pro did this take," which is exactly what the intra-pro variance analysis needs (FR-004, FR-013). Stable slugs survive file renames; file paths live in the manifest alongside.

**Alternatives considered**:
- Use the `.xsq` filename as the key — rejected: filenames change, and the three Light-of-Christmas sequences would each need an ad-hoc stable suffix anyway.
- Hash of the `.xsq` contents — rejected: changes every time the file is re-exported, breaking baseline pinning.

## 8. Jensen-Shannon divergence on effect histograms

**Decision**: Implement the calculation directly (`scipy`-free): normalize both distributions over the shared vocabulary to sum to 1, compute midpoint `M = 0.5*(P+Q)`, and return `0.5*KL(P||M) + 0.5*KL(Q||M)` using base-2 logs so the result is bounded in [0, 1]. Track `unknown_effect_fraction` as the share of placements whose effect type is in one distribution but not the other, reported separately.

**Rationale**: One textbook formula; no `scipy` dep needed. Bounded range makes cross-song comparison intuitive. Keeps `unknown_effect_fraction` separate so the histogram distance isn't polluted by vocabulary asymmetry (spec FR-009).

**Alternatives considered**:
- `scipy.spatial.distance.jensenshannon` — rejected: adds `scipy` dep for ~5 lines of code.
- Total-variation distance — rejected: less informative at tails; JS is the community default for histogram comparison.

## 9. Pathological-floor fixture design

**Decision**: Four synthetic `SequenceSummary` fixtures stored as JSON under `tests/evaluation/fixtures/degenerate/`:
- `monochrome.json` — 300 placements, all `#FFFFFF`, single effect type, beat-aligned
- `single_effect.json` — 300 placements, default palette, all `Plasma`, beat-aligned
- `random_alignment.json` — 300 placements, realistic palette+effect mix, timestamps drawn uniformly random (not beat-aligned)
- `empty.json` — 0 placements, minimal head metadata

Every metric implementation must include a test that loads each fixture and asserts the metric scores the fixture worse than the minimum observed on any real corpus entry (`tests/evaluation/test_pathological_floor.py`).

**Rationale**: Spec FR-020 / SC-003 require this as a gating property of the metric set. Encoding fixtures as JSON (not actual `.xsq`) bypasses the parser and tests the metric directly, so a broken parser can't hide a broken metric.

**Alternatives considered**:
- Generate degenerate `.xsq` on the fly per test — rejected: slower, entangles parser and metric concerns.
- Only one "all-bad" fixture — rejected: doesn't exercise the specific failure modes each metric targets.

## 10. Consistency threshold (80%) — constant vs. configurable

**Decision**: Hard-code 80% as the "consistent gap" threshold for v0. Expose as a named constant in `src.evaluation.compare` so it's reviewable but not CLI-configurable.

**Rationale**: Simplicity First. With 6 songs, 80% means 5-of-6 — a strong signal that's rare by chance. If later evidence shows we need 75% or 85%, the constant changes in one commit with PR discussion attached. CLI configurability invites drift across invocations.

**Alternatives considered**:
- CLI `--consistency-threshold` flag — rejected: YAGNI.
- Statistical significance test (binomial) — rejected: 6-song sample too small for meaningful p-values.
