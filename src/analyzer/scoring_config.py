"""Scoring configuration: categories, algorithm mapping, weights, and config loading."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Scoring criteria names ────────────────────────────────────────────────────

CRITERIA_NAMES: list[str] = ["density", "regularity", "mark_count", "coverage", "min_gap"]

CRITERIA_LABELS: dict[str, str] = {
    "density": "Mark density \u2014 timing marks per second of audio",
    "regularity": "Regularity \u2014 consistency of inter-mark intervals",
    "mark_count": "Mark count \u2014 total number of timing marks",
    "coverage": "Coverage \u2014 fraction of song duration with marks",
    "min_gap": "Minimum gap compliance \u2014 proportion of intervals >= threshold",
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "density": 0.25,
    "regularity": 0.25,
    "mark_count": 0.15,
    "coverage": 0.15,
    "min_gap": 0.20,
}


# ── Scoring categories ───────────────────────────────────────────────────────

@dataclass
class ScoringCategory:
    """Defines expected target ranges for a group of algorithms."""

    name: str
    description: str
    density_range: tuple[float, float]
    regularity_range: tuple[float, float]
    mark_count_range: tuple[int, int]
    coverage_range: tuple[float, float]

    def apply_overrides(self, overrides: dict) -> "ScoringCategory":
        """Return a new ScoringCategory with overrides applied."""
        return ScoringCategory(
            name=self.name,
            description=self.description,
            density_range=(
                overrides.get("density_min", self.density_range[0]),
                overrides.get("density_max", self.density_range[1]),
            ),
            regularity_range=(
                overrides.get("regularity_min", self.regularity_range[0]),
                overrides.get("regularity_max", self.regularity_range[1]),
            ),
            mark_count_range=(
                int(overrides.get("mark_count_min", self.mark_count_range[0])),
                int(overrides.get("mark_count_max", self.mark_count_range[1])),
            ),
            coverage_range=(
                overrides.get("coverage_min", self.coverage_range[0]),
                overrides.get("coverage_max", self.coverage_range[1]),
            ),
        )


# Built-in category definitions
BUILTIN_CATEGORIES: dict[str, ScoringCategory] = {
    "beats": ScoringCategory(
        name="beats",
        description="Beat tracking algorithms — high density, high regularity",
        density_range=(1.0, 4.0),
        regularity_range=(0.6, 1.0),
        mark_count_range=(100, 800),
        coverage_range=(0.8, 1.0),
    ),
    "bars": ScoringCategory(
        name="bars",
        description="Bar/measure tracking — moderate density, high regularity",
        density_range=(0.2, 1.0),
        regularity_range=(0.6, 1.0),
        mark_count_range=(20, 200),
        coverage_range=(0.7, 1.0),
    ),
    "onsets": ScoringCategory(
        name="onsets",
        description="Onset detection — high density, low regularity",
        density_range=(1.0, 8.0),
        regularity_range=(0.0, 0.6),
        mark_count_range=(100, 2000),
        coverage_range=(0.7, 1.0),
    ),
    "segments": ScoringCategory(
        name="segments",
        description="Song structure segmentation — very low density",
        density_range=(0.01, 0.1),
        regularity_range=(0.0, 0.5),
        mark_count_range=(4, 30),
        coverage_range=(0.5, 1.0),
    ),
    "pitch": ScoringCategory(
        name="pitch",
        description="Pitch and note event detection — moderate density",
        density_range=(0.5, 4.0),
        regularity_range=(0.1, 0.7),
        mark_count_range=(50, 500),
        coverage_range=(0.5, 1.0),
    ),
    "harmony": ScoringCategory(
        name="harmony",
        description="Chord and harmonic change detection — low density",
        density_range=(0.2, 2.0),
        regularity_range=(0.1, 0.6),
        mark_count_range=(20, 400),
        coverage_range=(0.5, 1.0),
    ),
    "general": ScoringCategory(
        name="general",
        description="Fallback category for unrecognized algorithms",
        density_range=(0.1, 5.0),
        regularity_range=(0.0, 1.0),
        mark_count_range=(10, 1000),
        coverage_range=(0.3, 1.0),
    ),
}

# Algorithm name → category name mapping
ALGORITHM_CATEGORY_MAP: dict[str, str] = {
    # beats
    "librosa_beats": "beats",
    "qm_beats": "beats",
    "beatroot_beats": "beats",
    "madmom_beats": "beats",
    "madmom_downbeats": "beats",
    # bars
    "librosa_bars": "bars",
    "qm_bars": "bars",
    # onsets
    "qm_onsets_complex": "onsets",
    "qm_onsets_hfc": "onsets",
    "qm_onsets_phase": "onsets",
    "librosa_onsets": "onsets",
    "drums": "onsets",
    # segments
    "qm_segments": "segments",
    "qm_tempo": "segments",
    # pitch
    "pyin_notes": "pitch",
    "pyin_pitch_changes": "pitch",
    # harmony
    "chordino_chords": "harmony",
    "nnls_chroma": "harmony",
    "harmonic_peaks": "harmony",
    # frequency bands → general (no specific category)
    "bass": "general",
    "mid": "general",
    "treble": "general",
}


def get_category_for_algorithm(algorithm_name: str) -> ScoringCategory:
    """Return the ScoringCategory for a given algorithm name. Falls back to 'general'."""
    cat_name = ALGORITHM_CATEGORY_MAP.get(algorithm_name, "general")
    return BUILTIN_CATEGORIES[cat_name]


# ── Scoring configuration ────────────────────────────────────────────────────

@dataclass
class ScoringConfig:
    """User-defined scoring configuration."""

    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    thresholds: dict[str, float] = field(default_factory=dict)
    diversity_tolerance_ms: int = 50
    diversity_threshold: float = 0.90
    min_gap_threshold_ms: int = 25
    category_overrides: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "ScoringConfig":
        """Return a ScoringConfig with all built-in defaults."""
        return cls()

    @classmethod
    def from_toml(cls, path: Path) -> "ScoringConfig":
        """Load and validate a ScoringConfig from a TOML file."""
        import tomllib

        with open(path, "rb") as f:
            data = tomllib.load(f)

        config = cls.default()

        # Weights
        if "weights" in data:
            for key, value in data["weights"].items():
                if key not in CRITERIA_NAMES:
                    raise ValueError(f"Unknown scoring criterion: '{key}'. Valid criteria: {', '.join(CRITERIA_NAMES)}")
                if not isinstance(value, (int, float)) or value < 0:
                    raise ValueError(f"Weight for '{key}' must be a non-negative number, got: {value}")
                config.weights[key] = float(value)

        # Thresholds
        if "thresholds" in data:
            for key, value in data["thresholds"].items():
                if not isinstance(value, (int, float)):
                    raise ValueError(f"Threshold '{key}' must be a number, got: {value}")
                config.thresholds[key] = float(value)

        # Diversity settings
        if "diversity" in data:
            div = data["diversity"]
            if "tolerance_ms" in div:
                config.diversity_tolerance_ms = int(div["tolerance_ms"])
                if config.diversity_tolerance_ms <= 0:
                    raise ValueError("diversity.tolerance_ms must be > 0")
            if "threshold" in div:
                config.diversity_threshold = float(div["threshold"])
                if not (0.0 < config.diversity_threshold <= 1.0):
                    raise ValueError("diversity.threshold must be in (0.0, 1.0]")

        # Min gap settings
        if "min_gap" in data:
            mg = data["min_gap"]
            if "threshold_ms" in mg:
                config.min_gap_threshold_ms = int(mg["threshold_ms"])
                if config.min_gap_threshold_ms <= 0:
                    raise ValueError("min_gap.threshold_ms must be > 0")

        # Category overrides
        if "categories" in data:
            for cat_name, overrides in data["categories"].items():
                if cat_name not in BUILTIN_CATEGORIES:
                    raise ValueError(
                        f"Unknown scoring category: '{cat_name}'. "
                        f"Valid categories: {', '.join(BUILTIN_CATEGORIES.keys())}"
                    )
                config.category_overrides[cat_name] = dict(overrides)

        # Validate weights sum > 0
        if sum(config.weights.values()) <= 0:
            raise ValueError("Sum of all criterion weights must be greater than zero")

        return config

    def get_category(self, algorithm_name: str) -> ScoringCategory:
        """Return the ScoringCategory for an algorithm, with any overrides applied."""
        cat = get_category_for_algorithm(algorithm_name)
        if cat.name in self.category_overrides:
            cat = cat.apply_overrides(self.category_overrides[cat.name])
        return cat


# ── Profile management ────────────────────────────────────────────────────────

_USER_PROFILE_DIR = Path.home() / ".config" / "xlight" / "scoring"
_PROJECT_PROFILE_DIR_NAME = ".scoring"


def _project_profile_dir() -> Path:
    """Return the project-local scoring profile directory."""
    return Path.cwd() / _PROJECT_PROFILE_DIR_NAME


def save_profile(name: str, source_path: Path, scope: str = "project") -> Path:
    """Save a TOML config file as a named profile. Returns the destination path."""
    if scope == "user":
        dest_dir = _USER_PROFILE_DIR
    else:
        dest_dir = _project_profile_dir()

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{name}.toml"
    dest.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def load_profile(name: str) -> ScoringConfig:
    """Load a named scoring profile. Searches project-local first, then user-global."""
    path = get_profile_path(name)
    if path is None:
        raise FileNotFoundError(
            f"Scoring profile '{name}' not found. "
            f"Searched: {_project_profile_dir()}, {_USER_PROFILE_DIR}"
        )
    return ScoringConfig.from_toml(path)


def get_profile_path(name: str) -> Optional[Path]:
    """Find the path for a named profile, or None if not found."""
    project_path = _project_profile_dir() / f"{name}.toml"
    if project_path.exists():
        return project_path
    user_path = _USER_PROFILE_DIR / f"{name}.toml"
    if user_path.exists():
        return user_path
    return None


def list_profiles() -> list[dict[str, str]]:
    """List all available scoring profiles with name and source."""
    profiles: dict[str, dict[str, str]] = {}

    # User-global profiles
    if _USER_PROFILE_DIR.exists():
        for p in sorted(_USER_PROFILE_DIR.glob("*.toml")):
            name = p.stem
            profiles[name] = {"name": name, "source": "user", "path": str(p)}

    # Project-local profiles (override user-global)
    proj_dir = _project_profile_dir()
    if proj_dir.exists():
        for p in sorted(proj_dir.glob("*.toml")):
            name = p.stem
            profiles[name] = {"name": name, "source": "project", "path": str(p)}

    return list(profiles.values())


def generate_default_toml() -> str:
    """Generate a fully commented TOML string with all defaults."""
    lines = [
        "# XLight Scoring Configuration",
        "# Copy this file and modify to create a custom scoring profile.",
        "",
        "[weights]",
        "# Criterion weights (all >= 0, must not all be zero)",
    ]
    for name, weight in DEFAULT_WEIGHTS.items():
        label = CRITERIA_LABELS[name]
        lines.append(f"{name} = {weight}       # {label}")

    lines += [
        "",
        "[thresholds]",
        "# Optional: tracks outside these bounds are excluded from ranked output",
        "# min_mark_count = 5",
        "# min_coverage = 0.1",
        "# max_density = 20.0",
        "",
        "[diversity]",
        "tolerance_ms = 50    # Mark alignment window for similarity comparison",
        "threshold = 0.90     # Proportion of matching marks to consider tracks near-identical",
        "",
        "[min_gap]",
        "threshold_ms = 25    # Minimum actionable gap (hardware constraint)",
        "",
        "# Category target ranges \u2014 override only what you need",
    ]

    for cat_name, cat in BUILTIN_CATEGORIES.items():
        if cat_name == "general":
            continue
        lines.append(f"# [{cat_name}]")
        lines.append(f"# density_min = {cat.density_range[0]}")
        lines.append(f"# density_max = {cat.density_range[1]}")
        lines.append(f"# regularity_min = {cat.regularity_range[0]}")
        lines.append(f"# regularity_max = {cat.regularity_range[1]}")
        lines.append(f"# mark_count_min = {cat.mark_count_range[0]}")
        lines.append(f"# mark_count_max = {cat.mark_count_range[1]}")
        lines.append(f"# coverage_min = {cat.coverage_range[0]}")
        lines.append(f"# coverage_max = {cat.coverage_range[1]}")

    return "\n".join(lines) + "\n"
