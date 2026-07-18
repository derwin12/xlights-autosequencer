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
    base_variation_seed: int = 0,
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

    ``base_variation_seed`` shifts every section's variation seed by a
    constant offset (default 0 preserves the historical
    ``variation_seed=section_index`` behaviour) and rotates the starting
    position within each mood's candidate pool, so two songs with the
    same section-mood sequence get different theme lineups. Generation
    derives it from the audio hash (``generator_runner._derive_seed``);
    the microscope tool pins it for deterministic measurement runs.
    """
    assignments: list[SectionAssignment] = []
    prev_theme_name: str | None = None
    label_theme_map: dict[str, Theme] = {}

    for i, section in enumerate(sections):
        # Adjust mood based on key/scale when available
        effective_mood = section.mood_tier
        if scale in _SCALE_MOOD_PREFERENCE:
            effective_mood = _adjust_mood_for_scale(section.mood_tier, scale)

        theme = _select_for_section(
            section, theme_library, genre, occasion,
            prev_theme_name, label_theme_map,
            mood_override=effective_mood,
            selection_seed=base_variation_seed,
        )

        # Use global section index as variation seed so every section cycles
        # through theme alternates independently of repeated-label counting.
        assignments.append(SectionAssignment(
            section=section,
            theme=theme,
            variation_seed=base_variation_seed + i,
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
    selection_seed: int = 0,
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
            theme = _pick_avoiding_adjacent(candidates, prev_theme_name, selection_seed)
            label_theme_map[section.label] = theme
            return theme

    # Ultimate fallback: any theme in the library
    all_themes = list(theme_library.themes.values())
    if all_themes:
        theme = _pick_avoiding_adjacent(all_themes, prev_theme_name, selection_seed)
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
    """Query themes matching mood + genre + occasion exactly.

    Occasion match is always strict, including "general": a request for
    "christmas" returns only themes tagged "christmas", and a request for
    "general" (the default for the vast majority of songs) returns only
    themes tagged "general" — not every theme regardless of occasion.
    `_fallback_sequence` owns broadening independently: it appends a
    (genre, "general") attempt as its own escalation tier when a
    specific-occasion query comes up empty, so Christmas songs still fall
    back to general themes when no Christmas-specific theme matches. A
    prior version special-cased occasion == "general" to skip this filter
    entirely, which meant an ordinary song's default "general" query could
    silently return Christmas/Halloween-tagged themes whenever mood+genre
    happened to match (found 2026-07-18 via a real song landing on
    "Festive Flash"/"Silent Night" in July with no holiday preference set).
    """
    results = []
    for theme in library.themes.values():
        if theme.mood != mood:
            continue
        if genre != "any" and theme.genre not in (genre, "any"):
            continue
        if theme.occasion != occasion:
            continue
        results.append(theme)
    return results


def _pick_avoiding_adjacent(
    candidates: list[Theme], prev_name: str | None, selection_seed: int = 0
) -> Theme:
    """Pick a theme from candidates, avoiding the previously used one.

    ``selection_seed`` rotates the starting position in the candidate
    list, so songs with different seeds pick different themes from the
    same pool. Seed 0 preserves the historical first-candidate choice.
    """
    start = selection_seed % len(candidates)
    rotated = candidates[start:] + candidates[:start]

    if prev_name is None or len(candidates) <= 1:
        return rotated[0]

    for theme in rotated:
        if theme.name != prev_name:
            return theme

    return rotated[0]
