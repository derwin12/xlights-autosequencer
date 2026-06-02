# Analyzer golden baseline

`baseline.json` is the reference snapshot the acceptance gate
(`xlight-evaluate gate`) compares live analyzer output against. It was
captured in the devcontainer (last committed 2026-04-25).

## Known environment-sensitive tracks (not regressions)

Two tracks legitimately drift against this baseline when the analyzer runs
in a **different container** than the one that produced it:

| track             | runs on stem | why it drifts                          |
|-------------------|--------------|----------------------------------------|
| `qm_onsets_phase` | `drums`      | demucs stem-separation variance        |
| `aubio_notes`     | `vocals`     | demucs stem-separation variance        |

These two are onset/note detectors that run on **demucs-separated stems**
(`preferred_stem`), not the full mix. demucs produces a slightly different
stem across torch/demucs versions and hardware, so onset/note times shift by
~100–200ms after roughly the first minute. The gate reports these as `timing`
violations (event #N vs #N), amplified by index-based comparison: a single
extra/missing onset cascades into many apparent drifts.

This is **environment variance, not a code or plugin regression.** Verified
2026-06-02:

- The Vamp plugin version is **not** the cause — `qm-vamp-plugins` built from
  the `qm-vamp-plugins-v1.8.0` tag and from `master` are byte-identical and
  produce identical onset output, both differing from the baseline.
- Every track that runs on the full mix or is rhythmically robust
  (`qm_bars`, `beatroot`, `segmentino`, `chordino`, `nnls_chroma`, …) matches
  the baseline within the 50ms tolerance.
- The generator suite passes.

### Reconciling if needed

Re-baseline **in the target environment** rather than chasing demucs parity:

```bash
xlight-evaluate snapshot-analyzer   # regenerates baseline.json here
```

A re-baseline ties the golden file to the current container's demucs/torch, so
only do it deliberately (e.g. when intentionally adopting a new stem model).
