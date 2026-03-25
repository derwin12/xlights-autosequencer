# CLI Contract: Hierarchy Orchestrator

## Commands

### `xlight-analyze <path>`

The primary (and only required) command. Replaces the existing `analyze` command.

**Arguments**:

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| path | file or directory | yes | Path to an MP3 file, or a directory of MP3 files |

**Optional Flags**:

| Flag | Description |
|------|-------------|
| `--fresh` | Ignore cache and re-run analysis |
| `--dry-run` | Show what would run without executing |

**No other flags.** Capability detection, algorithm selection, stem separation, and best-of selection are all automatic.

### Single File

```bash
$ xlight-analyze song.mp3

Analyzing: song.mp3 (3:28, ~116 BPM)
Capabilities: vamp ✓  madmom ✓  demucs ✓
Stems: separating... done (drums, bass, vocals, other)
L0 Special Moments: 8 impacts, 3 drops, 6 gaps
L1 Structure: 9 sections (A×5, B×2, N1, N2)
L2 Bars: 109 marks (qm_bars, 0.49 Hz)
L3 Beats: 415 marks (madmom_beats, 1.99 Hz)
L4 Events: drums 823, bass 456, vocals 89, other 312
L5 Energy: 5 curves (full_mix, drums, bass, vocals, spectral_flux)
L6 Harmony: 187 chord changes, 1 key (A major)
Interactions: leader track, tightness, 4 handoffs

Output: song/song_hierarchy.json
Timing: song/song.xtiming
```

### Directory

```bash
$ xlight-analyze /path/to/mp3s/

Batch: 22 MP3 files found
[1/22] Highway to Hell... done (cached)
[2/22] Christmas Dirtbag... done (3.2s)
...
[22/22] Wednesday mashup... done (2.8s)

Complete: 22/22 succeeded, 0 failed
```

### Dry Run

```bash
$ xlight-analyze song.mp3 --dry-run

Capabilities: vamp ✓  madmom ✓  demucs ✓
Would run:
  L0: bbc_energy (full_mix)
  L1: segmentino (full_mix)
  L2: qm_bars, librosa_bars, madmom_downbeats (drums)
  L3: qm_beats, librosa_beats, madmom_beats, beatroot_beats (drums)
  L4: aubio_onset (drums, bass, vocals, other), percussion_onsets (drums)
  L5: bbc_energy (drums, bass, vocals, other), bbc_spectral_flux (full_mix)
  L6: chordino_chords (full_mix), qm_key (full_mix)
  Interactions: leader, tightness, sidechain, handoffs
Total: 18 algorithm runs across 5 stems
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Input file not found or unreadable |
| 2 | No analysis tools available (not even librosa) |
| 3 | Output directory not writable |
| 4 | Batch processing completed with failures (partial success) |

## Output Structure

```
song_name/
├── song_name_hierarchy.json     # Primary output
└── song_name.xtiming            # xLights timing marks
```
