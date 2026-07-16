"""Tests for src/generator/moving_head.py — DMX moving-head color-wash placement."""
from __future__ import annotations

from pathlib import Path

from src.generator.models import SectionAssignment, SectionEnergy
from src.generator.moving_head import place_moving_head_effects
from src.grouper.layout import parse_layout
from src.themes.models import Theme

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "grouper"


def _assignment(start_ms: int, end_ms: int, palette: list[str], anchor: list[str] | None = None) -> SectionAssignment:
    section = SectionEnergy(
        label="verse", start_ms=start_ms, end_ms=end_ms,
        energy_score=50, mood_tier="structural", impact_count=0,
    )
    theme = Theme(
        name="Test Theme", mood="structural", occasion="general", genre="any",
        intent="test", layers=[], palette=palette,
    )
    return SectionAssignment(section=section, theme=theme, anchor_palette=anchor or [])


class TestPlaceMovingHeadEffects:
    def test_no_moving_head_group_returns_empty(self):
        layout = parse_layout(FIXTURES / "simple_layout.xml")
        assignments = [_assignment(0, 1000, ["#ff0000"])]
        assert place_moving_head_effects(layout, assignments) == {}

    def test_no_assignments_returns_empty(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assert place_moving_head_effects(layout, []) == {}

    def test_one_placement_per_section_on_the_group(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [
            _assignment(0, 1000, ["#ff0000"]),
            _assignment(1000, 2000, ["#00ff00"]),
        ]
        result = place_moving_head_effects(layout, assignments)
        assert list(result.keys()) == ["MH GRP"]
        placements = result["MH GRP"]
        assert len(placements) == 2
        assert [p.start_ms for p in placements] == [0, 1000]
        assert [p.end_ms for p in placements] == [1000, 2000]
        assert all(p.effect_name == "Moving Head" for p in placements)

    def test_settings_written_for_every_head_in_group_order(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment(0, 1000, ["#ff0000"])]
        placement = place_moving_head_effects(layout, assignments)["MH GRP"][0]
        assert "E_TEXTCTRL_MH1_Settings" in placement.parameters
        assert "E_TEXTCTRL_MH2_Settings" in placement.parameters
        assert "E_TEXTCTRL_MH3_Settings" not in placement.parameters
        for key in ("E_TEXTCTRL_MH1_Settings", "E_TEXTCTRL_MH2_Settings"):
            # Commas inside a TEXTCTRL value must be escaped as &comma; --
            # the outer settings string is itself comma-delimited, so a
            # literal comma here would make xLights misparse everything
            # after it (confirmed against a real rendered sequence).
            assert "Heads: 1&comma;2" in placement.parameters[key]
            assert "," not in placement.parameters[key]
            assert "Dimmer: 0.000000&comma;0.000000&comma;1.000000&comma;0.000000" in placement.parameters[key]

    def test_color_derived_from_anchor_palette_when_present(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment(0, 1000, ["#000000"], anchor=["#ff0000"])]
        placement = place_moving_head_effects(layout, assignments)["MH GRP"][0]
        settings = placement.parameters["E_TEXTCTRL_MH1_Settings"]
        # Pure red -> HSV hue 0.0, sat 1.0, val 1.0
        assert "Color: 0.000000&comma;1.000000&comma;1.000000" in settings

    def test_falls_back_to_theme_palette_without_anchor(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment(0, 1000, ["#0000ff"])]
        placement = place_moving_head_effects(layout, assignments)["MH GRP"][0]
        settings = placement.parameters["E_TEXTCTRL_MH1_Settings"]
        assert "Color: 0.666667&comma;1.000000&comma;1.000000" in settings

    def test_auto_shutter_and_no_motion_by_default(self):
        layout = parse_layout(FIXTURES / "moving_head_layout.xml")
        assignments = [_assignment(0, 1000, ["#ff0000"])]
        placement = place_moving_head_effects(layout, assignments)["MH GRP"][0]
        assert placement.parameters["E_CHECKBOX_AUTO_SHUTTER"] == "1"
        assert placement.parameters["E_SLIDER_MHPan"] == "0"
        assert placement.parameters["E_SLIDER_MHTilt"] == "0"
