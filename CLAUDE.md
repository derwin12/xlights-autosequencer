# XLight AutoSequencer Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-03-24

## Active Technologies
- Python 3.11+ + demucs (new), vamp, librosa, madmom, click, Flask (008-stem-separation)
- JSON files (local filesystem); WAV stem files in `.stems/<md5>/` (008-stem-separation)
- Python 3.11+ + whisperx (faster-whisper + wav2vec2), nltk cmudict, existing deps (vamp, librosa, madmom, demucs, click, Flask) (009-vocal-phoneme-tracks)
- JSON files + `.xtiming` XML files (local filesystem) (009-vocal-phoneme-tracks)
- Python 3.11+ + click 8+, Flask 3+ (existing); no new dependencies (010-analysis-cache-library)
- JSON files — `_analysis.json` (existing, extended with `source_hash`); `~/.xlight/library.json` (new) (010-analysis-cache-library)
- Python 3.11+ + numpy (scoring math), tomllib (TOML config parsing, stdlib in 3.11+), click 8+ (CLI), pytest (testing) (011-quality-score-config)
- TOML files (scoring configs/profiles), JSON files (analysis output with score breakdowns) (011-quality-score-config)
- Python 3.11+ + vamp, numpy, click 8+ (all existing — no new deps) (005-vamp-parameter-tuning)
- JSON files (local filesystem); new `~/.xlight/sweep_configs/` directory (005-vamp-parameter-tuning)
- Python 3.11+ + numpy (signal processing, cross-correlation), librosa 0.10+ (audio features, onset detection), vamp (plugin host), click 8+ (CLI), xml.etree.ElementTree (stdlib, xLights XML export) (012-intelligent-stem-sweep)
- JSON files (analysis output), XML files (`.xtiming`, `.xvc` exports), WAV stem files in `.stems/<md5>/` (012-intelligent-stem-sweep)
- Python 3.11+ + `lyricsgenius` (new optional dep), `mutagen` (new lightweight dep), (013-genius-lyric-segments)
- JSON files — existing MD5-keyed `_analysis.json` cache; `song_structure` field (013-genius-lyric-segments)
- Python 3.11+ + click 8+ (CLI), questionary 2+ (interactive prompts, new), rich 13+ (progress display, new), concurrent.futures (stdlib, parallelism) (014-cli-wizard-pipeline)
- JSON files (existing `_analysis.json` cache, `~/.xlight/library.json`) (014-cli-wizard-pipeline)

- **Language**: Python 3.11+
- **Audio analysis**: vamp (Python host), librosa 0.10+, madmom 0.16+
- **Vamp plugin packs**: QM Vamp Plugins, BeatRoot, pYIN, NNLS Chroma/Chordino, Silvet
- **Web server**: Flask 3+ (local review UI)
- **CLI**: click 8+
- **Testing**: pytest
- **Storage**: JSON files (local filesystem)
- **System dependencies**: ffmpeg (MP3 loading), Vamp plugin .dylib files in `~/Library/Audio/Plug-Ins/Vamp/`

## Project Structure

```text
src/
├── analyzer/
│   ├── audio.py              # MP3 loading and AudioFile metadata
│   ├── result.py             # AnalysisResult, TimingTrack, TimingMark data classes
│   ├── runner.py             # Orchestrates all 22 algorithm runs
│   ├── scorer.py             # Quality scoring → quality_score per track
│   └── algorithms/
│       ├── base.py           # Abstract Algorithm interface
│       ├── vamp_beats.py     # QM bar-beat tracker + BeatRoot (Vamp)
│       ├── vamp_onsets.py    # QM onset detector x3 methods (Vamp)
│       ├── vamp_structure.py # QM segmenter + tempo tracker (Vamp)
│       ├── vamp_pitch.py     # pYIN note events + pitch changes (Vamp)
│       ├── vamp_harmony.py   # Chordino chord changes + NNLS chroma peaks (Vamp)
│       ├── librosa_beats.py  # librosa beat tracking + bar grouping
│       ├── librosa_bands.py  # librosa frequency band energy peaks
│       ├── librosa_hpss.py   # librosa HPSS drums + harmonic peaks
│       └── madmom_beat.py    # madmom RNN+DBN beat + downbeat tracking
├── cli.py                    # Click CLI entry point (xlight-analyze command)
├── export.py                 # JSON serialization / deserialization
└── review/
    ├── server.py             # Flask app (/, /analysis, /audio, /export routes)
    └── static/               # Vanilla JS + Canvas 2D + Web Audio API single-page UI

tests/
├── fixtures/                 # Short royalty-free audio files for deterministic tests
├── unit/                     # Per-algorithm unit tests
└── integration/              # End-to-end pipeline tests
```

## Commands

```bash
# Install dependencies
pip install vamp librosa madmom click pytest
brew install ffmpeg  # macOS
# Install Vamp plugin packs from vamp-plugins.org → ~/Library/Audio/Plug-Ins/Vamp/

# Run analysis
xlight-analyze analyze song.mp3

# View track summary
xlight-analyze summary song_analysis.json

# Export selected tracks
xlight-analyze export song_analysis.json --select beats,drums,bass

# Launch review UI (opens browser at localhost:5173)
xlight-analyze review song_analysis.json

# Run tests
pytest tests/ -v
```

## Code Style

- Follow PEP 8
- Type hints on all public functions and class attributes
- Each algorithm class inherits from `base.Algorithm` and implements `run(audio_array, sample_rate) -> TimingTrack`
- Timestamps are always stored as integers (milliseconds) — never floats

## Recent Changes
- 014-cli-wizard-pipeline: Added Python 3.11+ + click 8+ (CLI), questionary 2+ (interactive prompts, new), rich 13+ (progress display, new), concurrent.futures (stdlib, parallelism)
- 013-genius-lyric-segments: Added Python 3.11+ + `lyricsgenius` (new optional dep), `mutagen` (new lightweight dep),
- 012-intelligent-stem-sweep: Added Python 3.11+ + numpy (signal processing, cross-correlation), librosa 0.10+ (audio features, onset detection), vamp (plugin host), click 8+ (CLI), xml.etree.ElementTree (stdlib, xLights XML export)
  `htdemucs_6s` separates audio into 6 stems (drums, bass, vocals, guitar, piano, other).
  Algorithms route to their preferred stem via `Algorithm.preferred_stem` class attribute.
  Stems are MD5-cached in `.stems/<hash>/` adjacent to the source file. Each `TimingTrack`
  carries a `stem_source` field. The `summary` command shows a `Stem` column. The review UI
  shows a stem badge on each track lane. New module: `src/analyzer/stems.py`.

  madmom produce 22 named timing tracks from a single MP3. Quality-scored JSON output
  with `--top N` auto-selection and manual track selection/export via CLI.
  serves a single-page Canvas+Web Audio app for visualizing timing tracks, synchronized
  playback, Next/Prev/Solo focus navigation, and filtered JSON export.
  with no args shows an upload page; SSE streams per-algorithm progress; browser auto-navigates
  to timeline when done. Vamp/madmom toggles on upload page.

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
