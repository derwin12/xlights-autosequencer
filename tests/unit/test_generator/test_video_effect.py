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

    def test_no_video_named_matrix_returns_empty(self):
        # Even with Matrix props present, absent a name signaling a video
        # role, no target is guessed by size -- see 2026-07-30 fix.
        props = [
            _prop("Small Matrix", display_as="Matrix", pixels=256),
            _prop("Big Matrix", display_as="Matrix", pixels=4096),
        ]
        assert _place_video_effect(props, "/tmp/video.mp4", 90000) == {}

    def test_places_on_matrix_named_for_video_regardless_of_size(self):
        props = [
            _prop("Matrix Video", display_as="Matrix", pixels=256),
            _prop("Big Matrix", display_as="Matrix", pixels=4096),
            _prop("Arch1", display_as="Arch"),
        ]
        result = _place_video_effect(props, "/tmp/video.mp4", 90000)
        assert set(result) == {"Matrix Video"}
        placements = result["Matrix Video"]
        assert len(placements) == 2
        p = next(pl for pl in placements if pl.effect_name == "Video")
        assert p.start_ms == 0
        assert p.end_ms == 90000
        assert p.parameters["E_FILEPICKERCTRL_Video_Filename"] == "/tmp/video.mp4"
        assert p.parameters["E_TEXTCTRL_Duration"] == "1:30.000"

    def test_fades_in_over_at_least_one_second(self):
        # Previously fade_in_ms defaulted to 0 -- the video cut in instantly
        # instead of fading in like other effects (user request, 2026-08-04).
        props = [_prop("Matrix Video", display_as="Matrix", pixels=256)]
        result = _place_video_effect(props, "/tmp/video.mp4", 90000)
        p = next(pl for pl in result["Matrix Video"] if pl.effect_name == "Video")
        assert p.fade_in_ms >= 1000

    def test_off_backdrop_placed_directly_behind_video(self):
        # User request 2026-08-08: an Off effect underneath the video so
        # nothing shows through for its duration.
        props = [_prop("Matrix Video", display_as="Matrix", pixels=256)]
        result = _place_video_effect(props, "/tmp/video.mp4", 90000)
        placements = result["Matrix Video"]
        assert len(placements) == 2
        video = next(pl for pl in placements if pl.effect_name == "Video")
        off = next(pl for pl in placements if pl.effect_name == "Off")
        assert off.start_ms == 0
        assert off.end_ms == 90000
        assert off.color_palette == ["#000000"]
        assert off.layer > video.layer
