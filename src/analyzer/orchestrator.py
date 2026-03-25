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
            # L5: bbc_energy per additional stem
            energy_stems = [s for s in stems_available if s not in ("full_mix",)]
            for stem in energy_stems[:4]:  # drums, bass, vocals, other
                if stem in ("drums", "bass", "vocals", "other"):
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
    from src.analyzer.result import HierarchyResult, TimingMark, ValueCurve
    from src.analyzer.runner import AnalysisRunner
    from src.analyzer.selector import select_best_bar_track, select_best_beat_track

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
               f"demucs {'✓' if caps['demucs'] else '✗'}")
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
    else:
        warnings.append("L2 Bars: no bar track produced")

    # L3: select best beat track
    beat_algo_names = {"qm_beats", "librosa_beats", "madmom_beats", "beatroot_beats"}
    beat_candidates = [t for t in analysis.timing_tracks if t.algorithm_name in beat_algo_names]
    beats = select_best_beat_track(beat_candidates, onset_times)
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
        events=events,
        energy_curves=energy_curves,
        spectral_flux=spectral_flux,
        chords=chords,
        key_changes=key_changes,
        interactions=interactions,
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

    _add_mark_layer(root, "beats", result.beats)
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
        if mark.duration_ms:
            end = start + mark.duration_ms
        elif i + 1 < len(marks):
            end = marks[i + 1].time_ms
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
    for name in ("aubio_onset", "librosa_onsets", "qm_onsets_complex"):
        tracks = tracks_by_name.get(name, [])
        if tracks:
            return [m.time_ms for m in tracks[0].marks]
    return []


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
