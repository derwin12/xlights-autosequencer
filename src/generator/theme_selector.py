"""Theme selection engine — maps section energy/genre/occasion to themes."""
from __future__ import annotations

from src.generator.models import SectionAssignment, SectionEnergy
from src.themes.library import ThemeLibrary
from src.themes.models import Theme


# Map essentia scale to mood preference.
# Minor keys favor darker/more dramatic themes; major keys favor brighter ones.
_SCALE_MOOD_PREFERENCE: dict[str, list[str]] = {
    "minor": ["dark", "aggressive", "structural", "ethereal"],
    "major": ["ethereal", "structural", "aggressive", "dark"],
}


def select_themes(
    sections: list[SectionEnergy],
    theme_library: ThemeLibrary,
    genre: str,
    occasion: str,
    scale: str | None = None,
) -> list[SectionAssignment]:
    """Select a theme for each song section based on mood, genre, and occasion.

    Rules:
    - Each section's mood_tier drives the primary theme query
    - When essentia scale is available, low-energy sections in minor-key
      songs prefer "dark" themes over "ethereal"
    - Adjacent sections get different themes (rotate through candidates)
    - Repeated section types (e.g. Chorus 1, Chorus 2) get the same theme
      but with different variation_seed values
    - Fallback broadening: genre -> "any", then occasion -> "general"
    """
    assignments: list[SectionAssignment] = []
    prev_theme_name: str | None = None
    label_theme_map: dict[str, Theme] = {}
    label_seed_counter: dict[str, int] = {}

    for section in sections:
        # Adjust mood based on key/scale when available
        effective_mood = section.mood_tier
        if scale in _SCALE_MOOD_PREFERENCE:
            effective_mood = _adjust_mood_for_scale(section.mood_tier, scale)

        theme = _select_for_section(
            section, theme_library, genre, occasion,
            prev_theme_name, label_theme_map,
            mood_override=effective_mood,
        )

        # Track variation seed for repeated section types
        seed = label_seed_counter.get(section.label, 0)
        label_seed_counter[section.label] = seed + 1

        assignments.append(SectionAssignment(
            section=section,
            theme=theme,
            variation_seed=seed,
        ))
        prev_theme_name = theme.name

    return assignments


def _adjust_mood_for_scale(mood_tier: str, scale: str) -> str:
    """Adjust mood tier based on the song's key/scale.

    Minor key: ethereal → dark (quiet sections feel brooding, not peaceful)
    Major key: no change (default mood tiers already fit major keys)
    """
    if scale == "minor" and mood_tier == "ethereal":
        return "dark"
    return mood_tier


def _select_for_section(
    section: SectionEnergy,
    theme_library: ThemeLibrary,
    genre: str,
    occasion: str,
    prev_theme_name: str | None,
    label_theme_map: dict[str, Theme],
    mood_override: str | None = None,
) -> Theme:
    """Select a theme for a single section with fallback broadening."""
    # If this section type was already assigned a theme, reuse it
    if section.label in label_theme_map:
        return label_theme_map[section.label]

    mood = mood_override or section.mood_tier

    # Try progressively broader queries
    for attempt_genre, attempt_occasion in _fallback_sequence(genre, occasion):
        candidates = _query_themes(theme_library, mood, attempt_genre, attempt_occasion)
        if candidates:
            theme = _pick_avoiding_adjacent(candidates, prev_theme_name)
            label_theme_map[section.label] = theme
            return theme

    # Ultimate fallback: any theme in the library
    all_themes = list(theme_library.themes.values())
    if all_themes:
        theme = _pick_avoiding_adjacent(all_themes, prev_theme_name)
        label_theme_map[section.label] = theme
        return theme

    raise ValueError("Theme library is empty — cannot select any theme")


def _fallback_sequence(genre: str, occasion: str) -> list[tuple[str, str]]:
    """Generate a sequence of (genre, occasion) pairs with progressive broadening."""
    attempts = [(genre, occasion)]
    if genre != "any":
        attempts.append(("any", occasion))
    if occasion != "general":
        attempts.append((genre, "general"))
        if genre != "any":
            attempts.append(("any", "general"))
    return attempts


def _query_themes(
    library: ThemeLibrary, mood: str, genre: str, occasion: str
) -> list[Theme]:
    """Query themes matching mood + genre + occasion."""
    results = []
    for theme in library.themes.values():
        if theme.mood != mood:
            continue
        if genre != "any" and theme.genre not in (genre, "any"):
            continue
        if occasion != "general" and theme.occasion not in (occasion, "general"):
            continue
        results.append(theme)
    return results


def _pick_avoiding_adjacent(
    candidates: list[Theme], prev_name: str | None
) -> Theme:
    """Pick a theme from candidates, avoiding the previously used one."""
    if prev_name is None or len(candidates) <= 1:
        return candidates[0]

    for theme in candidates:
        if theme.name != prev_name:
            return theme

    return candidates[0]
