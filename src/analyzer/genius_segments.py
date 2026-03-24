"""Genius lyric segment timing: fetch, parse, and align section headers to audio."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import whisperx
except ImportError:
    whisperx = None  # type: ignore[assignment]

from src.log import get_logger

log = get_logger("xlight.genius")


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class LyricSegment:
    """An intermediate section parsed from Genius lyrics (not persisted)."""

    label: str            # header text without brackets, e.g. "Chorus", "Verse 1"
    text: str             # lyric body for this section (stripped)
    occurrence_index: int # 0-based index of this label's repetition


@dataclass
class GeniusMatch:
    """Result of a successful Genius API lookup (transient audit record)."""

    genius_id: int
    title: str
    artist: str
    raw_lyrics: str


# ── Title sanitisation ────────────────────────────────────────────────────────

def sanitize_title(raw_title: str) -> str:
    """
    Strip common suffixes from a song title before Genius search.

    Removes:
    - "Remastered YYYY", "Live at ...", "Radio Edit", "Acoustic", etc.
    - Parenthetical qualifiers: (Remastered), [Live]
    - "feat. / ft. / featuring / with ..." phrases
    - Trailing " - ..." patterns (e.g. "Song - 2024 Version")
    """
    title = raw_title.strip()

    # Remove standalone parenthetical/bracket qualifiers at end
    title = re.sub(r"\s*[\(\[].*?[\)\]]\s*$", "", title)

    # Remove common descriptor suffixes (case-insensitive).
    # Use (?=\s|$) instead of \b so terms ending in '.' (feat., ft.) match correctly.
    title = re.sub(
        r"\s*(feat\.|ft\.|featuring|with|live|acoustic|radio edit|"
        r"explicit|demo|single|remastered|version|mix)(?=\s|$).*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    # Remove trailing " - anything" if result would still be non-empty
    candidate = re.sub(r"\s+-\s+.+$", "", title).strip()
    if candidate:
        title = candidate

    return title.strip()


# ── Boilerplate stripping ─────────────────────────────────────────────────────

def strip_boilerplate(raw_lyrics: str) -> str:
    """
    Remove Genius-specific boilerplate from raw lyrics.

    Strips:
    - Leading contributor count line: "N Contributors to 'Song' Lyrics"
    - Trailing "Embed" token (sometimes with a number prefix like "42Embed")
    """
    lines = raw_lyrics.splitlines()

    # Drop first line if it looks like "N Contributors to ... Lyrics"
    if lines and re.match(r"^\d+\s+Contributor", lines[0], re.IGNORECASE):
        lines = lines[1:]

    text = "\n".join(lines)

    # Strip trailing "Embed" or "NNEmbed"
    text = re.sub(r"\d*Embed\s*$", "", text.rstrip()).rstrip()

    return text


# ── Section parsing ───────────────────────────────────────────────────────────

def parse_sections(lyrics: str) -> list[LyricSegment]:
    """
    Split lyrics into sections using bracketed headers as boundaries.

    Returns a list of LyricSegment, one per [Header] found.
    Sections with empty text bodies are included (callers may skip them).

    Occurrence index tracks how many times each label has appeared so far
    (0-based), so the first [Chorus] gets index 0, the second gets 1, etc.
    """
    # Split on [anything], keeping the headers
    parts = re.split(r"(\[.*?\])", lyrics)

    segments: list[LyricSegment] = []
    label_counts: dict[str, int] = {}

    i = 1  # parts[0] is text before the first header (often empty/boilerplate)
    while i < len(parts):
        header_raw = parts[i]
        text_body = parts[i + 1].strip() if i + 1 < len(parts) else ""

        label = header_raw.strip("[]").strip()
        if not label:
            i += 2
            continue

        idx = label_counts.get(label, 0)
        label_counts[label] = idx + 1

        is_instr = is_instrumental_section(label)
        preview = text_body[:60].replace("\n", " ") if text_body else "(empty)"
        log.debug(
            "parse_sections: [%s] occ=%d instrumental=%s text=%r",
            label, idx, is_instr, preview,
        )
        segments.append(LyricSegment(label=label, text=text_body, occurrence_index=idx))
        i += 2

    log.info("parse_sections: %d sections parsed", len(segments))
    return segments


# ── ID3 tag reading ───────────────────────────────────────────────────────────

def read_id3_tags(audio_path: str) -> tuple[str, str]:
    """
    Read Artist and Title from ID3 tags via mutagen EasyID3.

    Returns (artist, title).
    Raises ValueError if tags are missing or unreadable.
    """
    try:
        from mutagen.easyid3 import EasyID3
        tags = EasyID3(audio_path)
        artist = tags["artist"][0]
        title = tags["title"][0]
        return artist, title
    except Exception as exc:
        raise ValueError(
            f"Missing or unreadable ID3 tags in {audio_path!r}: {exc}. "
            "Artist and Title tags are required for Genius lookup."
        ) from exc


# ── Genius API fetch ──────────────────────────────────────────────────────────

def fetch_genius_lyrics(title: str, artist: str, token: str) -> Optional[GeniusMatch]:
    """
    Search Genius for the song and return a GeniusMatch, or None when no song
    is found.

    Uses remove_section_headers=False to preserve [Chorus] / [Verse] markers.

    Raises:
        ImportError: if lyricsgenius is not installed.
        Exception: on network/API errors (propagated so callers can log details).
    """
    import lyricsgenius  # let ImportError propagate with a clear message
    genius = lyricsgenius.Genius(
        token,
        verbose=False,
        remove_section_headers=False,
    )
    song = genius.search_song(title, artist)
    if song is None:
        return None
    return GeniusMatch(
        genius_id=song._body.get("id", 0) if hasattr(song, "_body") else 0,
        title=song.title,
        artist=song.artist,
        raw_lyrics=song.lyrics,
    )


# ── WhisperX alignment ────────────────────────────────────────────────────────

def align_sections(
    sections: list[LyricSegment],
    audio_path: str,
    duration_s: float,
    vocals_path: Optional[str] = None,
    device: str = "cpu",
) -> list[tuple[LyricSegment, int]]:
    """
    Force-align each section's text to the audio and return (section, start_ms) pairs.

    Uses the vocals stem when available; falls back to full mix.
    Sections whose alignment yields no words are skipped (per-section warning
    is appended to align_sections.warnings on the returned list attribute).

    Returns a list of (LyricSegment, start_ms_int) for successfully aligned sections.
    The returned list has a .warnings attribute (list[str]) with per-section messages.
    """
    warnings: list[str] = []
    results: list[tuple[LyricSegment, int]] = []

    align_audio_path = vocals_path if vocals_path and Path(vocals_path).exists() else audio_path

    try:
        import whisperx

        audio = whisperx.load_audio(align_audio_path)

        # Detect language via a quick transcription pass
        try:
            _model = whisperx.load_model("base", device, compute_type="float32")
            quick = _model.transcribe(audio, batch_size=4)
            language = quick.get("language", "en")
        except Exception:
            language = "en"

        align_model, metadata = whisperx.load_align_model(
            language_code=language, device=device
        )

        for section in sections:
            if is_instrumental_section(section.label):
                log.info("align_sections: SKIP instrumental [%s]", section.label)
                warnings.append(
                    f"Section [{section.label}] is instrumental — skipping alignment."
                )
                continue
            if not section.text:
                warnings.append(
                    f"Section [{section.label}] (occurrence {section.occurrence_index}) "
                    "has no lyric text — skipping alignment."
                )
                continue

            try:
                aligned = whisperx.align(
                    [{"text": section.text, "start": 0.0, "end": duration_s}],
                    align_model,
                    metadata,
                    audio,
                    device,
                )
                word_segments = aligned.get("word_segments", [])
                start_s = next(
                    (ws["start"] for ws in word_segments if ws.get("start") is not None),
                    None,
                )
                if start_s is None:
                    warnings.append(
                        f"Section [{section.label}] (occurrence {section.occurrence_index}): "
                        "no words could be aligned — skipping."
                    )
                    continue
                start_ms = int(round(start_s * 1000))
                log.info(
                    "align_sections: [%s] occ=%d → start=%dms (%d words aligned)",
                    section.label, section.occurrence_index, start_ms, len(word_segments),
                )
                results.append((section, start_ms))

            except Exception as exc:
                warnings.append(
                    f"Section [{section.label}] (occurrence {section.occurrence_index}): "
                    f"alignment error — {exc}. Skipping."
                )

    except ImportError:
        warnings.append(
            "whisperx is not installed — cannot align Genius sections. "
            "Install with: pip install whisperx"
        )

    results_with_warnings = _AnnotatedList(results)
    results_with_warnings.warnings = warnings
    results_with_warnings.word_marks = []  # word timing now handled by PhonemeAnalyzer
    return results_with_warnings


# Labels that indicate instrumental sections with no vocals.
# Matched case-insensitively against the section label from Genius.
_INSTRUMENTAL_LABELS = re.compile(
    r"(?i)^(guitar\s*solo|solo|instrumental|interlude|outro\s*solo|intro\s*solo|"
    r"sax\s*solo|piano\s*solo|drum\s*solo|organ\s*solo|break)$"
)


def is_instrumental_section(label: str) -> bool:
    """Return True if a Genius section label indicates an instrumental (no lyrics)."""
    return bool(_INSTRUMENTAL_LABELS.match(label.strip()))


class _AnnotatedList(list):
    """list subclass that carries .warnings and .word_marks attributes."""
    warnings: list[str]
    word_marks: list[tuple[str, int, int]]  # (word, start_ms, end_ms)


# ── GeniusSegmentAnalyzer ─────────────────────────────────────────────────────

class GeniusSegmentAnalyzer:
    """
    Orchestrates the full Genius lyric segment pipeline.

    Usage::

        analyzer = GeniusSegmentAnalyzer()
        structure, warnings = analyzer.run(
            audio_path="song.mp3",
            token=os.environ["GENIUS_API_TOKEN"],
            stem_dir=Path("stems/"),
            duration_ms=210_000,
        )
    """

    def run(
        self,
        audio_path: str,
        token: str,
        stem_dir: Optional[Path] = None,
        duration_ms: int = 0,
        device: str = "cpu",
    ) -> tuple[Optional["SongStructure"], Optional["PhonemeResult"], list[str]]:  # noqa: F821
        """
        Run the full pipeline: ID3 → sanitize → Genius fetch → parse → align → emit.

        Returns (SongStructure, PhonemeResult, warnings).
        - SongStructure holds section-level segment boundaries (chorus/verse/etc.).
        - PhonemeResult holds word-level timing from WhisperX forced alignment of the
          Genius lyrics — verified text with accurate timestamps (lyrics_source="genius").
        Both are None on failure. Warnings are always returned.
        """
        from src.analyzer.structure import SongStructure, StructureSegment

        warnings: list[str] = []

        # ── Validate token ────────────────────────────────────────────────────
        if not token:
            warnings.append(
                "GENIUS_API_TOKEN is not set. Obtain a token at genius.com/api-clients "
                "and set: export GENIUS_API_TOKEN=\"<your-token>\""
            )
            return None, None, warnings

        # ── Read ID3 tags ─────────────────────────────────────────────────────
        try:
            artist, title = read_id3_tags(audio_path)
        except ValueError as exc:
            warnings.append(str(exc))
            return None, None, warnings

        # ── Sanitize title ────────────────────────────────────────────────────
        clean_title = sanitize_title(title)
        log.info("Genius lookup: artist=%r title=%r clean_title=%r", artist, title, clean_title)

        # ── Fetch lyrics from Genius ──────────────────────────────────────────
        try:
            match = fetch_genius_lyrics(clean_title, artist, token)
        except ImportError:
            warnings.append(
                "lyricsgenius is not installed. "
                "Install with: pip install lyricsgenius"
            )
            return None, None, warnings
        except Exception as exc:
            warnings.append(
                f"Genius API error for '{clean_title}' by '{artist}': {exc}. "
                "Check your GENIUS_API_TOKEN and network connection."
            )
            return None, None, warnings

        if match is None:
            warnings.append(
                f"No Genius match found for '{clean_title}' by '{artist}'. "
                "Skipping segment detection."
            )
            return None, None, warnings

        # ── Strip boilerplate and parse sections ──────────────────────────────
        clean_lyrics = strip_boilerplate(match.raw_lyrics)
        log.debug("Genius raw lyrics (%d chars):\n%s", len(clean_lyrics), clean_lyrics[:2000])
        sections = parse_sections(clean_lyrics)

        if not sections:
            warnings.append(
                f"No section headers found in Genius lyrics for '{clean_title}' "
                "by '{artist}'. Skipping segment detection."
            )
            return None, None, warnings

        # ── Discover vocals stem ──────────────────────────────────────────────
        vocals_path: Optional[str] = None
        log.info("Vocals stem discovery: stem_dir=%s", stem_dir)
        if stem_dir is not None:
            for candidate in [
                stem_dir / "vocals.mp3",
                stem_dir / "vocals.wav",
            ]:
                log.debug("  checking %s → exists=%s", candidate, candidate.exists())
                if candidate.exists():
                    vocals_path = str(candidate)
                    break

        if vocals_path is None:
            audio_p = Path(audio_path)
            for stem_subdir in [audio_p.parent / "stems", audio_p.parent / ".stems"]:
                for ext in ["mp3", "wav"]:
                    candidate = stem_subdir / f"vocals.{ext}"
                    log.debug("  checking %s → exists=%s", candidate, candidate.exists())
                    if candidate.exists():
                        vocals_path = str(candidate)
                        break
                if vocals_path:
                    break

        if vocals_path is None:
            log.warning("Vocals stem NOT FOUND — will use full mix (guitar solo will leak)")
            warnings.append(
                "Vocals stem not found — using full mix for alignment. "
                "Run with --stems for better accuracy."
            )
        else:
            log.info("Vocals stem found: %s", vocals_path)

        # ── Build word-level PhonemeResult ─────────────────────────────────
        # Strategy: single-pass alignment of all Genius lyrics as one block
        # (gives WhisperX full context for best word timing), then use a
        # quick transcription to detect vocal regions and filter out any
        # words that land in instrumental gaps (e.g. guitar solos).
        duration_s = duration_ms / 1000.0 if duration_ms > 0 else 0.0
        if duration_s <= 0:
            try:
                import librosa
                duration_s = float(librosa.get_duration(path=audio_path))
            except Exception:
                duration_s = 300.0

        align_audio = vocals_path if vocals_path else audio_path
        log.info("WhisperX alignment audio: %s (vocals_path=%s, audio_path=%s)",
                 align_audio, vocals_path, audio_path)

        phoneme_result: Optional["PhonemeResult"] = None
        vocal_sections = [
            s for s in sections
            if s.text and s.text.strip() and not is_instrumental_section(s.label)
        ]
        if not vocal_sections:
            warnings.append("No vocal sections found in Genius lyrics.")
        else:
            try:
                from src.analyzer.phonemes import (
                    PhonemeResult, WordTrack, WordMark,
                    PhonemeTrack, LyricsBlock, PhonemeMark,
                    word_to_papagayo, distribute_phoneme_timing,
                )
                import nltk
                nltk.download("cmudict", quiet=True)
                from nltk.corpus import cmudict as _cmudict
                cmu_dict = _cmudict.dict()

                audio = whisperx.load_audio(align_audio)

                # Step 1: Quick transcribe to discover vocal regions
                log.info("Step 1: transcribing vocals stem to find vocal regions...")
                model = whisperx.load_model("base", device, compute_type="float32", language="en")
                transcribed = model.transcribe(audio, batch_size=8)
                raw_segments = transcribed.get("segments", [])
                log.info("Transcription found %d raw segments", len(raw_segments))
                for seg in raw_segments:
                    log.debug("  transcribed: %.1fs–%.1fs %r",
                              seg.get("start", 0), seg.get("end", 0),
                              seg.get("text", "")[:60])

                # Build vocal regions (groups of segments with gaps < 4s)
                vocal_regions: list[tuple[float, float]] = []
                if raw_segments:
                    r_start = raw_segments[0]["start"]
                    r_end = raw_segments[0]["end"]
                    for seg in raw_segments[1:]:
                        if seg["start"] - r_end > 4.0:
                            vocal_regions.append((r_start, r_end))
                            r_start = seg["start"]
                        r_end = seg["end"]
                    vocal_regions.append((r_start, r_end))

                log.info("Step 1: found %d vocal regions", len(vocal_regions))
                for i, (rs, re_) in enumerate(vocal_regions):
                    log.info("  vocal region %d: %.1fs–%.1fs (%.1fs)", i, rs, re_, re_ - rs)

                # Step 2: Single-pass alignment — all lyrics as one block
                full_lyrics = " ".join(
                    " ".join(re.sub(r"[^a-zA-Z\s']", " ", s.text).split())
                    for s in vocal_sections
                )
                log.info("Step 2: aligning %d words as single block (%.1fs duration)",
                         len(full_lyrics.split()), duration_s)

                align_model, metadata = whisperx.load_align_model(
                    language_code="en", device=device
                )
                aligned = whisperx.align(
                    [{"text": full_lyrics, "start": 0.0, "end": duration_s}],
                    align_model, metadata, audio, device,
                )
                word_segments = aligned.get("word_segments", [])
                log.info("Step 2: alignment returned %d word_segments", len(word_segments))

                # Build word marks
                word_marks = []
                for ws in word_segments:
                    word = ws.get("word", "").strip()
                    start = ws.get("start")
                    end = ws.get("end")
                    if not word or start is None or end is None:
                        continue
                    word_marks.append(WordMark(
                        label=word.upper(),
                        start_ms=int(round(start * 1000)),
                        end_ms=int(round(end * 1000)),
                    ))

                # Step 3: Filter out words in instrumental gaps
                # A word is kept if it overlaps any vocal region.
                def in_vocal_region(wm: WordMark) -> bool:
                    mid_s = (wm.start_ms + wm.end_ms) / 2000.0
                    return any(rs <= mid_s <= re_ for rs, re_ in vocal_regions)

                before = len(word_marks)
                word_marks = [wm for wm in word_marks if in_vocal_region(wm)]
                filtered = before - len(word_marks)
                if filtered:
                    log.info("Step 3: filtered %d words in instrumental gaps (%d → %d)",
                             filtered, before, len(word_marks))
                else:
                    log.info("Step 3: no words filtered (all in vocal regions)")

                if word_marks:
                    phoneme_marks: list[PhonemeMark] = []
                    for wm in word_marks:
                        papagayo = word_to_papagayo(wm.label, cmu_dict)
                        phoneme_marks.extend(
                            distribute_phoneme_timing(papagayo, wm.start_ms, wm.end_ms)
                        )

                    lyrics_text = " ".join(wm.label for wm in word_marks)
                    phoneme_result = PhonemeResult(
                        lyrics_block=LyricsBlock(
                            text=lyrics_text,
                            start_ms=word_marks[0].start_ms,
                            end_ms=word_marks[-1].end_ms,
                        ),
                        word_track=WordTrack(
                            name="genius-words",
                            marks=word_marks,
                            lyrics_source="genius",
                        ),
                        phoneme_track=PhonemeTrack(
                            name="whisperx-phonemes",
                            marks=phoneme_marks,
                        ),
                        source_file=audio_path,
                        language="en",
                        model_name="base",
                    )
                    log.info("Genius alignment complete: %d words, %d phonemes",
                             len(word_marks), len(phoneme_marks))
                else:
                    warnings.append("Genius word alignment produced no word marks")
            except Exception as exc:
                log.error("Genius word alignment failed: %s", exc, exc_info=True)
                warnings.append(f"Genius word alignment failed: {exc}")

        # ── Derive section boundaries from word-level timestamps ─────────
        # Match each section's first few words against the aligned word marks
        # to find where each section starts in the audio.
        song_structure: Optional["SongStructure"] = None
        if phoneme_result is not None:
            song_duration_ms = duration_ms if duration_ms > 0 else int(
                (duration_s if duration_s > 0 else 300.0) * 1000
            )
            word_marks = phoneme_result.word_track.marks
            # Build a list of (word_upper, start_ms) for matching
            wm_words = [(wm.label.upper(), wm.start_ms) for wm in word_marks]

            section_starts: list[tuple["LyricSegment", int]] = []
            search_offset = 0  # advance through words as we match sections

            for section in sections:
                if is_instrumental_section(section.label):
                    # Instrumental: place it after the last matched section
                    section_starts.append((section, -1))  # placeholder
                    continue
                if not section.text:
                    continue

                # Extract first 3 words of the section for matching
                sec_words = re.sub(r"[^a-zA-Z\s']", " ", section.text).upper().split()[:3]
                if not sec_words:
                    continue

                # Scan forward in aligned words to find this section
                matched_ms = None
                for j in range(search_offset, len(wm_words)):
                    if wm_words[j][0].startswith(sec_words[0][:4]):
                        matched_ms = wm_words[j][1]
                        search_offset = j + 1
                        break

                if matched_ms is not None:
                    log.info("Section boundary: [%s] occ=%d → %dms (matched word %r)",
                             section.label, section.occurrence_index, matched_ms, sec_words[0])
                    section_starts.append((section, matched_ms))
                else:
                    log.warning("Section boundary: [%s] occ=%d — could not match words %s",
                                section.label, section.occurrence_index, sec_words)

            # Fill in instrumental section timestamps (midpoint between neighbors)
            filled: list[tuple["LyricSegment", int]] = []
            for i, (sec, ms) in enumerate(section_starts):
                if ms == -1:
                    prev_ms = filled[-1][1] if filled else 0
                    next_ms = song_duration_ms
                    for _, nms in section_starts[i + 1:]:
                        if nms >= 0:
                            next_ms = nms
                            break
                    ms = (prev_ms + next_ms) // 2
                    log.info("Section boundary: [%s] (instrumental) → %dms (interpolated)", sec.label, ms)
                filled.append((sec, ms))

            if filled:
                segments: list[StructureSegment] = []
                for i, (sec, start_ms) in enumerate(filled):
                    end_ms = filled[i + 1][1] if i + 1 < len(filled) else song_duration_ms
                    segments.append(StructureSegment(
                        label=sec.label,
                        start_ms=start_ms,
                        end_ms=max(end_ms, start_ms + 1),
                    ))
                song_structure = SongStructure(segments=segments, source="genius")
                log.info("Song structure: %d segments built from word timestamps",
                         len(segments))

                # Remove words that fall inside instrumental sections
                # (WhisperX can't distinguish guitar from vocals)
                instrumental_ranges = [
                    (seg.start_ms, seg.end_ms) for seg in segments
                    if is_instrumental_section(seg.label)
                ]
                if instrumental_ranges and phoneme_result is not None:
                    before_count = len(phoneme_result.word_track.marks)
                    phoneme_result.word_track.marks = [
                        wm for wm in phoneme_result.word_track.marks
                        if not any(r_start <= wm.start_ms < r_end
                                   for r_start, r_end in instrumental_ranges)
                    ]
                    removed = before_count - len(phoneme_result.word_track.marks)
                    if removed:
                        log.info("Removed %d words from instrumental sections: %s",
                                 removed, [(f"{r[0]/1000:.1f}s-{r[1]/1000:.1f}s") for r in instrumental_ranges])
                        # Also rebuild phonemes for remaining words
                        new_phonemes: list = []
                        for wm in phoneme_result.word_track.marks:
                            from src.analyzer.phonemes import word_to_papagayo, distribute_phoneme_timing
                            pap = word_to_papagayo(wm.label, cmu_dict)
                            new_phonemes.extend(
                                distribute_phoneme_timing(pap, wm.start_ms, wm.end_ms)
                            )
                        phoneme_result.phoneme_track.marks = new_phonemes
                        phoneme_result.lyrics_block.text = " ".join(
                            wm.label for wm in phoneme_result.word_track.marks
                        )
                        log.info("After instrumental filter: %d words, %d phonemes",
                                 len(phoneme_result.word_track.marks), len(new_phonemes))

        return song_structure, phoneme_result, warnings
