"""Unit tests for Creative Brief schema defaults and preset round-trips (spec 047)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# T010: schema default parsing
# ---------------------------------------------------------------------------

BRIEF_AXES = (
    "genre",
    "occasion",
    "mood_intent",
    "variation",
    "palette",
    "duration",
    "accents",
    "transitions",
    "curves",
)


def _parse_brief(body: dict) -> dict:
    """Apply the Brief JSON defaults used by brief_routes.PUT on missing fields.

    Kept inline here so the test is independent of the server — it only
    asserts the shape that both sides must honor.
    """
    normalized = {
        "brief_schema_version": int(body.get("brief_schema_version", 1)),
        "source_hash": body.get("source_hash", ""),
        "updated_at": body.get("updated_at", ""),
        "advanced": dict(body.get("advanced") or {}),
        "per_section_overrides": list(body.get("per_section_overrides") or []),
    }
    for axis in BRIEF_AXES:
        normalized[axis] = body.get(axis, "auto")
    return normalized


class TestBriefSchemaDefaults:
    def test_all_omitted_fields_default_to_auto(self):
        parsed = _parse_brief({})
        for axis in BRIEF_AXES:
            assert parsed[axis] == "auto", f"axis {axis} default should be 'auto'"

    def test_per_section_overrides_default_empty_list(self):
        assert _parse_brief({})["per_section_overrides"] == []

    def test_advanced_default_empty_dict(self):
        assert _parse_brief({})["advanced"] == {}

    def test_brief_schema_version_default_is_1(self):
        assert _parse_brief({})["brief_schema_version"] == 1


# ---------------------------------------------------------------------------
# T017: preset-to-GenerationConfig round-trip (SC-008)
# ---------------------------------------------------------------------------

# Mirror of src/review/static/brief-presets.js BRIEF_PRESETS (research.md §1).
# If the JS is updated, update this table and re-run the test.
# Each entry: axis -> list of (preset_id, raw_overrides_dict)
PRESET_TABLE: dict = {
    "genre": [
        ("auto", {}),
        ("pop", {"genre": "pop"}),
        ("rock", {"genre": "rock"}),
        ("classical", {"genre": "classical"}),
        ("any", {"genre": "any"}),
    ],
    "occasion": [
        ("auto", {}),
        ("general", {"occasion": "general"}),
        ("christmas", {"occasion": "christmas"}),
        ("halloween", {"occasion": "halloween"}),
    ],
    "mood_intent": [
        ("auto", {"mood_intent": "auto"}),
        ("party", {"mood_intent": "party"}),
        ("emotional", {"mood_intent": "emotional"}),
        ("dramatic", {"mood_intent": "dramatic"}),
        ("playful", {"mood_intent": "playful"}),
    ],
    "variation": [
        ("auto", {}),
        ("focused", {"focused_vocabulary": True, "embrace_repetition": True, "tier_selection": True}),
        ("balanced", {"focused_vocabulary": True, "embrace_repetition": False, "tier_selection": True}),
        ("varied", {"focused_vocabulary": False, "embrace_repetition": False, "tier_selection": True}),
    ],
    "palette": [
        ("auto", {}),
        ("restrained", {"palette_restraint": True}),
        ("balanced", {}),
        ("full", {"palette_restraint": False}),
    ],
    "duration": [
        ("auto", {}),
        ("snappy", {"duration_scaling": True, "duration_feel": "snappy"}),
        ("balanced", {"duration_scaling": True, "duration_feel": "balanced"}),
        ("flowing", {"duration_scaling": True, "duration_feel": "flowing"}),
    ],
    "accents": [
        ("auto", {}),
        ("none", {"beat_accent_effects": False, "accent_strength": "auto"}),
        ("subtle", {"beat_accent_effects": True, "accent_strength": "subtle"}),
        ("strong", {"beat_accent_effects": True, "accent_strength": "strong"}),
    ],
    "transitions": [
        ("auto", {}),
        ("none", {"transition_mode": "none"}),
        ("subtle", {"transition_mode": "subtle"}),
        ("dramatic", {"transition_mode": "dramatic"}),
    ],
    "curves": [
        ("auto", {}),
        ("on", {"curves_mode": "all"}),
        ("off", {"curves_mode": "none"}),
    ],
}


class TestPresetRoundTrip:
    def test_every_preset_roundtrips_through_generation_config(self, tmp_path):
        """SC-008: every preset combination builds a valid GenerationConfig."""
        from src.generator.models import GenerationConfig

        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"ID3")
        layout = tmp_path / "layout.xml"
        layout.write_text("<xlightsproject/>")

        for axis, presets in PRESET_TABLE.items():
            for preset_id, raw in presets:
                cfg = GenerationConfig(
                    audio_path=audio,
                    layout_path=layout,
                    output_dir=tmp_path,
                    **raw,
                )
                # Round-trip the field-value back against the same raw map.
                for field_name, expected in raw.items():
                    actual = getattr(cfg, field_name)
                    assert actual == expected, (
                        f"axis={axis} preset={preset_id} field={field_name} "
                        f"got {actual!r} want {expected!r}"
                    )


# ---------------------------------------------------------------------------
# Preset map structure invariants (used by US2 Phase 4 too — landed early here)
# ---------------------------------------------------------------------------

def _load_brief_presets_js() -> str:
    path = Path(__file__).resolve().parents[2] / "src" / "review" / "static" / "brief-presets.js"
    return path.read_text(encoding="utf-8")


def _js_has_preset_entries(js: str, axis: str, preset_ids: list[str]) -> bool:
    # Very rough: for each preset id, check the JS file contains `id: "<preset>"`
    # or `id: '<preset>'`. Good enough to catch drops/typos.
    for pid in preset_ids:
        patt = re.compile(r"""id\s*:\s*['"]""" + re.escape(pid) + r"""['"]""")
        if not patt.search(js):
            return False
    return True


class TestBriefPresetsJs:
    def test_preset_ids_present_for_every_axis(self):
        js = _load_brief_presets_js()
        for axis, presets in PRESET_TABLE.items():
            preset_ids = [p for p, _ in presets]
            assert _js_has_preset_entries(js, axis, preset_ids), (
                f"axis {axis} is missing preset ids in brief-presets.js"
            )
