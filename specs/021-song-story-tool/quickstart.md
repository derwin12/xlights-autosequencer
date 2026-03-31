# Quickstart: Song Story Tool

**Feature**: 021-song-story-tool | **Date**: 2026-03-30

## Prerequisites

- Python 3.11+ with existing xlight-analyze dependencies installed
- Demucs (htdemucs_6s model) for stem separation
- Vamp plugins for segmentation and harmony (optional but recommended)

## Usage

### Generate a Song Story

```bash
# Generate song story from an MP3
xlight-analyze story song.mp3

# Generate and immediately open review UI
xlight-analyze story song.mp3 --review

# Force regeneration (overwrite existing story)
xlight-analyze story song.mp3 --force

# Specify output path
xlight-analyze story song.mp3 --output my_story.json
```

### Review a Song Story

```bash
# Open review UI for an existing story
xlight-analyze story-review song_story.json

# Specify port
xlight-analyze story-review song_story.json --port 5174
```

### Generate Sequence from Song Story

```bash
# Generate sequence using song story (instead of raw analysis)
xlight-analyze generate song.mp3 --layout layout.xml --output show.xsq --story song_story.json
```

## Output

The `story` command produces a `_story.json` file adjacent to the audio file:

```
/music/
├── Magic.mp3
├── Magic_hierarchy.json    # existing analysis cache
├── Magic_story.json        # NEW: song story
└── .stems/
    └── <md5>/              # existing stem cache
        ├── drums.mp3
        ├── bass.mp3
        ├── vocals.mp3
        ├── guitar.mp3
        ├── piano.mp3
        └── other.mp3
```

## Development

### Run Tests

```bash
# All song story tests
pytest tests/unit/test_section_classifier.py tests/unit/test_section_merger.py tests/unit/test_moment_classifier.py tests/unit/test_energy_arc.py tests/unit/test_section_profiler.py tests/unit/test_lighting_mapper.py tests/unit/test_stem_curves.py -v

# Integration test
pytest tests/integration/test_story_pipeline.py -v
```

### Module Structure

```
src/story/
├── builder.py              # Entry point: build_song_story()
├── section_classifier.py   # Role assignment
├── section_merger.py       # Micro-segment → meaningful sections
├── moment_classifier.py    # Moment detection + classification + ranking
├── energy_arc.py           # Global energy arc shape
├── section_profiler.py     # Per-section character profiling
├── lighting_mapper.py      # Role → lighting guidance
├── stem_curves.py          # 2Hz stem curve extraction
└── models.py               # Data classes
```

### Key Entry Points

- `src/story/builder.py::build_song_story(hierarchy, audio_path)` — generates the complete song story dict
- `src/review/story_routes.py` — Flask blueprint for review API
- `src/cli.py` — `story` and `story-review` click commands
