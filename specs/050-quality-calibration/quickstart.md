# Quickstart: Quality Calibration Harness

Walkthrough for a maintainer setting this up for the first time and running the full loop once.

## Prereqs

- `pip install -e .` in the project root (adds the `xlight-evaluate` console script).
- Pro sequences under `/home/node/xlights/baseline-sequences/` (already present).
- Matching MP3s for each corpus entry on local disk. For missing MP3s, the entry is skipped; not fatal.

## 1. Build the manifest

Create `tests/golden/pro_reference/manifest.json` referencing every `(song, pro)` pair you want in the corpus. Use one notes file per unique song.

```bash
mkdir -p tests/golden/pro_reference/notes
$EDITOR tests/golden/pro_reference/manifest.json
```

Example entry — see `data-model.md` §Manifest entry for the full schema. Minimum:

```json
{
  "entries": [
    {
      "song_id": "light-of-christmas",
      "pro_id": "xatw",
      "xsq_path": "/home/node/xlights/baseline-sequences/Light Of Christmas XATW.xsq",
      "mp3_path": "/home/node/xlights/baseline-sequences/02 - Light Of Christmas [feat. Owl City].mp3",
      "audio_hash": "md5:TBD",
      "tags": ["christmas", "pop"],
      "notes_ref": "notes/light-of-christmas.md",
      "master_may_differ": false
    }
  ]
}
```

Compute `audio_hash` once: `md5sum <mp3_path>` and prefix with `md5:`. The harness verifies on every run and warns if the on-disk file changed.

## 2. First compare run

```bash
xlight-evaluate compare
```

This will:
- Run our generator on each unique `song_id` (fixed seed from audio hash).
- Parse every pro `.xsq`/`.xsqz`.
- Compute 9 metrics for each sequence; compute intra-pro variance for songs with multiple pros; flag consistent cross-song gaps.
- Write `tests/golden/reports/<iso>.json` and print a terminal summary.

First run is slower if stem separation hasn't run yet — expect 7-10 minutes for 6 songs on the first pass. Subsequent runs use cached stems and finish in under 2 minutes per song.

## 3. Commit the first baseline

Inspect the report. If ours output looks reasonable:

```bash
xlight-evaluate snapshot
git add tests/golden/pro_reference/manifest.json \
        tests/golden/pro_reference/notes/ \
        tests/golden/baseline.json
git commit -m "chore(eval): bootstrap quality calibration corpus + baseline"
```

From this commit forward, every PR runs `xlight-evaluate check` in CI.

## 4. Iteration loop

When you change generator code:

```bash
xlight-evaluate check
```

- Exit `0`: no gated-metric regressions; ship it.
- Exit `6`: the regressions are listed with `(song, metric, baseline, current, delta, tolerance)`. Either fix the generator or, if the change is intentional:

```bash
xlight-evaluate snapshot --force
git add tests/golden/baseline.json
# Include in the same commit/PR as the code change.
```

Reviewers see the baseline diff next to the code diff and can judge whether the metric shift is desired.

## 5. Finding tuning targets (ongoing)

`compare` surfaces "consistent gap" trends — metrics where ours differs from pros in the same direction on ≥ 80% of songs. These are your menu of experiments. Pick the biggest gap, change one generator parameter, rerun `compare`, see if the gap narrowed without triggering regressions on the gated metrics.

## Troubleshooting

- **`exit 4 — No baseline committed`**: first-time setup. Run `snapshot`, commit, done.
- **`exit 5 — baseline schema version mismatch`**: the metric set changed. Follow the printed migration message (usually: re-run `snapshot` to regenerate).
- **Generator error on one song**: exit `3`. The song is listed with the exception summary. Fix the generator or file a bug — our-side skips are never silently tolerated.
- **Intra-pro variance looks wrong**: multiple pros on same song are expected to differ; the variance range is the baseline for "artistic noise." If our delta is within it, stop chasing the gap.
- **`master_may_differ=true` entries show `reliability: reduced`**: expected. Beat-alignment and section-transition metrics are less trustworthy when the pro's source master differs from yours.
