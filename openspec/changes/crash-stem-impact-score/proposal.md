# Proposal: crash-stem impact score

## Why

The rare whole-house crash-accent feature (shipped 2026-07-14, recalibrated
2026-07-15) has never placed a single effect in any of the user's generated
sequences. Diagnosis on 2026-07-16 (bug-265, bug-266) found two independent
failures, plus a validated better detector design:

1. **Silent stale-cache skip (bug-265).** `SCHEMA_VERSION` stayed `"2.0.0"`
   when the `crash_accents` field was added, so hierarchy caches analyzed
   before 2026-07-14 still validate; `HierarchyResult.from_dict` defaults the
   missing field to `[]` and `plan.py:319` silently skips placement. All 7
   generated Dream On `.xsq` files — including ones generated after the
   feature shipped — contain zero crash effects.

2. **Detector misbehaves on the real audio (bug-266).** Run fresh on the
   actual generation audio (`dream-on...mp4`), the shipped full-mix treble
   detector returns 5 marks at 62.3/110.1/126.4/174.5/186.3s — none at the
   user's flagged 190.2s crash. Root cause: the 10s minimum gap is applied
   inside `find_peaks` candidate-picking, so a stronger nearby peak (186.31s,
   6.29x) suppresses the true crash before scoring. The "single 6.17x
   standout" from the original validation also does not reproduce on this
   rip (5 candidates clear the 6.0x floor), so the calibration was overfit
   to a specific audio file.

3. **A validated redesign exists.** Prototyping on user-supplied drum-kit
   stems (2026-07-16) showed that scoring envelope peaks on a
   *cymbal-isolated stem* by `log1p(isolation) x log1p(wash_area)` ranks all
   6 user-confirmed Dream On crashes (51.1, 103.7, 122.0, 125.0, 163.5,
   190.2s) as the top 6 candidates with a clean score gap below them —
   including the 50.85s crash the shipped design formally accepted as
   undetectable. The same scoring on the plain full-kit drums stem or the
   full mix fails (misses, false positives, no gap); on a combined
   crash+ride+hihat cymbals stem it ranks 5 of 6 in the top 5. Cymbal-level
   separation is the enabling ingredient.

## What changes

- Rewrite `detect_crash_accents` internals: isolation-scored envelope
  analysis on a cymbals stem, with the min-gap constraint moved from
  candidate-picking to post-scoring output selection. Keeps the cold-open
  full-mix pre-RMS guard, the hard 5-mark cap, and the rare-by-design
  absolute score floor (most songs still get zero marks).
- New `src/analyzer/drum_stems.py`: cymbal separation stage chained on the
  existing demucs drums stem (drumsep-class checkpoint via the existing
  demucs dependency; no new pip package in round 1), cached in
  `.stems/<md5>/`. Graceful degradation: no cymbals stem -> no crash marks.
- Bump hierarchy `SCHEMA_VERSION` to `"2.1.0"` so pre-feature and
  broken-detector caches re-analyze, and fix the six brittle hard-coded
  `== "2.0.0"` reader checks to accept any `2.x` (major-version check via
  the existing `src/schema_check.py` helpers).
- Expose the marks as a derived L0 timing track (same pattern as
  `eighth_notes`) so crashes are visible in the review UI and exports.
- Generator side (`_place_crash_accents`, `GenerationConfig.crash_accents`,
  `SequencePlan.crash_effects`) is unchanged.

## Impact

- Affected specs: analyzer hierarchy schema (2.0.0 -> 2.1.0), stems cache
  layout (new cymbals file), crash-accent detection semantics.
- Affected code: `src/analyzer/` (crash_accents, orchestrator, new
  drum_stems), `src/cli/review.py`, `src/cli_old.py`, `src/review/server.py`
  (schema readers only), tests.
- All hierarchy caches re-analyze on next use (intended — they either lack
  the field or carry the broken detector's marks).
