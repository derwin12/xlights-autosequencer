"""Hierarchy orchestrator: zero-flag pipeline for hierarchical music analysis.

Produces a HierarchyResult (schema 2.0.0) with 7 levels (L0-L6) from a single MP3.
Auto-detects installed capabilities (vamp, madmom, demucs) and runs only the
~15 algorithms needed per level.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import librosa
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
        if (data.get("schema_version") == SCHEMA_VERSION
                and data.get("source_hash") == source_hash):
            from src.analyzer.result import HierarchyResult as _HR
            return _HR.from_dict(data)
    except Exception:
        pass
    return None


def _write_cache(audio_path: Path, result: "HierarchyResult") -> None:
    """Write HierarchyResult JSON to output folder."""
    json_path = _hierarchy_json_path(audio_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ── Algorithm list builder ────────────────────────────────────────────────────

def _make_stem_algo(algo_cls, stem: str):
    """Create an algorithm instance configured for a specific stem."""
    inst = algo_cls()
    inst.preferred_stem = stem
    # Encode stem in name so vamp_runner can route it correctly
    inst.name = f"{inst.name}:{stem}"
    return inst


def _build_algorithm_list(caps: dict[str, bool], stems_available: list[str]):
    """Build the ~15 algorithm instances needed per the level mapping (research.md R6)."""
    from src.analyzer.algorithms.librosa_beats import LibrosaBeatAlgorithm, LibrosaBarAlgorithm
    from src.analyzer.algorithms.librosa_onset import LibrosaOnsetAlgorithm  # name="librosa_onsets"

    algos = []

    # ── Always-available (librosa) ────────────────────────────────────────────
    algos += [
        LibrosaBarAlgorithm(),    # L2 bar candidate (name="librosa_bars")
        LibrosaBeatAlgorithm(),   # L3 beat candidate (name="librosa_beats")
        LibrosaOnsetAlgorithm(),  # L4 full_mix events (name="librosa_onsets")
    ]

    # ── Vamp algorithms (optional) ────────────────────────────────────────────
    if caps.get("vamp"):
        try:
            from src.analyzer.algorithms.vamp_beats import QMBarAlgorithm, QMBeatAlgorithm, BeatRootAlgorithm
            algos += [
                QMBarAlgorithm(),     # L2 bar candidate
                QMBeatAlgorithm(),    # L3 beat candidate
                BeatRootAlgorithm(),  # L3 beat candidate
            ]
        except Exception as exc:
            print(f"WARNING: vamp_beats unavailable: {exc}", file=sys.stderr)

        try:
            from src.analyzer.algorithms.vamp_bbc import BBCEnergyAlgorithm, BBCSpectralFluxAlgorithm
            # L0/L5: bbc_energy on full_mix (for impacts/gaps derivation)
            algos.append(BBCEnergyAlgorithm())
            # L5: bbc_spectral_flux on full_mix
            algos.append(BBCSpectralFluxAlgorithm())
            # L5: bbc_energy per stem (guitar included for solo detection + L4 filtering)
            energy_stems = [s for s in stems_available if s not in ("full_mix",)]
            for stem in energy_stems[:5]:  # drums, bass, vocals, guitar, other
                if stem in ("drums", "bass", "vocals", "guitar", "other"):
                    algos.append(_make_stem_algo(BBCEnergyAlgorithm, stem))
        except Exception as exc:
            print(f"WARNING: vamp_bbc unavailable: {exc}", file=sys.stderr)

        try:
            from src.analyzer.algorithms.vamp_segmentation import SegmentinoAlgorithm
            algos.append(SegmentinoAlgorithm())  # L1 sections
        except Exception as exc:
            print(f"WARNING: segmentino unavailable: {exc}", file=sys.stderr)

        try:
            from src.analyzer.algorithms.vamp_harmony import ChordinoAlgorithm
            # Force full_mix: Chordino's default preferred_stem="piano" is too sparse
            # for most genres. Full mix gives reliable chord detection.
            algos.append(_make_stem_algo(ChordinoAlgorithm, "full_mix"))  # L6 chords
        except Exception as exc:
            print(f"WARNING: chordino unavailable: {exc}", file=sys.stderr)

        try:
            from src.analyzer.algorithms.vamp_extra import QMKeyAlgorithm
            algos.append(QMKeyAlgorithm())  # L6 key
        except Exception as exc:
            print(f"WARNING: qm_key unavailable: {exc}", file=sys.stderr)

        try:
            from src.analyzer.algorithms.vamp_aubio import AubioOnsetAlgorithm
            # L4: per-stem onset detection
            for stem in stems_available:
                if stem != "full_mix":
                    algos.append(_make_stem_algo(AubioOnsetAlgorithm, stem))
        except Exception as exc:
            print(f"WARNING: aubio unavailable: {exc}", file=sys.stderr)

    # ── Madmom algorithms (optional) ─────────────────────────────────────────
    if caps.get("madmom"):
        try:
            from src.analyzer.algorithms.madmom_beat import MadmomBeatAlgorithm, MadmomDownbeatAlgorithm
            algos += [
                MadmomBeatAlgorithm(),     # L3 beat candidate
                MadmomDownbeatAlgorithm(), # L2 bar candidate
            ]
        except Exception as exc:
            print(f"WARNING: madmom unavailable: {exc}", file=sys.stderr)

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
) -> "HierarchyResult":
    """Run the full hierarchy analysis pipeline on a single MP3 file.

    Args:
        audio_path: Path to the source MP3 file.
        fresh: If True, ignore any cached result and re-run analysis.
        dry_run: If True, print what would run and return without executing.
        progress_callback: Optional callable(index, total, name, mark_count).

    Returns:
        HierarchyResult with all available hierarchy levels populated.
    """
    from src.analyzer.audio import load
    from src.analyzer.capabilities import detect_capabilities
    from src.analyzer.derived import derive_energy_drops, derive_energy_impacts, derive_gaps
    from src.analyzer.result import HierarchyResult, TimingMark, TimingTrack, ValueCurve
    from src.analyzer.runner import AnalysisRunner
    from src.analyzer.selector import select_best_bar_track, select_best_beat_track, rank_tracks

    src_path = Path(audio_path).resolve()

    # ── Stage 1: Detect capabilities ─────────────────────────────────────────
    caps = detect_capabilities()
    warnings: list[str] = []

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

    runner = AnalysisRunner(algos)
    analysis = runner.run(str(src_path), progress_callback=progress_callback, stems=stems)

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

    # L1: sections from segmentino
    sections: list["TimingMark"] = []
    seg_tracks = tracks_by_name.get("segmentino", [])
    if seg_tracks:
        sections = seg_tracks[0].marks
        print(f"L1 Structure: {len(sections)} sections "
              f"({_section_summary(sections)})")
    else:
        warnings.append("L1 Structure: skipped — segmentino not available (install Vamp plugin 'segmentino')")

    # L2: select best bar track
    bar_algo_names = {"qm_bars", "librosa_bars", "madmom_downbeats"}
    bar_candidates = [t for t in analysis.timing_tracks if t.algorithm_name in bar_algo_names]
    onset_times = _collect_onset_times(tracks_by_name)
    bars = select_best_bar_track(bar_candidates, onset_times)
    if bars:
        print(f"L2 Bars: {bars.mark_count} marks ({bars.algorithm_name}, "
              f"{bars.mark_count / (meta.duration_ms / 1000):.2f} Hz)")
        # Snap L1 section boundaries to nearest bar now that we have the bar track
        if sections:
            sections = _snap_sections_to_bars(sections, bars)
    else:
        warnings.append("L2 Bars: no bar track produced")

    # L3: select best beat track with BPM-range validation
    beat_algo_names = {"qm_beats", "librosa_beats", "madmom_beats", "beatroot_beats"}
    beat_candidates = [t for t in analysis.timing_tracks if t.algorithm_name in beat_algo_names]
    beats = _select_beat_with_bpm_check(beat_candidates, onset_times, estimated_bpm, meta.duration_ms)
    if beats:
        print(f"L3 Beats: {beats.mark_count} marks ({beats.algorithm_name}, "
              f"{beats.mark_count / (meta.duration_ms / 1000):.2f} Hz)")
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

    curve_summary = ", ".join(list(energy_curves.keys()) +
                               (["spectral_flux"] if spectral_flux else []))
    print(f"L5 Energy: {len(energy_curves)} curves ({curve_summary or 'none'})")

    # L6: harmony
    chords_tracks = tracks_by_name.get("chordino_chords", [])
    chords = chords_tracks[0] if chords_tracks else None

    key_tracks = tracks_by_name.get("qm_key", [])
    key_changes = key_tracks[0] if key_tracks else None

    if chords or key_changes:
        chord_count = chords.mark_count if chords else 0
        key_count = key_changes.mark_count if key_changes else 0
        print(f"L6 Harmony: {chord_count} chord changes, {key_count} key(s)")
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
    result = HierarchyResult(
        schema_version=SCHEMA_VERSION,
        source_file=str(src_path),
        source_hash=source_hash,
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
        interactions=interactions,
        solos=solos,
        essentia_features=essentia_features,
        stems_available=stems_available,
        capabilities=caps,
        algorithms_run=[a.name for a in algos],
        warnings=warnings,
    )

    # ── Stage 11: Validate mark placement ────────────────────────────────────
    from src.analyzer.validator import validate_hierarchy, format_validation_report
    result.validation = validate_hierarchy(result)
    print(format_validation_report(result.validation))

    # ── Stage 12: Write outputs ───────────────────────────────────────────────
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


def _snap_sections_to_bars(sections: list, bars: "TimingTrack") -> list:
    """Snap each section boundary to the nearest bar mark within the adaptive window.

    Uses the same adaptive window as the validator: half the median bar interval,
    clamped to 400–1200 ms.  Sections already on a bar boundary are unchanged.
    Returns a (possibly mutated) list of TimingMark objects.
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

    result = []
    snapped = 0
    for mark in sections:
        nearest = _nearest_in_sorted(mark.time_ms, bar_times)
        if nearest is not None and abs(nearest - mark.time_ms) <= window_ms and nearest != mark.time_ms:
            new_mark = _copy.copy(mark)
            new_mark.time_ms = nearest
            result.append(new_mark)
            snapped += 1
        else:
            result.append(mark)

    if snapped:
        print(f"  L1 snap: {snapped}/{len(sections)} boundaries snapped to bars (window={window_ms}ms)")
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
) -> "TimingTrack | None":
    """Select best beat track, falling back through candidates if BPM range check fails.

    After scoring all candidates by regularity + onset correlation, pick the
    highest-scoring one whose Hz is within *tolerance* (±20%) of estimated_bpm/60.
    If no candidate passes the check, return the highest-scoring one anyway so we
    always produce a beat track.
    """
    from src.analyzer.selector import rank_tracks

    ranked = rank_tracks(candidates, onset_times)
    if not ranked:
        return None

    if estimated_bpm < 20:
        # No reliable BPM estimate — just use best combined score
        return ranked[0]

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
                return track

    # No track passed — fall back to best combined score
    print(f"  L3 BPM check: no candidate within ±{tolerance:.0%} of {expected_hz:.2f} Hz — "
          f"using best-score fallback ({ranked[0].algorithm_name})")
    return ranked[0]


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
