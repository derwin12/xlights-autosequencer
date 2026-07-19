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

    def test_author_is_xonset(self, tmp_path: Path) -> None:
        """<head><author> identifies xOnset as the sequence author."""
        root = _write_and_parse(_make_plan(), tmp_path)
        head = root.find("head")
        assert head is not None
        author_el = head.find("author")
        assert author_el is not None
        assert author_el.text == "xOnset"

    def test_song_and_artist_from_profile(self, tmp_path: Path) -> None:
        """<head><song>/<artist> reflect the plan's SongProfile."""
        root = _write_and_parse(_make_plan(), tmp_path)
        head = root.find("head")
        assert head is not None
        assert head.find("song").text == "Test"
        assert head.find("artist").text == "Artist"

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

    def test_moving_head_effects_are_never_deduplicated(self, tmp_path: Path) -> None:
        """Moving Head placements always get their own EffectDB entry, even
        with byte-identical parameters -- unlike every other effect type.

        Regression (bug-304, 2026-07-17): a real xLights round-trip test
        showed clicking one Moving Head effect in the UI could corrupt a
        DIFFERENT placement's content on save when the two shared an
        EffectDB entry. Moving Head placements from this pipeline are
        always immediately-adjacent warmup+punch pairs (zero gap between
        them), which real xLights' effect hit-test can conflate at the
        shared boundary -- giving two placements the same dedup'd entry
        makes that conflation corrupt saved data. A dedicated entry per
        placement removes the shared state entirely.
        """
        plan = _make_plan()
        mh_1 = EffectPlacement(
            effect_name="Moving Head",
            xlights_id="Moving Head",
            model_or_group="MH-1",
            start_ms=0,
            end_ms=1000,
            parameters={"E_SLIDER_MHTilt": "65.0"},
        )
        mh_2 = EffectPlacement(
            effect_name="Moving Head",
            xlights_id="Moving Head",
            model_or_group="MH-1",
            start_ms=1000,
            end_ms=2000,
            parameters={"E_SLIDER_MHTilt": "65.0"},
        )
        plan.moving_head_effects = {"MH-1": [mh_1, mh_2]}
        root = _write_and_parse(plan, tmp_path)
        effect_db = root.find("EffectDB")
        assert effect_db is not None

        entries = list(effect_db)
        mh_entries = [
            entry.get("settings") or entry.text or ""
            for entry in entries
            if "E_SLIDER_MHTilt=65.0" in (entry.get("settings") or entry.text or "")
        ]
        assert len(mh_entries) == 2, (
            f"Expected 2 non-deduplicated Moving Head EffectDB entries, got {len(mh_entries)}"
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

    def test_base_all_marked_as_model_group(self, tmp_path: Path) -> None:
        """01_BASE_All(_FADES) are real xLights modelGroups (written by
        src/grouper/writer.py) -- mislabeling them type="model" makes
        xLights apply per-model buffer-style semantics regardless of the
        B_CHOICE_BufferStyle=Default setting on the same element."""
        plan = _make_plan()
        placement = EffectPlacement(
            effect_name="On", xlights_id="On", model_or_group="01_BASE_All",
            start_ms=0, end_ms=5000, parameters={}, color_palette=["#FFFFFF"],
        )
        plan.sections[0].group_effects["01_BASE_All"] = [placement]
        root = _write_and_parse(plan, tmp_path)

        for section_name in ("DisplayElements", "ElementEffects"):
            section = root.find(section_name)
            assert section is not None
            base_all = next(
                (e for e in section if e.get("name") == "01_BASE_All"), None
            )
            assert base_all is not None, f"01_BASE_All missing from {section_name}"
            assert base_all.get("type") == "modelGroup"

    def test_base_all_sorts_after_every_other_group(self, tmp_path: Path) -> None:
        """01_BASE_All(_FADES) are whole-house override canvases, not
        ordinary tier-1 base groups -- the mined corpus names their
        equivalents "All (Put on bottom for GLOBAL EFFECTS/FADES)" and
        places them at the END of the element list, after tier 08 HERO.
        Sorting them with the rest of tier 01 would put them first instead,
        which does not match that convention."""
        plan = _make_plan()
        for name in ("01_BASE_All", "01_BASE_All_FADES", "08_HERO_Star"):
            plan.sections[0].group_effects[name] = [
                EffectPlacement(
                    effect_name="On", xlights_id="On", model_or_group=name,
                    start_ms=0, end_ms=5000, parameters={},
                    color_palette=["#FFFFFF"],
                )
            ]
        root = _write_and_parse(plan, tmp_path)

        for section_name in ("DisplayElements", "ElementEffects"):
            section = root.find(section_name)
            assert section is not None
            names = [e.get("name") for e in section]
            assert names.index("08_HERO_Star") < names.index("01_BASE_All")
            assert names.index("08_HERO_Star") < names.index("01_BASE_All_FADES")

    def test_buffer_style_is_baked_into_each_effects_own_params(self, tmp_path: Path) -> None:
        """xLights derives the buffer style it actually applies from each
        effect's OWN EffectDB settings string, not from the EffectLayer's
        separate "settings" attribute -- confirmed against the real corpus
        (every sampled reference .xsqz has B_CHOICE_BufferStyle baked into
        each effect's own params, sorted first alphabetically) and against
        a generated file where a tier-6 group's effects had no
        B_CHOICE_BufferStyle key at all despite the EffectLayer "settings"
        attribute saying Per Model Default -- xLights showed "Default" on
        import. Every placement's own EffectDB entry must carry the key."""
        plan = _make_plan()
        for name, expected in (
            ("06_PROP_Test", "Per Model Default"),
            ("08_HERO_Test", "Per Model Default"),
            ("01_BASE_All", "Default"),
            ("01_BASE_All_FADES", "Default"),
        ):
            plan.sections[0].group_effects[name] = [
                EffectPlacement(
                    effect_name="On", xlights_id="On", model_or_group=name,
                    start_ms=0, end_ms=5000, parameters={},
                    color_palette=["#FFFFFF"],
                )
            ]
        root = _write_and_parse(plan, tmp_path)
        effectdb = [ef.text or "" for ef in root.find("EffectDB")]

        effects_el = root.find("ElementEffects")
        for group_name, expected in (
            ("06_PROP_Test", "Per Model Default"),
            ("08_HERO_Test", "Per Model Default"),
            ("01_BASE_All", "Default"),
            ("01_BASE_All_FADES", "Default"),
        ):
            group_el = next(e for e in effects_el if e.get("name") == group_name)
            effect_el = group_el.find("EffectLayer").find("Effect")
            ref = int(effect_el.get("ref"))
            assert f"B_CHOICE_BufferStyle={expected}" in effectdb[ref], (
                f"{group_name}: expected B_CHOICE_BufferStyle={expected} in "
                f"'{effectdb[ref]}'"
            )

    def test_strobe_and_marquee_get_per_model_default_on_all_group(self, tmp_path: Path) -> None:
        """Strobe/Marquee look wrong stretched across the ALL group's unified
        canvas, so they render Per Model Default even though every other
        effect on 01_BASE_All(_FADES) uses the group's "Default" style."""
        plan = _make_plan()
        for name in ("01_BASE_All", "01_BASE_All_FADES"):
            plan.sections[0].group_effects[name] = [
                EffectPlacement(
                    effect_name="Strobe", xlights_id="Strobe", model_or_group=name,
                    start_ms=0, end_ms=1000, parameters={},
                    color_palette=["#FFFFFF"],
                ),
                EffectPlacement(
                    effect_name="Marquee", xlights_id="Marquee", model_or_group=name,
                    start_ms=1000, end_ms=2000, parameters={},
                    color_palette=["#FFFFFF"],
                ),
                EffectPlacement(
                    effect_name="On", xlights_id="On", model_or_group=name,
                    start_ms=2000, end_ms=3000, parameters={},
                    color_palette=["#FFFFFF"],
                ),
            ]
        root = _write_and_parse(plan, tmp_path)
        effectdb = [ef.text or "" for ef in root.find("EffectDB")]
        effects_el = root.find("ElementEffects")

        for group_name in ("01_BASE_All", "01_BASE_All_FADES"):
            group_el = next(e for e in effects_el if e.get("name") == group_name)
            effect_els = group_el.find("EffectLayer").findall("Effect")
            by_name = {e.get("name"): int(e.get("ref")) for e in effect_els}
            assert f"B_CHOICE_BufferStyle=Per Model Default" in effectdb[by_name["Strobe"]]
            assert f"B_CHOICE_BufferStyle=Per Model Default" in effectdb[by_name["Marquee"]]
            assert "B_CHOICE_BufferStyle=Default" in effectdb[by_name["On"]]

    def test_shockwave_gets_the_preview_variant_of_its_tier_style(self, tmp_path: Path) -> None:
        """Shockwave always renders as the "...Per Preview" variant of
        whichever tier-based style would otherwise apply (user request,
        2026-07-18): Default -> Per Preview, Per Model Default -> Per
        Model Per Preview. A non-Shockwave effect in the same groups keeps
        the ordinary tier style, confirming this is Shockwave-specific."""
        plan = _make_plan()
        for name in ("01_BASE_All_FADES", "06_PROP_Test"):
            plan.sections[0].group_effects[name] = [
                EffectPlacement(
                    effect_name="Shockwave", xlights_id="Shockwave", model_or_group=name,
                    start_ms=0, end_ms=1000, parameters={},
                    color_palette=["#FFFFFF"],
                ),
                EffectPlacement(
                    effect_name="On", xlights_id="On", model_or_group=name,
                    start_ms=1000, end_ms=2000, parameters={},
                    color_palette=["#FFFFFF"],
                ),
            ]
        root = _write_and_parse(plan, tmp_path)
        effectdb = [ef.text or "" for ef in root.find("EffectDB")]
        effects_el = root.find("ElementEffects")

        for group_name, expected_shockwave, expected_on in (
            ("01_BASE_All_FADES", "Per Preview", "Default"),
            ("06_PROP_Test", "Per Model Per Preview", "Per Model Default"),
        ):
            group_el = next(e for e in effects_el if e.get("name") == group_name)
            effect_els = group_el.find("EffectLayer").findall("Effect")
            by_name = {e.get("name"): int(e.get("ref")) for e in effect_els}
            assert f"B_CHOICE_BufferStyle={expected_shockwave}" in effectdb[by_name["Shockwave"]]
            assert f"B_CHOICE_BufferStyle={expected_on}" in effectdb[by_name["On"]]

    def test_shockwave_on_individual_model_gets_per_model_per_preview(self, tmp_path: Path) -> None:
        """Regression (2026-07-18): a Shockwave targeting an individual
        model directly (e.g. "Snowflake Prop", type="model" -- not routed
        through any tier-prefixed group) has no tier convention to read,
        so _buffer_style_for_group returns None. The two-entry Default/Per
        Model Default map left that case with no override at all
        (rendered as unset on import). A single-model target is inherently
        "per model" already, so it must still get Per Model Per Preview."""
        plan = _make_plan()
        plan.sections[0].group_effects["Snowflake Prop"] = [
            EffectPlacement(
                effect_name="Shockwave", xlights_id="Shockwave",
                model_or_group="Snowflake Prop",
                start_ms=0, end_ms=1000, parameters={},
                color_palette=["#FFFFFF"],
            ),
        ]
        root = _write_and_parse(plan, tmp_path)
        effectdb = [ef.text or "" for ef in root.find("EffectDB")]
        effects_el = root.find("ElementEffects")
        group_el = next(e for e in effects_el if e.get("name") == "Snowflake Prop")
        ref = int(group_el.find("EffectLayer").find("Effect").get("ref"))
        assert "B_CHOICE_BufferStyle=Per Model Per Preview" in effectdb[ref]

    def test_all_beat_groups_get_per_model_per_preview_for_every_effect(self, tmp_path: Path) -> None:
        """Every effect on the four BEAT groups gets the preview variant
        (user request, 2026-07-18) -- not just Shockwave. A non-Shockwave
        effect (e.g. "On") on an unrelated tier-4 group keeps the ordinary
        "Per Model Default" style, confirming this is BEAT-group-specific."""
        plan = _make_plan()
        for name in ("04_BEAT_1", "04_BEAT_2", "04_BEAT_3", "04_BEAT_4", "04_OTHER_Test"):
            plan.sections[0].group_effects[name] = [
                EffectPlacement(
                    effect_name="On", xlights_id="On", model_or_group=name,
                    start_ms=0, end_ms=1000, parameters={},
                    color_palette=["#FFFFFF"],
                ),
            ]
        root = _write_and_parse(plan, tmp_path)
        effectdb = [ef.text or "" for ef in root.find("EffectDB")]
        effects_el = root.find("ElementEffects")

        for name in ("04_BEAT_1", "04_BEAT_2", "04_BEAT_3", "04_BEAT_4"):
            group_el = next(e for e in effects_el if e.get("name") == name)
            ref = int(group_el.find("EffectLayer").find("Effect").get("ref"))
            assert f"B_CHOICE_BufferStyle=Per Model Per Preview" in effectdb[ref], name

        group_el = next(e for e in effects_el if e.get("name") == "04_OTHER_Test")
        ref = int(group_el.find("EffectLayer").find("Effect").get("ref"))
        assert "B_CHOICE_BufferStyle=Per Model Default" in effectdb[ref]

    def test_tier_1_to_3_non_override_groups_get_no_buffer_style_key(self, tmp_path: Path) -> None:
        """Tiers 01-03 (other than the 01_BASE_All(_FADES) override
        canvases) render as a unified group with no explicit buffer style
        override -- matches pre-existing behavior, not part of this fix."""
        plan = _make_plan()
        plan.sections[0].group_effects["02_GEO_Test"] = [
            EffectPlacement(
                effect_name="On", xlights_id="On", model_or_group="02_GEO_Test",
                start_ms=0, end_ms=5000, parameters={},
                color_palette=["#FFFFFF"],
            )
        ]
        root = _write_and_parse(plan, tmp_path)
        effectdb = [ef.text or "" for ef in root.find("EffectDB")]
        effects_el = root.find("ElementEffects")
        group_el = next(e for e in effects_el if e.get("name") == "02_GEO_Test")
        effect_el = group_el.find("EffectLayer").find("Effect")
        ref = int(effect_el.get("ref"))
        assert "B_CHOICE_BufferStyle" not in effectdb[ref]

    def test_other_groups_stay_marked_as_model(self, tmp_path: Path) -> None:
        """Only 01_BASE_All(_FADES) get the modelGroup fix -- every other
        group name (e.g. tier-6 PROP groups) keeps type="model" as before,
        since their existing "Per Model Default" buffer-style behavior may
        already rely on it."""
        root = _write_and_parse(_make_plan(), tmp_path)
        for section_name in ("DisplayElements", "ElementEffects"):
            section = root.find(section_name)
            assert section is not None
            for elem in section:
                if elem.get("name") in ("Model1", "Model2"):
                    assert elem.get("type") == "model"


class TestCanvasPropertyNeverSet:
    """User rule (2026-07-18): never emit T_CHECKBOX_Canvas on any effect,
    even if a mined vendor .xsqz template includes it. Enforced as a strip
    in _serialize_effect_params, not just an omission from
    _XLIGHTS_EFFECT_DEFAULTS -- so it can't come back via a placement's own
    parameters or a future template-mining pass either."""

    def test_canvas_absent_from_default_placements(self, tmp_path: Path) -> None:
        root = _write_and_parse(_make_plan(), tmp_path)
        effect_db = root.find("EffectDB")
        assert effect_db is not None
        for entry in effect_db:
            text = entry.get("settings") or entry.text or ""
            assert "T_CHECKBOX_Canvas" not in text

    def test_canvas_stripped_even_when_explicitly_set(self, tmp_path: Path) -> None:
        """Even a placement that explicitly sets T_CHECKBOX_Canvas in its
        own parameters (e.g. copied from a mined template) must not have
        it survive serialization."""
        plan = _make_plan()
        plan.sections[0].group_effects["Model1"][0].parameters["T_CHECKBOX_Canvas"] = "1"
        root = _write_and_parse(plan, tmp_path)
        effect_db = root.find("EffectDB")
        assert effect_db is not None
        for entry in effect_db:
            text = entry.get("settings") or entry.text or ""
            assert "T_CHECKBOX_Canvas" not in text


class TestSpiralsDefaultsMatchCatalogStorageNames:
    """Regression guard for the Spirals_Movement bug: xLights persists a
    stale E_SLIDER_ snapshot alongside the real E_TEXTCTRL_ value in its
    clipboard format, but only the E_TEXTCTRL_ key survives once the
    effect is actually opened in xLights. _XLIGHTS_EFFECT_DEFAULTS used
    the stale E_SLIDER_ key, so every generated Spirals effect carried
    both — this asserts the default keys match the real catalog."""

    def test_default_keys_are_real_storage_names(self):
        from src.effects.library import load_effect_library
        from src.generator.xsq_writer import _XLIGHTS_EFFECT_DEFAULTS

        library = load_effect_library()
        effect_def = library.effects["Spirals"]
        known = {p.storage_name for p in effect_def.parameters}
        for key in _XLIGHTS_EFFECT_DEFAULTS["Spirals"]:
            if key.startswith(("T_", "C_")):
                continue
            assert key in known, f"Spirals.{key} is not a real catalog storage_name"


def _default_keys_match_catalog(effect_name: str) -> None:
    """Shared assertion for the storage-name regression guards below —
    same check as TestSpiralsDefaultsMatchCatalogStorageNames, scoped per
    effect so a failure names exactly which effect's writer defaults
    drifted from the catalog."""
    from src.effects.library import load_effect_library
    from src.generator.xsq_writer import _XLIGHTS_EFFECT_DEFAULTS

    library = load_effect_library()
    effect_def = library.effects[effect_name]
    known = {p.storage_name for p in effect_def.parameters}
    for key in _XLIGHTS_EFFECT_DEFAULTS[effect_name]:
        if key.startswith(("T_", "C_", "E_NOTEBOOK", "E_FILEPICKERCTRL", "E_FONTPICKER")):
            continue
        assert key in known, f"{effect_name}.{key} is not a real catalog storage_name"


class TestMorphCoordinateKeysMatchCatalog:
    """Regression guard: Morph_Start_X1/Y1 and Morph_End_X1/Y1 were catalogued
    as E_SLIDER_MorphStartX1 etc (missing underscores) instead of the real
    E_SLIDER_Morph_Start_X1. xLights' GetValueCurveInt only checks
    SLIDER_Morph_Start_X1 then TEXTCTRL_Morph_Start_X1 — the mangled name
    matches neither, so a non-default coordinate is silently dropped and
    the effect always renders at the hardcoded 0,0/100,100 corners."""

    def test_coordinate_params_use_underscored_storage_names(self):
        from src.effects.library import load_effect_library

        library = load_effect_library()
        by_name = {p.name: p.storage_name for p in library.effects["Morph"].parameters}
        assert by_name["Morph_Start_X1"] == "E_SLIDER_Morph_Start_X1"
        assert by_name["Morph_Start_Y1"] == "E_SLIDER_Morph_Start_Y1"
        assert by_name["Morph_End_X1"] == "E_SLIDER_Morph_End_X1"
        assert by_name["Morph_End_Y1"] == "E_SLIDER_Morph_End_Y1"

    def test_stagger_allows_negative_values(self):
        from src.effects.library import load_effect_library

        library = load_effect_library()
        by_name = {p.name: p for p in library.effects["Morph"].parameters}
        assert by_name["Morph_Stagger"].min == -100


class TestMeteorsOffsetKeysMatchCatalog:
    """Regression guard: Meteors_XOffset/YOffset persist as E_TEXTCTRL_ in
    xLights (the panel's real control is a text ctrl; the paired slider is
    a non-persisting display twin), not E_SLIDER_. Render has a
    SLIDER-then-TEXTCTRL fallback so the old key still rendered, but was
    not the GUI-canonical key."""

    def test_offset_params_use_textctrl_storage_names(self):
        from src.effects.library import load_effect_library

        library = load_effect_library()
        by_name = {p.name: p.storage_name for p in library.effects["Meteors"].parameters}
        assert by_name["Meteors_XOffset"] == "E_TEXTCTRL_Meteors_XOffset"
        assert by_name["Meteors_YOffset"] == "E_TEXTCTRL_Meteors_YOffset"


class TestGarlandsCatalogAndDefaults:
    """Garlands had no catalog entry at all, and _XLIGHTS_EFFECT_DEFAULTS
    used the pre-migration E_SLIDER_Garlands_Cycles key (xLights migrated
    this control to E_TEXTCTRL_Garlands_Cycles, divisor 10, in 2026.05.2)
    plus an out-of-range Spacing default (0, when the real control's min
    is 1)."""

    def test_writer_defaults_match_catalog(self):
        _default_keys_match_catalog("Garlands")

    def test_cycles_uses_textctrl_storage_name(self):
        from src.effects.library import load_effect_library

        library = load_effect_library()
        by_name = {p.name: p.storage_name for p in library.effects["Garlands"].parameters}
        assert by_name["Garlands_Cycles"] == "E_TEXTCTRL_Garlands_Cycles"

    def test_writer_spacing_default_within_real_min(self):
        from src.generator.xsq_writer import _XLIGHTS_EFFECT_DEFAULTS

        assert int(_XLIGHTS_EFFECT_DEFAULTS["Garlands"]["E_SLIDER_Garlands_Spacing"]) >= 1


class TestCirclesValuesMatchXLightsRanges:
    """Circles_Speed/XC/YC had wrong default/range (Speed 1/0-50 vs the
    real 10/1-30; XC/YC +-100 vs the real +-50), Circles_Bounce defaulted
    true instead of false, and a phantom Circles_Collide parameter aliased
    to E_CHECKBOX_Circles_Bounce duplicated a control xLights removed in
    2026.05.2 (migrated into Bounce, then erased)."""

    def test_speed_and_center_ranges_match_xlights(self):
        from src.effects.library import load_effect_library

        library = load_effect_library()
        by_name = {p.name: p for p in library.effects["Circles"].parameters}
        assert (by_name["Circles_Speed"].default, by_name["Circles_Speed"].min, by_name["Circles_Speed"].max) == (10, 1, 30)
        assert (by_name["Circles_XC"].min, by_name["Circles_XC"].max) == (-50, 50)
        assert (by_name["Circles_YC"].min, by_name["Circles_YC"].max) == (-50, 50)
        assert by_name["Circles_Bounce"].default is False

    def test_phantom_collide_param_removed(self):
        from src.effects.library import load_effect_library

        library = load_effect_library()
        names = {p.name for p in library.effects["Circles"].parameters}
        assert "Circles_Collide" not in names


class TestGalaxyCatalogAndDefaults:
    """Galaxy had no catalog entry at all, and _XLIGHTS_EFFECT_DEFAULTS'
    Revolutions default ("3") was off by two orders of magnitude — the
    real slider stores a pre-divisor int (divisor 360), so "3" is
    effectively ~0.008 revolutions instead of the intended 4.0 (raw 1440)."""

    def test_writer_defaults_match_catalog(self):
        _default_keys_match_catalog("Galaxy")

    def test_writer_revolutions_default_is_pre_divisor_scale(self):
        from src.generator.xsq_writer import _XLIGHTS_EFFECT_DEFAULTS

        # 1440 / 360 == 4.0 revolutions; "3" (the old value) would be ~0.008.
        assert _XLIGHTS_EFFECT_DEFAULTS["Galaxy"]["E_SLIDER_Galaxy_Revolutions"] == "1440"


class TestTextCatalogKeysMatchXLights:
    """Text_Line1/E_TEXTCTRL_Text_Line1 and E_SLIDER_Text_Speed had no
    render-side fallback in xLights — TextEffect.cpp only ever reads
    TEXTCTRL_Text and TEXTCTRL_Text_Speed, so a catalog consumer using the
    old keys would silently render no text / ignore the speed override."""

    def test_text_and_speed_use_textctrl_storage_names(self):
        from src.effects.library import load_effect_library

        library = load_effect_library()
        by_name = {p.name: p.storage_name for p in library.effects["Text"].parameters}
        assert by_name["Text"] == "E_TEXTCTRL_Text"
        assert by_name["Text_Speed"] == "E_TEXTCTRL_Text_Speed"

    def test_text_dir_choices_are_real_lowercase_tokens(self):
        from src.effects.library import load_effect_library

        library = load_effect_library()
        by_name = {p.name: p for p in library.effects["Text"].parameters}
        assert by_name["Text_Dir"].default == "none"
        assert "vector" in by_name["Text_Dir"].choices
        assert "Left" not in by_name["Text_Dir"].choices


class TestFacesCatalogAndDefaults:
    """Faces had no catalog entry at all. LeadFrames persists as a spin
    control (E_SPINCTRL_Faces_LeadFrames), not a slider/textctrl, and
    Faces_Fade was missing from the writer defaults entirely."""

    def test_writer_defaults_match_catalog(self):
        _default_keys_match_catalog("Faces")

    def test_lead_frames_uses_spinctrl_storage_name(self):
        from src.effects.library import load_effect_library

        library = load_effect_library()
        by_name = {p.name: p.storage_name for p in library.effects["Faces"].parameters}
        assert by_name["Faces_LeadFrames"] == "E_SPINCTRL_Faces_LeadFrames"

    def test_writer_defaults_include_fade(self):
        from src.generator.xsq_writer import _XLIGHTS_EFFECT_DEFAULTS

        assert "E_CHECKBOX_Faces_Fade" in _XLIGHTS_EFFECT_DEFAULTS["Faces"]


class TestPinwheel3DChoiceCasing:
    """Pinwheel_3D's "None" option was catalogued as lowercase "none".
    xLights' to3dType() treats any non-matching string as None anyway, so
    this was cosmetic/round-trip-only, not a rendering bug — this guards
    against it drifting from the canonical casing the variants already use."""

    def test_none_choice_uses_canonical_casing(self):
        from src.effects.library import load_effect_library

        library = load_effect_library()
        by_name = {p.name: p for p in library.effects["Pinwheel"].parameters}
        assert by_name["Pinwheel_3D"].default == "None"
        assert "None" in by_name["Pinwheel_3D"].choices
        assert "none" not in by_name["Pinwheel_3D"].choices


class TestVideoEffectPortability:
    """Video effect filenames must be host/devcontainer-portable, like mediaFile."""

    def test_video_filename_rewritten_to_basename_and_copied(self, tmp_path: Path) -> None:
        """The source video is copied next to the .xsq and the effect param
        is rewritten to a bare filename — a container-only absolute path
        (e.g. /home/node/.xlight/library/...) is unusable by xLights on the
        host, exactly like an unqualified audio mediaFile path would be."""
        source_video = tmp_path / "source" / "clip_480p.mp4"
        source_video.parent.mkdir()
        source_video.write_bytes(b"fake video bytes")

        plan = _make_plan()
        plan.video_effects = {
            "Matrix1": [
                EffectPlacement(
                    effect_name="Video",
                    xlights_id="Video",
                    model_or_group="Matrix1",
                    start_ms=0,
                    end_ms=10000,
                    parameters={
                        "E_FILEPICKERCTRL_Video_Filename": str(source_video),
                        "E_TEXTCTRL_Duration": "0:10.000",
                    },
                    color_palette=["#FFFFFF"],
                )
            ]
        }

        out_dir = tmp_path / "output"
        out_dir.mkdir()
        out_path = out_dir / "test.xsq"
        write_xsq(plan, out_path)

        placement = plan.video_effects["Matrix1"][0]
        assert placement.parameters["E_FILEPICKERCTRL_Video_Filename"] == "clip_480p.mp4"
        assert (out_dir / "clip_480p.mp4").exists()

        root = ET.parse(out_path).getroot()
        effect_db = root.find("EffectDB")
        assert effect_db is not None
        found = any(
            "E_FILEPICKERCTRL_Video_Filename=clip_480p.mp4" in (entry.get("settings") or entry.text or "")
            for entry in effect_db
        )
        assert found, "Expected bare filename in the serialized Video EffectDB entry"


class TestPictureFilenamePortability:
    """Pictures effect filenames must resolve to the user's original upload
    name, not the id-prefixed name used internally to avoid collisions inside
    the image library folder (bug reported 2026-07-15: exported filename
    showed as '<id>_books.png' instead of 'books.png')."""

    def _picture_plan(self, stored_path: str) -> SequencePlan:
        plan = _make_plan()
        plan.picture_effects = {
            "Matrix1": [
                EffectPlacement(
                    effect_name="Pictures",
                    xlights_id="Pictures",
                    model_or_group="Matrix1",
                    start_ms=0,
                    end_ms=10000,
                    parameters={"E_TEXTCTRL_Pictures_Filename": stored_path},
                    color_palette=["#FFFFFF"],
                )
            ]
        }
        return plan

    def test_filename_rewritten_to_original_upload_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path / "state"))
        from src.generator.image_catalog import save_image_to_library

        entry = save_image_to_library(
            tag="books", filename="books.png", data=b"fake image bytes",
            uploaded_at="2026-07-15T00:00:00Z",
        )

        plan = self._picture_plan(entry["stored_path"])
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        out_path = out_dir / "test.xsq"
        write_xsq(plan, out_path)

        placement = plan.picture_effects["Matrix1"][0]
        assert placement.parameters["E_TEXTCTRL_Pictures_Filename"] == "books.png"
        assert (out_dir / "books.png").exists()

    def test_colliding_original_names_fall_back_to_stored_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("XLIGHT_STATE_HOME", str(tmp_path / "state"))
        from src.generator.image_catalog import save_image_to_library

        first = save_image_to_library(
            tag="books-a", filename="books.png", data=b"image one",
            uploaded_at="2026-07-15T00:00:00Z",
        )
        second = save_image_to_library(
            tag="books-b", filename="books.png", data=b"image two",
            uploaded_at="2026-07-15T00:01:00Z",
        )

        plan = _make_plan()
        plan.picture_effects = {
            "Matrix1": [
                EffectPlacement(
                    effect_name="Pictures", xlights_id="Pictures",
                    model_or_group="Matrix1", start_ms=0, end_ms=5000,
                    parameters={"E_TEXTCTRL_Pictures_Filename": first["stored_path"]},
                    color_palette=["#FFFFFF"],
                ),
                EffectPlacement(
                    effect_name="Pictures", xlights_id="Pictures",
                    model_or_group="Matrix1", start_ms=5000, end_ms=10000,
                    parameters={"E_TEXTCTRL_Pictures_Filename": second["stored_path"]},
                    color_palette=["#FFFFFF"],
                ),
            ]
        }

        out_dir = tmp_path / "output"
        out_dir.mkdir()
        write_xsq(plan, out_dir / "test.xsq")

        first_name = plan.picture_effects["Matrix1"][0].parameters["E_TEXTCTRL_Pictures_Filename"]
        second_name = plan.picture_effects["Matrix1"][1].parameters["E_TEXTCTRL_Pictures_Filename"]
        assert first_name == "books.png"
        assert second_name == Path(second["stored_path"]).name
        assert first_name != second_name
        assert (out_dir / first_name).read_bytes() == b"image one"
        assert (out_dir / second_name).read_bytes() == b"image two"


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

    def test_onsets_tracks_are_hidden_from_the_timing_display_list(self, tmp_path: Path) -> None:
        """Onsets (<stem>) tracks exist only to bind stem-aware effect
        triggers -- they clutter xLights' timing-track list, so they're
        written visible="0" while Beats/Bars/Sections/Chords stay visible."""
        hierarchy = _make_hierarchy_with_stems(["drums", "vocals"])
        hierarchy.beats = TimingTrack(
            name="beats", algorithm_name="test", element_type="beat",
            marks=[TimingMark(time_ms=100, confidence=0.9)], quality_score=0.8,
        )
        out = tmp_path / "test.xsq"
        write_xsq(_make_plan(), out, hierarchy=hierarchy)
        root = ET.parse(out).getroot()

        display_els = {e.get("name"): e for e in root.find("DisplayElements").findall("Element")
                       if e.get("type") == "timing"}
        assert display_els["Onsets (drums)"].get("visible") == "0"
        assert display_els["Onsets (vocals)"].get("visible") == "0"
        assert display_els["Beats"].get("visible") == "1"


class TestLyricsTimingTrack:
    """Synced-lyrics lines get embedded as a "Lyrics" timing track."""

    def test_lyrics_produce_a_timing_track(self):
        lyrics = [
            {"t_ms": 1000, "duration_ms": 2000, "text": "la la placeholder line one"},
            {"t_ms": 3000, "duration_ms": 2000, "text": "la la placeholder line two"},
        ]
        tracks = _collect_timing_tracks(None, lyrics)
        assert "Lyrics" in tracks
        assert [m.label for m in tracks["Lyrics"]] == [
            "la la placeholder line one",
            "la la placeholder line two",
        ]
        assert tracks["Lyrics"][0].time_ms == 1000
        assert tracks["Lyrics"][0].duration_ms == 2000

    def test_no_lyrics_produces_no_lyrics_track(self):
        tracks = _collect_timing_tracks(None, None)
        assert "Lyrics" not in tracks

    def test_empty_lyrics_list_produces_no_lyrics_track(self):
        tracks = _collect_timing_tracks(None, [])
        assert "Lyrics" not in tracks

    def test_write_xsq_embeds_lyrics_element(self, tmp_path: Path) -> None:
        """End-to-end: write_xsq(..., lyrics=...) emits a Lyrics <Element>
        with one <Effect> per line, in the same shape as Beats/Bars/etc.

        Marks carrying a duration_ms end at start+duration (capped at the
        next mark's start); these lines' durations reach exactly to the next
        mark / song end, so they span contiguously.
        """
        lyrics = [
            {"t_ms": 1000, "duration_ms": 2000, "text": "la la placeholder line one"},
            {"t_ms": 3000, "duration_ms": 7000, "text": "la la placeholder line two"},
        ]
        out = tmp_path / "test.xsq"
        write_xsq(_make_plan(), out, lyrics=lyrics)
        root = ET.parse(out).getroot()

        display_els = root.find("DisplayElements").findall("Element")
        lyrics_display = [e for e in display_els if e.get("name") == "Lyrics"]
        assert len(lyrics_display) == 1
        assert lyrics_display[0].get("type") == "timing"

        effect_els = root.find("ElementEffects").findall("Element")
        lyrics_effects = [e for e in effect_els if e.get("name") == "Lyrics"]
        assert len(lyrics_effects) == 1
        effects = lyrics_effects[0].find("EffectLayer").findall("Effect")
        assert [e.get("label") for e in effects] == [
            "la la placeholder line one",
            "la la placeholder line two",
        ]
        assert effects[0].get("startTime") == "1000"
        assert effects[0].get("endTime") == "3000"
        assert effects[1].get("startTime") == "3000"
        assert effects[1].get("endTime") == "10000"  # last mark → song duration


class TestLyricLayeredTimingTrack:
    """With word+phoneme marks, "Lyrics" becomes xLights' native 3-layer
    lyric track: layer 1 phrases, layer 2 words, layer 3 phonemes."""

    LYRICS = [{"t_ms": 1000, "duration_ms": 3500, "text": "hello world"}]
    WORDS = [
        {"label": "HELLO", "start_ms": 1000, "end_ms": 1400},
        {"label": "WORLD", "start_ms": 4000, "end_ms": 4500},
    ]
    PHONEMES = [
        {"label": "E", "start_ms": 1000, "end_ms": 1200},
        {"label": "O", "start_ms": 1200, "end_ms": 1400},
    ]

    def test_three_layers_in_order(self, tmp_path: Path) -> None:
        out = tmp_path / "test.xsq"
        write_xsq(_make_plan(), out, lyrics=self.LYRICS,
                  words=self.WORDS, phonemes=self.PHONEMES)
        root = ET.parse(out).getroot()

        effect_els = root.find("ElementEffects").findall("Element")
        lyrics_els = [e for e in effect_els
                      if e.get("type") == "timing" and e.get("name") == "Lyrics"]
        assert len(lyrics_els) == 1
        layers = lyrics_els[0].findall("EffectLayer")
        assert len(layers) == 3
        assert [e.get("label") for e in layers[0].findall("Effect")] == ["hello world"]
        assert [e.get("label") for e in layers[1].findall("Effect")] == ["HELLO", "WORLD"]
        assert [e.get("label") for e in layers[2].findall("Effect")] == ["E", "O"]
        # No separate Words/Phonemes elements
        names = {e.get("name") for e in effect_els if e.get("type") == "timing"}
        assert "Words" not in names and "Phonemes" not in names

    def test_word_effects_do_not_stretch_across_silence(self, tmp_path: Path) -> None:
        """A word's timing effect ends at its own end_ms, not at the next
        word's start — otherwise mouths/text hold through instrumental gaps."""
        out = tmp_path / "test.xsq"
        write_xsq(_make_plan(), out, lyrics=self.LYRICS,
                  words=self.WORDS, phonemes=self.PHONEMES)
        root = ET.parse(out).getroot()

        effect_els = root.find("ElementEffects").findall("Element")
        lyrics_el = [e for e in effect_els
                     if e.get("type") == "timing" and e.get("name") == "Lyrics"][0]
        word_effects = lyrics_el.findall("EffectLayer")[1].findall("Effect")
        assert word_effects[0].get("startTime") == "1000"
        assert word_effects[0].get("endTime") == "1400"  # not 4000
        assert word_effects[1].get("endTime") == "4500"  # not song duration

    def test_no_words_keeps_single_layer_lyrics(self, tmp_path: Path) -> None:
        out = tmp_path / "test.xsq"
        write_xsq(_make_plan(), out, lyrics=self.LYRICS)
        root = ET.parse(out).getroot()
        effect_els = root.find("ElementEffects").findall("Element")
        lyrics_el = [e for e in effect_els
                     if e.get("type") == "timing" and e.get("name") == "Lyrics"][0]
        assert len(lyrics_el.findall("EffectLayer")) == 1

    def test_no_lyric_lines_builds_phrase_spans_from_words(self, tmp_path: Path) -> None:
        """Free-transcription case: no LRC lines, but words/phonemes exist.
        Layer positions are fixed by xLights convention, so an unlabeled
        phrase layer is synthesized to keep words on layer 2."""
        out = tmp_path / "test.xsq"
        write_xsq(_make_plan(), out, words=self.WORDS, phonemes=self.PHONEMES)
        root = ET.parse(out).getroot()
        effect_els = root.find("ElementEffects").findall("Element")
        lyrics_el = [e for e in effect_els
                     if e.get("type") == "timing" and e.get("name") == "Lyrics"][0]
        layers = lyrics_el.findall("EffectLayer")
        assert len(layers) == 3
        assert [e.get("label") for e in layers[1].findall("Effect")] == ["HELLO", "WORLD"]


class TestFacesAndTextEffectSerialization:
    """Faces/Text placements merge the real-xLights defaults with per-placement params."""

    def _plan_with(self, placement: EffectPlacement) -> SequencePlan:
        plan = _make_plan()
        plan.sections[0].group_effects[placement.model_or_group] = [placement]
        return plan

    def test_faces_effect_db_entry(self, tmp_path: Path) -> None:
        placement = EffectPlacement(
            effect_name="Faces",
            xlights_id="Faces",
            model_or_group="Singing Face",
            start_ms=1000,
            end_ms=5000,
            parameters={
                "E_CHOICE_Faces_FaceDefinition": "SingingFace",
                "E_CHOICE_Faces_TimingTrack": "Lyrics",
            },
            color_palette=["#FFFFFF"],
        )
        out = tmp_path / "test.xsq"
        write_xsq(self._plan_with(placement), out)
        root = ET.parse(out).getroot()

        entries = [e.text for e in root.find("EffectDB").findall("Effect")]
        faces = [s for s in entries if s and "E_CHOICE_Faces_FaceDefinition" in s]
        assert len(faces) == 1
        assert "E_CHOICE_Faces_FaceDefinition=SingingFace" in faces[0]
        assert "E_CHOICE_Faces_TimingTrack=Lyrics" in faces[0]
        assert "E_CHECKBOX_Faces_Outline=1" in faces[0]

    def test_vocal_effects_survive_zero_sections(self, tmp_path: Path) -> None:
        """bug-159 guard: plan.vocal_effects render even when a 0-section
        analysis produced no section assignments at all."""
        plan = _make_plan()
        plan.sections = []
        plan.vocal_effects = {
            "Singing Face": [EffectPlacement(
                effect_name="Faces",
                xlights_id="Faces",
                model_or_group="Singing Face",
                start_ms=1000,
                end_ms=5000,
                parameters={
                    "E_CHOICE_Faces_FaceDefinition": "SingingFace",
                    "E_CHOICE_Faces_TimingTrack": "Phonemes",
                },
                color_palette=["#FFFFFF"],
            )],
        }
        out = tmp_path / "test.xsq"
        write_xsq(plan, out)
        root = ET.parse(out).getroot()

        model_els = [e for e in root.find("ElementEffects")
                     if e.get("type") == "model" and e.get("name") == "Singing Face"]
        assert len(model_els) == 1
        effects = model_els[0].find("EffectLayer").findall("Effect")
        assert [e.get("name") for e in effects] == ["Faces"]

    def test_text_effect_db_entry(self, tmp_path: Path) -> None:
        placement = EffectPlacement(
            effect_name="Text",
            xlights_id="Text",
            model_or_group="Matrix - 1L",
            start_ms=1000,
            end_ms=5000,
            parameters={"E_CHOICE_Text_LyricTrack": "Lyrics - Words"},
            color_palette=["#FFFFFF"],
        )
        out = tmp_path / "test.xsq"
        write_xsq(self._plan_with(placement), out)
        root = ET.parse(out).getroot()

        entries = [e.text for e in root.find("EffectDB").findall("Effect")]
        texts = [s for s in entries if s and "E_CHOICE_Text_LyricTrack" in s]
        assert len(texts) == 1
        assert "E_CHOICE_Text_LyricTrack=Lyrics - Words" in texts[0]
        assert "E_FONTPICKER_Text_Font=" in texts[0]


# Bare parameter names whose slider widget was replaced by a float/int
# textctrl in current xLights (bugs 192-194, re-applied 2026-07-14 after
# the original fix landed on an unmerged branch). The obsolete E_SLIDER_
# form corrupts rendering when emitted; only the E_TEXTCTRL_ form may
# appear in writer defaults or builtin variant overrides.
_MIGRATED_TO_TEXTCTRL = (
    "Spirals_Movement",
    "Chase_Rotations",
    "Chase_Offset",
    "ColorWash_Cycles",
    "Shimmer_Cycles",
    "Ripple_Cycles",
    "Wave_Speed",
    "LifeTime",
    "Liquid_Gravity",
    "Liquid_GravityAngle",
    "Liquid_SourceSize1",
    "X1",
    "Y1",
    "Direction1",
    "Velocity1",
    "Flow1",
    "Meteors_XOffset",
    "Meteors_YOffset",
    "Garlands_Cycles",
)


class TestMigratedSliderKeysAbsent:
    def test_writer_defaults_carry_no_migrated_slider_keys(self) -> None:
        from src.generator.xsq_writer import _XLIGHTS_EFFECT_DEFAULTS

        for effect, params in _XLIGHTS_EFFECT_DEFAULTS.items():
            for bare in _MIGRATED_TO_TEXTCTRL:
                assert f"E_SLIDER_{bare}" not in params, (effect, bare)

    def test_builtin_variants_carry_no_migrated_slider_keys(self) -> None:
        import json
        from pathlib import Path

        for path in Path("src/variants/builtins").glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            for variant in data.get("variants", []):
                overrides = variant.get("parameter_overrides", {})
                for bare in _MIGRATED_TO_TEXTCTRL:
                    assert f"E_SLIDER_{bare}" not in overrides, (
                        path.name, variant["name"], bare,
                    )

    def test_builtin_effects_catalog_carries_no_migrated_slider_keys(self) -> None:
        from pathlib import Path

        text = Path("src/effects/builtin_effects.json").read_text(encoding="utf-8")
        for bare in _MIGRATED_TO_TEXTCTRL:
            assert f'"E_SLIDER_{bare}"' not in text, bare


class TestIncludeExtraTiming:
    """include_extra_timing=False omits the display-only Chords and
    Onsets (<stem>) timing tracks while keeping Beats/Bars/Sections."""

    def _hierarchy_with_all_tracks(self):
        hierarchy = _make_hierarchy_with_stems(["drums", "vocals"])
        hierarchy.beats = TimingTrack(
            name="beats", algorithm_name="test", element_type="beat",
            marks=[TimingMark(time_ms=100, confidence=0.9)], quality_score=0.8,
        )
        hierarchy.bars = TimingTrack(
            name="bars", algorithm_name="test", element_type="bar",
            marks=[TimingMark(time_ms=400, confidence=0.9)], quality_score=0.8,
        )
        hierarchy.chords = TimingTrack(
            name="chords", algorithm_name="test", element_type="chord",
            marks=[TimingMark(time_ms=200, confidence=0.9)], quality_score=0.8,
        )
        return hierarchy

    def test_collect_drops_chords_and_onsets_when_disabled(self):
        tracks = _collect_timing_tracks(
            self._hierarchy_with_all_tracks(), include_extra_timing=False)
        assert "Beats" in tracks
        assert "Bars" in tracks
        assert "Chords" not in tracks
        assert not any(name.startswith("Onsets") for name in tracks)

    def test_collect_default_keeps_all_tracks(self):
        tracks = _collect_timing_tracks(self._hierarchy_with_all_tracks())
        assert "Chords" in tracks
        assert "Onsets (drums)" in tracks
        assert "Onsets (vocals)" in tracks

    def test_write_xsq_omits_extra_timing_elements(self, tmp_path: Path) -> None:
        out = tmp_path / "test.xsq"
        write_xsq(_make_plan(), out, hierarchy=self._hierarchy_with_all_tracks(),
                  include_extra_timing=False)
        root = ET.parse(out).getroot()
        timing_names = [
            el.get("name")
            for el in root.find("DisplayElements").findall("Element")
            if el.get("type") == "timing"
        ]
        assert "Beats" in timing_names
        assert "Bars" in timing_names
        assert "Chords" not in timing_names
        assert not any(n.startswith("Onsets") for n in timing_names)
