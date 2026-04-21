# Contract: `xlight-evaluate check`

## Purpose

CI-gated regression check against the committed own-baseline (User Story 1).

## Invocation

```bash
xlight-evaluate check [--corpus PATH] [--baseline PATH]
```

## Arguments

- `--corpus PATH` — optional. Defaults to `tests/golden/pro_reference/`.
- `--baseline PATH` — optional. Defaults to `tests/golden/baseline.json`.

## Behavior

1. Load `baseline.json`. If missing, exit code `4` with message: *"No baseline committed. Run `xlight-evaluate snapshot` to create one, review the output, and commit `tests/golden/baseline.json`."*
2. If `baseline.schema_version` != current schema version, exit `5` with migration guidance.
3. Run the same generator pass as `compare` (same fixed seed derivation) to produce current metrics for every song in the baseline.
4. For each `song_id` in both baseline and current: walk each gated metric and apply its declared tolerance (see [data-model.md](../data-model.md) §MetricDefinition). Any violation is collected.
5. An our-side skip (generator error) is always a gate failure.
6. Song-count mismatches between baseline and current — any such mismatch is a failure unless the current commit also modifies `tests/golden/baseline.json` (detected via `git diff --name-only HEAD~1 HEAD` when run in CI; locally this check is skipped with a warning).

## Exit codes

- `0` — all gated metrics within tolerance; same song set as baseline; no our-side skips.
- `3` — one or more our-side skips (generator errors).
- `6` — one or more gated metric regressions.
- `7` — song-count mismatch without baseline update in same commit.
- `4` — baseline missing.
- `5` — baseline schema version mismatch.
- `1` — usage error.

## Output (stdout)

On success:

```
xLights Quality Calibration — check
  Baseline: tests/golden/baseline.json  (schema v1, generated 2026-04-15)
  Songs checked: 6 / 6
  All gated metrics within tolerance. ✅
```

On regression:

```
xLights Quality Calibration — check — FAILED
  Baseline: tests/golden/baseline.json  (schema v1)
  Songs checked: 6 / 6
  Regressions:
    light-of-christmas · palette_top5_colors
      baseline: [("#FFFFFF", 0.42), ("#FF0000", 0.18), ...]
      current:  [("#FFFFFF", 0.31), ("#FF0000", 0.29), ...]
      tolerance: 10% relative on top-color share  — violated
    danger-zone · tier_utilization (section chorus_2)
      baseline: 0.82   current: 0.65   Δ: -0.17   tolerance: ±0.05  — violated

  If these changes are intentional, run `xlight-evaluate snapshot` and
  commit the updated baseline in the same change.
```

## Acceptance criteria (mapped from spec)

- **US1-AS1** — Baseline matches current code → exit 0.
- **US1-AS2** — Deliberate generator change → check fails until baseline.json is updated in the same change.
- **US1-AS3** — Unintended side effect on an unrelated metric → check fails and names the specific metric.
- **SC-002** — Synthetic regression fixtures under `tests/evaluation/test_regression_detection.py` must trigger exit code `6` on ≥ 90% of injected regressions.
- Edge case *"first-ever run with no baseline committed"* → exit `4` with actionable message.
