# Analysis Pipeline Improvements — April 2026

This document captures an investigation into the accuracy of our section-boundary
detection and the resulting changes to the pipeline. It covers:

1. What we investigated and why
2. The diagnostic tooling added to score boundary quality
3. The three concrete improvements made to the pipeline
4. What we measured, what we left alone, and why
5. Follow-ups worth considering

## Motivation

The analysis pipeline has many independent boundary-detection sources (QM
segmenter, segmentino, librosa beats, madmom downbeats, stem-entry events,
energy impacts, chord-density spikes, Genius + WhisperX sections). They feed
into `src/story/builder.py`, which produces the `_story.json` that drives
effect generation downstream. Prior to this work we had no way to score how
well these sources *agreed* on boundaries, and no way to measure whether
parameter tweaks helped or hurt.

Two quality concerns prompted the investigation:

- **Genius section alignment was unreliable across songs.** Some songs
  correctly used Genius-sourced sections with WhisperX word alignment
  (`section_source: "genius"`), others silently fell back to the heuristic
  path. The cause was a mix of missing dependencies, firewall issues, and
  a broken title-sanitization rule.
- **QM segmenter was producing noisy over-segmentation.** On pop songs it
  often returned 16-22 boundaries where the human-perceived structure is
  8-12 sections.

## Diagnostic tooling added

Three new scripts live in `scripts/`:

### `scripts/boundary_confidence_map.py`

For a given song, extract boundaries from every source in `_hierarchy.json`
and `_story.json`, then cluster them within ±1 bar using single-linkage
clustering. Each cluster's *score* is the number of distinct sources that
agree on that boundary. Produces a text report plus an HTML timeline.

Sources currently aggregated:

- `qm_segmenter` — QM structural segmenter
- `segmentino` — segmentino structural segmenter
- `stem_entry:<stem>` — first vocal/drum/bass/guitar/piano/other entry per stem
- `energy_impact` / `energy_drop` — energy-curve transitions
- `chord_density_spike` — harmonic-rhythm bursts (N chord changes / 2 bars)
- `key_change` — tonal-centre shifts
- `genius` — lyric-structure boundaries (re-fetched for diagnostic comparison)
- `story` — final pipeline output (tagged as `story (genius)` or `story (heuristic)`)

The design insight: a boundary that multiple independent algorithms converge
on is more likely to be a real structural transition. We can score our final
pipeline output by how well it lands on high-agreement clusters.

### `scripts/qm_segmenter_sweep.py`

Sweeps the three QM-segmenter parameters — `nSegmentTypes`, `featureType`,
`neighbourhoodLimit` — across a grid (48 combos). For each combo, scores the
resulting QM boundaries against a baseline built from the *other* sources
(stem entries, segmentino, energy, key, chord, story). The fitness function
is "fraction of QM boundaries that land within ±1 bar of a ≥3-source
agreement cluster", penalised when the total boundary count drifts outside
a plausible 5-18 range.

### `scripts/self_similarity_prototype.py`

Beat-synchronous chroma + MFCC features → recurrence matrix (via
`librosa.segment.recurrence_matrix` + `path_enhance`) → diagonal-stripe
detection → grouped repetitions. Produces an SSM heatmap PNG + text report
aligning detected repetitions with story sections.

Intended as validation ("do the Genius-labeled choruses self-similar?") and
for sub-dividing long flat sections in instrumental songs. The prototype
finds real structural repetitions (e.g. on *Candy Cane Lane* it recovered
the full pre-chorus→chorus→post-chorus block repeating at 36.6s and
125.2s). Threshold tuning is needed before wiring it into the pipeline
— see *Follow-ups*.

## Pipeline changes

### 1. QM segmenter defaults (`src/analyzer/algorithms/vamp_structure.py`)

**Before:** `parameters = {}` (all defaults: nSegmentTypes=10, featureType=Hybrid, neighbourhoodLimit=4s).

**After:**
```python
parameters = {
    "nSegmentTypes": 5.0,
    "featureType": 1.0,       # Hybrid (Constant-Q)
    "neighbourhoodLimit": 6.0,
}
```

**Why.** Sweep results across 8 songs spanning pop, rock, EDM, classical, and
soundtrack:

| rank | nSegmentTypes | feature | nLim | mean score |
|---|---|---|---|---|
| 1 | 3 | Hybrid | 10s | 0.560 |
| 3 | 5 | Hybrid | 10s | 0.543 |
| **11** | **5** | **Hybrid** | **6s** | **0.478** |
| 37 (current) | 10 | Hybrid | 4s | 0.350 |

`nSegmentTypes=3` scored highest but caused two end-to-end regressions on
heuristic-path songs: *Let It Go* lost its intro label (became "bridge"),
*Excision remix* over-merged from 10 to 5 sections. `nSegmentTypes=5, 6s`
is ~37% better than defaults with **zero intro/outro regressions** on the
5 most-at-risk heuristic songs and identical role sequences on the 2
Genius-path songs tested.

**Conceptual note on `nSegmentTypes`.** This is a *clustering* parameter, not
a boundary count. QM clusters audio frames into `nSegmentTypes` feature
classes and marks boundaries at class transitions. The final section
*vocabulary* (verse/chorus/bridge/pre_chorus/post_chorus/outro/…) is
unaffected — section labels come from Genius (when available) or
`section_classifier.py` (heuristic path), never from QM's type letters.

The boundaries QM fails to find at any setting are boundaries it was never
capable of finding — lyric-distinguished (Chorus ↔ Post-Chorus, same music
different words) or vocal-entry-based (intro ↔ first verse, same backing
track plus vocals). Those are handled by Genius and `stem_entry:vocals`
respectively, which is the multi-source design working as intended.

### 2. WhisperX align-model fallback (`src/analyzer/genius_segments.py`)

Added `_load_align_model(language, device)` helper that tries torchaudio's
`WAV2VEC2_ASR_BASE_960H` first, then falls back to
`jonatasgrosman/wav2vec2-large-xlsr-53-english` on HuggingFace when the
torchaudio download fails (e.g. `download.pytorch.org` not in a firewall
allowlist, or the service is briefly unavailable).

Both call sites in the module now route through this helper. The torchaudio
model remains the primary (smaller, faster) and the fallback kicks in only
when the download errors out.

Also fixed `sanitize_title`: previously stripped "with" as a feature-credit
marker, which destroyed titles like "Down with the Sickness". The narrower
new rule only strips " with &lt;CapitalizedName&gt;…" at end-of-title.

### 3. Genius-subprocess hardening (`src/story/builder.py`)

Three robustness fixes in the `_try_genius_sections()` subprocess wrapper:

- **Timeout 120s → 600s.** First WhisperX run downloads models and sometimes
  exceeds 120s. Accompanied by a `TimeoutExpired`-specific error message
  that explains the cause.
- **`HF_HUB_DISABLE_XET=1`** in subprocess env. HuggingFace's Xet download
  client hangs intermittently in restricted-network environments; the
  stock HTTPS fallback works reliably.
- **`torch.load` monkey-patch** forcing `weights_only=False`. Torch 2.6
  flipped this default, which breaks pyannote/pytorch_lightning checkpoint
  loading (they pickle `ListConfig`, `DictConfig`, `typing.Any`, etc.).
  Models are from pinned trusted HF sources, so allowlisting every class
  via `add_safe_globals` would be higher-churn than this bounded patch.
- **Better error surfacing.** Previously, `ok: False` warnings from the
  subprocess were silently dropped; now they're printed with context so
  regressions surface in CI/local logs.

### 4. Devcontainer additions (`.devcontainer/`)

- `Dockerfile`: install `whisperx==3.3.0`, `nltk>=3.8`, re-pin `numpy<2`
  after whisperx installs (whisperx pulls numpy≥2 which breaks madmom's
  compiled Cython extensions), and pre-download `cmudict`.
- `devcontainer.json`: fix `XLIGHT_VENV_VAMP` from `/home/node/.venv-vamp/bin/python`
  (symlink to the system python with no ML deps) to
  `/workspace/.venv-vamp/bin/python` (the real venv with madmom/demucs/whisperx).
- `init-firewall.sh`: add `download.pytorch.org`, `cdn-lfs-us-1.huggingface.co`,
  `cas-bridge.xethub.hf.co`, and `hf.co` to the allowlist. These are required
  for WhisperX model downloads and the HF Xet download path.

## Measured results

### Genius coverage across the library

Before this work: 2 / 16 songs used Genius-aligned sections, 14 / 16 fell back
to heuristic. After: **11 / 16 use Genius**, 5 / 16 heuristic. All 5 remaining
heuristics are correct rejections:

- Carol of the Bells, First Snow — no Genius page (instrumentals)
- Let It Go — Genius page has only `[Elsa]` header, quality gate rejects `<3 sections`
- mad russian christmas — false Genius match, quality gate rejects
- Excision remix — remix structure ≠ source structure, quality gate rejects

### Agreement-score improvement from QM change

Aggregate across the 8 sweep test songs:

- Current defaults: mean score **0.350** (rank #37/48)
- New defaults (`nSeg=5, Hybrid, 6s`): mean score **0.478** (rank #11/48)

### End-to-end regression check

Re-ran full `analyze --fresh` + `story --force` pipeline on 7 songs (5 heuristic,
2 Genius). No intro/outro regressions. Section roles preserved in all cases.
Full comparison in the PR description.

## What we didn't ship, and why

- **`nSegmentTypes=3` (top sweep score)**: caused intro label loss on *Let It Go*
  and 10→5 over-merging on *Excision remix*. Precision gains on the sweep didn't
  account for recall loss in `section_classifier.py`.
- **Self-similarity matrix integration**: prototype works on some songs (Candy
  Cane Lane, First Snow's interlude sub-structure) but produces 0 groups on
  *Believe* at current threshold. Needs adaptive threshold tuning before it's
  dependable.
- **Per-section confidence score in `_story.json`**: would be useful for review
  UI but schema change has ripple effects into the review frontend and is a
  separate change.
- **Snap-to-cluster boundary refinement**: potentially lifts WhisperX drift
  (Candy Cane Lane's Verse 1 landed ~1.3s late because vocals sustain).
  Worth doing but not in this PR; the sweep win is a cleaner first step.

## Follow-ups

- **Tune SSM threshold** (auto or per-song) and add it as a validation signal
  for Genius-labeled Chorus sections.
- **Use SSM sub-division** for long heuristic "interlude" sections like First
  Snow's 180s block.
- **Snap-to-cluster**: for Genius path, snap each section boundary to the
  nearest ≥3-source cluster within ±1 bar. Fixes WhisperX drift on sustained
  vocals.
- **Expose per-section agreement score** in `_story.json` so review UI can
  highlight low-confidence sections for human attention.
- **Track mean agreement score as a regression metric** — one number across
  the whole library that catches pipeline regressions.
- **Improve the sweep fitness function** to penalise loss of Genius boundaries
  and loss of existing intro/outro roles (would let us ship `nSegmentTypes=3`
  cleanly, or show why we shouldn't).
