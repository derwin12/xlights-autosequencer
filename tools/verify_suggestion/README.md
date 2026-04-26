# tools/verify_suggestion

Per-suggestion verification harness for show-improvement changes. One CLI
runs the full pipeline (regen .xsq → render FSEQ → render MP4 → compose +
metrics) and emits a side-by-side comparison MP4 plus a metrics JSON, so we
can tell whether a code change *actually* improved the rendered show or
was a no-op.

## Setup

One-time:

```bash
pip install -e ".[video]"        # scipy + zstandard for the metrics decoder
cd tools/render && ./build.sh    # builds the xlights-render Docker image
```

## Usage

```bash
python -m tools.verify_suggestion.run \
    --suggestion 21 \
    --slug qm-boundary-fix \
    --what-changed "Force min density on qm_boundary sections" \
    --why         "Was rendering at 5% brightness across 63% of song"
```

Outputs (under `docs/video-samples/`):

- `comparison_21_qm-boundary-fix.mp4` — side-by-side baseline vs. candidate
  with on-screen banner and "what / why" footer
- `candidate_21_qm-boundary-fix.mp4` — standalone candidate render
- `metrics_21.json` — per-metric deltas (lit pixels, motion, distinct colors,
  third-band activations) with a `noop: true|false` verdict
- `notes_21_qm-boundary-fix.md` — embeddable PR-body fragment

## Skip flags

The pipeline has two slow phases (Docker FSEQ render: ~3 min on Apple Silicon
under emulation; .xsq regeneration: ~1 min). Skip them when you only want to
re-compose the comparison:

```bash
# Reuse existing .xsq, skip generator step
python -m tools.verify_suggestion.run --suggestion 21 --slug ... \
    --skip-regen --what-changed ... --why ...

# Reuse existing .fseq + candidate.mp4, skip Docker + xlight-video
python -m tools.verify_suggestion.run --suggestion 21 --slug ... \
    --skip-render --what-changed ... --why ...
```

`--skip-render` implies `--skip-regen`.

## Verdict logic

A suggestion is flagged `noop: true` if every tracked metric is within
±5 % of baseline. The CLI prints a yellow warning and the PR author should
seriously consider reverting before opening a PR.

## Frozen baseline

`docs/video-samples/baseline.mp4` is the reference render (PR #120 v6 build).
Don't replace it casually — every metric delta in this folder is computed
relative to it. If you replace the baseline, every prior comparison MP4 in
the folder is now meaningless.
