"""Hierarchy orchestrator: zero-flag pipeline for hierarchical music analysis.

Produces a HierarchyResult (schema 2.0.0) with 7 levels (L0-L6) from a single MP3.
Auto-detects installed capabilities (vamp, madmom, demucs) and runs only the
~15 algorithms needed per level.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import librosa

_snap_logger = logging.getLogger(__name__)
import numpy as np

if TYPE_CHECKING:
    from src.analyzer.result import HierarchyResult, TimingTrack, ValueCurve
    from src.analyzer.stems import StemSet

SCHEMA_VERSION = "2.0.0"


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _output_dir(audio_path: Path) -> Path:
    """Return the output folder: {parent}/{stem_name}/"""
    return audio_path.parent / audio_path.stem


def _hierarchy_json_path(audio_path: Path) -> Path:
    out = _output_dir(audio_path)
    return out / f"{audio_path.stem}_hierarchy.json"


def _xtiming_path(audio_path: Path) -> Path:
    out = _output_dir(audio_path)
    return out / f"{audio_path.stem}.xtiming"


def _load_cache(audio_path: Path, source_hash: str) -> "HierarchyResult | None":
    """Return cached HierarchyResult if valid (hash match + schema 2.0.0)."""
    json_path = _hierarchy_json_path(audio_path)
    if not json_path.exists():
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        cached_schema = data.get("schema_version")
        if (cached_schema == SCHEMA_VERSION
                and data.get("source_hash") == source_hash):
            from src.analyzer.result import HierarchyResult as _HR
            return _HR.from_dict(data)
        # Schema mismatch — emit a refresh-command hint so the user knows
        # why a re-analysis is happening rather than seeing it silently.
        # We deliberately don't raise here; a mismatched cache is a normal
        # outcome (e.g. after a code update) and the orchestrator will
        # rebuild it on this run. But quietly returning None is the bug
        # the helper exists to fix.
        if cached_schema is not None and cached_schema != SCHEMA_VERSION:
            from src.schema_check import check_stale_cache, SchemaFromFutureError
            try:
                check_stale_cache(
                    cached_schema,
                    SCHEMA_VERSION,
                    name=f"_hierarchy.json ({json_path.name})",
                    refresh_hint=f"re-run analysis on {audio_path.name}",
                    on_older="warn",
                )
            except SchemaFromFutureError as exc:
                # Future-version data is unsafe to use even as a cache — log
                # loudly and force re-analysis.
                _snap_logger.warning("%s", exc)
    except (MemoryError, SystemExit, KeyboardInterrupt):
        raise
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        _snap_logger.warning("Cache load failed for %s: %s", json_path, exc)
    except Exception as exc:
        _snap_logger.warning("Unexpected cache error for %s: %s", json_path, exc)
    return None


def _write_cache(audio_path: Path, result: "HierarchyResult") -> None:
    """Write HierarchyResult JSON to output folder atomically."""
    import os
    import tempfile

    json_path = _hierarchy_json_path(audio_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    # Write to temp file then rename for atomicity
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(json_path.parent),
        suffix=".tmp",
    )
    try:
        os.close(tmp_fd)
        Path(tmp_path).write_text(content, encoding="utf-8")
        os.replace(tmp_path, str(json_path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── Algorithm list builder ────────────────────────────────────────────────────

def _make_stem_algo(algo_cls, stem: str):
    """Create an algorithm instance configured for a specific stem."""
    inst = algo_cls()
    inst.preferred_stem = stem
    # Encode stem in name so vamp_runner can route it correctly
    inst.name = f"{inst.name}:{stem}"
    return inst


def _build_algorithm_list(caps: dict[str, bool], stems_available: list[str]):
    """Build the ~15 algorithm instances needed per the level mapping (research.md R6).

    Uses the centralized algorithm registry for class discovery instead of
    duplicating try/import/except blocks.
    """
    from src.analyzer.algorithms.registry import get_algorithm_map

    # Build the registry map filtered to requested libraries
    libraries: set[str] = {"librosa"}
    if caps.get("vamp"):
        libraries.add("vamp")
    if caps.get("madmom"):
        libraries.add("madmom")
    algo_map = get_algorithm_map(libraries=libraries)

    algos = []

    # Helper: instantiate by registry name, warn if unavailable
    def _add(name: str) -> bool:
        cls = algo_map.get(name)
        if cls is not None:
            algos.append(cls())
            return True
        return False

    def _add_stem(name: str, stem: str) -> bool:
        cls = algo_map.get(name)
        if cls is not None:
            algos.append(_make_stem_algo(cls, stem))
            return True
        return False

    # ── Always-available (librosa) ────────────────────────────────────────────
    _add("librosa_bars")     # L2 bar candidate
    _add("librosa_beats")    # L3 beat candidate
    _add("librosa_onsets")   # L4 full_mix events

    # ── Vamp algorithms (optional) ────────────────────────────────────────────
    if caps.get("vamp"):
        _add("qm_bars")      # L2 bar candidate
        _add("qm_beats")     # L3 beat candidate
        _add("beatroot")     # L3 beat candidate

        # L0/L5: bbc_energy on full_mix (for impacts/gaps derivation)
        _add("bbc_energy")
        # L5: bbc_spectral_flux on full_mix
        _add("bbc_spectral_flux")
        # L5: bbc_rhythm on full_mix — smoothed against bbc_energy in
        # the L5 assembly (see fix-misclassified-curves change).
        _add("bbc_rhythm")
        # L5: bbc_energy + bbc_rhythm per stem (guitar included for solo
        # detection + L4 filtering). bbc_rhythm runs only when bbc_energy does
        # so the smoothing pair lines up.
        if "bbc_energy" in algo_map:
            energy_stems = [s for s in stems_available if s not in ("full_mix",)]
            for stem in energy_stems[:5]:
                if stem in ("drums", "bass", "vocals", "guitar", "other"):
                    _add_stem("bbc_energy", stem)
                    if "bbc_rhythm" in algo_map:
                        _add_stem("bbc_rhythm", stem)

        _add("segmentino")    # L1 sections
        _add("qm_segments")   # L1 sections

        # Force full_mix: Chordino's default preferred_stem="piano" is too sparse
        # for most genres. Full mix gives reliable chord detection.
        _add_stem("chordino_chords", "full_mix")  # L6 chords

        # L6: NNLS Chroma per-frame curve on full_mix. Consumed by chord-color
        # fallback in src/generator/chord_colors.py for inter-chord modulation.
        _add_stem("nnls_chroma", "full_mix")

        _add("qm_key")        # L6 key

        # L4: per-stem onset detection
        if "aubio_onset" in algo_map:
            for stem in stems_available:
                if stem != "full_mix":
                    _add_stem("aubio_onset", stem)

    # ── Madmom algorithms (optional) ─────────────────────────────────────────
    if caps.get("madmom"):
        _add("madmom_beats")      # L3 beat candidate
        _add("madmom_downbeats")  # L2 bar candidate

    return algos


# ── Track extraction helpers ──────────────────────────────────────────────────

def _get_value_curve(track: "TimingTrack | None") -> "ValueCurve | None":
    if track is None:
        return None
    return getattr(track, "value_curve", None)


def _format_duration(ms: int) -> str:
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


# ── Main orchestrator ─────────────────────────────────────────────────────────

def run_orchestrator(
    audio_path: str,
    fresh: bool = False,
    dry_run: bool = False,
    progress_callback=None,
    profile: str | None = None,
) -> "HierarchyResult":
    """Run the full hierarchy analysis pipeline on a single MP3 file.

    Args:
        audio_path: Path to the source MP3 file.
        fresh: If True, ignore any cached result and re-run analysis.
        dry_run: If True, print what would run and return without executing.
        progress_callback: Optional callable(index, total, name, mark_count).
        profile: Analysis preset — "quick" (librosa-only), "standard" (auto-detect),
                 "full" (all available), or None (same as standard).

    Returns:
        HierarchyResult with all available hierarchy levels populated.
    """
    import time as _time

    from src.analyzer.audio import load
    from src.analyzer.capabilities import detect_capabilities
    from src.analyzer.derived import derive_energy_drops, derive_energy_impacts, derive_gaps
    from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve
    from src.analyzer.runner import AnalysisRunner
    from src.analyzer.selector import (
        annotate_agreement_confidence,
        rank_tracks,
        select_best_bar_track_with_candidates,
        select_best_beat_track_with_candidates,
    )

    _t0 = _time.monotonic()
    src_path = Path(audio_path).resolve()

    # ── Stage 1: Detect capabilities ─────────────────────────────────────────
    caps = detect_capabilities()
    warnings: list[str] = []

    # ── Apply profile constraints ────────────────────────────────────────────
    if profile == "quick":
        # Quick: librosa-only, no stems, no vamp, no madmom
        caps = {"vamp": False, "madmom": False, "demucs": False,
                "essentia": False, "librosa": True}
        warnings.append("Profile 'quick': librosa-only, no stems")
    elif profile == "full":
        pass  # use everything detected
    # None or "standard": use default detected capabilities

    # ── Stage 2: Dry run mode (before cache check) ────────────────────────────
    if dry_run:
        # Build algo list to show what would run
        stems_available_preview = ["full_mix"]
        if caps.get("demucs"):
            stems_available_preview = ["full_mix", "drums", "bass", "vocals", "other"]
        algos_preview = _build_algorithm_list(caps, stems_available_preview)
        print(f"Capabilities: vamp {'✓' if caps['vamp'] else '✗'}  "
              f"madmom {'✓' if caps['madmom'] else '✗'}  "
              f"demucs {'✓' if caps['demucs'] else '✗'}")
        print("Would run:")
        _print_dry_run(algos_preview)
        print(f"Total: {len(algos_preview)} algorithm runs")
        raise SystemExit(0)

    # ── Stage 3: Cache check ──────────────────────────────────────────────────
    source_hash = _md5_file(src_path)
    if not fresh:
        cached = _load_cache(src_path, source_hash)
        if cached is not None:
            return cached

    # ── Stage 4: Load audio ───────────────────────────────────────────────────
    audio, sr, meta = load(str(src_path))

    try:
        tempo_arr, _ = librosa.beat.beat_track(y=audio, sr=sr, hop_length=512)
        estimated_bpm = float(np.atleast_1d(tempo_arr)[0])
    except Exception:
        estimated_bpm = 0.0

    duration_str = _format_duration(meta.duration_ms)
    print(f"Analyzing: {src_path.name} ({duration_str}, ~{estimated_bpm:.0f} BPM)")

    cap_str = (f"Capabilities: vamp {'✓' if caps['vamp'] else '✗'}  "
               f"madmom {'✓' if caps['madmom'] else '✗'}  "
               f"demucs {'✓' if caps['demucs'] else '✗'}  "
               f"essentia {'✓' if caps.get('essentia') else '✗'}")
    print(cap_str)

    # ── Stage 5: Stem separation ──────────────────────────────────────────────
    from src.analyzer.stems import StemSeparator
    stems: "StemSet | None" = None
    stems_available = ["full_mix"]

    from src.analyzer.stems import StemCache
    _stem_cache = StemCache(src_path)
    if _stem_cache.is_valid():
        # Cached stems available — load without needing demucs
        print("Stems: separating...", end=" ", flush=True)
        try:
            stems = _stem_cache.load()
            stem_names = [n for n in ("drums", "bass", "vocals", "guitar", "piano", "other")
                          if stems.get(n) is not None]
            stems_available = ["full_mix"] + stem_names
            print(f"Stem separation: cache hit ({_stem_cache.source_hash[:8]})")
            print(f"done ({', '.join(stem_names)})")
        except Exception as exc:
            print(f"failed ({exc})")
            warnings.append(f"Stem cache load failed: {exc}. Using full_mix only.")
    elif caps.get("demucs"):
        print("Stems: separating...", end=" ", flush=True)
        try:
            separator = StemSeparator()
            stems = separator.separate(src_path)
            stem_names = [n for n in ("drums", "bass", "vocals", "guitar", "piano", "other")
                          if stems.get(n) is not None]
            stems_available = ["full_mix"] + stem_names
            print(f"done ({', '.join(stem_names)})")
        except Exception as exc:
            print(f"failed ({exc})")
            warnings.append(f"Stem separation failed: {exc}. Using full_mix only.")
    else:
        warnings.append("L4/L5 per-stem: skipped — demucs not available and no cache. Using full_mix only.")

    # ── Stage 6: Run algorithms ───────────────────────────────────────────────
    algos = _build_algorithm_list(caps, stems_available)

    # Default CLI progress display when no external callback is provided
    def _default_progress(index: int, total: int, name: str, mark_count: int) -> None:
        bar_width = 30
        filled = int(bar_width * index / total) if total else 0
        bar = "█" * filled + "░" * (bar_width - filled)
        pct = int(100 * index / total) if total else 0
        marks_str = f" ({mark_count} marks)" if mark_count else ""
        print(f"\r  [{bar}] {pct:3d}% ({index}/{total}) {name}{marks_str}",
              end="", flush=True, file=sys.stderr)
        if index == total:
            print(file=sys.stderr)  # newline when done

    effective_callback = progress_callback or _default_progress

    runner = AnalysisRunner(algos)
    analysis = runner.run(str(src_path), progress_callback=effective_callback, stems=stems)

    # Index tracks by base algorithm name (strip :stem or _stem suffix)
    tracks_by_name: dict[str, list["TimingTrack"]] = {}
    for track in analysis.timing_tracks:
        algo = track.algorithm_name
        # Strip :stem suffix (colon format from our request encoding)
        if ":" in algo:
            base = algo.split(":")[0]
        else:
            # Strip _stem suffix (underscore format from vamp_runner's name override)
            # Only strip known stem suffixes to avoid breaking other algorithm names
            base = algo
            for stem in ("drums", "bass", "vocals", "guitar", "piano", "other", "full_mix"):
                if algo.endswith(f"_{stem}"):
                    base = algo[: -(len(stem) + 1)]
                    break
        tracks_by_name.setdefault(base, []).append(track)

    # ── Stage 7: Map to hierarchy levels ─────────────────────────────────────

    # L0: get energy curve from full_mix bbc_energy
    energy_curve_full: "ValueCurve | None" = None
    for t in tracks_by_name.get("bbc_energy", []):
        if t.stem_source == "full_mix":
            energy_curve_full = _get_value_curve(t)
            break
    if energy_curve_full is None:
        # Fallback: first available
        for t in tracks_by_name.get("bbc_energy", []):
            vc = _get_value_curve(t)
            if vc:
                energy_curve_full = vc
                break

    # L1: sections from segmentino, optionally enriched with QM segmenter boundaries
    sections: list["TimingMark"] = []
    seg_tracks = tracks_by_name.get("segmentino", [])
    if seg_tracks:
        sections = seg_tracks[0].marks
        # Merge QM segmenter boundaries that don't overlap with segmentino
        qm_seg_tracks = tracks_by_name.get("qm_segments", [])
        if qm_seg_tracks:
            sections = _merge_qm_boundaries(sections, qm_seg_tracks[0].marks)
        print(f"L1 Structure: {len(sections)} sections "
              f"({_section_summary(sections)})")
    else:
        # Fall back to QM segmenter if segmentino unavailable
        qm_seg_tracks = tracks_by_name.get("qm_segments", [])
        if qm_seg_tracks:
            sections = qm_seg_tracks[0].marks
            print(f"L1 Structure: {len(sections)} sections from qm_segmenter "
                  f"({_section_summary(sections)})")
        else:
            warnings.append("L1 Structure: skipped — segmentino not available (install Vamp plugin 'segmentino')")

    # L2: select best bar track
    bar_algo_names = {"qm_bars", "librosa_bars", "madmom_downbeats"}
    bar_candidates = [t for t in analysis.timing_tracks if t.algorithm_name in bar_algo_names]
    onset_times = _collect_onset_times(tracks_by_name)
    bars, bar_losers = select_best_bar_track_with_candidates(bar_candidates, onset_times)
    if bars:
        print(f"L2 Bars: {bars.mark_count} marks ({bars.algorithm_name}, "
              f"{bars.mark_count / (meta.duration_ms / 1000):.2f} Hz)")
        # Snap L1 section boundaries to nearest bar now that we have the bar track
        if sections:
            sections = _snap_sections_to_bars(sections, bars)
        # Annotate per-mark cross-tracker agreement (L2). When no losers are
        # available (single-tracker fallback) this is a no-op and the
        # validator's track-level scalar takes over downstream.
        if bar_losers:
            annotate_agreement_confidence(bars, bar_losers, window_ms=35)
    else:
        warnings.append("L2 Bars: no bar track produced")

    # L3: select best beat track with BPM-range validation
    beat_algo_names = {"qm_beats", "librosa_beats", "madmom_beats", "beatroot_beats"}
    beat_candidates = [t for t in analysis.timing_tracks if t.algorithm_name in beat_algo_names]
    beats, beat_losers = _select_beat_with_bpm_check(
        beat_candidates, onset_times, estimated_bpm, meta.duration_ms,
    )
    if beats:
        print(f"L3 Beats: {beats.mark_count} marks ({beats.algorithm_name}, "
              f"{beats.mark_count / (meta.duration_ms / 1000):.2f} Hz)")
        # Annotate per-mark cross-tracker agreement (L3). The losers are the
        # non-winning candidates from `_select_beat_with_bpm_check`, which may
        # differ from the rank-1 candidate when the BPM-range fallback fires.
        if beat_losers:
            annotate_agreement_confidence(beats, beat_losers, window_ms=35)
    else:
        warnings.append("L3 Beats: no beat track produced")

    # L4: events per stem — group aubio_onset tracks by stem_source
    events: dict[str, "TimingTrack"] = {}
    for t in tracks_by_name.get("aubio_onset", []):
        stem = t.stem_source or "full_mix"
        events[stem] = t
    # Fallback: librosa onsets for full_mix if no aubio
    if "full_mix" not in events:
        librosa_onsets = tracks_by_name.get("librosa_onsets")
        if librosa_onsets:
            events["full_mix"] = librosa_onsets[0]
    # Percussion onsets as drums fallback
    perc_tracks = tracks_by_name.get("percussion_onsets", [])
    if perc_tracks and "drums" not in events:
        events["drums"] = perc_tracks[0]

    event_summary = ", ".join(f"{k} {v.mark_count}" for k, v in events.items())
    print(f"L4 Events: {event_summary or 'none'}")

    # Build early energy curves (needed for both dedup and energy filter below)
    _early_energy_curves: dict = {}
    for t in tracks_by_name.get("bbc_energy", []):
        vc = _get_value_curve(t)
        if vc:
            _early_energy_curves[t.stem_source or "full_mix"] = vc

    # Dedup same-hit doublings (aubio minioi param is silently ignored by Vamp wrapper)
    _early_sf: "ValueCurve | None" = None
    for t in tracks_by_name.get("bbc_spectral_flux", []):
        vc = _get_value_curve(t)
        if vc:
            _early_sf = vc
            break
    events = _deduplicate_events(events, _early_sf, _early_energy_curves)

    # Filter L4 events to top-60% energy onsets per stem (removes ghost notes)
    events = _filter_events_by_energy(events, _early_energy_curves, energy_curve_full)

    # Classify drum events as kick / snare / hihat
    if "drums" in events and stems is not None:
        drum_audio = stems.get("drums")
        if drum_audio is not None:
            try:
                from src.analyzer.drum_classifier import classify_drum_events
                classify_drum_events(events["drums"], drum_audio, sr)
            except Exception as exc:
                warnings.append(f"Drum classification failed: {exc}")

    # Label non-drum events with energy tier: h / m / l
    _label_energy_tiers(events, _early_energy_curves, energy_curve_full)

    # L5: energy curves per stem
    energy_curves: dict[str, "ValueCurve"] = {}
    spectral_flux: "ValueCurve | None" = None

    for t in tracks_by_name.get("bbc_energy", []):
        vc = _get_value_curve(t)
        if vc:
            stem = t.stem_source or "full_mix"
            energy_curves[stem] = vc

    for t in tracks_by_name.get("bbc_spectral_flux", []):
        vc = _get_value_curve(t)
        if vc:
            spectral_flux = vc

    # L5 smoothing: when bbc_rhythm is available for a stem that also has
    # bbc_energy, replace the energy curve with the per-frame mean. The two
    # signals cross-confirm rhythm-aligned activity (see design D2 of the
    # fix-misclassified-curves change). Stems that have only one of the two
    # signals are left unchanged.
    rhythm_curves: dict[str, "ValueCurve"] = {}
    for t in tracks_by_name.get("bbc_rhythm", []):
        vc = _get_value_curve(t)
        if vc:
            rhythm_curves[t.stem_source or "full_mix"] = vc

    for stem, energy_vc in list(energy_curves.items()):
        rhythm_vc = rhythm_curves.get(stem)
        if rhythm_vc is None:
            continue
        if energy_vc.fps != rhythm_vc.fps:
            warnings.append(
                f"L5 Energy: bbc_energy ({energy_vc.fps} fps) and bbc_rhythm "
                f"({rhythm_vc.fps} fps) disagree on fps for stem '{stem}'; "
                f"skipping smoothing for that stem"
            )
            continue
        n = min(len(energy_vc.values), len(rhythm_vc.values))
        if n == 0:
            continue
        if len(energy_vc.values) != len(rhythm_vc.values):
            warnings.append(
                f"L5 Energy: bbc_energy ({len(energy_vc.values)}) and "
                f"bbc_rhythm ({len(rhythm_vc.values)}) frame counts differ on "
                f"stem '{stem}'; truncating to {n}"
            )
        smoothed = [
            int(round((energy_vc.values[i] + rhythm_vc.values[i]) / 2))
            for i in range(n)
        ]
        from src.analyzer.result import ValueCurve as _VC
        energy_curves[stem] = _VC(
            name=f"{energy_vc.name}+rhythm",
            stem_source=stem,
            fps=energy_vc.fps,
            values=smoothed,
        )

    curve_summary = ", ".join(list(energy_curves.keys()) +
                               (["spectral_flux"] if spectral_flux else []))
    smoothed_count = sum(
        1 for s in energy_curves if s in rhythm_curves
    )
    print(
        f"L5 Energy: {len(energy_curves)} curves ({curve_summary or 'none'})"
        + (f" — {smoothed_count} smoothed with bbc_rhythm" if smoothed_count else "")
    )

    # L6: harmony
    chords_tracks = tracks_by_name.get("chordino_chords", [])
    chords = chords_tracks[0] if chords_tracks else None

    key_tracks = tracks_by_name.get("qm_key", [])
    key_changes = key_tracks[0] if key_tracks else None

    # L6 chroma curve: NNLS Chroma per-frame 12-bin pitch-class energy.
    # Consumed by chord_color_for_time() in src/generator/chord_colors.py
    # as a fallback when the gap between Chordino chord events is large.
    from src.analyzer.result import ChromaCurve as _ChromaCurve
    chroma_curve: "_ChromaCurve | None" = None
    chroma_tracks = tracks_by_name.get("nnls_chroma", [])
    for t in chroma_tracks:
        candidate = getattr(t, "value_curve", None)
        if isinstance(candidate, _ChromaCurve) and candidate.values:
            chroma_curve = candidate
            break
    if chroma_curve is None and not chroma_tracks:
        warnings.append("L6 Chroma: skipped — nnls_chroma not available")

    if chords or key_changes:
        chord_count = chords.mark_count if chords else 0
        key_count = key_changes.mark_count if key_changes else 0
        chroma_summary = (
            f", chroma_curve {len(chroma_curve.values)}f@{chroma_curve.fps}fps"
            if chroma_curve else ""
        )
        print(f"L6 Harmony: {chord_count} chord changes, {key_count} key(s){chroma_summary}")
    else:
        warnings.append("L6 Harmony: skipped — chordino/qm_key not available")

    # ── Stage 7b: Beat position labels, half-bars, eighth notes ─────────────
    half_bars: "TimingTrack | None" = None
    eighth_notes: "TimingTrack | None" = None
    if beats and bars:
        import copy as _copy
        _label_beats(beats, bars)

        # Half-bars: beats at positions 1 and 3
        hb_marks = [_copy.copy(m) for m in beats.marks if m.label in ("1", "3")]
        if hb_marks:
            half_bars = TimingTrack(
                name="half_bars", algorithm_name="derived",
                element_type="half_bar", marks=hb_marks, quality_score=0.0,
            )
            print(f"L2.5 Half-bars: {len(hb_marks)} marks")

        # Eighth notes: midpoints between consecutive beats
        en_marks = _derive_eighth_notes(beats)
        if en_marks:
            eighth_notes = TimingTrack(
                name="eighth_notes", algorithm_name="derived",
                element_type="eighth_note", marks=en_marks, quality_score=0.0,
            )
            print(f"L3.5 Eighth notes: {len(en_marks)} marks")

    # ── Stage 8: Derive L0 features ───────────────────────────────────────────
    impacts: list["TimingMark"] = []
    drops: list["TimingMark"] = []
    gaps: list["TimingMark"] = []

    if energy_curve_full:
        impacts = derive_energy_impacts(energy_curve_full)
        drops = derive_energy_drops(energy_curve_full)
        gaps = derive_gaps(energy_curve_full)
        print(f"L0 Special Moments: {len(impacts)} impacts, "
              f"{len(drops)} drops, {len(gaps)} gaps")
    else:
        warnings.append("L0 Special Moments: skipped — bbc_energy not available")

    # ── Stage 9: Interaction analysis ────────────────────────────────────────
    interactions = None
    if stems is not None:
        stem_audio: dict[str, np.ndarray] = {}
        for s in ("drums", "bass", "vocals", "other"):
            arr = stems.get(s)
            if arr is not None:
                stem_audio[s] = arr
        if len(stem_audio) >= 2:
            try:
                from src.analyzer.interaction import analyze_interactions
                interactions = analyze_interactions(stem_audio, sr)
                handoff_count = len(interactions.handoffs) if interactions else 0
                print(f"Interactions: leader track, tightness, {handoff_count} handoffs")
            except Exception as exc:
                warnings.append(f"Interaction analysis failed: {exc}")

    # ── Stage 9b: Solo detection ──────────────────────────────────────────────
    solos: dict = {}
    if len(energy_curves) >= 2:
        try:
            from src.analyzer.solos import detect_solos
            solos = detect_solos(energy_curves, meta.duration_ms)
            if solos:
                solo_summary = ", ".join(
                    f"{stem} {len(marks)}×{sum(m.duration_ms or 0 for m in marks)//1000}s"
                    for stem, marks in solos.items()
                )
                print(f"Solos: {solo_summary}")
        except Exception as exc:
            warnings.append(f"Solo detection failed: {exc}")

    # ── Stage 9b2: SSM repetition groups (Chorus validator input) ────────────
    # Per design D1 in
    # ``openspec/changes/agreement-score-operationalization/design.md``
    # SSM is a *validator* — never a source of truth for section roles.
    # The story builder reads this list to flag heuristically-labeled
    # Choruses without an SSM peer for human review.
    repetition_groups = None
    try:
        from src.analyzer.self_similarity import compute_repetition_groups
        ssm_t0 = _time.monotonic()
        repetition_groups = compute_repetition_groups(audio, sr)
        ssm_elapsed = _time.monotonic() - ssm_t0
        print(
            f"SSM: {len(repetition_groups)} repetition group(s) "
            f"in {ssm_elapsed:.1f}s"
        )
    except Exception as exc:
        # Per spec scenario "SSM unavailable or errored → None plus
        # warning": leave field as None and record the cause.
        warnings.append(f"SSM (self-similarity matrix) failed: {exc}")
        repetition_groups = None

    # ── Stage 9c: Essentia high-level features ─────────────────────────────────
    essentia_features = None
    if caps.get("essentia"):
        try:
            from src.analyzer.essentia_features import extract_essentia_features
            essentia_features = extract_essentia_features(audio, sr).to_dict()
            ef = essentia_features
            print(f"Essentia: key={ef['key']} {ef['scale']}  "
                  f"danceability={ef['danceability']:.2f}  "
                  f"dynamics={ef['dynamic_complexity']:.1f}  "
                  f"loudness={ef['loudness_lufs']:.1f} LUFS")
        except Exception as exc:
            warnings.append(f"Essentia analysis failed: {exc}")

    # ── Stage 10: Assemble result ─────────────────────────────────────────────
    from src.paths import PathContext as _PathContext
    _path_ctx = _PathContext()
    result = HierarchyResult(
        schema_version=SCHEMA_VERSION,
        source_file=str(src_path),
        source_hash=source_hash,
        relative_source_file=_path_ctx.to_relative(str(src_path)),
        duration_ms=meta.duration_ms,
        estimated_bpm=round(estimated_bpm, 2),
        energy_impacts=impacts,
        energy_drops=drops,
        gaps=gaps,
        sections=sections,
        bars=bars,
        beats=beats,
        half_bars=half_bars,
        eighth_notes=eighth_notes,
        events=events,
        energy_curves=energy_curves,
        spectral_flux=spectral_flux,
        chords=chords,
        key_changes=key_changes,
        chroma_curve=chroma_curve,
        interactions=interactions,
        solos=solos,
        essentia_features=essentia_features,
        stems_available=stems_available,
        capabilities=caps,
        algorithms_run=[a.name for a in algos],
        warnings=warnings,
        repetition_groups=repetition_groups,
    )

    # ── Stage 11: Validate mark placement ────────────────────────────────────
    from src.analyzer.validator import validate_hierarchy, format_validation_report
    result.validation = validate_hierarchy(result)
    print(format_validation_report(result.validation))

    # ── Stage 12: Write outputs ───────────────────────────────────────────────
    elapsed = _time.monotonic() - _t0
    print(f"\nAnalysis complete in {elapsed:.1f}s — "
          f"{len(analysis.timing_tracks)} tracks generated")

    _write_cache(src_path, result)
    _write_xtiming(src_path, result)

    out_dir = _output_dir(src_path)
    print(f"\nOutput: {out_dir}/{src_path.stem}_hierarchy.json")
    print(f"Timing: {out_dir}/{src_path.stem}.xtiming")

    return result


# ── .xtiming export ───────────────────────────────────────────────────────────

def _write_xtiming(audio_path: Path, result: "HierarchyResult") -> None:
    """Write a multi-layer .xtiming file from HierarchyResult."""
    import xml.etree.ElementTree as ET

    xtiming_path = _xtiming_path(audio_path)
    xtiming_path.parent.mkdir(parents=True, exist_ok=True)

    root = ET.Element("timings")

    _add_mark_layer(root, "eighth_notes", result.eighth_notes)
    _add_mark_layer(root, "beats", result.beats)
    _add_mark_layer(root, "half_bars", result.half_bars)
    _add_mark_layer(root, "bars", result.bars)
    _add_section_layer(root, "sections", result.sections)

    for stem_name, track in result.events.items():
        _add_mark_layer(root, f"events_{stem_name}", track)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    with open(str(xtiming_path), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        tree.write(fh, encoding="unicode", xml_declaration=False)


def _add_mark_layer(root, name: str, track: "TimingTrack | None") -> None:
    import xml.etree.ElementTree as ET
    if not track or not track.marks:
        return
    timing_el = ET.SubElement(root, "timing")
    timing_el.set("name", name)
    timing_el.set("SourceVersion", "2024.01")
    layer = ET.SubElement(timing_el, "EffectLayer")
    marks = track.marks
    for i, mark in enumerate(marks):
        start = mark.time_ms
        end = marks[i + 1].time_ms if i + 1 < len(marks) else start + 50
        label = mark.label or track.element_type
        ET.SubElement(layer, "Effect").attrib.update({
            "label": label, "starttime": str(start), "endtime": str(end),
        })


def _add_section_layer(root, name: str, marks: "list") -> None:
    import xml.etree.ElementTree as ET
    if not marks:
        return
    timing_el = ET.SubElement(root, "timing")
    timing_el.set("name", name)
    timing_el.set("SourceVersion", "2024.01")
    layer = ET.SubElement(timing_el, "EffectLayer")
    for i, mark in enumerate(marks):
        start = mark.time_ms
        if i + 1 < len(marks):
            end = marks[i + 1].time_ms
        elif mark.duration_ms:
            end = start + mark.duration_ms
        else:
            end = start + 10000
        label = mark.label or "section"
        ET.SubElement(layer, "Effect").attrib.update({
            "label": label, "starttime": str(start), "endtime": str(end),
        })


# ── Display helpers ───────────────────────────────────────────────────────────

def _section_summary(marks: list) -> str:
    from collections import Counter
    labels = [m.label for m in marks if m.label]
    if not labels:
        return "no labels"
    counter = Counter(labels)
    return ", ".join(f"{label}×{count}" for label, count in sorted(counter.items()))


def _collect_onset_times(tracks_by_name: dict) -> list[int]:
    """Return onset times for use in bar/beat selector scoring.

    Prefers aubio_onset on full_mix (densest, most accurate for beat alignment),
    then falls back to librosa_onsets or qm_onsets_complex.
    """
    # Prefer full_mix aubio onsets
    for t in tracks_by_name.get("aubio_onset", []):
        if (t.stem_source or "full_mix") == "full_mix":
            return [m.time_ms for m in t.marks]
    # Fallback: any aubio track
    aubio = tracks_by_name.get("aubio_onset", [])
    if aubio:
        return [m.time_ms for m in aubio[0].marks]
    # Final fallbacks
    for name in ("librosa_onsets", "qm_onsets_complex"):
        tracks = tracks_by_name.get(name, [])
        if tracks:
            return [m.time_ms for m in tracks[0].marks]
    return []


def _nearest_in_sorted(t: int, sorted_times: list[int]) -> int | None:
    """Binary-search nearest value in sorted list; return the value (not distance)."""
    if not sorted_times:
        return None
    lo, hi = 0, len(sorted_times) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_times[mid] < t:
            lo = mid + 1
        else:
            hi = mid
    best_idx = lo
    if lo > 0 and abs(sorted_times[lo - 1] - t) < abs(sorted_times[lo] - t):
        best_idx = lo - 1
    return sorted_times[best_idx]


def _merge_qm_boundaries(
    sections: list, qm_marks: list, min_gap_ms: int = 2000
) -> list:
    """Merge QM segmenter boundaries into the segmentino section list.

    Only adds QM boundaries that are at least *min_gap_ms* away from any
    existing segmentino boundary — this avoids creating tiny micro-sections
    while still capturing structural changes that segmentino missed.
    """
    import copy as _copy

    existing_times = {m.time_ms for m in sections}
    merged = list(sections)
    added = 0

    for qm_mark in qm_marks:
        t = qm_mark.time_ms
        # Skip if too close to an existing boundary
        if any(abs(t - et) < min_gap_ms for et in existing_times):
            continue
        new_mark = _copy.copy(qm_mark)
        if not new_mark.label:
            new_mark.label = "qm_boundary"
        merged.append(new_mark)
        existing_times.add(t)
        added += 1

    if added:
        merged.sort(key=lambda m: m.time_ms)
        print(f"  L1 merge: added {added} QM segmenter boundaries")

    return merged


def _snap_sections_to_bars(sections: list, bars: "TimingTrack") -> list:
    """Snap each section boundary to the nearest bar mark within the adaptive window.

    Uses the same adaptive window as the validator: half the median bar interval,
    clamped to 400–1200 ms.  Sections already on a bar boundary are unchanged.

    Enhanced with:
    - Crossover prevention: snap window reduced if moving a boundary would cross
      its neighbour in the sorted list.
    - Merge/duplicate prevention: after snapping, duplicate timestamps are resolved
      by absorbing the shorter adjacent section into its longer neighbour.
    - Minimum section duration guard: sections shorter than 2000ms are absorbed
      into their preceding neighbour with a logged warning.

    Returns a new list of TimingMark objects (originals are not mutated).
    """
    import copy as _copy
    if not sections or not bars or not bars.marks:
        return sections

    bar_times = sorted(m.time_ms for m in bars.marks)

    if len(bar_times) > 1:
        intervals = [bar_times[i + 1] - bar_times[i] for i in range(len(bar_times) - 1)]
        median_interval = sorted(intervals)[len(intervals) // 2]
        window_ms = max(400, min(1200, median_interval // 2))
    else:
        window_ms = 500

    # Sort sections by time before processing
    working = sorted(sections, key=lambda m: m.time_ms)

    # First pass: snap each boundary, respecting neighbours to prevent crossover
    result = []
    snapped = 0
    for i, mark in enumerate(working):
        prev_time = result[-1].time_ms if result else None
        next_time = working[i + 1].time_ms if i + 1 < len(working) else None

        nearest = _nearest_in_sorted(mark.time_ms, bar_times)
        if nearest is None or nearest == mark.time_ms:
            result.append(mark)
            continue

        dist = abs(nearest - mark.time_ms)
        if dist > window_ms:
            result.append(mark)
            continue

        # Crossover prevention: reduce effective window if neighbours are close
        effective_window = window_ms
        if prev_time is not None:
            gap_to_prev = mark.time_ms - prev_time
            # Don't snap past the previous boundary
            if nearest <= prev_time:
                result.append(mark)
                continue
            # Reduce window if boundaries are very close
            effective_window = min(effective_window, gap_to_prev // 2)
        if next_time is not None:
            gap_to_next = next_time - mark.time_ms
            # Don't snap past the next boundary
            if nearest >= next_time:
                result.append(mark)
                continue
            effective_window = min(effective_window, gap_to_next // 2)

        if dist <= effective_window:
            new_mark = _copy.copy(mark)
            new_mark.time_ms = nearest
            result.append(new_mark)
            snapped += 1
        else:
            result.append(mark)

    if snapped:
        print(f"  L1 snap: {snapped}/{len(sections)} boundaries snapped to bars (window={window_ms}ms)")

    # Second pass: resolve duplicate timestamps (zero-length sections)
    # Keep unique times, absorb duplicates into preceding section
    seen: list = []
    for mark in result:
        if seen and seen[-1].time_ms == mark.time_ms:
            # Duplicate — skip (absorb shorter section into preceding one)
            _snap_logger.debug(
                "Absorbed duplicate boundary at %dms", mark.time_ms
            )
        else:
            seen.append(mark)
    result = seen

    # Third pass: minimum section duration guard (2000ms)
    _MIN_SECTION_MS = 2000
    merged = True
    while merged and len(result) > 1:
        merged = False
        new_result = [result[0]]
        for i in range(1, len(result)):
            gap = result[i].time_ms - new_result[-1].time_ms
            if gap < _MIN_SECTION_MS:
                # Absorb into preceding section (drop this boundary)
                _snap_logger.warning(
                    "Absorbing short section (%dms < %dms minimum) at boundary %dms",
                    gap, _MIN_SECTION_MS, result[i].time_ms,
                )
                merged = True
            else:
                new_result.append(result[i])
        result = new_result

    return result


def _deduplicate_events(
    events: dict,
    spectral_flux: "ValueCurve | None",
    energy_curves: dict,
    min_gap_ms: int = 50,
) -> dict:
    """Remove same-hit doublings from L4 event tracks.

    Aubio's Vamp wrapper ignores the minioi parameter, so multiple detections
    of the same transient (typically 6–46 ms apart) slip through.  This groups
    nearby marks into clusters and keeps whichever mark in each cluster sits at
    the highest spectral-flux (or energy) value — the same judgement a human
    engineer makes when looking at the waveform.

    min_gap_ms=50 ms eliminates doublings while preserving 32nd notes at any
    tempo ≥ 60 BPM (32nd note ≈ 63 ms at 60 BPM, 150 ms at 115 BPM).
    """
    import copy as _copy

    # Choose the best available curve for picking within a cluster
    flux = spectral_flux

    result: dict = {}
    total_before = total_removed = 0

    for stem, track in events.items():
        marks = sorted(track.marks, key=lambda m: m.time_ms)
        if not marks:
            result[stem] = track
            continue

        # Use stem energy or full_mix as fallback for peak-picking
        curve = energy_curves.get(stem) or flux
        values = curve.values if curve else None
        fps = curve.fps if curve else 1

        kept = []
        cluster = [marks[0]]

        def _peak_mark(cluster):
            """Return mark with highest curve value, or first if no curve."""
            if not values:
                return cluster[0]
            def score(m):
                f = max(0, min(len(values) - 1, int(m.time_ms * fps / 1000)))
                return values[f]
            return max(cluster, key=score)

        for mark in marks[1:]:
            if mark.time_ms - cluster[-1].time_ms <= min_gap_ms:
                cluster.append(mark)
            else:
                kept.append(_peak_mark(cluster))
                cluster = [mark]
        kept.append(_peak_mark(cluster))

        removed = len(marks) - len(kept)
        total_before += len(marks)
        total_removed += removed

        if removed:
            new_track = _copy.copy(track)
            new_track.marks = kept
            result[stem] = new_track
        else:
            result[stem] = track

    if total_removed:
        print(f"  L4 dedup: removed {total_removed}/{total_before} same-hit doublings "
              f"(min gap {min_gap_ms}ms)")
    return result


def _filter_events_by_energy(
    events: dict,
    energy_curves: dict,
    full_mix_curve,
    percentile: float = 40.0,
) -> dict:
    """Keep only onsets above the given energy percentile per stem.

    For each stem track in *events*, look up the matching energy curve
    (falling back to full_mix).  Compute the energy value at each onset's
    frame, then discard onsets below the *percentile*-th percentile.
    If fewer than 10 marks remain after filtering the track is kept as-is
    to avoid degenerate output.
    """
    import copy as _copy
    filtered: dict = {}
    total_before = total_after = 0

    for stem, track in events.items():
        curve = energy_curves.get(stem) or full_mix_curve
        if not curve or not curve.values or not track.marks:
            filtered[stem] = track
            continue

        values = curve.values
        n = len(values)
        fps = curve.fps

        energies = [
            values[max(0, min(n - 1, int(m.time_ms * fps / 1000)))]
            for m in track.marks
        ]

        sorted_e = sorted(energies)
        threshold_idx = int(len(sorted_e) * percentile / 100)
        threshold = sorted_e[max(0, threshold_idx - 1)]

        kept = [m for m, e in zip(track.marks, energies) if e >= threshold]
        total_before += len(track.marks)
        total_after += len(kept)

        if len(kept) < 10:
            # Degenerate result — keep original
            filtered[stem] = track
            total_after += len(track.marks) - len(kept)  # correct counter
            continue

        new_track = _copy.copy(track)
        new_track.marks = kept
        filtered[stem] = new_track

    removed = total_before - total_after
    if removed:
        print(f"  L4 energy filter: removed {removed}/{total_before} low-energy onsets "
              f"(bottom {percentile:.0f}%)")
    return filtered


def _label_energy_tiers(
    events: dict,
    energy_curves: dict,
    full_mix_curve,
) -> None:
    """Label non-drum event marks with energy tier: h (top third), m, or l.

    Drums are skipped — they already have kick/snare/hihat labels.
    Tiers are relative to each stem's own surviving mark distribution so
    a quiet stem and a loud stem both get a full h/m/l spread.
    """
    for stem, track in events.items():
        if stem == "drums" or not track or not track.marks:
            continue
        curve = energy_curves.get(stem) or full_mix_curve
        if not curve or not curve.values:
            continue

        values = curve.values
        n = len(values)
        fps = curve.fps

        energies = [
            values[max(0, min(n - 1, int(m.time_ms * fps / 1000)))]
            for m in track.marks
        ]

        # Rank-based assignment guarantees equal thirds regardless of value clustering
        ranked = sorted(range(len(energies)), key=lambda i: energies[i])
        n_marks = len(ranked)
        tiers = ["l"] * n_marks
        for rank, idx in enumerate(ranked):
            if rank >= 2 * n_marks // 3:
                tiers[idx] = "h"
            elif rank >= n_marks // 3:
                tiers[idx] = "m"
            # else stays "l"

        for mark, tier in zip(track.marks, tiers):
            mark.label = tier


def _label_beats(beats: "TimingTrack", bars: "TimingTrack") -> None:
    """Label each beat mark with its position within the bar (1, 2, 3, 4…).

    Mutates beat marks in-place.  Beats before the first bar or after the last
    bar are labelled by extrapolating the bar grid at the estimated beat interval.
    """
    if not beats or not beats.marks or not bars or not bars.marks:
        return

    bar_times = sorted(m.time_ms for m in bars.marks)
    beat_marks = beats.marks  # already sorted

    # Estimate beat interval from median inter-beat gap
    if len(beat_marks) >= 2:
        gaps_b = [beat_marks[i + 1].time_ms - beat_marks[i].time_ms
                  for i in range(len(beat_marks) - 1)]
        beat_interval = sorted(gaps_b)[len(gaps_b) // 2]
    else:
        beat_interval = 500

    # For each bar, find the beats that fall within it and label them 1-N
    for i, bar_start in enumerate(bar_times):
        bar_end = bar_times[i + 1] if i + 1 < len(bar_times) else bar_start + beat_interval * 8
        bar_beats = [m for m in beat_marks if bar_start <= m.time_ms < bar_end]
        for pos, mark in enumerate(bar_beats, 1):
            mark.label = str(pos)

    # Label beats before the first bar by counting back from bar position 1
    first_bar = bar_times[0]
    pre_beats = sorted((m for m in beat_marks if m.time_ms < first_bar),
                       key=lambda m: m.time_ms, reverse=True)
    for i, mark in enumerate(pre_beats):
        # Count backwards: if first bar beat is "1", beat before it is "4", etc.
        pos = ((-(i + 1)) % 4) or 4
        mark.label = str(pos)


def _derive_eighth_notes(beats: "TimingTrack") -> "list":
    """Derive eighth-note marks by inserting midpoints between consecutive beats.

    Each midpoint is placed at the exact halfway point between two adjacent beat
    marks.  The resulting track interleaves original beat positions (odd eighth
    notes: "1e", "2e"…) with midpoints (even: "1&", "2&"…).

    Returns a flat sorted list of TimingMark objects covering both on-beat and
    off-beat eighth note positions.
    """
    from src.analyzer.result import TimingMark
    import copy as _copy

    marks = beats.marks
    if len(marks) < 2:
        return []

    result = []
    for i, mark in enumerate(marks):
        # On-beat eighth note — copy the existing beat mark
        on = _copy.copy(mark)
        result.append(on)

        if i + 1 < len(marks):
            # Off-beat eighth note — midpoint between this beat and the next
            mid_ms = (mark.time_ms + marks[i + 1].time_ms) // 2
            off_label = None
            if mark.label:
                off_label = mark.label + "&"
            result.append(TimingMark(time_ms=mid_ms, confidence=mark.confidence,
                                     label=off_label))

    return result


def _select_beat_with_bpm_check(
    candidates: list,
    onset_times: list[int],
    estimated_bpm: float,
    duration_ms: int,
    tolerance: float = 0.20,
) -> "tuple[TimingTrack | None, list[TimingTrack]]":
    """Select best beat track plus the remaining (loser) candidates.

    After scoring all candidates by regularity + onset correlation, pick the
    highest-scoring one whose Hz is within *tolerance* (±20%) of estimated_bpm/60.
    If no candidate passes the check, return the highest-scoring one anyway so we
    always produce a beat track.

    Returns ``(winner, losers)`` where ``losers`` are the input candidates with
    the chosen winner removed (preserving input order). When the BPM-range
    fallback selects a non-rank-1 candidate, the loser list still excludes that
    chosen winner — so the agreement annotation downstream measures convergence
    relative to whatever we actually picked.
    """
    from src.analyzer.selector import rank_tracks

    ranked = rank_tracks(candidates, onset_times)
    if not ranked:
        return None, []

    def _losers(winner) -> list:
        return [c for c in candidates if c is not winner]

    if estimated_bpm < 20:
        # No reliable BPM estimate — just use best combined score
        winner = ranked[0]
        return winner, _losers(winner)

    expected_hz = estimated_bpm / 60.0
    duration_s = duration_ms / 1000.0

    for track in ranked:
        actual_hz = track.mark_count / duration_s if duration_s > 0 else 0
        ratio = actual_hz / expected_hz if expected_hz > 0 else 1.0
        # Accept within ±tolerance, or at 2× (double-time) or 0.5× (half-time) within tolerance
        for multiplier in (1.0, 2.0, 0.5):
            if abs(ratio / multiplier - 1.0) <= tolerance:
                if multiplier != 1.0:
                    print(f"  L3 BPM check: {track.algorithm_name} accepted at "
                          f"{actual_hz:.2f} Hz ({multiplier:.0f}× of {expected_hz:.2f} Hz expected)")
                return track, _losers(track)

    # No track passed — fall back to best combined score
    print(f"  L3 BPM check: no candidate within ±{tolerance:.0%} of {expected_hz:.2f} Hz — "
          f"using best-score fallback ({ranked[0].algorithm_name})")
    winner = ranked[0]
    return winner, _losers(winner)


def _print_dry_run(algos) -> None:
    level_map = {
        "bbc_energy": "L0/L5", "bbc_spectral_flux": "L5",
        "segmentino": "L1",
        "qm_bars": "L2", "librosa_bars": "L2", "madmom_downbeats": "L2",
        "qm_beats": "L3", "librosa_beats": "L3", "madmom_beats": "L3", "beatroot_beats": "L3",
        "aubio_onset": "L4", "librosa_onsets": "L4", "percussion_onsets": "L4",
        "chordino_chords": "L6", "qm_key": "L6",
    }
    by_level: dict[str, list[str]] = {}
    for algo in algos:
        base = algo.name.split(":")[0] if ":" in algo.name else algo.name
        level = level_map.get(base, "?")
        stem = algo.preferred_stem if algo.preferred_stem != "full_mix" else ""
        label = f"{base}({stem})" if stem else base
        by_level.setdefault(level, []).append(label)
    for level, names in sorted(by_level.items()):
        print(f"  {level}: {', '.join(names)}")
