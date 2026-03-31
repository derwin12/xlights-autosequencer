"""Section merger for song story tool.

Merges raw boundary timestamps from HierarchyResult into a contiguous list
of (start_ms, end_ms) tuples suitable for section-level classification.
"""
from __future__ import annotations


def merge_sections(
    boundaries_ms: list[int],
    duration_ms: int,
    target_min: int = 8,
    target_max: int = 15,
    min_duration_ms: int = 4000,
) -> list[tuple[int, int]]:
    """Merge raw boundary timestamps into contiguous song sections.

    Args:
        boundaries_ms: Boundary timestamps (ms) from HierarchyResult.sections.
                       May include 0 and/or duration_ms; duplicates are removed.
        duration_ms:   Total song duration in milliseconds (used as sentinel end).
        target_min:    Desired minimum section count (best-effort).
        target_max:    Hard maximum section count; excess sections are merged.
        min_duration_ms: Minimum allowed section duration; shorter sections are
                         merged with the shorter neighbour.

    Returns:
        Sorted list of (start_ms, end_ms) tuples with no gaps or overlaps,
        starting at 0 and ending at duration_ms.
    """
    # --- Step 1: build sorted unique boundary list including 0 and duration_ms ---
    pts: list[int] = sorted(set([0] + list(boundaries_ms) + [duration_ms]))

    # Build mutable list of [start, end] pairs
    segments: list[list[int]] = [
        [pts[i], pts[i + 1]] for i in range(len(pts) - 1) if pts[i] < pts[i + 1]
    ]

    if not segments:
        return [(0, duration_ms)]

    # --- Step 2: remove segments shorter than min_duration_ms ---
    # Iterate until stable — merge short segment with shorter neighbour
    changed = True
    while changed and len(segments) > 1:
        changed = False
        for i, seg in enumerate(segments):
            dur = seg[1] - seg[0]
            if dur < min_duration_ms:
                # Merge with the shorter neighbour
                if len(segments) == 1:
                    break
                if i == 0:
                    # Only right neighbour
                    segments[1][0] = seg[0]
                    segments.pop(i)
                elif i == len(segments) - 1:
                    # Only left neighbour
                    segments[i - 1][1] = seg[1]
                    segments.pop(i)
                else:
                    left_dur = segments[i - 1][1] - segments[i - 1][0]
                    right_dur = segments[i + 1][1] - segments[i + 1][0]
                    if left_dur <= right_dur:
                        segments[i - 1][1] = seg[1]
                        segments.pop(i)
                    else:
                        segments[i + 1][0] = seg[0]
                        segments.pop(i)
                changed = True
                break  # restart scan after each merge

    # --- Step 3: if count exceeds target_max, merge the two shortest adjacent ---
    while len(segments) > target_max:
        # Find pair of adjacent segments whose combined duration is smallest
        best_idx = 0
        best_combined = float("inf")
        for i in range(len(segments) - 1):
            combined = segments[i + 1][1] - segments[i][0]
            if combined < best_combined:
                best_combined = combined
                best_idx = i
        # Merge segments[best_idx] and segments[best_idx + 1]
        segments[best_idx][1] = segments[best_idx + 1][1]
        segments.pop(best_idx + 1)

    return [(s[0], s[1]) for s in segments]
