"""TDD tests for src/story/section_classifier.py — must FAIL before implementation."""
import pytest

from src.story.section_classifier import classify_section_roles
from tests.fixtures.story_fixture import make_hierarchy_dict, make_hierarchy_dict_instrumental

# ---------------------------------------------------------------------------
# Helpers / constants
# ---------------------------------------------------------------------------

VOCAL_ROLES = {"verse", "chorus", "bridge", "pre_chorus", "post_chorus", "climax"}
NON_VOCAL_ROLES = {"intro", "outro", "instrumental_break", "interlude", "ambient_bridge"}
ALL_VALID_ROLES = VOCAL_ROLES | NON_VOCAL_ROLES


def _make_sections_ms(pairs: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return pairs


# ---------------------------------------------------------------------------
# Return-type and count contracts
# ---------------------------------------------------------------------------

class TestReturnType:
    """classify_section_roles must return one dict per input section."""

    def test_returns_list(self):
        hierarchy = make_hierarchy_dict()
        sections = [(0, 12_000), (12_000, 36_000), (36_000, 54_000), (54_000, 60_000)]
        result = classify_section_roles(sections, hierarchy)
        assert isinstance(result, list)

    def test_count_matches_input(self):
        """Output list length == input list length."""
        hierarchy = make_hierarchy_dict()
        sections = [(0, 12_000), (12_000, 36_000), (36_000, 54_000), (54_000, 60_000)]
        result = classify_section_roles(sections, hierarchy)
        assert len(result) == len(sections)

    def test_each_item_has_role_and_confidence(self):
        """Every dict must have 'role' (str) and 'confidence' (float) keys."""
        hierarchy = make_hierarchy_dict()
        sections = [(0, 12_000), (12_000, 36_000), (36_000, 54_000), (54_000, 60_000)]
        result = classify_section_roles(sections, hierarchy)
        for item in result:
            assert "role" in item, f"Missing 'role' key in {item}"
            assert "confidence" in item, f"Missing 'confidence' key in {item}"
            assert isinstance(item["role"], str)
            assert isinstance(item["confidence"], float)

    def test_confidence_in_unit_interval(self):
        """Confidence must be in [0.0, 1.0]."""
        hierarchy = make_hierarchy_dict()
        sections = [(0, 12_000), (12_000, 36_000), (36_000, 54_000), (54_000, 60_000)]
        result = classify_section_roles(sections, hierarchy)
        for item in result:
            assert 0.0 <= item["confidence"] <= 1.0, (
                f"Confidence {item['confidence']} out of [0, 1] for role {item['role']}"
            )

    def test_all_roles_are_valid_strings(self):
        """Every role value must be one of the known role strings."""
        hierarchy = make_hierarchy_dict()
        sections = [(0, 12_000), (12_000, 36_000), (36_000, 54_000), (54_000, 60_000)]
        result = classify_section_roles(sections, hierarchy)
        for item in result:
            assert item["role"] in ALL_VALID_ROLES, (
                f"Unknown role '{item['role']}' not in {ALL_VALID_ROLES}"
            )


# ---------------------------------------------------------------------------
# Vocal-activity-driven role assignment
# ---------------------------------------------------------------------------

class TestVocalRoles:
    """Sections with vocal activity must get vocal-appropriate roles."""

    def test_vocal_sections_not_intro_or_outro_or_instrumental(self):
        """Middle sections with vocals (RMS > 0.1) should not be intro/outro/instrumental."""
        hierarchy = make_hierarchy_dict()
        # Middle sections 12-36s and 36-54s have vocal energy 0.6 in fixture
        sections = [(12_000, 36_000), (36_000, 54_000)]
        result = classify_section_roles(sections, hierarchy)
        for item in result:
            assert item["role"] not in NON_VOCAL_ROLES, (
                f"Vocal section got non-vocal role '{item['role']}'"
            )

    def test_high_energy_vocal_section_is_chorus(self):
        """High-energy (0.8) vocal section in fixture is chorus."""
        hierarchy = make_hierarchy_dict()
        # 36-54s: energy=0.8, vocals=0.6 → should be chorus
        sections = [(36_000, 54_000)]
        result = classify_section_roles(sections, hierarchy)
        assert result[0]["role"] == "chorus", (
            f"Expected chorus for high-energy vocal section, got '{result[0]['role']}'"
        )

    def test_medium_energy_vocal_section_is_verse(self):
        """Medium-energy (0.5) vocal section in fixture is verse."""
        hierarchy = make_hierarchy_dict()
        # 12-36s: energy=0.5, vocals=0.6 → should be verse
        sections = [(12_000, 36_000)]
        result = classify_section_roles(sections, hierarchy)
        assert result[0]["role"] == "verse", (
            f"Expected verse for medium-energy vocal section, got '{result[0]['role']}'"
        )


# ---------------------------------------------------------------------------
# Positional roles (intro / outro)
# ---------------------------------------------------------------------------

class TestPositionalRoles:
    """First and last sections with no vocals should be intro and outro."""

    def test_first_section_no_vocals_is_intro(self):
        """First section with zero vocal energy → intro."""
        hierarchy = make_hierarchy_dict()
        # 0-12s: vocals=0.0 in fixture
        sections = [(0, 12_000), (12_000, 36_000), (36_000, 54_000), (54_000, 60_000)]
        result = classify_section_roles(sections, hierarchy)
        assert result[0]["role"] == "intro", (
            f"Expected intro for first silent section, got '{result[0]['role']}'"
        )

    def test_last_section_no_vocals_is_outro(self):
        """Last section with zero vocal energy → outro."""
        hierarchy = make_hierarchy_dict()
        # 54-60s: vocals=0.0 in fixture
        sections = [(0, 12_000), (12_000, 36_000), (36_000, 54_000), (54_000, 60_000)]
        result = classify_section_roles(sections, hierarchy)
        assert result[-1]["role"] == "outro", (
            f"Expected outro for last silent section, got '{result[-1]['role']}'"
        )


# ---------------------------------------------------------------------------
# Instrumental / no-vocal song
# ---------------------------------------------------------------------------

class TestInstrumentalSong:
    """When vocal energy is zero throughout, all roles must be non-vocal."""

    def test_all_sections_get_instrumental_roles(self):
        """Zero vocal activity → no verse/chorus/bridge roles anywhere."""
        hierarchy = make_hierarchy_dict_instrumental()
        sections = [(0, 12_000), (12_000, 36_000), (36_000, 54_000), (54_000, 60_000)]
        result = classify_section_roles(sections, hierarchy)
        for item in result:
            assert item["role"] not in VOCAL_ROLES, (
                f"Instrumental song section got vocal role '{item['role']}'"
            )

    def test_instrumental_first_section_is_intro(self):
        """First section of an instrumental song → intro."""
        hierarchy = make_hierarchy_dict_instrumental()
        sections = [(0, 12_000), (12_000, 36_000), (36_000, 54_000), (54_000, 60_000)]
        result = classify_section_roles(sections, hierarchy)
        assert result[0]["role"] == "intro"

    def test_instrumental_last_section_is_outro(self):
        """Last section of an instrumental song → outro."""
        hierarchy = make_hierarchy_dict_instrumental()
        sections = [(0, 12_000), (12_000, 36_000), (36_000, 54_000), (54_000, 60_000)]
        result = classify_section_roles(sections, hierarchy)
        assert result[-1]["role"] == "outro"

    def test_instrumental_middle_sections_are_instrumental_break(self):
        """Interior sections with no vocals → instrumental_break or similar."""
        hierarchy = make_hierarchy_dict_instrumental()
        sections = [(0, 12_000), (12_000, 36_000), (36_000, 54_000), (54_000, 60_000)]
        result = classify_section_roles(sections, hierarchy)
        middle = result[1:-1]
        for item in middle:
            assert item["role"] in NON_VOCAL_ROLES, (
                f"Interior instrumental section got role '{item['role']}' "
                f"which is not in {NON_VOCAL_ROLES}"
            )


# ---------------------------------------------------------------------------
# Single-section edge case
# ---------------------------------------------------------------------------

class TestSingleSection:
    """A single-section song must return a list with exactly one classified dict."""

    def test_single_section_returns_one_item(self):
        hierarchy = make_hierarchy_dict()
        result = classify_section_roles([(0, 60_000)], hierarchy)
        assert len(result) == 1

    def test_single_section_has_valid_role(self):
        hierarchy = make_hierarchy_dict()
        result = classify_section_roles([(0, 60_000)], hierarchy)
        assert result[0]["role"] in ALL_VALID_ROLES
