"""Regression test for the review API's bar/beat display numbering.

``_assign_bar_beat_numbers`` (src/review/api/v1/analysis.py) originally
computed `bar` via blind index grouping (`i // 4 + 1`) while `beat` fell
back to an unreliable per-mark `label` field when present -- those two
sources could desync mid-song (e.g. `qm_beats` attaching its own
metrical-position label that shifts from a 4-beat to a 2-beat pattern
partway through a song), producing bar/beat pairs like (21, 1), (21, 1)
[again], (22, 2).

A second version tried to fix that by aligning numbering to the real L2
bar/downbeat track instead. That was reverted after testing on real
material (Aerosmith "Dream On") showed the bar track itself is unreliable
(near-empty for the song's first 71s, then firing at ~2x the correct rate)
-- worse than plain grouping's own failure mode. The current version always
assumes plain 4/4 grouping off the beat track alone, which is both the
simpler, more robust source (the beat track is well-validated after
bug-760's fold-down fix) and correct standard music theory for the 4/4
songs this tool targets almost exclusively.
"""
from __future__ import annotations

from src.review.api.v1.analysis import _assign_bar_beat_numbers


def test_groups_every_four_beats_into_a_bar():
    beat_times = list(range(0, 900, 100))  # 9 beats, 100ms apart

    result = _assign_bar_beat_numbers(beat_times)

    assert result == [
        (1, 1), (1, 2), (1, 3), (1, 4),
        (2, 1), (2, 2), (2, 3), (2, 4),
        (3, 1),
    ]


def test_empty_input_returns_empty_list():
    assert _assign_bar_beat_numbers([]) == []
