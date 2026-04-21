# Contract: `xlight-evaluate compare`

## Purpose

Run our generator against every measurable corpus entry, extract metrics from both pro(s) and ours, and emit a report (User Story 2).

## Invocation

```bash
xlight-evaluate compare [--corpus PATH] [--json] [--song SONG_ID ...]
```

## Arguments

- `--corpus PATH` — optional. Directory containing `manifest.json`. Defaults to `tests/golden/pro_reference/`.
- `--json` — optional flag. When set, suppresses terminal summary and emits only the JSON report path on stdout.
- `--song SONG_ID` — optional, repeatable. Limit the run to the listed `song_id`s (useful for iteration on a single song).

## Behavior

1. Load manifest; resolve paths; compute audio hashes; classify skips (see [data-model.md](../data-model.md) §Manifest entry).
2. For each unique `song_id` that is measurable, invoke the generator via `generator_runner.run(song_id, seed=<derived from audio hash>)`. Capture its in-memory `.xsq` bytes. If the call raises, record a **our-side skip** and continue.
3. Parse each pro `.xsq`/`.xsqz` and the in-memory ours `.xsq` bytes into `SequenceSummary`s.
4. Compute every registered metric against each summary, reusing the cached audio analysis for the song.
5. Assemble `Report` (see [data-model.md](../data-model.md) §Report), compute intra-pro variance and cross-song trends, write to `tests/golden/reports/<iso>.json`, and render a terminal summary unless `--json` was set.

## Exit codes

- `0` — report written; every measurable entry produced metrics on both sides. Corpus-side skips are permitted.
- `2` — no corpus entry was measurable (every entry skipped). Fatal.
- `3` — one or more our-side (generator error) skips occurred. Report is still written; exit non-zero so CI fails. (Spec FR-015 clarification.)
- `1` — usage error (bad args, manifest unreadable).

## Output (stdout, non-`--json`)

```
xLights Quality Calibration — compare
  Corpus: tests/golden/pro_reference (6 songs, 9 pro sequences)
  Measured: 5 songs   Skipped: 1 (corpus-side)

Song: light-of-christmas  (3 pro takes)
  metric                            pro(min..max)    ours     Δ-vs-pro-mean  [reliability]
  placements_per_minute             38.0 .. 44.1     71.2     +70%  ⚠ exceeds pro variance
  palette_top5_colors               …               …         JS=0.18  within-variance
  …

Cross-song trends (≥80% consistent):
  placements_per_minute: ours>pro on 5/6 songs  (consistent gap)
  effect_type_histogram: JS≥0.15 on 4/6 songs   (not consistent)

Report: tests/golden/reports/2026-04-15T14-33-12Z.json
```

## Acceptance criteria (mapped from spec)

- **US2-AS1** — Report lists per-song `metric | pro | ours | delta | direction` for every comparable metric and every pro entry.
- **US2-AS2** — Cross-song summary flags `consistent_gap: true` when ≥ 80% of comparable songs move the same direction.
- **US2-AS3** — For songs with ≥ 2 pro entries, `intra_pro_variance` block is populated.
- **US3-AS1** — Corpus entries with missing MP3 are listed as `skips[].category = "corpus-side"`, other songs measured normally.
- **US3-AS3** — For entries with `master_may_differ=true`, audio-dependent metrics carry `reliability: "reduced"`.
- **US4-AS1** — Songs with ≥ 2 pro entries show min/max/range per metric.
- **US4-AS2** — Deltas within intra-pro range rendered as `within-variance`; deltas exceeding it as `exceeds pro variance`.
