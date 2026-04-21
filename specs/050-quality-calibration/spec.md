# Feature Specification: xLights Sequence Quality Calibration Harness

**Feature Branch**: `050-quality-calibration`
**Created**: 2026-04-15
**Status**: Draft
**Input**: User description: "xLights sequence quality calibration harness — extract shared metrics from pro .xsq files and our generator output on the same songs to produce repeatable reports tracking cross-corpus deltas; two signals: pro deltas (informational) and own-baseline regression (CI-gated)"

## Clarifications

### Session 2026-04-15

- Q: How should the regression-gate tolerance be defined for v0? → A: Per-metric tolerance defined alongside each metric, with a conservative default for metrics that don't specify one.
- Q: What should happen when our generator raises an exception on a specific corpus song during a comparison run? → A: Record as a skip in the report with reason "generator error" AND treat it as a CI-failing condition, distinct from non-failing corpus-side skips (missing MP3, unparseable pro file).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Detect Unintended Generator Regressions (Priority: P1)

A generator maintainer lands a change (e.g. new duration-scaling rule, new theme, palette tweak) and wants confidence that the change moved the metrics they *intended* to move and didn't silently regress anything else. Before merge, they run a comparison check against a committed baseline of their own prior output, and the CI gate blocks the merge if any regression-gated metric moved by more than the allowed tolerance without the baseline being intentionally updated in the same change.

**Why this priority**: Without this, the team has no safety net. Today every change is a judgment call, and subtle regressions (a palette that went monochrome in one section, tier 3 going silent, beat alignment eroding) land unnoticed. Catching unintended drift is strictly more valuable than measuring against pros, because it protects against every change the team makes regardless of whether pro references exist.

**Independent Test**: A maintainer makes a deliberate generator change, runs the check command, and either sees the expected metric movements in a report or sees the CI gate fail with the specific metric and delta that regressed. Works with zero pro references present.

**Acceptance Scenarios**:

1. **Given** a committed baseline and no code changes, **When** the check command runs, **Then** all regression-gated metrics match the baseline within tolerance and the command exits zero.
2. **Given** a generator change that intentionally reduces effect density, **When** the maintainer runs the check, **Then** the report shows which songs and sections moved and by how much, and the gate fails until the baseline is intentionally updated in the same change.
3. **Given** a generator change that was meant to only affect palette selection but accidentally broke tier 3 placement, **When** the check runs, **Then** the tier-utilization metric regresses and the gate fails, surfacing the unintended side effect.

---

### User Story 2 — Compare Against Professional References (Priority: P2)

A generator maintainer wants to know, on songs where a professional sequencer we admire has published a sequence, how our output compares. They run a comparison report that shows, per song and aggregated across the corpus, which metrics differ from pro output, in which direction, and whether the difference is consistent enough across multiple songs to represent a real gap rather than a single-song quirk.

**Why this priority**: Pros are one of several calibration sources, not the judge. The comparison is informational — it tells the team where they diverge from work they admire, which becomes a menu of candidate tuning experiments. It's P2 because the report is useful the moment it exists but doesn't block any change on its own.

**Independent Test**: A maintainer runs the compare command against the pro corpus and receives a per-song table plus a cross-song trend summary flagging metrics where the same-direction delta appears on at least 80% of songs.

**Acceptance Scenarios**:

1. **Given** a corpus with 6 songs and 9 pro sequences, **When** the compare command runs, **Then** each pro sequence is measured against the same-song output from our generator and produces per-song deltas for every comparable metric.
2. **Given** a cross-song report, **When** a metric shows ours > pro on at least 80% of songs in the same direction, **Then** the report flags that metric as a "consistent gap" with the magnitude and the songs involved.
3. **Given** a song with multiple pro sequences (e.g. three different pros sequencing "Light of Christmas"), **When** the compare command runs, **Then** the report also shows intra-pro variance for that song so the team can tell whether an ours-vs-pro delta exceeds normal pro-vs-pro artistic variation.

---

### User Story 3 — Handle Partial Corpus Gracefully (Priority: P2)

A corpus entry may be missing its audio file (MP3 not yet acquired, file moved, hash mismatch) or have a pro sequence whose audio master differs from ours. The harness must handle this without failing the whole run — skip the entry with a clear reason, continue measuring every other entry, and surface the skip count prominently in the report so it isn't silently ignored.

**Why this priority**: Corpus assembly is a long-running, human-paced process. Blocking reports on completeness means the harness is unusable until every MP3 is acquired, which is weeks or months away. The team needs useful output from day one on whatever subset is present.

**Independent Test**: A maintainer adds a manifest entry for a song without an MP3 on disk, runs the compare command, and receives a report that measures every complete entry, clearly lists the skipped entries with the reason, and exits successfully when at least one entry was measurable.

**Acceptance Scenarios**:

1. **Given** a manifest entry whose MP3 path does not resolve, **When** the compare command runs, **Then** the song is skipped with reason "MP3 missing" and the remaining songs are fully measured.
2. **Given** all manifest entries are skippable, **When** the compare command runs, **Then** the harness exits with a non-zero status and a message naming every skipped entry and its reason.
3. **Given** a pro sequence whose source audio is flagged in the manifest as "master may differ," **When** metrics that depend on source audio alignment are computed, **Then** the report annotates those metrics for that song with a reliability warning.

---

### User Story 4 — Measure Intra-Pro Noise Floor (Priority: P3)

When two or three different professional sequencers have each sequenced the same song, the difference between their outputs establishes a noise floor — a baseline of artistic variance between equally legitimate interpretations. A maintainer wants the report to surface this noise floor alongside ours-vs-pro deltas so they can tell whether a gap is a real tuning opportunity or just normal artistic variation.

**Why this priority**: This is what keeps calibration honest — without it, any ours-vs-pro delta looks like a problem, even when pros differ from each other by similar amounts. It's P3 because the feature still delivers value without it (just with less interpretive confidence), and it only applies to songs where multiple pro sequences exist.

**Independent Test**: A maintainer runs the compare command on a corpus containing at least one song with two or more pro sequences and receives a report that includes pro-vs-pro variance statistics for every metric on that song, alongside the ours-vs-pro deltas.

**Acceptance Scenarios**:

1. **Given** a song with three pro sequences, **When** the compare command runs, **Then** the report shows the min/max/range of each metric across the three pro sequences as the song's noise floor.
2. **Given** an ours-vs-pro delta on a metric that is smaller than the intra-pro range for that same song, **When** the report is generated, **Then** the delta is marked as "within pro variance" so the team does not chase it as a gap.

---

### Edge Cases

- **Pro sequence file cannot be parsed** (corrupted or unrecognized schema): skip the single file with the error recorded in the report; do not crash the run.
- **Audio hash mismatch** between the on-disk MP3 and the hash recorded in the manifest: surface as a warning in the report but still measure, since the user may have intentionally replaced the file; prompt the maintainer to update the manifest hash.
- **Zero placements** in a sequence (empty or trivially short): all metrics must produce a defined value (zero, not error) so pathological cases still appear in the report rather than crashing it.
- **Effect type present in a pro sequence that our generator never emits**: count toward an "unknown-effect fraction" tracked separately; exclude from the direct-comparison histogram so comparison stays apples-to-apples on shared vocabulary.
- **Audio-derived section classifier produces different section counts on the same audio on different runs**: metrics that use audio windows must be deterministic across runs given a fixed audio hash; classifier output must be cached keyed by hash.
- **First-ever run with no baseline committed**: the check command must produce a useful error telling the maintainer how to create the initial baseline rather than comparing against an empty file.
- **Our generator raises an exception on a specific song**: record the song as a skip with reason "generator error" including the exception summary, continue measuring every other song, and surface it as a CI-failing condition distinct from non-failing corpus-side skips (missing audio, unparseable pro file).

## Requirements *(mandatory)*

### Functional Requirements

**Corpus management**

- **FR-001**: System MUST support a corpus manifest that references pro sequence files and source audio files by absolute local path, with neither type of file stored inside the repository.
- **FR-002**: System MUST record a source-audio hash per manifest entry and detect when the hash of the on-disk audio file no longer matches the manifest.
- **FR-003**: System MUST allow a corpus entry to be marked as "audio master may differ from pro's" so metrics depending on audio alignment can be flagged as reduced-reliability for that entry.
- **FR-004**: System MUST support multiple pro sequence entries per song so intra-pro variance can be measured.

**Metric extraction**

- **FR-005**: System MUST extract the same metric set from pro sequence files and from our generator's output so the two are directly comparable.
- **FR-006**: System MUST support both uncompressed and zipped xLights sequence file formats.
- **FR-007**: System MUST compute beat-alignment metrics using audio-derived beats from the source audio, with a tolerance of ±80 milliseconds for v0.
- **FR-008**: System MUST compute section-window metrics by imposing audio-derived section boundaries on both the pro and our outputs (generation-time sections are not used for measurement).
- **FR-009**: System MUST track the fraction of effect-type occurrences that fall outside the shared vocabulary between pro and our outputs, so histogram comparisons remain apples-to-apples without silently dropping data.
- **FR-010**: System MUST produce a defined numeric value for every metric on every input — including degenerate inputs (empty, monochrome, single-effect) — rather than raising errors.

**Comparison & reporting**

- **FR-011**: System MUST produce per-song comparison tables listing each metric with its pro value, our value, delta, and direction.
- **FR-012**: System MUST produce a cross-song trend summary that flags a metric as a "consistent gap" when the same-direction delta appears on at least 80% of comparable songs in the corpus.
- **FR-013**: For songs with two or more pro sequences, system MUST report intra-pro variance (min, max, range) per metric alongside the ours-vs-pro delta, and annotate deltas that fall within pro variance.
- **FR-014**: System MUST persist each report run to a timestamped file so reports can be compared over time.
- **FR-015**: System MUST skip corpus entries that cannot be measured (missing audio, unparseable sequence, unresolvable path, generator runtime failure) and list every skipped entry with its reason in the report. Skips MUST be categorized as either **corpus-side** (missing audio, unparseable pro file, unresolvable path) — non-failing as long as at least one entry was measurable — or **our-side** (generator raised an exception during metric extraction) — always CI-failing, even when other entries succeeded.

**Regression gating**

- **FR-016**: System MUST maintain a committed baseline of its own prior output metrics, separate from pro references.
- **FR-017**: System MUST provide a check mode that fails with a non-zero exit status and a per-metric diagnostic when any regression-gated metric moves beyond its tolerance from the baseline, unless the baseline has been intentionally updated in the same change. Each metric MUST declare its own tolerance as part of its definition; metrics that do not declare one MUST fall back to a conservative default tolerance applied uniformly.
- **FR-018**: Regression gating MUST apply only to own-baseline deltas. Pro deltas MUST NOT be CI-gated in v0.
- **FR-019**: System MUST run the generator with a fixed seed during metric extraction so cross-run differences reflect code changes rather than stochastic variation.

**Pathological-floor validation**

- **FR-020**: Every metric in the v0 set MUST be validated against degenerate reference outputs (monochrome palette, single-effect-everywhere, random/zero-alignment placements, empty sequence) and MUST score each degenerate case worse than every real corpus entry; any metric that fails this check MUST be removed from the gated set.

**Scope exclusions for v0**

- **FR-021**: System MUST NOT invoke xLights rendering or video analysis as part of any automated flow. Rendering may only be invoked by a human on explicit request.
- **FR-022**: System MUST NOT automatically tune generator parameters from metric deltas; all generator changes remain human-authored.

### Key Entities

- **Corpus manifest**: the ordered list of songs to measure, each entry referencing a pro sequence file, a source audio file, an audio hash, and human notes.
- **Corpus entry**: a single (song, pro sequence) pair; a song may have multiple entries when multiple pros have sequenced it.
- **Sequence summary**: the neutral, format-agnostic representation of a sequence file — placements with timing, effect type, model/group assignment, and palette — that every metric consumes.
- **Metric value**: a named numeric or structured value derived from a sequence summary plus optional audio analysis, with a definition that allows the same metric to be computed from pro and our outputs.
- **Report**: a timestamped snapshot of all metric values for all measurable corpus entries, plus cross-song trends and intra-pro variance statistics.
- **Baseline**: a committed snapshot of our generator's own metric values on the corpus, used as the comparison point for regression gating.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A maintainer can run the comparison report on the full corpus and receive a complete per-song table plus cross-song trend summary within 5 minutes of wall time.
- **SC-002**: The CI regression gate surfaces unintended metric drift on at least 90% of synthetic generator regressions injected as test fixtures (measured by a dedicated regression-detection test suite).
- **SC-003**: All metrics in the v0 set pass pathological-floor validation — each one scores every degenerate reference output worse than every real corpus entry.
- **SC-004**: The comparison report labels every ours-vs-pro delta with either "within pro variance" or "exceeds pro variance" for songs that have two or more pro sequences.
- **SC-005**: The harness runs to completion and produces a useful report when at least one corpus entry is measurable, even if up to 50% of entries are skipped for missing audio or unreadable files.
- **SC-006**: Maintainers can point to a specific "consistent gap" flagged in a report, propose a generator change to close it, and measure the effect of that change by re-running the comparison — end-to-end within a single working session.

## Assumptions

- **Corpus size is small and human-curated.** 6 songs / 9 pro sequences is acceptable for v0; statistical significance comes from the consistency threshold (≥80% same-direction across songs) rather than large N.
- **Audio files live outside the repo.** The repo only holds manifest pointers and notes; users manage their own audio on local disk.
- **Cached audio analysis is trustworthy.** The existing hash-keyed analysis cache (beats, energy curves, section boundaries) is reused for metric computation; the harness does not re-analyze audio on every run.
- **Human A/B validation is out of scope for v0.** Pro deltas remain informational signals; converting specific pro-delta metrics into regression gates is a future feature that depends on accumulated preference data.
- **Audio classifier determinism.** The section classifier and beat tracker produce identical output on identical audio across runs. If either has stochastic components, they must be seeded or their output cached by audio hash.
- **Layout mismatch is acceptable at song-level aggregates.** Per-prop-group metrics will differ between pro and our outputs for structural (not quality) reasons; only song-level aggregates are used for cross-system comparison, and per-group metrics remain in the ours-only regression set.
