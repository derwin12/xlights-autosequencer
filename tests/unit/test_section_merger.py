"""TDD tests for src/story/section_merger.py — must FAIL before implementation."""
import pytest

from src.story.section_merger import merge_sections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert_contiguous(sections: list[tuple[int, int]], duration_ms: int) -> None:
    """Assert no gaps and no overlaps; first section starts at 0, last ends at duration_ms."""
    assert sections[0][0] == 0, "First section must start at 0"
    assert sections[-1][1] == duration_ms, f"Last section must end at {duration_ms}"
    for i in range(len(sections) - 1):
        assert sections[i][1] == sections[i + 1][0], (
            f"Gap or overlap between section {i} ({sections[i]}) "
            f"and section {i+1} ({sections[i+1]})"
        )


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------

class TestContiguousCoverage:
    """Output sections must cover the song with no gaps or overlaps."""

    def test_no_gaps_no_overlaps_typical(self):
        """Standard 4-minute song with boundaries every ~30 seconds."""
        boundaries_ms = list(range(0, 240_000, 30_000))
        result = merge_sections(boundaries_ms, duration_ms=240_000)
        _assert_contiguous(result, 240_000)

    def test_first_section_starts_at_zero(self):
        """Result always begins at time 0 regardless of input boundaries."""
        boundaries_ms = [15_000, 45_000, 90_000]
        result = merge_sections(boundaries_ms, duration_ms=120_000)
        assert result[0][0] == 0

    def test_last_section_ends_at_duration(self):
        """Result always ends at the supplied duration_ms."""
        boundaries_ms = [10_000, 40_000, 80_000]
        result = merge_sections(boundaries_ms, duration_ms=100_000)
        assert result[-1][1] == 100_000


# ---------------------------------------------------------------------------
# Minimum duration enforcement
# ---------------------------------------------------------------------------

class TestMinimumDuration:
    """Sections shorter than min_duration_ms must be merged with a neighbour."""

    def test_short_section_merged(self):
        """A 2-second section (< 4000 ms default) must be absorbed."""
        # Boundary at 1s creates a 1s section that should not survive on its own
        boundaries_ms = [1_000, 30_000, 60_000, 90_000]
        result = merge_sections(boundaries_ms, duration_ms=120_000)
        durations = [end - start for start, end in result]
        assert all(d >= 4_000 for d in durations), (
            f"Found section shorter than 4 000 ms: {durations}"
        )

    def test_custom_min_duration_respected(self):
        """Sections shorter than a custom min_duration_ms must be merged."""
        boundaries_ms = [500, 30_000, 60_000]
        result = merge_sections(boundaries_ms, duration_ms=90_000, min_duration_ms=2_000)
        durations = [end - start for start, end in result]
        assert all(d >= 2_000 for d in durations)

    def test_many_micro_boundaries_collapsed(self):
        """Dozens of boundaries spaced 500 ms apart should collapse into longer sections."""
        boundaries_ms = list(range(0, 60_000, 500))
        result = merge_sections(boundaries_ms, duration_ms=60_000)
        durations = [end - start for start, end in result]
        assert all(d >= 4_000 for d in durations)


# ---------------------------------------------------------------------------
# Target section count
# ---------------------------------------------------------------------------

class TestTargetSectionCount:
    """Output should have 8–15 sections for a typical 3-minute+ song."""

    def test_typical_song_section_count_in_range(self):
        """200-second song with reasonable boundaries produces 8-15 sections."""
        # Provide 30 boundaries roughly every 7 seconds
        boundaries_ms = list(range(0, 210_000, 7_000))
        result = merge_sections(boundaries_ms, duration_ms=210_000)
        assert 8 <= len(result) <= 15, f"Expected 8-15 sections, got {len(result)}"

    def test_custom_target_min_max_honored(self):
        """Explicit target_min / target_max are respected."""
        boundaries_ms = list(range(0, 300_000, 5_000))
        result = merge_sections(
            boundaries_ms, duration_ms=300_000, target_min=5, target_max=10
        )
        assert 5 <= len(result) <= 10, f"Expected 5-10 sections, got {len(result)}"


# ---------------------------------------------------------------------------
# Adjacent-short-section merge
# ---------------------------------------------------------------------------

class TestAdjacentShortSectionMerge:
    """Adjacent very short sections should be merged together."""

    def test_two_adjacent_short_sections_merged(self):
        """Two consecutive 1.5-second sections should be collapsed into one."""
        boundaries_ms = [1_500, 3_000, 30_000, 60_000]
        result = merge_sections(boundaries_ms, duration_ms=60_000)
        # Neither 0-1500 nor 1500-3000 should remain as standalone sections
        for start, end in result:
            assert end - start >= 4_000, f"Surviving short section: ({start}, {end})"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Degenerate inputs must not crash and must return sensible results."""

    def test_no_boundaries_returns_full_song(self):
        """No boundaries at all → single section covering the entire song."""
        result = merge_sections([], duration_ms=60_000)
        assert result == [(0, 60_000)], f"Expected [(0, 60000)], got {result}"

    def test_single_boundary_returns_single_section(self):
        """One interior boundary → still one section (or two if >= min_duration)."""
        result = merge_sections([30_000], duration_ms=60_000)
        assert len(result) >= 1
        _assert_contiguous(result, 60_000)

    def test_single_boundary_too_short_first_half(self):
        """A boundary at 1 s on a 60-second song → first half merges into second."""
        result = merge_sections([1_000], duration_ms=60_000)
        _assert_contiguous(result, 60_000)
        durations = [end - start for start, end in result]
        assert all(d >= 4_000 for d in durations)

    def test_at_least_one_section_always_returned(self):
        """Function must never return an empty list."""
        result = merge_sections([], duration_ms=5_000)
        assert len(result) >= 1

    def test_sentinel_end_boundary_used(self):
        """If the last boundary equals duration_ms it is treated as the sentinel end."""
        boundaries_ms = [15_000, 45_000, 60_000]   # 60_000 == duration_ms
        result = merge_sections(boundaries_ms, duration_ms=60_000)
        assert result[-1][1] == 60_000
        _assert_contiguous(result, 60_000)

    def test_returns_list_of_tuples(self):
        """Return type must be list[tuple[int, int]]."""
        result = merge_sections([30_000], duration_ms=60_000)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple) and len(item) == 2
            assert isinstance(item[0], int) and isinstance(item[1], int)

    def test_sections_are_positive_duration(self):
        """Every section must have start < end."""
        boundaries_ms = [10_000, 20_000, 50_000]
        result = merge_sections(boundaries_ms, duration_ms=60_000)
        for start, end in result:
            assert start < end, f"Zero-or-negative duration section: ({start}, {end})"
