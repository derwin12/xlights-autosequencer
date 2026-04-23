# Section confidence scores + Genius snap-to-cluster — April 2026

Follow-on to [analysis-pipeline-improvements-2026-04.md](analysis-pipeline-improvements-2026-04.md).
Addresses two of the items flagged there as "worth doing next":

1. **Snap-to-cluster boundary refinement** — fix the systematic 1-3s drift
   in Genius + WhisperX section boundaries on sustained vocals.
2. **Per-section agreement score** — expose how many independent sources
   corroborate each section's start boundary.

Plus a follow-up tool:

3. **Library-wide fidelity score** — a single regression metric tracking
   overall section-boundary quality across the song library.

## What the change does

### 1. Shared clustering module

`src/analyzer/boundary_cluster.py` is new. It holds the logic previously
duplicated in `scripts/boundary_confidence_map.py`:

- `Boundary` / `AgreementCluster` data classes
- Source extractors: `extract_segmentino`, `extract_qm_segmenter`,
  `extract_key_changes`, `extract_energy_events`, `extract_chord_density_spikes`,
  `extract_stem_entry_events`
- `cluster_boundaries()` — single-linkage clustering within tolerance
- `build_clusters_for_hierarchy()` — one-call convenience wrapper
- `snap_to_cluster()` — move a time to the nearest ≥ min_score cluster
- `agreement_score_at()` — score a boundary without moving it

`scripts/boundary_confidence_map.py` now imports from this module. The
script's `extract_story_sections` stays in the script because it reads
story.json (the pipeline's *output*, not its input).

### 2. Snap-to-cluster in `src/story/builder.py`

On the Genius path, every section start is compared against the
agreement clusters from the hierarchy. When a cluster with ≥3 distinct
sources is within ±1 bar of the Genius boundary, the boundary snaps to
the cluster centre. The previous section's end follows so sections stay
contiguous.

**Why this matters.** WhisperX word alignment places a section boundary
where the *first word* of the section lands. On held notes and
naturally-slow-onset vocals, the word-level timestamp can be 1-3s after
the actual musical transition — the drums kick in, the band shifts, the
energy jumps, but the first lyric is a tenth of a beat late. Every
non-vocal source knows the real time; WhisperX just picks the word.

Candy Cane Lane example:

| | Before | After |
|---|---|---|
| Verse 1 start | 8.08s (first word "Take") | **6.58s** (multi-source cluster: drums + guitar + bass + piano + energy_impact + segmentino) |
| Auto-intro span | 0.00 – 8.08s | 0.00 – 6.58s |

Believe is the most dramatic case — 7 of 11 boundaries snapped with
corrections up to 3s.

### 3. Per-section `agreement_score` field in `_story.json`

Every section now carries an integer `agreement_score` alongside its
`role` and `role_confidence`. Values:

- **0** — no other source corroborates (purely lyric-based transition,
  e.g. Chorus → Post-Chorus on Candy Cane Lane where the music is
  identical and only the words change)
- **1-2** — some corroboration (one or two stem entries, maybe an
  energy drop)
- **3+** — strong multi-source consensus; this is the real transition

Schema change is additive — existing consumers are unaffected. Review UI
can sort/filter by score to surface the 1-2 low-confidence sections per
song for reviewer attention, rather than re-checking all 10.

### 4. `scripts/library_fidelity.py`

One command, walks a songs directory, reports:

- Per-song: source, section count, mean score, zero-score sections
- Library-wide: total sections, % with score 0, library mean + median

Intended workflow: run before and after any future pipeline change as a
regression gate. An improvement shows up as higher library mean without
intro/outro role loss; a regression is the inverse.

## Measured results

Re-ran `story --force` on 6 songs (mix of Genius + heuristic, spanning
pop, rock, EDM, and classical):

| Song | Source | Sections | Snapped | Mean score |
|---|---|---|---|---|
| Believe | genius | 11 | **7 / 11** | 2.73 |
| First Snow | heuristic | 4 | 0 | 2.75 |
| Carol of the Bells | heuristic | 9 | 0 | 2.56 |
| Disturbed | genius | 9 | 0 | 1.67 |
| Candy Cane Lane | genius | 10 | 1 / 10 | 1.40 |
| Crazy Train | genius | 13 | 0 | 0.92 |

Observations:

- **Heuristic-path songs score well by construction** — their boundaries
  come from the same clusters we're measuring against. First Snow (2.75)
  and Carol of the Bells (2.56) are already strongly multi-sourced.
- **Genius snapping works where it should** — Believe had severe WhisperX
  drift and snapping corrected it on 7 boundaries with scores now 3-4.
- **Candy Cane Lane's low scores (1.40)** are expected: post_chorus and
  outro boundaries are lyric-distinguished (same music, different words)
  — no non-lyric source agrees on them by design. A score of 0 on a
  post_chorus boundary is a correct signal that the transition is purely
  lyric-based, not a bug.

## What this deliberately doesn't do

- **Does not change section labels.** Only the time of each boundary can
  change (via snap), and only additively via `agreement_score`. Role
  classification is untouched.
- **Does not snap heuristic-path boundaries.** Those already come from
  the same sources we'd snap to, so there's nothing to snap.
- **Does not retroactively score old stories.** Stories without the new
  field get `agreement_score = 0` from the getter default. Re-run
  `xlight-analyze story <mp3> --force` to populate.
- **Does not hard-gate based on score.** A section with score 0 is a
  *review hint*, not a rejection. The pipeline still ships a complete
  story regardless.

## Known session non-determinism

During testing, Down with the Sickness went from 12 sections (old
story) to 9 sections (new story). Root cause is pre-existing: the
Genius subprocess can return different segment counts across sessions
because WhisperX/pyannote inference has subtle state dependencies (the
same issue was noted for Believe in the previous investigation). Not
introduced by this change — back-to-back runs within a single session
are deterministic.

Crazy Train's first parallel run dropped from 13 → 7 sections when
re-run alongside Believe. Serial re-run recovered 13. Cause is a race
on the HuggingFace model cache when two processes load the wav2vec2
align model simultaneously. Workaround: run `story --force` serially
until the subprocess is hardened to handle concurrent first-use model
downloads. Not in scope for this change.

## Follow-ups (from PR #81's list, still open)

- **SSM integration** — threshold tuning first, then use as a validator
  for Genius chorus sections.
- **Heuristic classifier robustness** — dedicated intro/outro detectors
  using stem_entry:vocals and energy_drop.
- **Instrumental short-circuit** — skip Genius subprocess when vocal
  stem RMS < 5% of total energy.
- **HF cache lock** — serialize first-use model downloads in the
  subprocess to fix the Crazy-Train-style race.
