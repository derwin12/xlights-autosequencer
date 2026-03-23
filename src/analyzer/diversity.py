"""Diversity filter — removes near-identical tracks from --top N selection."""
from __future__ import annotations

import numpy as np

from src.analyzer.result import TimingTrack


class DiversityFilter:
    """
    Greedy diversity filter for --top N track selection.

    Compares candidate tracks to already-selected tracks using mark-alignment
    similarity. If the proportion of a candidate's marks that align (within
    ±tolerance_ms) with an already-selected track's marks exceeds the threshold,
    the candidate is considered near-identical and skipped.
    """

    def __init__(self, tolerance_ms: int = 50, threshold: float = 0.90) -> None:
        self.tolerance_ms = tolerance_ms
        self.threshold = threshold

    def _similarity(self, candidate: TimingTrack, selected: TimingTrack) -> float:
        """
        Compute the bidirectional mark-alignment similarity between two tracks.

        Returns the minimum of:
        - proportion of candidate's marks that align with selected's marks
        - proportion of selected's marks that align with candidate's marks

        Using the minimum prevents false positives when a low-density track's
        few marks happen to fall near marks in a high-density track.
        """
        if len(candidate.marks) == 0 or len(selected.marks) == 0:
            return 0.0

        candidate_times = np.array([m.time_ms for m in candidate.marks], dtype=float)
        selected_times = np.array([m.time_ms for m in selected.marks], dtype=float)

        def _count_matching(source: np.ndarray, target: np.ndarray) -> int:
            count = 0
            for t in source:
                if np.any(np.abs(target - t) <= self.tolerance_ms):
                    count += 1
            return count

        fwd = _count_matching(candidate_times, selected_times) / len(candidate_times)
        rev = _count_matching(selected_times, candidate_times) / len(selected_times)
        return min(fwd, rev)

    def filter(
        self,
        tracks: list[TimingTrack],
        n: int,
    ) -> tuple[list[TimingTrack], list[TimingTrack]]:
        """
        Select up to n diverse tracks from a scored list.

        Tracks must already have quality_score and score_breakdown set
        (via score_all_tracks). Returns (selected, skipped) where:
        - selected: up to n tracks, sorted by score descending
        - skipped: tracks excluded due to near-identical similarity

        Sets skipped_as_duplicate=True and duplicate_of on excluded tracks'
        score_breakdown.
        """
        if not tracks:
            return [], []

        sorted_tracks = sorted(tracks, key=lambda t: t.quality_score, reverse=True)

        selected: list[TimingTrack] = []
        skipped: list[TimingTrack] = []

        for candidate in sorted_tracks:
            if len(selected) >= n:
                break

            duplicate_of: str | None = None
            for sel in selected:
                sim = self._similarity(candidate, sel)
                if sim >= self.threshold:
                    duplicate_of = sel.name
                    break

            if duplicate_of is not None:
                # Mark as skipped
                if candidate.score_breakdown is not None:
                    candidate.score_breakdown.skipped_as_duplicate = True
                    candidate.score_breakdown.duplicate_of = duplicate_of
                skipped.append(candidate)
            else:
                selected.append(candidate)

        return selected, skipped
