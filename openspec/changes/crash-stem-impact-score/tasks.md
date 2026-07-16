# Tasks: crash-stem impact score

- [x] 1. `src/analyzer/drum_stems.py`: cymbal separation via drumsep
      checkpoint (`49469ca8.th`, auto-downloaded from Google Drive with
      confirm-form handling; torch>=2.6 needs `safe_globals([HDemucs])`);
      cache as `.stems/<md5>/drums_cymbals.mp3`; None on any unavailability.
- [x] 2. Validated local cymbal-stem quality on Dream On: 5/6 confirmed
      crashes (163.5s rides a tom fill drumsep routes to toms/snare —
      accepted miss). >=4kHz band on the platillos stem required to match
      the reference-stem ranking.
- [x] 3. Rewrote `detect_crash_accents` (isolation x wash-area, post-scoring
      min-gap shrunk to 3s — the confirmed 122/125s pair is 3s apart, cap 6
      per user decision, normalization distribution from all ordinary peaks
      so a lone crash isn't normalized against itself). Rewrote
      `tests/unit/test_crash_accents.py` (9 tests) + new
      `tests/unit/test_drum_stems.py` (10 tests).
- [x] 4. Orchestrator wiring: Stage 8 drums-stem -> cymbals -> detector;
      `crash_accents` .xtiming layer (700ms fixed width); SCHEMA_VERSION
      "2.1.0"; six `== "2.0.0"` readers -> `is_hierarchy_schema()` 2.x check.
- [x] 5. Panel sweep (6 local songs): floor 7.0 final — 6/3/2/1/0/0 marks;
      Dream On confirmed crashes 7.51-10.61 vs 6.17 first non-confirmed.
- [x] 6. End-to-end: fresh analysis + generation on Dream On, crash
      Shockwaves on `01_BASE_All_FADES` outside the fade window.
- [ ] 7. `xlight-evaluate gate` full analyzer tier + `snapshot-analyzer`
      reconciliation in the devcontainer (unit/generator suites green on
      the Windows host; analyzer golden tier needs .venv-vamp). CLAUDE.md,
      buglog (bug-265/266 fixes), cerebrum updated.
