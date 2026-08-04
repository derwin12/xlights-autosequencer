"""Regression test for the review API's bar/beat display numbering.

``_assign_bar_beat_numbers`` (src/review/api/v1/analysis.py) replaced a
scheme that computed `bar` via blind index grouping (`i // 4 + 1`) while
`beat` fell back to an unreliable per-mark `label` field when present. Those
two sources could desync mid-song -- e.g. `qm_beats` attaching its own
metrical-position label that shifts from a 4-beat to a 2-beat pattern
partway through a song, while `bar` kept climbing on the untouched index
count, producing bar/beat pairs like (21, 1), (21, 1) [again], (22, 2).
"""
from __future__ import annotations

from src.review.api.v1.analysis import _assign_bar_beat_numbers


def test_numbers_beats_against_real_bar_track():
    # 8 beats, 2 per bar according to the bar track (500ms bars).
    beat_times = [0, 250, 500, 750, 1000, 1250, 1500, 1750]
    bar_times = [0, 500, 1000, 1500]

    result = _assign_bar_beat_numbers(beat_times, bar_times)

    assert result == [
        (1, 1), (1, 2),
        (2, 1), (2, 2),
        (3, 1), (3, 2),
        (4, 1), (4, 2),
    ]


def test_never_desyncs_when_a_bar_has_an_irregular_beat_count():
    # Bar 2 has 3 beats instead of 2 (e.g. a real tracker hiccup) -- the
    # numbering should climb past the "normal" count rather than silently
    # wrapping or drifting the bar count out of alignment with bar_times.
    beat_times = [0, 250, 500, 750, 900, 1000, 1250]
    bar_times = [0, 500, 1000]

    result = _assign_bar_beat_numbers(beat_times, bar_times)

    assert result == [
        (1, 1), (1, 2),
        (2, 1), (2, 2), (2, 3),
        (3, 1), (3, 2),
    ]


def test_falls_back_to_index_grouping_with_no_bar_track():
    beat_times = list(range(0, 900, 100))  # 9 beats

    result = _assign_bar_beat_numbers(beat_times, bar_times=[])

    assert result == [
        (1, 1), (1, 2), (1, 3), (1, 4),
        (2, 1), (2, 2), (2, 3), (2, 4),
        (3, 1),
    ]
