# Requirements Checklist: 037 Duration Scaling

Verified against spec.md on 2026-04-09.

## Spec Structure

- [x] Spec contains User Scenarios & Testing section
- [x] Spec contains Requirements section with Functional Requirements
- [x] Spec contains Requirements section with Key Entities
- [x] Spec contains Success Criteria section with Measurable Outcomes
- [x] Spec contains Assumptions section
- [x] Spec contains Relationship to Other Phases section

## User Stories

- [x] All user stories have assigned priorities (P1/P2/P3)
- [x] Each user story has a "Why this priority" explanation
- [x] Each user story has an "Independent Test" description
- [x] Each user story has acceptance scenarios in Given/When/Then format
- [x] User stories are ordered by priority (P1 first)
- [x] Each user story is independently testable as a standalone slice
- [x] At least one P1 story covers the fast-song (high BPM) case
- [x] At least one P1 story covers the slow-song (low BPM) case
- [x] At least one P1 story covers the mid-tempo interpolation case
- [x] Energy modulation within a song is addressed (US4)
- [x] Fade timing proportional to duration is addressed (US5)
- [x] Independent toggle/disable is addressed (US6)
- [x] Edge case for bimodal/mixed-character songs is addressed (US7)

## Edge Cases

- [x] BPM detection failure or extreme values handled (clamp to bounds)
- [x] Zero energy score handled (default fallback)
- [x] No detected sections handled (single-section fallback)
- [x] Half-time / double-time BPM detection noted as out of scope
- [x] Fixed duration_type effects (Faces/lip-sync) exempt from scaling

## Functional Requirements

- [x] FR-001: Target duration range derived from BPM + energy
- [x] FR-002: High BPM (>120) produces median under 1 second
- [x] FR-003: Low BPM (<80) produces median 1.5-4s, zero sub-250ms
- [x] FR-004: Mid BPM (80-120) scales continuously between extremes
- [x] FR-005: Section energy modulates BPM baseline
- [x] FR-006: BPM+energy mapping is continuous and monotonic
- [x] FR-007: Fade times scale proportionally with duration
- [x] FR-008: Fixed duration_type effects are exempt
- [x] FR-009: Duration scaling is independently toggleable
- [x] FR-010: Duration targets clamped to safe bounds (250ms-8s)
- [x] FR-011: Per-effect duration behavior hints supported (standard/sustained/accent)
- [x] Every FR is testable (has a corresponding acceptance scenario or success criterion)

## Key Entities

- [x] DurationStrategy entity defined (BPM+energy to duration range)
- [x] DurationBehavior entity defined (per-effect classification)
- [x] FadeProfile entity defined (duration-proportional fades)
- [x] Entities are described without implementation details

## Success Criteria

- [x] SC-001: Measurable metric for high-BPM songs (median <1s)
- [x] SC-002: Measurable metric for low-BPM songs (median 1.5-4s, zero sub-250ms)
- [x] SC-003: Measurable metric for mid-BPM continuous scaling
- [x] SC-004: Measurable metric for energy-driven contrast within a song (30% shorter)
- [x] SC-005: Measurable metric for fade proportionality (0-40% of duration)
- [x] SC-006: Measurable metric for toggle-off baseline identity
- [x] SC-007: No regression when disabled
- [x] SC-008: Analyzer comparison against reference sequences
- [x] All success criteria are technology-agnostic
- [x] All success criteria reference concrete numbers or ranges

## Stakeholder Readability

- [x] Spec uses plain language suitable for non-technical stakeholders
- [x] No programming language, framework, or API names appear in requirements
- [x] No implementation details (data structures, algorithms, file formats) in requirements
- [x] Reference analysis data is cited to justify thresholds and targets

## Relationship to Other Phases

- [x] Identified as Phase 2 of 5
- [x] Phase table lists all 5 phases with dependencies
- [x] Independence from Phase 1 is stated
- [x] Complementary benefits with Phase 1 are explained
- [x] Downstream benefit to Phase 4 is noted

## Traceability

- [x] Every P1 user story maps to at least one FR
- [x] Every FR maps to at least one SC
- [x] US1 (fast songs) traces to FR-002, SC-001
- [x] US2 (slow songs) traces to FR-003, SC-002
- [x] US3 (mid-tempo) traces to FR-004, SC-003
- [x] US4 (energy modulation) traces to FR-005, SC-004
- [x] US5 (fade timing) traces to FR-007, SC-005
- [x] US6 (toggleable) traces to FR-009, SC-006, SC-007
- [x] US7 (bimodal) traces to FR-011
