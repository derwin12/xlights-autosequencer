"""Tests for theme selection engine."""
import pytest

from src.generator.models import SectionEnergy, SectionAssignment
from src.themes.models import Theme, EffectLayer
from src.themes.library import ThemeLibrary
from src.generator.theme_selector import select_themes


def _make_theme(
    name: str,
    mood: str,
    occasion: str = "general",
    genre: str = "any",
) -> Theme:
    """Return a Theme with a minimal single-layer stack."""
    return Theme(
        name=name,
        mood=mood,
        occasion=occasion,
        genre=genre,
        intent=f"Test theme {name}",
        layers=[
            EffectLayer(variant="Color Wash", blend_mode="Normal"),
        ],
        palette=["#FF0000", "#00FF00"],
    )


def _make_library(themes: list[Theme]) -> ThemeLibrary:
    """Return a ThemeLibrary from a list of themes, keyed by name."""
    return ThemeLibrary(
        schema_version="1.0",
        themes={t.name: t for t in themes},
    )


def _make_section(
    label: str,
    energy_score: int,
    mood_tier: str,
    start_ms: int = 0,
    end_ms: int = 1000,
) -> SectionEnergy:
    """Return a SectionEnergy with sensible defaults."""
    return SectionEnergy(
        label=label,
        start_ms=start_ms,
        end_ms=end_ms,
        energy_score=energy_score,
        mood_tier=mood_tier,
        impact_count=0,
    )


class TestThemeSelector:
    """Tests for select_themes mapping sections to themes."""

    def test_selects_theme_matching_mood(self):
        """An ethereal section should receive a theme tagged ethereal."""
        ethereal_theme = _make_theme("Starlight", mood="ethereal")
        aggressive_theme = _make_theme("Inferno", mood="aggressive")
        library = _make_library([ethereal_theme, aggressive_theme])

        sections = [_make_section("intro", energy_score=20, mood_tier="ethereal")]
        result = select_themes(sections, library, genre="pop", occasion="general")

        assert len(result) == 1
        assert result[0].theme.mood == "ethereal"

    def test_selects_theme_matching_occasion(self):
        """A christmas occasion should filter to christmas-tagged themes."""
        xmas_theme = _make_theme("Candy Cane", mood="ethereal", occasion="christmas")
        general_theme = _make_theme("Starlight", mood="ethereal", occasion="general")
        library = _make_library([xmas_theme, general_theme])

        sections = [_make_section("verse", energy_score=25, mood_tier="ethereal")]
        result = select_themes(sections, library, genre="pop", occasion="christmas")

        assert len(result) == 1
        assert result[0].theme.occasion == "christmas"

    def test_selects_theme_matching_genre(self):
        """A rock genre should prefer rock-tagged themes (or 'any')."""
        rock_theme = _make_theme("Power Chord", mood="aggressive", genre="rock")
        pop_theme = _make_theme("Bubblegum", mood="aggressive", genre="pop")
        library = _make_library([rock_theme, pop_theme])

        sections = [_make_section("chorus", energy_score=80, mood_tier="aggressive")]
        result = select_themes(sections, library, genre="rock", occasion="general")

        assert len(result) == 1
        assert result[0].theme.genre in ("rock", "any")

    def test_adjacent_sections_get_different_themes(self):
        """Three adjacent sections with 2+ matching themes should not repeat adjacently."""
        theme_a = _make_theme("Starlight", mood="ethereal")
        theme_b = _make_theme("Moonbeam", mood="ethereal")
        theme_c = _make_theme("Twilight", mood="ethereal")
        library = _make_library([theme_a, theme_b, theme_c])

        sections = [
            _make_section("intro", energy_score=20, mood_tier="ethereal", start_ms=0, end_ms=1000),
            _make_section("verse", energy_score=25, mood_tier="ethereal", start_ms=1000, end_ms=2000),
            _make_section("bridge", energy_score=30, mood_tier="ethereal", start_ms=2000, end_ms=3000),
        ]
        result = select_themes(sections, library, genre="pop", occasion="general")

        assert len(result) == 3
        for i in range(len(result) - 1):
            assert result[i].theme.name != result[i + 1].theme.name

    def test_repeated_section_type_same_theme_different_seed(self):
        """Two chorus sections should get the same theme but different variation_seed."""
        theme = _make_theme("Power Chord", mood="aggressive")
        library = _make_library([theme])

        sections = [
            _make_section("chorus", energy_score=80, mood_tier="aggressive", start_ms=0, end_ms=1000),
            _make_section("chorus", energy_score=80, mood_tier="aggressive", start_ms=2000, end_ms=3000),
        ]
        result = select_themes(sections, library, genre="pop", occasion="general")

        assert len(result) == 2
        assert result[0].theme.name == result[1].theme.name
        assert result[0].variation_seed != result[1].variation_seed

    def test_fallback_broadens_genre(self):
        """When no themes match genre+mood+occasion, broaden to genre='any'."""
        any_genre_theme = _make_theme("Universal Glow", mood="ethereal", genre="any")
        library = _make_library([any_genre_theme])

        sections = [_make_section("intro", energy_score=20, mood_tier="ethereal")]
        # Request genre="classical" but only a genre="any" theme is available.
        result = select_themes(sections, library, genre="classical", occasion="general")

        assert len(result) == 1
        assert result[0].theme.name == "Universal Glow"

    def test_fallback_broadens_occasion(self):
        """When no themes match at all, broaden occasion to 'general'."""
        general_theme = _make_theme("Starlight", mood="ethereal", occasion="general")
        library = _make_library([general_theme])

        sections = [_make_section("intro", energy_score=20, mood_tier="ethereal")]
        # Request occasion="halloween" but only a general theme is available.
        result = select_themes(sections, library, genre="pop", occasion="halloween")

        assert len(result) == 1
        assert result[0].theme.name == "Starlight"

    def test_general_occasion_excludes_holiday_themes(self):
        """A plain occasion='general' query (the default for most songs)
        must not pick a Christmas/Halloween-tagged theme just because it
        matches mood+genre -- regression for 2026-07-18 bug where a real
        non-holiday song landed on 'Festive Flash'/'Silent Night' in July
        because _query_themes skipped its occasion filter entirely
        whenever the query's own occasion was 'general'."""
        xmas_theme = _make_theme("Festive Flash", mood="aggressive", occasion="christmas")
        general_theme = _make_theme("Inferno", mood="aggressive", occasion="general")
        library = _make_library([xmas_theme, general_theme])

        sections = [_make_section("chorus", energy_score=80, mood_tier="aggressive")]
        result = select_themes(sections, library, genre="pop", occasion="general")

        assert len(result) == 1
        assert result[0].theme.name == "Inferno"
        assert result[0].theme.occasion == "general"

    def test_returns_assignment_per_section(self):
        """Output length must match input sections."""
        theme = _make_theme("Starlight", mood="ethereal")
        library = _make_library([theme])

        sections = [
            _make_section("intro", energy_score=20, mood_tier="ethereal", start_ms=0, end_ms=1000),
            _make_section("verse", energy_score=30, mood_tier="ethereal", start_ms=1000, end_ms=2000),
            _make_section("chorus", energy_score=70, mood_tier="aggressive", start_ms=2000, end_ms=3000),
            _make_section("outro", energy_score=15, mood_tier="ethereal", start_ms=3000, end_ms=4000),
        ]
        result = select_themes(sections, library, genre="pop", occasion="general")

        assert len(result) == len(sections)
        for assignment in result:
            assert isinstance(assignment, SectionAssignment)


class TestPerSongSeedRotation:
    """base_variation_seed rotates theme choice so songs differ."""

    def _library(self) -> ThemeLibrary:
        return _make_library([
            _make_theme("Starlight", mood="ethereal"),
            _make_theme("Moonbeam", mood="ethereal"),
            _make_theme("Twilight", mood="ethereal"),
        ])

    def _sections(self) -> list[SectionEnergy]:
        return [
            _make_section("intro", energy_score=20, mood_tier="ethereal", start_ms=0, end_ms=1000),
            _make_section("verse", energy_score=25, mood_tier="ethereal", start_ms=1000, end_ms=2000),
        ]

    def test_seed_zero_preserves_legacy_first_candidate(self):
        """Seed 0 must keep the historical candidates[0] choice."""
        result = select_themes(self._sections(), self._library(),
                               genre="pop", occasion="general")
        assert result[0].theme.name == "Starlight"

    def test_different_seeds_give_different_theme_lineups(self):
        """Songs with different seeds must not all get the same lineup."""
        lineups = set()
        for seed in (0, 1, 2):
            result = select_themes(self._sections(), self._library(),
                                   genre="pop", occasion="general",
                                   base_variation_seed=seed)
            lineups.add(tuple(a.theme.name for a in result))
        assert len(lineups) == 3

    def test_seed_rotation_keeps_adjacent_variety(self):
        """Rotated picks must still avoid repeating the previous theme."""
        sections = self._sections() + [
            _make_section("bridge", energy_score=30, mood_tier="ethereal",
                          start_ms=2000, end_ms=3000),
        ]
        for seed in (0, 1, 2, 0x9E3779B9):
            result = select_themes(sections, self._library(),
                                   genre="pop", occasion="general",
                                   base_variation_seed=seed)
            for i in range(len(result) - 1):
                assert result[i].theme.name != result[i + 1].theme.name

    def test_seed_rotation_keeps_repeated_label_reuse(self):
        """Repeated section labels still share one theme under a seed."""
        sections = [
            _make_section("chorus", energy_score=80, mood_tier="aggressive", start_ms=0, end_ms=1000),
            _make_section("chorus", energy_score=80, mood_tier="aggressive", start_ms=2000, end_ms=3000),
        ]
        library = _make_library([
            _make_theme("Power Chord", mood="aggressive"),
            _make_theme("Inferno", mood="aggressive"),
        ])
        result = select_themes(sections, library, genre="pop", occasion="general",
                               base_variation_seed=7)
        assert result[0].theme.name == result[1].theme.name
        assert result[0].variation_seed != result[1].variation_seed

    def test_same_seed_is_deterministic(self):
        """The same seed must reproduce the same lineup."""
        a = select_themes(self._sections(), self._library(),
                          genre="pop", occasion="general", base_variation_seed=5)
        b = select_themes(self._sections(), self._library(),
                          genre="pop", occasion="general", base_variation_seed=5)
        assert [x.theme.name for x in a] == [x.theme.name for x in b]
