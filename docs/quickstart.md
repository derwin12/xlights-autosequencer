# Quickstart: Analyzing a Song End-to-End

This guide walks through running a full analysis on an MP3 from scratch using the CLI.

---

## Before you start

You need the virtual environment active for every command in this guide:

```bash
cd /path/to/xlight-autosequencer
source .venv/bin/activate
```

Verify the CLI is working:

```bash
xlight-analyze --help
```

---

## Level 1 — Basic analysis (librosa only, ~10 seconds)

The fastest path. No extra setup required beyond the base install.

```bash
xlight-analyze analyze song.mp3 --no-vamp --no-madmom
```

This produces `song_analysis.json` next to the MP3 with 8 librosa tracks:
beats, bars, onsets, bass energy, mid energy, treble energy, drums (HPSS), and harmonic peaks.

**Review what you got:**

```bash
xlight-analyze summary song_analysis.json
```

The summary table shows each track's mark count, average interval between marks, and quality score (0–100). Higher quality = more useful for sequencing. Look for tracks with scores above 50.

---

## Level 2 — Full analysis with Vamp + madmom (~30–60 seconds)

Adds ~14 more tracks from QM Vamp plugins, BeatRoot, pYIN, Chordino, and madmom's RNN beat tracker.

**Requires:**
- Vamp plugin .dylib files in `~/Library/Audio/Plug-Ins/Vamp/`
- `.venv-vamp` built (see README prerequisites)

```bash
xlight-analyze analyze song.mp3
```

Expected output: progress lines for each algorithm as they complete, then a summary table with ~22 tracks total.

**If `.venv-vamp` is missing**, Vamp and madmom tracks are silently skipped — you'll still get the 8 librosa tracks. The summary will show fewer tracks but won't error.

---

## Level 3 — Stem separation (2–5 minutes first run, instant after)

Separates the mix into 6 stems (drums, bass, vocals, guitar, piano, other) using Demucs, then routes each algorithm to its best stem. This significantly improves beat and onset quality.

**Requires:** `demucs` installed (`pip install demucs`), and ffmpeg.

```bash
xlight-analyze analyze song.mp3 --stems
```

First run downloads the Demucs model (~200 MB) and runs stem separation (~2–5 min on CPU). Results are cached in `songs/<song_name>/stems/` — re-runs are instant.

The summary table gains a `Stem` column showing which stem each track used.

---

## Level 4 — Phoneme/lyric timing (adds 3–10 minutes)

Transcribes the vocals and generates word- and phoneme-level timing tracks, plus an `.xtiming` file for xLights.

**Requires:** `whisperx` installed (see README), and `--stems` (implied automatically).

```bash
xlight-analyze analyze song.mp3 --phonemes
```

This adds:
- A vocals phoneme timing track in the JSON
- `song.xtiming` — xLights-compatible timing XML with one timing mark per phoneme
- `song.lyrics.txt` — auto-transcribed lyrics you can edit

**If the word timing is off**, correct the lyrics file and re-run with a larger model:

```bash
# Edit the lyrics file first, then:
xlight-analyze analyze song.mp3 --phonemes --phoneme-model small --lyrics song.lyrics.txt --no-cache
```

Model sizes (larger = more accurate, slower): `tiny`, `base` (default), `small`, `medium`, `large-v2`.

---

## Level 5 — Song structure detection

Detects semantic sections (intro, verse, chorus, bridge, outro) using the All-in-One model.

**Requires:** `allin1` installed (`pip install allin1`).

```bash
xlight-analyze analyze song.mp3 --structure
```

Structure segments are stored in the JSON and rendered as colored bands in the review UI.

---

## Putting it all together

A typical full-featured run:

```bash
xlight-analyze analyze song.mp3 --stems --phonemes --structure
```

This runs everything: stem separation, all algorithms routed to their best stem, phoneme timing, and song structure detection. On first run this may take 10–20 minutes depending on CPU. Subsequent runs for the same file are instant (cached by MD5).

---

## Working with the output

**Re-read the quality summary at any time:**

```bash
xlight-analyze summary song_analysis.json
```

**Export just the tracks you want for xLights:**

```bash
xlight-analyze export song_analysis.json --select beats,drums,bass,vocals_phonemes
```

This writes `song_selected.json` with only the chosen tracks.

**Open the visual timeline in a browser:**

```bash
xlight-analyze review song_analysis.json
```

---

## Where files are saved

After analysis, all files land in `songs/<song_name>/` relative to where you ran the command:

```
songs/
└── My_Song/
    ├── My_Song.mp3
    ├── My_Song_analysis.json    <- full analysis (re-used on re-runs)
    ├── My_Song.xtiming          <- xLights phoneme timing file
    ├── My_Song.lyrics.txt       <- editable auto-transcription
    └── stems/
        ├── drums.mp3
        ├── bass.mp3
        ├── vocals.mp3
        ├── guitar.mp3
        ├── piano.mp3
        └── other.mp3
```

Analyzed songs are also registered in `~/.xlight/library.json` so the review UI's song library can find them.

---

## Troubleshooting quick reference

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Only 8 tracks in summary | `.venv-vamp` missing or Vamp plugins not installed | See README prerequisites §3 and §4 |
| `FileNotFoundError: ffmpeg` | ffmpeg not on PATH | `brew install ffmpeg` |
| `SSLCertVerificationError` during Demucs download | Python.org install missing certs | Run `open "/Applications/Python 3.12/Install Certificates.command"` |
| Phoneme words don't match song | Transcription error or wrong model | Edit `song.lyrics.txt`, re-run with `--lyrics` and a larger `--phoneme-model` |
| Analysis re-runs every time | Cache miss (file was modified) | Normal — cache is keyed by MD5; use `--no-cache` to force a re-run intentionally |
| `allin1` not found | Package not installed | `pip install allin1` |
