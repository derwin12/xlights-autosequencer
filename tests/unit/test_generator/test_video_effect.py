"""Tests for YouTube-video placement (effect_placer._place_video_effect)."""
from __future__ import annotations

from src.generator.effect_placer import _place_video_effect
from src.grouper.layout import Prop


def _prop(name: str, display_as: str = "Custom", *, pixels: int = 0) -> Prop:
    return Prop(
        name=name,
        display_as=display_as,
        world_x=0.0, world_y=0.0, world_z=0.0,
        scale_x=1.0, scale_y=1.0,
        parm1=1, parm2=1,
        sub_models=[],
        pixel_count=pixels,
    )


class TestPlaceVideoEffect:
    def test_no_video_path_returns_empty(self):
        props = [_prop("Matrix1", display_as="Matrix", pixels=1024)]
        assert _place_video_effect(props, None, 60000) == {}

    def test_no_matrix_props_returns_empty(self):
        props = [_prop("Arch1", display_as="Arch")]
        assert _place_video_effect(props, "/tmp/video.mp4", 60000) == {}

    def test_places_on_largest_matrix(self):
        props = [
            _prop("Small Matrix", display_as="Matrix", pixels=256),
            _prop("Big Matrix", display_as="Matrix", pixels=4096),
            _prop("Arch1", display_as="Arch"),
        ]
        result = _place_video_effect(props, "/tmp/video.mp4", 90000)
        assert set(result) == {"Big Matrix"}
        placements = result["Big Matrix"]
        assert len(placements) == 1
        p = placements[0]
        assert p.effect_name == "Video"
        assert p.start_ms == 0
        assert p.end_ms == 90000
        assert p.parameters["E_FILEPICKERCTRL_Video_Filename"] == "/tmp/video.mp4"
        assert p.parameters["E_TEXTCTRL_Duration"] == "1:30.000"
