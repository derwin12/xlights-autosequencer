"""Lyric-anchored boundary refinement.

Three small, targeted refinements applied after the existing section-boundary
derivation in the story builder. Consumes WhisperX forced-alignment word marks
(already produced for vocal sections) and a free-transcription word stream
(``src.analyzer.free_transcription.transcribe_free``) for ground-truth
``is anyone audibly singing here`` evidence.

OpenSpec change: ``lyric-anchored-boundary-refinement``.

Empirical record: 16-song corpus run produced 8 fires, 0 false positives —
Cher (Fix 1 + Fix 2 full + Fix 3), Crazy Train (Fix 2 split + Fix 3),
Ghostbusters (Fix 2 full), Hoist the Colours (Fix 3), Down with the Sickness
(Fix 3); 11 others zero fires.

Section dict shape (per ``src/story/builder.py``)
-------------------------------------------------
- ``role``: one of the values in ``VALID_ROLES`` (this module treats
  the role as the "kind" referenced by the spec)
- ``start``, ``end``: floats in seconds
- ``agreement_score``: int (0..N)
- ``boundary_refinements``: list[str] — added by ``refine_section_boundaries``,
  always present after this module has run (empty list when no refinement
  fires).
"""
from __future__ import annotations

import copy
import re
from typing import Iterable, Optional

from src.analyzer.phonemes import WordMark
from src.log import get_logger

log = get_logger("xlight.boundary_refinement")


VOCAL_ROLES: frozenset[str] = frozenset({
    "verse", "chorus", "pre_chorus", "post_chorus", "bridge",
})

# Sections whose first transcribed word arrives so late that splitting off the
# instrumental prefix would leave less than this many milliseconds of vocal
# remainder are likely whole-section mislabels — out of scope for Fix 3.
MIN_REMAINING_VOCAL_MS = 3000

# Stopwords for chorus-first-line distinctive-hook extraction. Includes common
# contractions because forced alignment frequently drops them; relying on them
# as anchors causes false negatives.
_STOPWORDS = frozenset({
    # function words
    "the", "a", "an", "of", "and", "or", "but", "if", "then", "to", "for",
    "in", "on", "at", "by", "with", "from", "into", "out", "up", "down",
    "is", "are", "was", "were", "be", "been", "being", "am", "do", "does",
    "did", "have", "has", "had", "this", "that", "these", "those", "as",
    "so", "not", "no", "yes",
    # pronouns
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us",
    "them", "my", "your", "his", "their", "our", "its",
    # contractions (commonly dropped by forced alignment)
    "i'm", "you're", "we're", "they're", "it's", "he's", "she's",
    "i'll", "you'll", "we'll", "they'll", "i've", "you've", "we've",
    "don't", "doesn't", "didn't", "won't", "can't", "isn't", "aren't",
    # high-frequency filler observed in corpus iteration
    "going", "off", "now", "just", "like", "all", "oh", "yeah", "ah",
    "what", "when", "where", "why", "how",
})


# ── Helpers ───────────────────────────────────────────────────────────────────


def _norm(word: str) -> str:
    """Normalise a word for hook matching: lowercase, trim non-alphabetic."""
    return re.sub(r"[^a-z']", "", word.lower())


def _chorus_first_line_distinctives(chorus_body: str, n: int = 4) -> list[str]:
    """Return up to ``n`` distinctive words from the chorus body's first line.

    Distinctive = length ≥ 3 AND not in the stopword set. Words are returned
    in their original order. Empty/short results signal the chorus first
    line lacks enough lexical content for hook matching.
    """
    if not chorus_body:
        return []
    first_line = next(
        (line for line in chorus_body.splitlines() if line.strip()),
        "",
    )
    distinctives: list[str] = []
    for tok in first_line.split():
        w = _norm(tok)
        if len(w) < 3 or w in _STOPWORDS:
            continue
        distinctives.append(w)
        if len(distinctives) >= n:
            break
    return distinctives


def _consecutive_in_order_count(
    targets: list[str],
    words: list[WordMark],
    window: int = 12,
) -> int:
    """Count targets that appear in ``words`` in order.

    Each match must be within ``window`` words after the previous match.
    Targets that aren't found anywhere advance the cursor by zero, so a
    single ASR drop doesn't abort the count — but if a target *is* found
    later than ``window`` words past the previous match, it doesn't count.
    """
    if not targets or not words:
        return 0

    word_labels = [_norm(w.label) for w in words]
    cursor = 0
    matched = 0
    for target in targets:
        # Look for ``target`` starting at ``cursor``, within the window.
        end = min(len(word_labels), cursor + window)
        # First time around (no previous match), search the entire word list.
        scan_end = end if matched > 0 else len(word_labels)
        try:
            idx = word_labels.index(target, cursor, scan_end)
        except ValueError:
            continue
        matched += 1
        cursor = idx + 1
    return matched


def _hook_matches(targets: list[str], words: list[WordMark]) -> bool:
    """True iff ``words`` contain the chorus first-line hook in order.

    Threshold: ``max(2, len(targets) - 1)`` — N-1 of N tolerance so a single
    ASR drop doesn't abort the match.
    """
    if len(targets) < 2:
        return False
    threshold = max(2, len(targets) - 1)
    return _consecutive_in_order_count(targets, words) >= threshold


def _words_in_span(
    words: list[WordMark], start_s: float, end_s: float,
) -> list[WordMark]:
    start_ms = int(round(start_s * 1000))
    end_ms = int(round(end_s * 1000))
    return [w for w in words if w.start_ms >= start_ms and w.end_ms <= end_ms]


def _largest_internal_gap(
    words: list[WordMark],
    *,
    min_gap_ms: int = 3000,
) -> Optional[tuple[int, int, int]]:
    """Return the largest internal vocal gap ≥ ``min_gap_ms`` if any.

    Returns ``(prev_end_ms, next_start_ms, gap_ms)`` or ``None`` when no
    qualifying gap exists.
    """
    best: Optional[tuple[int, int, int]] = None
    for i in range(1, len(words)):
        prev_end = words[i - 1].end_ms
        next_start = words[i].start_ms
        gap = next_start - prev_end
        if gap >= min_gap_ms and (best is None or gap > best[2]):
            best = (prev_end, next_start, gap)
    return best


def _is_instrumental_role(role: str | None) -> bool:
    if not role:
        return False
    rl = role.lower()
    return "instrumental" in rl or "break" in rl


# ── Fix 1: short post_chorus tail merge ───────────────────────────────────────


def merge_short_post_chorus_tail(
    sections: list[dict],
    forced_words: list[WordMark],
) -> tuple[list[dict], list[str]]:
    """Merge a short ``post_chorus`` continuous with its prior section.

    Preconditions (all must hold):
    - prior section role in ``{verse, chorus, pre_chorus, bridge}``
    - this section role == ``"post_chorus"``
    - this section duration < 6000 ms
    - this section ``agreement_score`` <= 1
    - gap from prior section's last forced-aligned word's ``end_ms`` to this
      section's first forced-aligned word's ``start_ms`` is <= 1500 ms

    Returns ``(refined_sections, notes)``.
    """
    notes: list[str] = []
    if not sections:
        return list(sections), notes

    out: list[dict] = []
    i = 0
    while i < len(sections):
        cur = sections[i]
        prev = out[-1] if out else None

        is_short_tail = (
            prev is not None
            and prev.get("role") in {"verse", "chorus", "pre_chorus", "bridge"}
            and cur.get("role") == "post_chorus"
            and (cur["end"] - cur["start"]) * 1000 < 6000
            and int(cur.get("agreement_score", 99)) <= 1
        )

        if is_short_tail:
            prev_words = _words_in_span(forced_words, prev["start"], prev["end"])
            cur_words = _words_in_span(forced_words, cur["start"], cur["end"])
            gap_ms: Optional[int] = None
            if prev_words and cur_words:
                gap_ms = cur_words[0].start_ms - prev_words[-1].end_ms

            if gap_ms is not None and gap_ms <= 1500:
                merged = copy.deepcopy(prev)
                # extend prior to last word + 250 ms tail
                merged_end_s = (cur_words[-1].end_ms + 250) / 1000.0
                merged["end"] = round(merged_end_s, 3)
                merged["duration"] = round(merged_end_s - merged["start"], 3)
                note = (
                    f"merged short post_chorus into prior {prev.get('role')} "
                    f"(gap={gap_ms}ms, words={len(cur_words)})"
                )
                refs = list(merged.get("boundary_refinements") or [])
                refs.append(note)
                merged["boundary_refinements"] = refs
                notes.append(note)
                out[-1] = merged
                i += 1
                continue

        out.append(copy.deepcopy(cur))
        i += 1

    return out, notes


# ── Fix 2: bridge relabel/split via chorus first-line hook ───────────────────


def relabel_or_split_bridge(
    sections: list[dict],
    free_words: list[WordMark],
    chorus_body: Optional[str],
) -> tuple[list[dict], list[str]]:
    """Relabel or split bridge sections whose sung content opens with chorus hook.

    Branches per the spec:
    - no internal gap, hook matched in whole → relabel as chorus
    - internal gap (>=3s), hook in BOTH halves → relabel as chorus
    - internal gap, hook in PREFIX only → split into chorus prefix + bridge tail
    - otherwise → unchanged
    """
    notes: list[str] = []
    targets = _chorus_first_line_distinctives(chorus_body or "")
    if len(targets) < 2:
        # Insufficient lexical content; caller should emit a skip warning.
        return [copy.deepcopy(s) for s in sections], notes

    out: list[dict] = []
    for sec in sections:
        if sec.get("role") != "bridge":
            out.append(copy.deepcopy(sec))
            continue

        words = _words_in_span(free_words, sec["start"], sec["end"])
        if not words:
            out.append(copy.deepcopy(sec))
            continue

        gap = _largest_internal_gap(words, min_gap_ms=3000)
        whole_matches = _hook_matches(targets, words)

        if gap is None:
            if whole_matches:
                relabeled = copy.deepcopy(sec)
                relabeled["role"] = "chorus"
                note = f"chorus hook present in transcribed bridge — relabel whole (targets={targets[:4]})"
                refs = list(relabeled.get("boundary_refinements") or [])
                refs.append(note)
                relabeled["boundary_refinements"] = refs
                notes.append(note)
                out.append(relabeled)
            else:
                out.append(copy.deepcopy(sec))
            continue

        # Has internal gap — split words at the gap.
        prev_end_ms, next_start_ms, _ = gap
        prefix_words = [w for w in words if w.end_ms <= prev_end_ms]
        suffix_words = [w for w in words if w.start_ms >= next_start_ms]
        prefix_match = _hook_matches(targets, prefix_words)
        suffix_match = _hook_matches(targets, suffix_words)

        if prefix_match and suffix_match:
            # Two chorus iterations around silence — relabel whole
            relabeled = copy.deepcopy(sec)
            relabeled["role"] = "chorus"
            note = (
                f"chorus hook present in BOTH halves of bridge around "
                f"{(next_start_ms - prev_end_ms) / 1000.0:.1f}s gap — relabel whole"
            )
            refs = list(relabeled.get("boundary_refinements") or [])
            refs.append(note)
            relabeled["boundary_refinements"] = refs
            notes.append(note)
            out.append(relabeled)
        elif prefix_match and not suffix_match:
            # Split: prefix becomes chorus, suffix stays bridge
            split_s = (prev_end_ms + 250) / 1000.0
            split_s = round(split_s, 3)

            chorus_part = copy.deepcopy(sec)
            chorus_part["role"] = "chorus"
            chorus_part["end"] = split_s
            chorus_part["duration"] = round(split_s - chorus_part["start"], 3)
            note_a = (
                f"chorus hook present in bridge prefix only — split at "
                f"{split_s:.3f}s (Bridge→Chorus)"
            )
            refs_a = list(chorus_part.get("boundary_refinements") or [])
            refs_a.append(note_a)
            chorus_part["boundary_refinements"] = refs_a

            bridge_part = copy.deepcopy(sec)
            bridge_part["start"] = split_s
            bridge_part["duration"] = round(bridge_part["end"] - split_s, 3)
            note_b = (
                f"bridge tail retained after chorus hook split at {split_s:.3f}s"
            )
            refs_b = list(bridge_part.get("boundary_refinements") or [])
            refs_b.append(note_b)
            bridge_part["boundary_refinements"] = refs_b

            notes.append(note_a)
            out.append(chorus_part)
            out.append(bridge_part)
        else:
            # No prefix match (suffix-only or none) — unchanged
            out.append(copy.deepcopy(sec))

    return out, notes


# ── Fix 3: pre-vocal instrumental ramp split ──────────────────────────────────


def split_pre_vocal_instrumental(
    sections: list[dict],
    free_words: list[WordMark],
) -> tuple[list[dict], list[str]]:
    """Split a pre-vocal instrumental ramp off the front of vocal sections.

    Preconditions:
    - section role in ``VOCAL_ROLES``
    - role does NOT contain "instrumental" or "break"
    - section has ≥1 free-transcribed word
    - gap from section.start to first transcribed word's start ≥ 5000 ms
    - remaining vocal portion (first_word.start → section.end) ≥ 3000 ms
    """
    notes: list[str] = []
    out: list[dict] = []

    for sec in sections:
        role = sec.get("role")
        if role not in VOCAL_ROLES or _is_instrumental_role(role):
            out.append(copy.deepcopy(sec))
            continue

        words = _words_in_span(free_words, sec["start"], sec["end"])
        if not words:
            out.append(copy.deepcopy(sec))
            continue

        first_word = words[0]
        gap_ms = first_word.start_ms - int(round(sec["start"] * 1000))
        remaining_ms = int(round(sec["end"] * 1000)) - first_word.start_ms

        if gap_ms < 5000:
            out.append(copy.deepcopy(sec))
            continue

        if remaining_ms < MIN_REMAINING_VOCAL_MS:
            # Section is mostly silent — likely a whole-section mislabel.
            mislabel = copy.deepcopy(sec)
            note = (
                f"section likely mislabeled — only {remaining_ms} ms of vocal "
                f"after {gap_ms / 1000.0:.1f}s instrumental prefix"
            )
            refs = list(mislabel.get("boundary_refinements") or [])
            refs.append(note)
            mislabel["boundary_refinements"] = refs
            notes.append(note)
            out.append(mislabel)
            continue

        # Split: synthetic instrumental section + shifted vocal section.
        split_s = round((first_word.start_ms - 250) / 1000.0, 3)
        # Guard: split point must remain after section.start (250 ms cushion
        # could undershoot the start when first_word lands very close to it).
        split_s = max(split_s, round(sec["start"] + 0.001, 3))

        synthetic = copy.deepcopy(sec)
        synthetic["role"] = "instrumental"
        synthetic["end"] = split_s
        synthetic["duration"] = round(split_s - synthetic["start"], 3)
        note_synth = (
            f"pre-vocal gap split off as instrumental — first word at "
            f"{first_word.start_ms / 1000.0:.2f}s ({gap_ms} ms after section start)"
        )
        synthetic["boundary_refinements"] = [note_synth]
        # Keep agreement_score on synthetic (inherited) — UI may want to know.

        shifted = copy.deepcopy(sec)
        shifted["start"] = split_s
        shifted["duration"] = round(shifted["end"] - split_s, 3)
        note_shift = (
            f"shifted start to first transcribed word at "
            f"{first_word.start_ms / 1000.0:.2f}s "
            f"(was {sec['start']:.2f}s, {gap_ms / 1000.0:.1f}s instrumental ramp)"
        )
        refs = list(shifted.get("boundary_refinements") or [])
        refs.append(note_shift)
        shifted["boundary_refinements"] = refs

        notes.append(note_shift)
        out.append(synthetic)
        out.append(shifted)

    return out, notes


# ── Orchestrator ──────────────────────────────────────────────────────────────


def _ensure_refinements_field(sections: list[dict]) -> list[dict]:
    """Ensure every section has a ``boundary_refinements`` list[str] field."""
    out = []
    for sec in sections:
        s = copy.deepcopy(sec) if "boundary_refinements" not in sec else sec
        if "boundary_refinements" not in s:
            s["boundary_refinements"] = []
        out.append(s)
    return out


def refine_section_boundaries(
    sections: list[dict],
    *,
    forced_words: Iterable[WordMark] = (),
    free_words: Iterable[WordMark] = (),
    chorus_body: Optional[str] = None,
) -> tuple[list[dict], list[str]]:
    """Run the three boundary-refinement passes in fixed order 1 → 2 → 3.

    Each pass operates on the previous pass's output. Every section in the
    returned list has a ``boundary_refinements: list[str]`` field, present
    even when empty.

    Returns ``(refined_sections, all_notes)``. ``all_notes`` is a flat list
    of every note emitted across the three passes, suitable for logging.
    """
    forced_list = list(forced_words)
    free_list = list(free_words)

    refined = [copy.deepcopy(s) for s in sections]

    refined, notes_1 = merge_short_post_chorus_tail(refined, forced_list)
    refined, notes_2 = relabel_or_split_bridge(refined, free_list, chorus_body)
    refined, notes_3 = split_pre_vocal_instrumental(refined, free_list)

    refined = _ensure_refinements_field(refined)

    all_notes: list[str] = []
    all_notes.extend(notes_1)
    all_notes.extend(notes_2)
    all_notes.extend(notes_3)

    if all_notes:
        log.info(
            "refine_section_boundaries: %d total fires (Fix1=%d, Fix2=%d, Fix3=%d)",
            len(all_notes), len(notes_1), len(notes_2), len(notes_3),
        )

    return refined, all_notes
