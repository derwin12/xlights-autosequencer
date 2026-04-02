# xlight-autosequencer

Automatically generate xLights sequences from audio files. Analyzes your music, detects beats/onsets/chords/sections, groups your layout props, and applies themed effects — all driven by the audio.

## What It Does

1. **Audio Analysis** — Analyzes MP3 files using 17 algorithms across 6 hierarchy levels to extract beats, onsets, chords, sections, energy curves, and stem separation (drums/bass/vocals/guitar/piano/other)
2. **Layout Grouping** — Reads your `xlights_rgbeffects.xml` and auto-generates 8-tier Power Groups (spatial, rhythmic, prop type, compound, heroes)
3. **Effect Library** — 35 xLights effects cataloged with parameters, prop suitability ratings, and analysis-to-parameter mappings
4. **Variant Library** — 123+ pre-tuned effect variants with contextual tags (energy, tier, section role, genre) for quick effect selection
5. **Theme Engine** — 21 composite "looks" (Inferno, Aurora, Winter Wonderland, etc.) organized by mood, occasion, and genre
6. **Song Story** — Automatic section classification with Genius lyrics integration, energy arcs, and lighting moment detection
7. **Sequence Generation** — Produces `.xsq` files ready to import into xLights with effects placed by tier, energy, and theme
8. **Web UI** — Browser-based dashboard for the full workflow: upload, analyze, review, edit themes, browse variants, group layout, and export

---

## Quick Start

### Prerequisites

- **Python 3.11 or 3.12** — [python.org](https://www.python.org/downloads/) or `brew install python@3.12`
- **ffmpeg** — `brew install ffmpeg`
- **Vamp plugins** (recommended) — Download from [vamp-plugins.org](https://vamp-plugins.org/pack.html) and copy `.dylib` files to `~/Library/Audio/Plug-Ins/Vamp/`:
  - QM Vamp Plugins, BeatRoot, pYIN, NNLS Chroma/Chordino, Silvet

### Install

```bash
git clone https://github.com/bobbyfriday/xlight-autosequencer.git
cd xlight-autosequencer
python3.12 -m venv .venv
source .venv/bin/activate

# Install everything
pip install -e ".[all]"

# PyTorch (required for stem separation and phonemes)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# nltk data (for phoneme analysis)
python -c "import nltk; nltk.download('cmudict')"
```

> **macOS Python.org installer:** Run `open "/Applications/Python 3.12/Install Certificates.command"` once for SSL certs.

### Optional: Vamp + madmom secondary environment

Vamp and madmom require NumPy 1.x, which conflicts with whisperx. A separate venv is auto-detected:

```bash
python3.12 -m venv .venv-vamp
source .venv-vamp/bin/activate
pip install "numpy<2" vamp madmom librosa soundfile
deactivate
```

When `.venv-vamp/` exists, Vamp and madmom algorithms run through it automatically (~14 additional tracks).

---

## Launch the Web UI

The web UI is the primary way to use xLight AutoSequencer. It provides the full workflow in your browser.

```bash
source .venv/bin/activate
xlight-analyze review
```

Opens **http://localhost:5173** with the following pages:

| Page | URL | What it does |
|------|-----|--------------|
| **Song Library** | `/` | Upload MP3s, browse analyzed songs, launch analysis |
| **Theme Editor** | `/themes/` | Create and edit composite lighting themes with layered effects |
| **Variant Library** | `/variants/` | Browse 123+ pre-tuned effect variants, filter by energy/tier/section |
| **Layout Grouping** | `/grouper` | Upload xLights layout XML, preview and edit 8-tier Power Groups |
| **Timeline** | `/timeline` | Visualize timing tracks with synchronized playback, export |
| **Story Review** | `/story-review` | Review song sections, assign themes, view energy arcs |
| **Phonemes** | `/phonemes-view` | View and edit vocal phoneme alignment |
| **Sweep Results** | `/sweep-view` | Compare algorithm parameter sweep results |

### Typical workflow

1. **Upload** — Drag an MP3 onto the Song Library page. Analysis runs automatically with SSE progress streaming.
2. **Review** — Open the timeline to visualize detected beats, onsets, and sections. Listen with synchronized playback.
3. **Group layout** — Upload your `xlights_rgbeffects.xml` to generate Power Groups for your props.
4. **Pick themes** — Open Story Review to assign themes to song sections, or edit themes in the Theme Editor.
5. **Browse variants** — Use the Variant Library to find pre-tuned effect presets that match your energy and style.
6. **Generate** — Run the generator to produce an `.xsq` sequence file ready for xLights.

---

## CLI Reference

The `xlight-analyze` command provides 30+ subcommands for every workflow step.

### Analysis

```bash
# Basic analysis (beats, onsets, chords)
xlight-analyze analyze song.mp3

# Full analysis with stems and phonemes
xlight-analyze analyze song.mp3 --stems --phonemes

# Full analysis with stems, phonemes, and Genius lyrics
xlight-analyze full song.mp3

# Batch analysis (all MP3s in a directory)
xlight-analyze analyze ./songs/

# Interactive wizard
xlight-analyze wizard

# View analysis summary
xlight-analyze summary song_analysis.json
```

### Sequence Generation

```bash
# End-to-end pipeline: analyze → export .xtiming + .xvc files for xLights
xlight-analyze pipeline song.mp3 --output-dir ./xlight-export

# Generate .xsq sequence from MP3 + layout
xlight-analyze generate song.mp3 --layout ~/xLights/xlights_rgbeffects.xml

# Interactive sequence generation
xlight-analyze generate-wizard

# Export analysis to xLights timing files
xlight-analyze export-xlights song_analysis.json --output-dir DIR
```

### Layout Grouping

```bash
# Preview Power Groups without modifying files
xlight-analyze group-layout ~/xLights/xlights_rgbeffects.xml --dry-run

# Generate groups (creates .xml.bak backup first)
xlight-analyze group-layout ~/xLights/xlights_rgbeffects.xml

# Use a show profile to filter tiers
xlight-analyze group-layout ~/xLights/xlights_rgbeffects.xml --profile energetic

# Specify hero props manually
xlight-analyze group-layout ~/xLights/xlights_rgbeffects.xml --hero "Mega Tree"
```

### Effect Variants

```bash
# List all variants
xlight-analyze variant list

# Filter by effect and energy
xlight-analyze variant list --effect Bars --energy high

# Show variant details
xlight-analyze variant show "Bars Single 3D Half-Cycle"

# Coverage report (which effects have variants)
xlight-analyze variant coverage

# Create a custom variant
xlight-analyze variant create --name "My Bars" --base-effect Bars --description "Custom bars"

# Import variants from an existing .xsq sequence
xlight-analyze variant import sequence.xsq
```

### Song Story

```bash
# Build song story from analysis
xlight-analyze story song.mp3

# Interactive story review
xlight-analyze story-review song.mp3
```

### Stem & Phoneme Tools

```bash
# Inspect stem separation results
xlight-analyze stem-inspect song.mp3

# Review and approve stems
xlight-analyze stem-review song.mp3
```

### Scoring Profiles

```bash
# List available scoring profiles
xlight-analyze scoring list

# Show profile configuration
xlight-analyze scoring show default

# Save current config as a named profile
xlight-analyze scoring save my-profile
```

### Library Management

```bash
# Scan directory for analyzed songs
xlight-analyze library ./songs/

# Launch the web UI
xlight-analyze review

# Launch with a specific analysis file open
xlight-analyze review song_analysis.json
```

---

## Output Files

```
song.mp3
song/
├── song_analysis.json          # Full analysis (cached by MD5)
├── song_hierarchy.json         # Hierarchical analysis (L0-L6)
├── song_story.json             # Song story with sections and moments
├── song.xtiming                # xLights timing file (phonemes)
├── song.lyrics.txt             # Auto-transcribed lyrics (edit and rerun)
├── stems/                      # Separated audio stems
│   ├── drums.mp3, bass.mp3, vocals.mp3, guitar.mp3, piano.mp3, other.mp3
│   └── manifest.json
└── analysis/                   # xLights export files
    ├── song_timing.xtiming     # All timing tracks
    ├── drums_beat.xvc          # Value curves (full resolution + macro)
    └── export_manifest.json
```

### Importing into xLights

| File | How to import |
|------|---------------|
| `*.xtiming` | Sequence editor > right-click > Import Timing Tracks |
| `*.xvc` | Effect > value curve editor > load from file |
| `*.xsq` | File > Open Sequence |

---

## Project Structure

```
src/
├── analyzer/               # Audio analysis pipeline
│   ├── audio.py            # MP3 loading via librosa
│   ├── result.py           # Data classes (TimingTrack, HierarchyResult, etc.)
│   ├── runner.py           # Orchestrates algorithm runs
│   ├── orchestrator.py     # Hierarchy assembly (L0-L6)
│   ├── scorer.py           # Quality scoring
│   ├── stems.py            # Demucs stem separation (6 stems)
│   ├── phonemes.py         # WhisperX phoneme analysis
│   ├── xtiming.py          # .xtiming XML writer
│   ├── xvc_export.py       # .xvc value curve writer
│   ├── pipeline.py         # End-to-end export pipeline
│   └── algorithms/         # 17 algorithm implementations (librosa, vamp, madmom, essentia)
├── grouper/                # xLights layout -> Power Groups
│   ├── layout.py           # Parse xlights_rgbeffects.xml
│   ├── classifier.py       # Normalize, classify, detect heroes
│   ├── grouper.py          # 8-tier group generation
│   └── writer.py           # Inject groups back into XML
├── effects/                # xLights effect catalog
│   ├── builtin_effects.json  # 35 effect definitions
│   ├── models.py           # EffectDefinition, EffectParameter, AnalysisMapping
│   └── library.py          # Load, query effects
├── variants/               # Pre-tuned effect presets
│   ├── builtins/           # 34 per-effect JSON files (123+ variants)
│   ├── models.py           # EffectVariant, VariantTags
│   ├── library.py          # Load, query, save custom variants
│   ├── scorer.py           # Context-aware variant scoring
│   └── importer.py         # Import variants from .xsq files
├── themes/                 # Composite effect themes
│   ├── builtin_themes.json # 21 theme definitions
│   ├── models.py           # Theme, EffectLayer (with variant_ref)
│   └── library.py          # Load, query by mood/occasion/genre
├── story/                  # Song story builder
│   ├── models.py           # SongStory, Section, Moment, MoodCurve
│   ├── builder.py          # Build story from hierarchy + Genius
│   ├── section_classifier.py # Detect verse/chorus/bridge/etc.
│   ├── energy_arc.py       # Energy curve computation
│   └── lighting_mapper.py  # Map story to lighting cues
├── generator/              # Sequence generation
│   ├── models.py           # GeneratorConfig, SequencePlan, EffectPlacement
│   ├── plan.py             # Generate effect placement plan
│   ├── theme_selector.py   # Theme selection by mood/occasion
│   ├── effect_placer.py    # Place effects on props (resolves variant_ref)
│   ├── value_curves.py     # Dynamic parameter changes
│   └── xsq_writer.py      # Write .xsq sequence XML
├── review/                 # Web UI
│   ├── server.py           # Flask app (dashboard, upload, timeline, export)
│   ├── theme_routes.py     # Theme CRUD API + editor page
│   ├── variant_routes.py   # Variant library API + browser page
│   ├── story_routes.py     # Story review API
│   └── static/             # HTML, CSS, JS (vanilla, no build step)
├── cli.py                  # Click CLI entry point (30+ commands)
├── cache.py                # MD5-keyed analysis cache
├── library.py              # ~/.xlight/library.json song index
└── export.py               # JSON serialization
```

---

## User Data

| Path | Contents |
|------|----------|
| `~/.xlight/library.json` | Song library index |
| `~/.xlight/custom_themes/*.json` | Custom theme overrides |
| `~/.xlight/custom_variants/*.json` | Custom effect variants |
| `~/.xlight/sweep_configs/` | Parameter sweep configs |
| `.stems/<md5>/` | Cached stem separation output (adjacent to source audio) |

---

## Known Issues

| Issue | Fix |
|-------|-----|
| `SSLCertVerificationError` during demucs download | Run `open "/Applications/Python 3.12/Install Certificates.command"` (Python.org installs only) |
| `No module named 'demucs.api'` | `pip install -U demucs` (need >= 4.0.1) |
| `TorchCodec is required` warning | Harmless — can be ignored |
| `FileNotFoundError: ffmpeg` | Add ffmpeg to PATH: `export PATH="/opt/homebrew/bin:$PATH"` |
| Stem separation slow on first run | Normal — demucs downloads ~200 MB model. Cached after first run. |
| whisperx alignment model fails | `pip install huggingface_hub && huggingface-cli login` |

---

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

---

## Documentation

Detailed docs for each subsystem are in [`docs/`](docs/README.md).

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
