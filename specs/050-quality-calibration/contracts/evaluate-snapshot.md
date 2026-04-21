# Contract: `xlight-evaluate snapshot`

## Purpose

Regenerate `tests/golden/baseline.json` from a fresh run of the generator across the full corpus. Authoritative way to record a new own-baseline after an intentional change.

## Invocation

```bash
xlight-evaluate snapshot [--corpus PATH] [--baseline PATH] [--force]
```

## Arguments

- `--corpus PATH` — optional. Defaults to `tests/golden/pro_reference/`.
- `--baseline PATH` — optional. Defaults to `tests/golden/baseline.json`.
- `--force` — optional. Overwrite even if current baseline would regress gated metrics without the flag. Without `--force`, snapshot runs `check` first and refuses to write if `check` would fail, unless the user passes `--force` to acknowledge the intentional change.

## Behavior

1. Run the generator on every unique `song_id` in the manifest that is measurable (same seed derivation as `compare` / `check`).
2. Skip any corpus-side-unmeasurable song but continue with the rest.
3. Our-side (generator error) skips abort the snapshot with exit `3` — baselines must be captured from a clean generator run.
4. Without `--force`, if the new metrics would fail `check`, print the regressions and exit `8`. With `--force`, write the baseline anyway.
5. Write the new baseline to the target path, overwriting any existing file. Include `generator_commit` (from `git rev-parse HEAD`), `generated_at`, and the current schema version.

## Exit codes

- `0` — baseline written.
- `3` — our-side generator skip; baseline not written.
- `8` — baseline would regress and `--force` was not given.
- `1` — usage error.

## Output (stdout)

```
xLights Quality Calibration — snapshot
  Corpus: tests/golden/pro_reference  (6 songs, 9 pro sequences)
  Generating metrics for 6 songs...
  Check preview: 2 metrics would regress.
  Add --force to accept these changes; see diff below:
    light-of-christmas · placements_per_minute   baseline=52.1 → current=61.3  (+17.6%)
    danger-zone · beat_alignment_pct             baseline=72%  → current=68%   (-4pp)
```

On `--force`:

```
  Wrote tests/golden/baseline.json  (6 songs, 9 gated metrics × songs = 54 values)
  Remember to commit both code change and baseline in the same change.
```

## Acceptance criteria

- Refuses to silently overwrite a baseline that would hide a regression unless the user opts in via `--force`.
- Preserves determinism: running `snapshot` twice in a row produces byte-identical `baseline.json` (modulo `generated_at` / `generator_commit`).
- `check` immediately after `snapshot` must exit 0.
