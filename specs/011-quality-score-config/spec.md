# Feature Specification: Configurable Quality Scoring

**Feature Branch**: `011-quality-score-config`
**Created**: 2026-03-22
**Status**: Draft
**Input**: User description: "Configurable quality scoring with explainable breakdowns and user profiles"

## Overview

The current quality scoring system (`scorer.py`) produces a single opaque number per timing track. Users cannot see why a track scored high or low, cannot tune scoring to match their genre or display type, and cannot save preferences for reuse. This feature replaces the black-box score with an explainable, configurable scoring system: each track receives a per-criterion breakdown showing what was measured and how it contributed to the final score. Users can adjust criterion weights and thresholds via configuration files, and save tuned settings as named profiles.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Explainable Score Breakdowns (Priority: P1)

A lighting designer runs analysis and sees that their preferred drum track scored lower than an onset track they find musically uninteresting. They request score details and see a per-criterion breakdown — density, regularity, mark count, coverage — with plain-language descriptions. Now they understand the drum track was penalized for irregular spacing and can decide whether to override the ranking.

**Why this priority**: A black-box score breeds distrust. Explainability is what makes scoring a tool rather than a gatekeep. Users need this before they can meaningfully configure scoring.

**Independent Test**: Run `xlight-analyze analyze song.mp3`, then run `xlight-analyze summary song_analysis.json --breakdown` and verify each track shows per-criterion scores with descriptions.

**Acceptance Scenarios**:

1. **Given** a completed analysis run, **When** the user requests score details for a track, **Then** the output shows each scoring criterion with its measured value, weight, score contribution, and a plain-language description.
2. **Given** two tracks with different scores, **When** the user compares their breakdowns, **Then** the specific criteria producing the score difference are identifiable.
3. **Given** a track that scores well on density but poorly on regularity, **When** the breakdown is shown, **Then** those two dimensions are reported separately rather than collapsed into a single number.

---

### User Story 2 — Adjust Scoring Weights and Thresholds (Priority: P1)

A user lighting a song with a fast, busy arrangement wants denser timing tracks. Another user lighting ambient music wants sparser tracks. Both configure criterion weights so the auto-selected top tracks match their aesthetic preference without manual track selection every time.

**Why this priority**: Default scoring is optimized for a generic case. Different music genres, display types, and user preferences require different definitions of "good."

**Independent Test**: Create a scoring config that doubles the density weight, run analysis, and verify that denser tracks now rank higher than under default weights.

**Acceptance Scenarios**:

1. **Given** a configuration that increases the weight of track density, **When** analysis runs and tracks are scored, **Then** denser tracks rank higher than they did under default weights.
2. **Given** a configuration that sets a minimum mark count threshold, **When** tracks are scored, **Then** tracks below the threshold are excluded from the ranked output regardless of other score components.
3. **Given** default configuration (no user config file), **When** analysis runs, **Then** scoring results are identical to the current pre-configuration baseline.
4. **Given** an invalid scoring configuration (weight outside valid range, unknown criterion name), **When** analysis starts, **Then** the tool rejects it with a descriptive error before running any analysis.
5. **Given** a configuration that adjusts the target density range for the "beats" category, **When** beat tracks are scored, **Then** they are evaluated against the customized target rather than the built-in default.

---

### User Story 3 — Save and Share Scoring Profiles (Priority: P2)

A user who has tuned scoring weights for a particular genre or display type saves those settings as a named profile. They can reuse the profile across sessions, share it with other users, or switch between profiles for different projects.

**Why this priority**: Without profiles, users must re-enter their preferences each session. Profiles make customization persistent and portable.

**Independent Test**: Save a scoring profile, re-run analysis using the profile name, and verify identical scoring results.

**Acceptance Scenarios**:

1. **Given** a customized scoring configuration, **When** the user saves it as a named profile, **Then** running analysis with that profile name applies the saved settings.
2. **Given** a scoring profile file, **When** it is loaded on a different machine, **Then** it produces identical scoring results for the same input tracks.
3. **Given** multiple saved profiles, **When** the user lists available profiles, **Then** all saved profiles are shown with their names and a summary of how they differ from defaults.

---

### Edge Cases

- A configuration where all weights are zero — scoring should reject this with a clear error rather than producing undefined results.
- A configuration where thresholds eliminate all tracks — the system should warn the user and still output the full track list (unranked) rather than an empty result.
- Scoring a track that has zero timing marks — the score should be 0 with the breakdown showing why.
- A profile that references a scoring criterion that does not exist (typo or version mismatch) — should fail with an error naming the unknown criterion.
- A profile that references an unknown scoring category — should fail with an error.
- Negative weights — should be rejected as invalid.
- An algorithm not assigned to any category — should fall back to a "general" default category with broad target ranges.
- All 22 tracks are near-identical (e.g., a song where every algorithm converges on the same beats) — the diversity filter should still select `--top N` tracks, choosing the highest-scoring representative from each similarity cluster.
- Diversity filter with a very low threshold (e.g., 10%) — effectively disables deduplication; all tracks are considered unique.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every scored track MUST include a per-criterion breakdown in the output, showing the measured value, weight, score contribution, and a plain-language label for each criterion.
- **FR-002**: The scoring system MUST expose at minimum five criteria: mark density (marks per second), regularity (consistency of inter-mark intervals), total mark count, coverage (fraction of song duration containing marks), and minimum gap compliance (proportion of inter-mark intervals at or above the minimum actionable threshold).
- **FR-002a**: Consecutive timing marks closer than 25 ms apart MUST be treated as a scoring defect. The scoring system MUST include a **minimum gap** criterion that penalizes tracks with a high proportion of sub-25 ms intervals, since lighting controllers cannot execute changes faster than ~25 ms.
- **FR-002b**: Each algorithm MUST belong to a scoring category that defines expected target ranges for each criterion. Categories include at minimum: beats (high density, high regularity), bars (moderate density, high regularity), onsets (high density, low regularity), segments/structure (very low density), pitch (moderate density), and harmony (low density).
- **FR-002b**: Scoring MUST evaluate each track relative to its category's target ranges rather than a single global target. A segment track with 12 marks and a beat track with 300 marks can both score high if they meet their respective category expectations.
- **FR-002c**: Users MUST be able to customize category target ranges in the scoring configuration, overriding the built-in defaults.
- **FR-003**: Users MUST be able to configure the weight of each scoring criterion via a configuration file.
- **FR-004**: Users MUST be able to set minimum and maximum thresholds for any scoring criterion; tracks outside thresholds are excluded from ranked output.
- **FR-005**: The configuration file schema MUST be self-documenting — including valid ranges, defaults, and descriptions for each criterion.
- **FR-006**: Scoring configurations MUST be saveable as named profiles on the filesystem.
- **FR-007**: Default scoring behavior MUST be preserved when no custom configuration is provided — existing analysis results MUST remain comparable.
- **FR-008**: Invalid configurations (unknown criteria, out-of-range weights, all-zero weights) MUST be rejected with descriptive errors before analysis runs.
- **FR-011**: When auto-selecting top tracks (`--top N`), the system MUST apply a diversity filter: if a candidate track is near-identical to an already-selected track (high proportion of marks aligning within a configurable time tolerance), it MUST be skipped in favor of the next-highest-scoring unique track.
- **FR-012**: The similarity tolerance (time window for mark matching) and similarity threshold (percentage of matching marks that constitutes "near-identical") MUST be configurable in the scoring configuration.
- **FR-013**: The summary output MUST indicate when a track was skipped due to redundancy, showing which selected track it duplicates.
- **FR-009**: The summary command MUST support a breakdown view showing per-criterion scores for each track.
- **FR-010**: Score breakdowns MUST be included in the analysis JSON output for use by the review UI.

### Key Entities

- **ScoringCategory**: A grouping of algorithms with shared scoring expectations. Has a name (e.g., "beats", "bars", "onsets", "segments", "pitch", "harmony"), a description, and target ranges for each scoring criterion (expected density, expected mark count range, expected regularity range, expected coverage range). Each algorithm belongs to exactly one category.
- **ScoringCriterion**: A single measurable dimension of track quality. Has a name, plain-language description, measured value, category target range, weight, and score contribution. The score contribution reflects how well the measured value falls within the category's expected range.
- **ScoreBreakdown**: The full per-track scoring result. Contains the overall score, a list of ScoringCriteria with values and contributions, and pass/fail threshold results.
- **ScoringConfig**: A user-defined configuration specifying criterion weights, optional thresholds, category target overrides, and diversity filter settings (similarity tolerance and threshold). Can be loaded from a file or use built-in defaults.
- **ScoringProfile**: A named, saved ScoringConfig stored on the filesystem for reuse.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user who disagrees with a track's ranking can identify the specific scoring criterion responsible by reading the breakdown alone, without inspecting code.
- **SC-002**: Adjusting a single criterion weight changes the ranking of at least one track in a reference test set in the expected direction.
- **SC-003**: All scoring criteria, their default weights, and valid ranges are discoverable from the tool's output without reading source code.
- **SC-004**: Custom scoring profiles produce identical results across machines and sessions when the same profile and input are used.
- **SC-005**: Default scoring (no config file) produces results identical to the current baseline scorer output.

## Assumptions

- The current scorer uses density and regularity as primary criteria; these become the first configurable criteria in this feature.
- Each of the 22 algorithms is assigned to one scoring category based on its output type. The built-in category assignments and target ranges serve as sensible defaults; users can override both in configuration.
- Score breakdowns are added to the existing JSON output structure as a new field on each track, not a separate file.
- "Plain-language labels" means a short human-readable description string per criterion (e.g., "Mark density — number of timing marks per second of audio").
- Scoring criteria are a fixed set (density, regularity, mark count, coverage). Extensibility via plugins is out of scope.
- Default diversity filter settings: similarity tolerance of ±50 ms (marks within this window count as matching), similarity threshold of 90% (tracks with ≥90% matching marks are considered near-identical). Both are configurable.
- The minimum actionable gap is 25 ms — this is a hardware constraint of lighting controllers. Marks closer than 25 ms apart cannot produce distinct visible effects. The default minimum gap threshold is 25 ms and is configurable (users with faster controllers could lower it).
- Criterion weights are always a weighted sum — no AND/OR threshold logic combinations.
- Profiles are stored as files in a well-known directory (e.g., `~/.config/xlight/profiles/` or a project-local `.scoring/` directory).

## Out of Scope

- Machine learning-based scoring or scoring that learns from user feedback.
- A graphical interface for score configuration (may be added to the review UI in a future feature).
- Automatic scoring profile recommendation based on genre detection.
- User-defined custom scoring criteria via plugins or scripts.
- AND/OR Boolean threshold logic between criteria.
