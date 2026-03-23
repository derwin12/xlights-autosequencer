# Quickstart: Configurable Quality Scoring

**Branch**: `011-quality-score-config` | **Date**: 2026-03-22

---

## No New Dependencies

This feature uses only Python stdlib (`tomllib` for TOML parsing, available in Python 3.11+). No new `pip install` required.

---

## Run Analysis with Default Scoring

```bash
# Default scoring — same behavior as before, now with breakdowns in JSON
xlight-analyze analyze song.mp3
```

---

## View Score Breakdowns

```bash
# Summary with per-criterion breakdown
xlight-analyze summary song_analysis.json --breakdown
```

Each track shows:
- Overall score and category
- Per-criterion: measured value, target range, weight, contribution
- Threshold pass/fail status
- Diversity filter status (if `--top N` was used)

---

## Customize Scoring

```bash
# Generate default config as a starting point
xlight-analyze scoring defaults > my_scoring.toml

# Edit weights, thresholds, or category targets
# Then run analysis with custom config
xlight-analyze analyze song.mp3 --scoring-config my_scoring.toml
```

Example: prioritize dense tracks for fast EDM:
```toml
[weights]
density = 0.50
regularity = 0.15
mark_count = 0.15
coverage = 0.10
min_gap = 0.10
```

---

## Save and Use Profiles

```bash
# Save a config as a named profile
xlight-analyze scoring save fast_edm --from my_scoring.toml

# Use the profile by name
xlight-analyze analyze song.mp3 --scoring-profile fast_edm

# List available profiles
xlight-analyze scoring list

# View a profile's settings
xlight-analyze scoring show fast_edm
```

Profiles are stored in:
- Project-local: `.scoring/` (takes precedence)
- User-global: `~/.config/xlight/scoring/`

---

## Key Module: `src/analyzer/scorer.py`

The existing `scorer.py` is replaced with the new scoring system:

```python
class ScoringConfig:
    """Loads from TOML or uses built-in defaults."""
    @classmethod
    def from_toml(cls, path: Path) -> ScoringConfig: ...
    @classmethod
    def default(cls) -> ScoringConfig: ...

class CategoryScorer:
    """Scores a track against its category's target ranges."""
    def score_track(self, track: TimingTrack, duration_ms: int) -> ScoreBreakdown: ...

class DiversityFilter:
    """Removes near-identical tracks from --top N selection."""
    def filter(self, tracks: list[TimingTrack], n: int) -> list[tuple[TimingTrack, ScoreBreakdown]]: ...
```

---

## Running Tests

```bash
pytest tests/ -v                              # all tests
pytest tests/unit/test_scorer.py -v          # scoring unit tests
pytest tests/unit/test_scoring_config.py -v  # config loading/validation tests
pytest tests/unit/test_diversity.py -v       # diversity filter tests
pytest tests/integration/ -v                 # end-to-end pipeline tests
```
