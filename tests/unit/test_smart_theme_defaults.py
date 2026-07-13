"""Dashboard default theme assignment — energy/key-aware selector wiring.

`_auto_assign_defaults` previously mapped section *kind* to a fixed theme
regardless of the song. It now routes through the generator's real
`select_themes` (energy-derived mood tiers, story preferences) whenever the
analysis hierarchy is available, falling back to the static kind map when
it isn't (stub analysis, count mismatch, derivation failure).
"""
from __future__ import annotations

from src.review.api.v1.analysis import _KIND_TO_THEME, _auto_assign_defaults
from src.review.api.v1.themes import _load_themes, _slugify


def _ui_sections(kinds: list[str]) -> list[dict]:
    return [
        {"index": i, "kind": k, "label": k.title(),
         "start_ms": i * 10_000, "end_ms": (i + 1) * 10_000}
        for i, k in enumerate(kinds)
    ]


def _story(energies: list[tuple[str, int]]) -> dict:
    """Minimal song-story dict as consumed by _section_energies_from_story."""
    return {
        "preferences": {},
        "sections": [
            {
                "role": role,
                "start": i * 10.0,
                "end": (i + 1) * 10.0,
                "character": {"energy_score": score},
            }
            for i, (role, score) in enumerate(energies)
        ],
    }


class TestStaticFallback:
    def test_no_hierarchy_uses_kind_map(self):
        sections = _ui_sections(["intro", "verse", "chorus"])
        assignments = _auto_assign_defaults("song1", sections)
        assert [a["theme_id"] for a in assignments] == [
            _KIND_TO_THEME["intro"], _KIND_TO_THEME["verse"], _KIND_TO_THEME["chorus"],
        ]
        assert all(a["user_confirmed"] is False for a in assignments)

    def test_section_count_mismatch_falls_back(self):
        # Story has 2 sections but the UI list has 3 — smart path must bail.
        sections = _ui_sections(["intro", "verse", "chorus"])
        story = _story([("intro", 20), ("chorus", 90)])
        assignments = _auto_assign_defaults(
            "song1", sections, hierarchy=object(), story=story,
        )
        assert [a["theme_id"] for a in assignments] == [
            _KIND_TO_THEME["intro"], _KIND_TO_THEME["verse"], _KIND_TO_THEME["chorus"],
        ]


class TestSmartDefaults:
    def test_story_energies_drive_theme_moods(self):
        """High-energy sections default to aggressive-mood themes, quiet
        sections to ethereal — not one fixed theme per kind."""
        sections = _ui_sections(["intro", "chorus", "outro"])
        story = _story([("intro", 15), ("chorus", 92), ("outro", 10)])
        assignments = _auto_assign_defaults(
            "song1", sections, hierarchy=object(), story=story,
        )
        assert len(assignments) == 3
        catalog = {t["theme_id"]: t for t in _load_themes()}
        moods = [catalog[a["theme_id"]]["mood"] for a in assignments]
        assert moods[0] == "ethereal"
        assert moods[1] == "aggressive"
        assert moods[2] == "ethereal"
        # Every default must be selectable in the Theme screen.
        assert all(a["theme_id"] in catalog for a in assignments)

    def test_smart_ids_are_valid_catalog_slugs(self):
        sections = _ui_sections(["verse", "chorus"])
        story = _story([("verse", 50), ("chorus", 85)])
        assignments = _auto_assign_defaults(
            "song1", sections, hierarchy=object(), story=story,
        )
        catalog_ids = {t["theme_id"] for t in _load_themes()}
        for a in assignments:
            assert a["theme_id"] in catalog_ids
            assert a["theme_id"] == _slugify(a["theme_id"])
