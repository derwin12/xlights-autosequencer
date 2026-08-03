"""Load and query the effect themes library."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.effects.library import EffectLibrary, load_effect_library
from src.themes.models import VALID_GENRES, Theme
from src.themes.validator import validate_theme

logger = logging.getLogger(__name__)

_BUILTIN_PATH = Path(__file__).parent / "builtin_themes.json"
_DEFAULT_CUSTOM_DIR = Path.home() / ".xlight" / "custom_themes"

# Themes authored through the review UI's palette-only Theme editor (no
# layer/effect picker exists there) have no `layers` at all -- validate_theme
# rejects that ("Theme must have at least one layer"), which used to mean
# load_theme_library() silently dropped the theme from its catalog with only
# a logger.warning (user report 2026-08-03: assigned a theme to a section,
# the exported .xsq's "Themes" diagnostic track showed the auto-selected
# theme instead of the one actually chosen). "Color Wash Smooth" is a real
# built-in bottom-layer variant (used by an actual shipped theme) that
# renders using the theme's own palette, so a layers-less custom theme gets
# a real, working default look transparently instead of being silently
# inert.
DEFAULT_THEME_LAYERS: list[dict] = [
    {"variant": "Color Wash Smooth", "blend_mode": "Normal", "effect_pool": [], "stem": None},
]


def heal_custom_theme_data(data: dict) -> dict:
    """Fix common ways the review UI's free-text/paste-driven Theme editor
    produces data validate_theme() would otherwise reject outright, dropping
    the theme from the catalog entirely with only a logger.warning (found
    2026-08-03 investigating a real user theme that hit all three at once):

    - No `layers` (see DEFAULT_THEME_LAYERS above -- the dialog has no
      layer/effect picker at all).
    - `genre` in the wrong case ("Rock" instead of "rock") -- the Genre
      field is free text, not a dropdown like Mood/Occasion.
    - `accent_palette` with exactly 1 color -- validate_theme requires 0
      (omitted entirely) or 2+ (a real contrasting family, see the
      two-group AI palette prompt); a paste that only carried one color
      through is dropped rather than treated as a fatal error, since an
      accent palette is optional in the first place.
    """
    healed = dict(data)
    if not healed.get("layers"):
        healed["layers"] = DEFAULT_THEME_LAYERS
    genre = str(healed.get("genre", "")).strip().lower()
    if genre in VALID_GENRES:
        healed["genre"] = genre
    elif "genre" in healed:
        healed["genre"] = "any"
    if len(healed.get("accent_palette") or []) == 1:
        healed["accent_palette"] = []
    return healed


@dataclass
class ThemeLibrary:
    schema_version: str
    themes: dict[str, Theme]

    def get(self, name: str) -> Theme | None:
        """Look up a theme by name (case-insensitive)."""
        if name in self.themes:
            return self.themes[name]
        name_lower = name.lower()
        for key, theme in self.themes.items():
            if key.lower() == name_lower:
                return theme
        return None

    def by_mood(self, mood: str) -> list[Theme]:
        """Return all themes in the given mood collection."""
        return [t for t in self.themes.values() if t.mood == mood]

    def by_occasion(self, occasion: str) -> list[Theme]:
        """Return all themes tagged with the given occasion."""
        return [t for t in self.themes.values() if t.occasion == occasion]

    def by_genre(self, genre: str) -> list[Theme]:
        """Return themes tagged with the given genre or 'any'."""
        return [t for t in self.themes.values() if t.genre == genre or t.genre == "any"]

    def query(
        self,
        mood: str | None = None,
        occasion: str | None = None,
        genre: str | None = None,
    ) -> list[Theme]:
        """Return themes matching all provided filters (AND logic)."""
        results = list(self.themes.values())
        if mood is not None:
            results = [t for t in results if t.mood == mood]
        if occasion is not None:
            results = [t for t in results if t.occasion == occasion]
        if genre is not None:
            results = [t for t in results if t.genre == genre or t.genre == "any"]
        return results


def load_theme_library(
    builtin_path: str | Path | None = None,
    custom_dir: str | Path | None = None,
    effect_library: EffectLibrary | None = None,
    variant_library=...,  # sentinel — callers must pass explicitly
) -> ThemeLibrary:
    """Load the theme library from built-in JSON + optional custom overrides.

    Args:
        builtin_path: Path to the built-in themes JSON. Defaults to bundled file.
        custom_dir: Path to custom overrides directory. Defaults to ~/.xlight/custom_themes/.
        effect_library: Loaded effect library for validation. If None, loads automatically.
        variant_library: VariantLibrary for variant_ref validation. Required.
    """
    # variant_library is required — guard against accidental None or missing arg
    if variant_library is ...:
        raise ValueError("variant_library is required for theme loading")
    if variant_library is None:
        raise ValueError("variant_library is required for theme loading")

    builtin_path = Path(builtin_path) if builtin_path else _BUILTIN_PATH
    custom_dir = Path(custom_dir) if custom_dir else _DEFAULT_CUSTOM_DIR

    if effect_library is None:
        effect_library = load_effect_library()

    if not builtin_path.exists():
        raise FileNotFoundError(f"Built-in theme library not found: {builtin_path}")

    with open(builtin_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    schema_version = raw.get("schema_version", "0.0.0")
    themes: dict[str, Theme] = {}

    for name, data in raw.get("themes", {}).items():
        errors = validate_theme(data, effect_library, variant_library)
        if errors:
            logger.warning("Built-in theme '%s' has validation errors: %s", name, errors)
            continue
        theme = Theme.from_dict(data)
        theme.theme_id = _slugify(name)
        themes[name] = theme

    # Load custom overrides
    if custom_dir.is_dir():
        for custom_file in sorted(custom_dir.glob("*.json")):
            try:
                with open(custom_file, "r", encoding="utf-8") as f:
                    custom_data = json.load(f)
                custom_data = heal_custom_theme_data(custom_data)
                errors = validate_theme(custom_data, effect_library, variant_library)
                if errors:
                    logger.warning(
                        "Skipping invalid custom theme '%s': %s",
                        custom_file.name, errors,
                    )
                    continue
                custom_theme = Theme.from_dict(custom_data)
                # The filename stem, not a slug of the (possibly since-
                # renamed) current name -- see Theme.theme_id's docstring.
                custom_theme.theme_id = custom_file.stem
                themes[custom_theme.name] = custom_theme
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning("Skipping malformed custom file '%s': %s", custom_file.name, exc)

    return ThemeLibrary(schema_version=schema_version, themes=themes)


def _slugify(name: str) -> str:
    """Convert a theme name to a filesystem-safe slug."""
    import re
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "theme"


def save_custom_theme(
    theme: Theme,
    custom_dir: str | Path | None = None,
) -> Path:
    """Save a custom theme to ~/.xlight/custom_themes/{slug}.json."""
    custom_dir = Path(custom_dir) if custom_dir else _DEFAULT_CUSTOM_DIR
    custom_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(theme.name)
    out_path = custom_dir / f"{slug}.json"

    from dataclasses import asdict
    data = asdict(theme)
    out_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return out_path


def delete_custom_theme(
    name: str,
    custom_dir: str | Path | None = None,
) -> None:
    """Delete a custom theme file by name."""
    custom_dir = Path(custom_dir) if custom_dir else _DEFAULT_CUSTOM_DIR

    slug = _slugify(name)
    target = custom_dir / f"{slug}.json"
    if target.exists():
        target.unlink()
        return

    # Fallback: scan by name field inside JSON files
    if custom_dir.is_dir():
        for f in custom_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("name", "").lower() == name.lower():
                    f.unlink()
                    return
            except Exception:
                continue

    raise FileNotFoundError(f"Custom theme not found: {name}")
