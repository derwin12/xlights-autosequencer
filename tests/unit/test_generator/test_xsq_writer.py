"""Tests for XSQ writer — xLights .xsq XML serialization."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.analyzer.result import TimingMark, TimingTrack
from src.generator.models import (
    EffectPlacement,
    SectionAssignment,
    SectionEnergy,
    SequencePlan,
    SongProfile,
)
from src.generator.xsq_writer import _collect_timing_tracks, write_xsq
from src.themes.models import EffectLayer, Theme


def _make_theme() -> Theme:
    return Theme(
        name="TestTheme",
        mood="structural",
        occasion="general",
        genre="any",
        intent="test",
        layers=[EffectLayer(variant="Fire")],
        palette=["#FF0000", "#00FF00"],
    )


def _make_plan() -> SequencePlan:
    """Build a minimal SequencePlan with two sections and two models."""
    profile = SongProfile(
        title="Test",
        artist="Artist",
        genre="pop",
        occasion="general",
        duration_ms=10000,
        estimated_bpm=120.0,
    )

    theme = _make_theme()

    placement_1 = EffectPlacement(
        effect_name="Fire",
        xlights_id="Fire",
        model_or_group="Model1",
        start_ms=0,
        end_ms=5000,
        parameters={"E_SLIDER_Fire_Height": 50},
        color_palette=["#FF0000", "#00FF00"],
        fade_in_ms=200,
        fade_out_ms=200,
    )

    placement_2 = EffectPlacement(
        effect_name="Fire",
        xlights_id="Fire",
        model_or_group="Model2",
        start_ms=5000,
        end_ms=10000,
        parameters={"E_SLIDER_Fire_Height": 50},
        color_palette=["#FF0000", "#00FF00"],
        fade_in_ms=200,
        fade_out_ms=200,
    )

    section_1 = SectionAssignment(
        section=SectionEnergy(
            label="verse",
            start_ms=0,
            end_ms=5000,
            energy_score=40,
            mood_tier="structural",
            impact_count=2,
        ),
        theme=theme,
        group_effects={"Model1": [placement_1]},
    )

    section_2 = SectionAssignment(
        section=SectionEnergy(
            label="chorus",
            start_ms=5000,
            end_ms=10000,
            energy_score=80,
            mood_tier="aggressive",
            impact_count=4,
        ),
        theme=theme,
        group_effects={"Model2": [placement_2]},
    )

    return SequencePlan(
        song_profile=profile,
        sections=[section_1, section_2],
        models=["Model1", "Model2"],
    )


def _write_and_parse(plan: SequencePlan, tmp_path: Path) -> ET.Element:
    """Write the plan to a temp .xsq file and return the parsed XML root."""
    out = tmp_path / "test.xsq"
    write_xsq(plan, out)
    tree = ET.parse(out)
    return tree.getroot()


class TestXsqWriter:
    def test_valid_xml_structure(self, tmp_path: Path) -> None:
        """Root is <xsequence> with head, ColorPalettes, EffectDB,
        DisplayElements, and ElementEffects children."""
        root = _write_and_parse(_make_plan(), tmp_path)

        assert root.tag == "xsequence"

        expected_children = {
            "head",
            "ColorPalettes",
            "EffectDB",
            "DisplayElements",
            "ElementEffects",
        }
        actual_children = {child.tag for child in root}
        assert expected_children.issubset(actual_children), (
            f"Missing children: {expected_children - actual_children}"
        )

    def test_fixed_point_timing(self, tmp_path: Path) -> None:
        """Root element has FixedPointTiming='25'."""
        root = _write_and_parse(_make_plan(), tmp_path)
        assert root.get("FixedPointTiming") == "25"

    def test_media_file_reference(self, tmp_path: Path) -> None:
        """<head> contains a <mediaFile> element with the audio path."""
        root = _write_and_parse(_make_plan(), tmp_path)
        head = root.find("head")
        assert head is not None
        media = head.find("mediaFile")
        assert media is not None
        # The media file text should be non-empty
        assert media.text is not None and len(media.text.strip()) > 0

    def test_sequence_duration(self, tmp_path: Path) -> None:
        """<head> contains <sequenceDuration> matching the plan duration."""
        plan = _make_plan()
        root = _write_and_parse(plan, tmp_path)
        head = root.find("head")
        assert head is not None
        duration_el = head.find("sequenceDuration")
        assert duration_el is not None
        # Duration in seconds: 10000ms -> 10.0s or "10.000"
        duration_val = float(duration_el.text)
        expected_sec = plan.song_profile.duration_ms / 1000.0
        assert abs(duration_val - expected_sec) < 0.01

    def test_effect_parameter_serialization(self, tmp_path: Path) -> None:
        """EffectDB entries have comma-separated key=value parameter format."""
        root = _write_and_parse(_make_plan(), tmp_path)
        effect_db = root.find("EffectDB")
        assert effect_db is not None
        entries = list(effect_db)
        assert len(entries) > 0

        # At least one entry should contain the Fire parameter
        found = False
        for entry in entries:
            text = entry.get("settings") or entry.text or ""
            if "E_SLIDER_Fire_Height=50" in text:
                found = True
                break
        assert found, "Expected 'E_SLIDER_Fire_Height=50' in EffectDB entries"

    def test_color_palette_serialization(self, tmp_path: Path) -> None:
        """ColorPalette entries use C_BUTTON_PaletteN format."""
        root = _write_and_parse(_make_plan(), tmp_path)
        palettes = root.find("ColorPalettes")
        assert palettes is not None
        entries = list(palettes)
        assert len(entries) > 0

        # Check that at least one palette references the colors
        found = False
        for entry in entries:
            text = entry.get("settings") or entry.text or ""
            if "C_BUTTON_Palette" in text:
                found = True
                break
        assert found, "Expected 'C_BUTTON_Palette' in ColorPalettes entries"

    def test_effectdb_deduplication(self, tmp_path: Path) -> None:
        """Two placements with identical params share one EffectDB entry."""
        plan = _make_plan()
        root = _write_and_parse(plan, tmp_path)
        effect_db = root.find("EffectDB")
        assert effect_db is not None

        # Both placements have identical parameters (E_SLIDER_Fire_Height=50),
        # so there should be exactly one matching EffectDB entry, not two.
        entries = list(effect_db)
        fire_entries = []
        for entry in entries:
            text = entry.get("settings") or entry.text or ""
            if "E_SLIDER_Fire_Height=50" in text:
                fire_entries.append(text)
        assert len(fire_entries) == 1, (
            f"Expected 1 deduplicated EffectDB entry, got {len(fire_entries)}"
        )

    def test_palette_deduplication(self, tmp_path: Path) -> None:
        """Two placements with identical palettes share one palette entry."""
        plan = _make_plan()
        root = _write_and_parse(plan, tmp_path)
        palettes = root.find("ColorPalettes")
        assert palettes is not None

        # Both placements use ["#FF0000", "#00FF00"], so only one palette entry
        entries = list(palettes)
        palette_texts = []
        for entry in entries:
            text = entry.get("settings") or entry.text or ""
            if "#FF0000" in text and "#00FF00" in text:
                palette_texts.append(text)
        assert len(palette_texts) == 1, (
            f"Expected 1 deduplicated palette entry, got {len(palette_texts)}"
        )

    def test_frame_aligned_times(self, tmp_path: Path) -> None:
        """All startTime/endTime in ElementEffects are multiples of 25."""
        root = _write_and_parse(_make_plan(), tmp_path)
        element_effects = root.find("ElementEffects")
        assert element_effects is not None

        for element in element_effects.iter():
            start = element.get("startTime")
            end = element.get("endTime")
            if start is not None:
                assert int(start) % 25 == 0, (
                    f"startTime {start} is not a multiple of 25"
                )
            if end is not None:
                assert int(end) % 25 == 0, (
                    f"endTime {end} is not a multiple of 25"
                )

    def test_model_names_in_display_elements(self, tmp_path: Path) -> None:
        """DisplayElements contains Element entries for each model."""
        plan = _make_plan()
        root = _write_and_parse(plan, tmp_path)
        display = root.find("DisplayElements")
        assert display is not None

        model_names = set()
        for elem in display:
            name = elem.get("name")
            if name:
                model_names.add(name)

        for model in plan.models:
            assert model in model_names, (
                f"Model '{model}' not found in DisplayElements"
            )


class TestScopedPreviewParams:
    """Tests for spec 049 — scoped_duration_ms and audio_offset_ms kwargs."""

    def _make_preview_plan(self) -> SequencePlan:
        """Return a plan with placements starting at 45000ms (for offset tests)."""
        profile = SongProfile(
            title="PreviewTest",
            artist="Artist",
            genre="pop",
            occasion="general",
            duration_ms=180000,
            estimated_bpm=120.0,
        )
        theme = _make_theme()
        placement = EffectPlacement(
            effect_name="Fire",
            xlights_id="Fire",
            model_or_group="Model1",
            start_ms=45000,
            end_ms=60000,
            parameters={"E_SLIDER_Fire_Height": 50},
            color_palette=["#FF0000"],
        )
        section = SectionAssignment(
            section=SectionEnergy(
                label="chorus",
                start_ms=45000,
                end_ms=60000,
                energy_score=80,
                mood_tier="aggressive",
                impact_count=2,
            ),
            theme=theme,
            group_effects={"Model1": [placement]},
        )
        return SequencePlan(
            song_profile=profile,
            sections=[section],
            models=["Model1"],
        )

    def test_scoped_duration_overrides_song_duration(self, tmp_path: Path) -> None:
        """scoped_duration_ms replaces sequenceDuration in the output."""
        plan = self._make_preview_plan()
        out = tmp_path / "preview.xsq"
        write_xsq(plan, out, scoped_duration_ms=15000)

        tree = ET.parse(out)
        root = tree.getroot()
        head = root.find("head")
        assert head is not None
        dur_el = head.find("sequenceDuration")
        assert dur_el is not None
        assert abs(float(dur_el.text) - 15.0) < 0.01

    def test_audio_offset_emits_media_offset_element(self, tmp_path: Path) -> None:
        """audio_offset_ms emits <mediaOffset> element in <head>."""
        plan = self._make_preview_plan()
        out = tmp_path / "preview.xsq"
        write_xsq(plan, out, audio_offset_ms=45000)

        tree = ET.parse(out)
        root = tree.getroot()
        head = root.find("head")
        assert head is not None
        media_offset_el = head.find("mediaOffset")
        assert media_offset_el is not None
        assert media_offset_el.text == "45000"

    def test_audio_offset_shifts_placement_times(self, tmp_path: Path) -> None:
        """audio_offset_ms subtracts from startTime/endTime in output."""
        plan = self._make_preview_plan()  # placement at 45000-60000ms
        out = tmp_path / "preview.xsq"
        write_xsq(plan, out, scoped_duration_ms=15000, audio_offset_ms=45000)

        tree = ET.parse(out)
        root = tree.getroot()
        effects_el = root.find("ElementEffects")
        assert effects_el is not None

        found = False
        for elem in effects_el.iter("Effect"):
            start = elem.get("startTime")
            end = elem.get("endTime")
            if start is not None and end is not None:
                assert int(start) == 0, f"Expected startTime=0 (45000-45000), got {start}"
                assert int(end) == 15000, f"Expected endTime=15000 (60000-45000), got {end}"
                found = True
                break
        assert found, "No Effect elements found in ElementEffects"

    def test_audio_offset_does_not_mutate_placements(self, tmp_path: Path) -> None:
        """EffectPlacement objects are not mutated by audio_offset_ms serialization."""
        plan = self._make_preview_plan()  # placement at 45000-60000ms
        original_start = plan.sections[0].group_effects["Model1"][0].start_ms
        original_end = plan.sections[0].group_effects["Model1"][0].end_ms

        out = tmp_path / "preview.xsq"
        write_xsq(plan, out, scoped_duration_ms=15000, audio_offset_ms=45000)

        # Verify in-memory placement is unchanged
        placement = plan.sections[0].group_effects["Model1"][0]
        assert placement.start_ms == original_start
        assert placement.end_ms == original_end

    def test_no_media_offset_when_none(self, tmp_path: Path) -> None:
        """When audio_offset_ms is None, no <mediaOffset> element is emitted."""
        plan = self._make_preview_plan()
        out = tmp_path / "preview.xsq"
        write_xsq(plan, out)

        tree = ET.parse(out)
        root = tree.getroot()
        head = root.find("head")
        assert head is not None
        media_offset_el = head.find("mediaOffset")
        assert media_offset_el is None

    def test_scoped_and_offset_together(self, tmp_path: Path) -> None:
        """scoped_duration_ms=15000 + audio_offset_ms=45000 produces correct output."""
        plan = self._make_preview_plan()
        out = tmp_path / "preview.xsq"
        write_xsq(plan, out, scoped_duration_ms=15000, audio_offset_ms=45000)

        tree = ET.parse(out)
        root = tree.getroot()
        head = root.find("head")

        # Verify sequenceDuration is the scoped value
        dur_el = head.find("sequenceDuration")
        assert abs(float(dur_el.text) - 15.0) < 0.01

        # Verify mediaOffset is present
        media_offset_el = head.find("mediaOffset")
        assert media_offset_el is not None
        assert media_offset_el.text == "45000"

        # Verify placement times are shifted
        effects_el = root.find("ElementEffects")
        for elem in effects_el.iter("Effect"):
            start = elem.get("startTime")
            if start is not None:
                assert int(start) == 0


class TestXsqParser:
    """Tests for parsing existing .xsq files and section regeneration."""

    def test_parse_xsq_roundtrip(self, tmp_path: Path) -> None:
        """Write an XSQ, parse it back, verify structure preserved."""
        from src.generator.xsq_writer import parse_xsq

        plan = _make_plan()
        out = tmp_path / "test.xsq"
        write_xsq(plan, out)

        doc = parse_xsq(out)

        assert doc.media_file != ""
        assert doc.duration_sec > 0
        assert len(doc.effect_db) > 0
        assert len(doc.color_palettes) > 0
        assert len(doc.display_elements) > 0
        assert len(doc.element_effects) > 0

    def test_remove_effects_in_time_range(self, tmp_path: Path) -> None:
        """Remove effects within a time range, keep effects outside."""
        from src.generator.xsq_writer import parse_xsq, remove_effects_in_range

        plan = _make_plan()
        out = tmp_path / "test.xsq"
        write_xsq(plan, out)

        doc = parse_xsq(out)

        # Remove effects in 0-5000ms range (should remove Model1's placement)
        remove_effects_in_range(doc, 0, 5000)

        # Model1 had effect at 0-5000ms -> should be removed
        model1_effects = doc.element_effects.get("Model1", [])
        for p in model1_effects:
            assert not (p.start_ms >= 0 and p.end_ms <= 5000), \
                "Effects in removed range should be gone"

        # Model2 had effect at 5000-10000ms -> should still be there
        model2_effects = doc.element_effects.get("Model2", [])
        assert len(model2_effects) > 0, "Effects outside range should be preserved"

    def test_effects_outside_range_preserved(self, tmp_path: Path) -> None:
        """Effects outside the regeneration range are semantically identical."""
        from src.generator.xsq_writer import parse_xsq, remove_effects_in_range

        plan = _make_plan()
        out = tmp_path / "test.xsq"
        write_xsq(plan, out)

        doc = parse_xsq(out)
        # Capture Model2 effects before modification
        original_model2 = [
            (p.effect_name, p.start_ms, p.end_ms)
            for p in doc.element_effects.get("Model2", [])
        ]

        # Remove effects in 0-5000ms range (only affects Model1)
        remove_effects_in_range(doc, 0, 5000)

        # Model2 should be unchanged
        after_model2 = [
            (p.effect_name, p.start_ms, p.end_ms)
            for p in doc.element_effects.get("Model2", [])
        ]
        assert original_model2 == after_model2


def _make_hierarchy_with_stems(stem_names: list[str]):
    """Build a bare HierarchyResult whose only content is onset tracks per stem."""
    from src.analyzer.result import HierarchyResult

    events = {
        name: TimingTrack(
            name=f"onsets_{name}",
            algorithm_name="test",
            element_type="onset",
            marks=[TimingMark(time_ms=100 * (i + 1), confidence=0.9) for i in range(3)],
            quality_score=0.8,
            stem_source=name,
        )
        for name in stem_names
    }
    return HierarchyResult(
        schema_version="2.0.0",
        source_file="test.mp3",
        source_hash="deadbeef",
        duration_ms=1000,
        estimated_bpm=120.0,
        events=events,
    )


class TestStemOnsetTimingTracks:
    """Regression tests for FR-044 multi-stem onset timing tracks.

    Stem-aware trigger placement relies on one `Onsets (<stem>)` timing track
    per stem being embedded in the XSQ.  A previous implementation stopped
    after the first stem via `break`, leaving vocal/bass/guitar triggers with
    nothing to bind to in xLights.
    """

    def test_all_stems_with_marks_get_timing_tracks(self):
        hierarchy = _make_hierarchy_with_stems(["drums", "vocals", "bass", "guitar"])
        tracks = _collect_timing_tracks(hierarchy)
        assert "Onsets (drums)" in tracks
        assert "Onsets (vocals)" in tracks
        assert "Onsets (bass)" in tracks
        assert "Onsets (guitar)" in tracks

    def test_empty_stem_track_is_skipped(self):
        from src.analyzer.result import HierarchyResult

        hierarchy = HierarchyResult(
            schema_version="2.0.0",
            source_file="test.mp3",
            source_hash="deadbeef",
            duration_ms=1000,
            estimated_bpm=120.0,
            events={
                "drums": TimingTrack(
                    name="onsets_drums", algorithm_name="test", element_type="onset",
                    marks=[TimingMark(time_ms=100, confidence=0.9)],
                    quality_score=0.8, stem_source="drums",
                ),
                "vocals": TimingTrack(
                    name="onsets_vocals", algorithm_name="test", element_type="onset",
                    marks=[], quality_score=0.0, stem_source="vocals",
                ),
            },
        )
        tracks = _collect_timing_tracks(hierarchy)
        assert "Onsets (drums)" in tracks
        assert "Onsets (vocals)" not in tracks
