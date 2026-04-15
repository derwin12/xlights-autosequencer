"""Tests for pick_representative_section() — User Story 3 ranking rules."""
from __future__ import annotations

import pytest

from src.generator.models import SectionEnergy
from src.generator.preview import pick_representative_section


def _make_section(
    label: str,
    start_ms: int,
    end_ms: int,
    energy_score: int,
    mood_tier: str = "structural",
    impact_count: int = 0,
) -> SectionEnergy:
    return SectionEnergy(
        label=label,
        start_ms=start_ms,
        end_ms=end_ms,
        energy_score=energy_score,
        mood_tier=mood_tier,
        impact_count=impact_count,
    )


# ── T035: chorus-heavy fixture ─────────────────────────────────────────────

def test_chorus_heavy_picks_first_chorus():
    """Chorus-heavy song: picker returns the first chorus (highest energy)."""
    sections = [
        _make_section("intro", 0, 15000, 30),
        _make_section("verse", 15000, 45000, 55),
        _make_section("chorus", 45000, 75000, 85),       # <-- first chorus
        _make_section("verse", 75000, 105000, 50),
        _make_section("chorus", 105000, 135000, 85),     # second chorus, same energy
        _make_section("outro", 135000, 150000, 25),
    ]
    result = pick_representative_section(sections)
    assert result == 2  # first chorus index


# ── T036: EDM with drops ───────────────────────────────────────────────────

def test_edm_picks_first_drop():
    """EDM song: picker returns the first drop, not the pre-drop build."""
    sections = [
        _make_section("intro", 0, 20000, 40),
        _make_section("build", 20000, 50000, 65),
        _make_section("drop", 50000, 80000, 95),         # <-- highest energy
        _make_section("breakdown", 80000, 110000, 45),
        _make_section("build", 110000, 130000, 60),
        _make_section("drop", 130000, 160000, 90),
    ]
    result = pick_representative_section(sections)
    assert result == 2  # first drop


# ── T037: ballad / verse-heavy ─────────────────────────────────────────────

def test_ballad_picks_chorus_over_longer_verses():
    """Ballad: picker returns first chorus even though verses are longer."""
    sections = [
        _make_section("intro", 0, 15000, 25),
        _make_section("verse", 15000, 60000, 55),      # long verse
        _make_section("chorus", 60000, 78000, 78),     # <-- chorus, higher energy
        _make_section("verse", 78000, 118000, 52),     # long verse again
        _make_section("chorus", 118000, 138000, 75),
        _make_section("outro", 138000, 150000, 30),
    ]
    result = pick_representative_section(sections)
    assert result == 2  # first chorus


# ── T038: instrumental climax ─────────────────────────────────────────────

def test_instrumental_picks_highest_energy_non_intro():
    """Instrumental: picker returns highest-energy non-intro/outro section."""
    sections = [
        _make_section("intro", 0, 20000, 40),
        _make_section("main_theme", 20000, 60000, 65),
        _make_section("variation", 60000, 100000, 72),
        _make_section("climax", 100000, 130000, 90),    # <-- highest energy
        _make_section("outro", 130000, 150000, 35),
    ]
    result = pick_representative_section(sections)
    assert result == 3  # climax


# ── T039: low dynamic range / ambient ─────────────────────────────────────

def test_low_dynamic_range_picks_longest_candidate():
    """Low-dynamic-range song: no energy >= 50, so pick the longest candidate."""
    sections = [
        _make_section("intro", 0, 15000, 35),
        _make_section("ambient_A", 15000, 65000, 42),     # longest non-intro/outro = 50000ms
        _make_section("ambient_B", 65000, 105000, 40),    # 40000ms
        _make_section("ambient_C", 105000, 135000, 38),   # 30000ms
        _make_section("outro", 135000, 150000, 30),
    ]
    result = pick_representative_section(sections)
    assert result == 1  # ambient_A is longest non-intro/outro


# ── T040: role tiebreaker ─────────────────────────────────────────────────

def test_role_tiebreaker_prefers_chorus_over_verse():
    """Equal energy: picker prefers chorus over verse."""
    sections = [
        _make_section("intro", 0, 10000, 30),
        _make_section("verse", 10000, 40000, 70),          # same energy, non-preferred role
        _make_section("chorus", 40000, 70000, 70),         # <-- same energy, preferred role
        _make_section("outro", 70000, 90000, 30),
    ]
    result = pick_representative_section(sections)
    assert result == 2  # chorus preferred over verse at equal energy


def test_role_tiebreaker_prefers_drop():
    """Equal energy: picker prefers 'drop' role over 'bridge'."""
    sections = [
        _make_section("bridge", 0, 30000, 80),
        _make_section("drop", 30000, 60000, 80),   # <-- preferred
        _make_section("outro", 60000, 75000, 20),
    ]
    result = pick_representative_section(sections)
    assert result == 1  # drop preferred


def test_role_tiebreaker_prefers_climax():
    """Equal energy: picker prefers 'climax' role."""
    sections = [
        _make_section("main_theme", 0, 30000, 75),
        _make_section("climax", 30000, 60000, 75),   # <-- preferred
    ]
    result = pick_representative_section(sections)
    assert result == 1


# ── T041: start-time tiebreaker ───────────────────────────────────────────

def test_start_time_tiebreaker_prefers_earlier_chorus():
    """Two choruses with equal energy: picker prefers the earlier one."""
    sections = [
        _make_section("verse", 0, 30000, 55),
        _make_section("chorus", 30000, 60000, 85),      # <-- first, same energy
        _make_section("verse", 60000, 90000, 50),
        _make_section("chorus", 90000, 120000, 85),     # second, same energy
    ]
    result = pick_representative_section(sections)
    assert result == 1  # first chorus


# ── T042: intro/outro-only fallback (Fallback B) ──────────────────────────

def test_intro_outro_only_falls_back_to_first_long_section():
    """All sections are intro/outro: fallback B returns first with duration >= 4s."""
    sections = [
        _make_section("intro", 0, 2000, 40),      # too short
        _make_section("intro", 2000, 10000, 45),   # long enough, role=intro → fallback B
        _make_section("outro", 10000, 20000, 35),
    ]
    result = pick_representative_section(sections)
    assert result == 1  # first section with duration >= 4s


def test_all_sections_intro_outro_long_enough():
    """Three intro sections all > 4s: fallback B picks index 0."""
    sections = [
        _make_section("intro", 0, 20000, 30),
        _make_section("intro", 20000, 40000, 35),
        _make_section("outro", 40000, 60000, 25),
    ]
    result = pick_representative_section(sections)
    assert result == 0  # first one with duration >= 4s


# ── T043: empty section list (Fallback C) ────────────────────────────────

def test_empty_section_list_returns_zero():
    """Empty section list: Fallback C returns 0."""
    result = pick_representative_section([])
    assert result == 0


# ── Additional edge cases ─────────────────────────────────────────────────

def test_single_section():
    """A song with one section: always returns 0."""
    sections = [_make_section("verse", 0, 30000, 60)]
    result = pick_representative_section(sections)
    assert result == 0


def test_sections_too_short_fallback_c():
    """All sections < 4s: none qualify, fallback C returns 0."""
    sections = [
        _make_section("chorus", 0, 2000, 90),   # too short
        _make_section("verse", 2000, 3000, 80),  # too short
    ]
    result = pick_representative_section(sections)
    assert result == 0


def test_high_energy_ignores_intro():
    """A high-energy intro should not be picked when other sections exist."""
    sections = [
        _make_section("intro", 0, 30000, 95),       # very high energy but intro
        _make_section("verse", 30000, 60000, 70),
        _make_section("chorus", 60000, 90000, 85),  # <-- should be picked
    ]
    result = pick_representative_section(sections)
    assert result == 2  # chorus, not intro


def test_picks_non_outro_over_high_energy_outro():
    """High-energy outro should not be picked when other sections exist."""
    sections = [
        _make_section("verse", 0, 30000, 60),
        _make_section("chorus", 30000, 60000, 80),   # <-- should be picked
        _make_section("outro", 60000, 90000, 95),    # high energy but outro
    ]
    result = pick_representative_section(sections)
    assert result == 1  # chorus, not outro
