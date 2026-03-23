"""CLI entry point for xlight-analyze."""
from __future__ import annotations

import errno
import json
import sys
import threading
import webbrowser
from pathlib import Path

import click

from src import export as export_mod
from src.analyzer.result import AnalysisResult


# ──────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────────

def _format_duration(ms: int) -> str:
    total_s = ms // 1000
    return f"{total_s // 60}:{total_s % 60:02d}"


def _print_summary_table(tracks, *, limit: int | None = None) -> None:
    sorted_tracks = sorted(tracks, key=lambda t: t.quality_score, reverse=True)
    if limit is not None:
        sorted_tracks = sorted_tracks[:limit]
    click.echo("\nTrack Summary (sorted by quality score):")
    click.echo(f"  {'SCORE':<6}  {'NAME':<20} {'TYPE':<12} {'STEM':<10} {'MARKS':>6}   AVG INTERVAL")
    for t in sorted_tracks:
        stem = getattr(t, "stem_source", "full_mix") or "full_mix"
        flag = "  ** HIGH DENSITY" if t.avg_interval_ms > 0 and t.avg_interval_ms < 200 else ""
        click.echo(
            f"  {t.quality_score:<6.2f}  {t.name:<20} {t.element_type:<12} "
            f"{stem:<10} {t.mark_count:>6}      {t.avg_interval_ms:>4} ms{flag}"
        )


# ──────────────────────────────────────────────────────────────────────────────
# Main CLI group
# ──────────────────────────────────────────────────────────────────────────────

@click.group()
def cli() -> None:
    """xlight-analyze — generate xLights timing tracks from audio."""


# ──────────────────────────────────────────────────────────────────────────────
# analyze command
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("analyze")
@click.argument("mp3_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", default=None, help="Output JSON path (default: <input>_analysis.json)")
@click.option(
    "--algorithms", default="all",
    help="Comma-separated algorithm names, or 'all'",
)
@click.option("--no-vamp", is_flag=True, default=False, help="Skip Vamp plugin algorithms")
@click.option("--no-madmom", is_flag=True, default=False, help="Skip madmom algorithms")
@click.option("--top", "top_n", default=None, type=int, help="Auto-export top N tracks")
@click.option(
    "--stems/--no-stems", "use_stems", default=False,
    help="Run stem separation before analysis (requires demucs)",
)
@click.option(
    "--phonemes/--no-phonemes", "use_phonemes", default=False,
    help="Run vocal phoneme analysis and write .xtiming file (implies --stems)",
)
@click.option(
    "--lyrics", "lyrics_path", default=None, type=click.Path(dir_okay=False),
    help="Lyrics text file for improved word alignment (requires --phonemes)",
)
@click.option(
    "--no-cache", "no_cache", is_flag=True, default=False,
    help="Re-run analysis even if a cached result exists for this file",
)
def analyze_cmd(
    mp3_file: str,
    output: str | None,
    algorithms: str,
    no_vamp: bool,
    no_madmom: bool,
    top_n: int | None,
    use_stems: bool,
    use_phonemes: bool,
    lyrics_path: str | None,
    no_cache: bool,
) -> None:
    """Run all analysis algorithms on MP3_FILE and write a JSON result."""
    from src.analyzer.runner import AnalysisRunner, default_algorithms
    from src.cache import AnalysisCache
    from src.library import Library, LibraryEntry
    import time

    audio_path = Path(mp3_file)

    # --phonemes implies --stems
    if use_phonemes:
        use_stems = True

    # Warn if --lyrics used without --phonemes
    if lyrics_path is not None and not use_phonemes:
        click.echo(
            "WARNING: --lyrics is ignored without --phonemes. "
            "Add --phonemes to enable phoneme analysis.",
            err=True,
        )

    # Determine output path
    if output is None:
        out_path = str(audio_path.parent / (audio_path.stem + "_analysis.json"))
    else:
        out_path = output

    # ── Cache hit check ───────────────────────────────────────────────────────
    cache = AnalysisCache(audio_path, Path(out_path))
    if not no_cache and cache.is_valid():
        result = cache.load()
        click.echo(f"Loading audio: {audio_path.name}")
        click.echo(
            f"Analysis cache: hit ({(result.source_hash or '')[:8]}) — skipping algorithms."
        )
        click.echo(f"Output: {out_path}")
        _print_summary_table(result.timing_tracks)
        return

    # ── Full analysis run ─────────────────────────────────────────────────────

    # Check output is writable
    try:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).touch()
    except OSError as exc:
        click.echo(f"ERROR: Cannot write to {out_path}: {exc}", err=True)
        sys.exit(3)

    # Build algorithm list
    algo_list = default_algorithms(
        include_vamp=not no_vamp,
        include_madmom=not no_madmom,
    )

    # Optional algorithm filter
    if algorithms.strip().lower() != "all":
        names = {n.strip() for n in algorithms.split(",")}
        algo_list = [a for a in algo_list if a.name in names]

    if no_vamp:
        click.echo("INFO: --no-vamp specified — Vamp algorithms skipped.", err=True)
    if no_madmom:
        click.echo("INFO: --no-madmom specified — madmom algorithms skipped.", err=True)

    total = len(algo_list)

    def progress(idx, total, name, mark_count):
        click.echo(f"  [{idx:>2}/{total}] {name:<35} ... done ({mark_count} marks)")

    # Quick load to show duration/BPM header before running
    try:
        from src.analyzer.audio import load
        import librosa, numpy as np
        audio, sr, meta = load(str(audio_path))
        try:
            tempo_arr, _ = librosa.beat.beat_track(y=audio, sr=sr, hop_length=512)
            bpm = float(np.atleast_1d(tempo_arr)[0])
        except Exception:
            bpm = 0.0
        click.echo(
            f"Loading audio: {audio_path.name} ({_format_duration(meta.duration_ms)}) | BPM: ~{bpm:.1f}"
        )
        click.echo("Analysis cache: miss — running algorithms...")
    except Exception as exc:
        click.echo(f"ERROR: Cannot load {mp3_file}: {exc}", err=True)
        sys.exit(1)

    # Stem separation (optional, requires demucs)
    stems = None
    if use_stems:
        try:
            from src.analyzer.stems import StemSeparator
            sep = StemSeparator()
            stems = sep.separate(audio_path)
        except Exception as exc:
            click.echo(
                f"WARNING: Stem separation failed ({exc}). Falling back to full-mix analysis.",
                err=True,
            )
            stems = None

    runner = AnalysisRunner(algo_list)

    try:
        result = runner.run(str(audio_path), progress_callback=progress, stems=stems)
    except Exception as exc:
        click.echo(f"ERROR: Analysis failed: {exc}", err=True)
        sys.exit(2)

    if not result.timing_tracks:
        click.echo("ERROR: All algorithms failed — no output written.", err=True)
        sys.exit(2)

    # Phoneme analysis (optional, requires whisperx)
    xtiming_path: str | None = None
    if use_phonemes:
        try:
            from src.analyzer.phonemes import PhonemeAnalyzer
            from src.analyzer.xtiming import XTimingWriter

            vocal_stem_path = str(audio_path)
            if stems is not None:
                stem_vocals = getattr(stems, "vocals", None)
                if stem_vocals and Path(stem_vocals).exists():
                    vocal_stem_path = stem_vocals

            click.echo("Phoneme analysis:")
            model_name = "base"
            click.echo(f"  → Transcribing vocals (whisper {model_name} model)...")

            analyzer = PhonemeAnalyzer(model_name=model_name)
            phoneme_result = analyzer.analyze(
                vocal_stem_path, str(audio_path), lyrics_path=lyrics_path
            )

            for warning in getattr(analyzer, "warnings", []):
                click.echo(f"  → Warning: {warning}")

            if phoneme_result is not None:
                word_count = len(phoneme_result.word_track.marks)
                phoneme_count = len(phoneme_result.phoneme_track.marks)
                xtiming_path = str(audio_path.parent / (audio_path.stem + ".xtiming"))
                click.echo(
                    f"  → Writing {audio_path.stem}.xtiming "
                    f"(3 layers: lyrics, {word_count} words, {phoneme_count} phonemes)"
                )
                XTimingWriter().write(phoneme_result, xtiming_path)
                result.phoneme_result = phoneme_result
            else:
                click.echo("  → Warning: No vocals detected in audio. Skipping phoneme analysis.")

        except RuntimeError as exc:
            click.echo(f"WARNING: Phoneme analysis failed: {exc}", err=True)
        except Exception as exc:
            click.echo(f"WARNING: Phoneme analysis failed: {exc}", err=True)

    try:
        cache.save(result)
    except OSError as exc:
        click.echo(f"ERROR: Cannot write output: {exc}", err=True)
        sys.exit(3)

    # ── Library registration ──────────────────────────────────────────────────
    try:
        lib_entry = LibraryEntry(
            source_hash=result.source_hash or "",
            source_file=str(audio_path.resolve()),
            filename=audio_path.name,
            analysis_path=str(Path(out_path).resolve()),
            duration_ms=result.duration_ms,
            estimated_tempo_bpm=result.estimated_tempo_bpm,
            track_count=len(result.timing_tracks),
            stem_separation=result.stem_separation,
            analyzed_at=int(time.time() * 1000),
        )
        Library().upsert(lib_entry)
    except Exception:
        pass  # library registration is best-effort; never block analysis output

    if xtiming_path:
        click.echo(f"\nAnalysis complete: {out_path} + {Path(xtiming_path).name}")
    else:
        click.echo(f"\nAnalysis complete. Output: {out_path}")
    _print_summary_table(result.timing_tracks)

    if top_n is not None:
        click.echo(f"\nAuto-selecting top {top_n} tracks by quality score...")
        top_path = str(audio_path.parent / f"{audio_path.stem}_top{top_n}.json")
        sorted_tracks = sorted(
            result.timing_tracks, key=lambda t: t.quality_score, reverse=True
        )[:top_n]
        top_result = AnalysisResult(
            schema_version=result.schema_version,
            source_file=result.source_file,
            filename=result.filename,
            duration_ms=result.duration_ms,
            sample_rate=result.sample_rate,
            estimated_tempo_bpm=result.estimated_tempo_bpm,
            run_timestamp=result.run_timestamp,
            algorithms=[
                a for a in result.algorithms
                if a.name in {t.algorithm_name for t in sorted_tracks}
            ],
            timing_tracks=sorted_tracks,
        )
        export_mod.write(top_result, top_path)
        click.echo(f"Output: {top_path}")
    else:
        click.echo("\nUse --top N or 'xlight-analyze export' to select tracks.")


# ──────────────────────────────────────────────────────────────────────────────
# summary command
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("summary")
@click.argument("analysis_json", type=click.Path(exists=True, dir_okay=False))
@click.option("--top", "top_n", default=None, type=int, help="Show only top N tracks")
def summary_cmd(analysis_json: str, top_n: int | None) -> None:
    """Print the scored summary table from an existing analysis JSON."""
    try:
        result = export_mod.read(analysis_json)
    except Exception as exc:
        click.echo(f"ERROR: Cannot read {analysis_json}: {exc}", err=True)
        sys.exit(1)

    duration_str = _format_duration(result.duration_ms)
    click.echo(
        f"Source: {result.filename} ({duration_str}) | BPM: {result.estimated_tempo_bpm} "
        f"| Analyzed: {result.run_timestamp} | {len(result.timing_tracks)} tracks"
    )

    pr = result.phoneme_result
    if pr is not None:
        word_count = len(pr.word_track.marks)
        phoneme_count = len(pr.phoneme_track.marks)
        lang = pr.language
        model = pr.model_name
        click.echo(
            f"Phonemes: {word_count} words | {phoneme_count} phonemes "
            f"| Language: {lang} | Model: {model}"
        )

    _print_summary_table(result.timing_tracks, limit=top_n)


# ──────────────────────────────────────────────────────────────────────────────
# export command
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("export")
@click.argument("analysis_json", type=click.Path(exists=True, dir_okay=False))
@click.option("--select", "select_names", default=None, help="Comma-separated track names")
@click.option("--top", "top_n", default=None, type=int, help="Top N tracks by quality score")
@click.option("--output", default=None, help="Output path (default: <input>_selected.json)")
def export_cmd(
    analysis_json: str,
    select_names: str | None,
    top_n: int | None,
    output: str | None,
) -> None:
    """Filter an existing analysis to a subset of tracks and write a new JSON."""
    if select_names is None and top_n is None:
        click.echo("ERROR: Provide --select <names> or --top <N>.", err=True)
        sys.exit(5)

    try:
        result = export_mod.read(analysis_json)
    except Exception as exc:
        click.echo(f"ERROR: Cannot read {analysis_json}: {exc}", err=True)
        sys.exit(1)

    if top_n is not None:
        selected = sorted(
            result.timing_tracks, key=lambda t: t.quality_score, reverse=True
        )[:top_n]
        label = f"top {top_n}"
    else:
        names = {n.strip() for n in select_names.split(",")}
        track_map = {t.name: t for t in result.timing_tracks}
        missing = names - track_map.keys()
        if missing:
            click.echo(
                f"ERROR: Track(s) not found: {', '.join(sorted(missing))}. "
                f"Available: {', '.join(sorted(track_map.keys()))}",
                err=True,
            )
            sys.exit(4)
        selected = [track_map[n] for n in names if n in track_map]
        label = f"selected {len(selected)}"

    in_path = Path(analysis_json)
    out_path = output or str(in_path.parent / (in_path.stem.replace("_analysis", "") + "_selected.json"))

    filtered = AnalysisResult(
        schema_version=result.schema_version,
        source_file=result.source_file,
        filename=result.filename,
        duration_ms=result.duration_ms,
        sample_rate=result.sample_rate,
        estimated_tempo_bpm=result.estimated_tempo_bpm,
        run_timestamp=result.run_timestamp,
        algorithms=[
            a for a in result.algorithms
            if a.name in {t.algorithm_name for t in selected}
        ],
        timing_tracks=selected,
    )

    try:
        export_mod.write(filtered, out_path)
    except OSError as exc:
        click.echo(f"ERROR: Cannot write output: {exc}", err=True)
        sys.exit(3)

    click.echo(
        f"Exporting {label} of {len(result.timing_tracks)} tracks from {analysis_json}"
    )
    _print_summary_table(selected)
    click.echo(f"\nOutput: {out_path}")


# ──────────────────────────────────────────────────────────────────────────────
# review command
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("review")
@click.argument("audio_or_json", required=False, default=None, type=click.Path(dir_okay=False))
def review_cmd(audio_or_json: str | None) -> None:
    """Launch the track review UI in the default browser.

    AUDIO_OR_JSON can be a previously generated analysis JSON, an audio file
    path (resolved via the song library), or omitted to open the library home
    page.
    """
    from src.review.server import create_app

    if audio_or_json is None:
        app = create_app()
        url = "http://127.0.0.1:5173/"
        click.echo(f"Starting review UI at {url}")
        click.echo("Press Ctrl-C to stop.")
        threading.Timer(0.5, webbrowser.open, args=[url]).start()
        try:
            app.run(host="127.0.0.1", port=5173, use_reloader=False, debug=False)
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                click.echo(
                    "ERROR: Port 5173 is already in use.\n"
                    "Kill the process using that port and try again.",
                    err=True,
                )
                sys.exit(5)
            raise
        return

    given_path = Path(audio_or_json)

    # ── Audio file path: look up via library ──────────────────────────────────
    if given_path.suffix.lower() != ".json":
        import hashlib
        from src.library import Library
        if not given_path.exists():
            click.echo(f"ERROR: File not found: {audio_or_json}", err=True)
            sys.exit(4)
        h = hashlib.md5()
        with open(given_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        md5 = h.hexdigest()
        entry = Library().find_by_hash(md5)
        if entry is None:
            click.echo(
                f"ERROR: No cached analysis found for {given_path.name}.\n"
                f"Run 'xlight-analyze analyze {audio_or_json}' first.",
                err=True,
            )
            sys.exit(4)
        analysis_json_path = entry.analysis_path
        audio_path_str = entry.source_file
    else:
        # ── JSON path: existing behaviour ─────────────────────────────────────
        analysis_path = given_path
        if not analysis_path.exists():
            click.echo(f"ERROR: Analysis file not found: {audio_or_json}", err=True)
            sys.exit(4)
        try:
            with open(analysis_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            click.echo(f"ERROR: Cannot read {audio_or_json}: {exc}", err=True)
            sys.exit(4)
        audio_path_str = data.get("source_file", "")
        if not audio_path_str or not Path(audio_path_str).exists():
            click.echo(
                f"ERROR: Audio file not found: {audio_path_str!r}\n"
                "The analysis JSON's 'source_file' path does not exist on this machine.",
                err=True,
            )
            sys.exit(3)
        analysis_json_path = str(analysis_path.resolve())

    app = create_app(analysis_json_path, audio_path_str)

    url = "http://127.0.0.1:5173/"
    click.echo(f"Starting review UI at {url}")
    click.echo("Press Ctrl-C to stop.")

    threading.Timer(0.5, webbrowser.open, args=[url]).start()

    try:
        app.run(host="127.0.0.1", port=5173, use_reloader=False, debug=False)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            click.echo(
                "ERROR: Port 5173 is already in use.\n"
                "Kill the process using that port and try again.",
                err=True,
            )
            sys.exit(5)
        raise


def main() -> None:
    cli()
