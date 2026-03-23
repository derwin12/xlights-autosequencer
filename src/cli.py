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
        bd = getattr(t, "score_breakdown", None)
        skip_note = ""
        if bd and bd.skipped_as_duplicate and bd.duplicate_of:
            skip_note = f"  [SKIPPED: near-identical to {bd.duplicate_of}]"
        flag = "  ** HIGH DENSITY" if t.avg_interval_ms > 0 and t.avg_interval_ms < 200 else ""
        click.echo(
            f"  {t.quality_score:<6.2f}  {t.name:<20} {t.element_type:<12} "
            f"{stem:<10} {t.mark_count:>6}      {t.avg_interval_ms:>4} ms{flag}{skip_note}"
        )


def _print_breakdown(tracks) -> None:
    """Print per-criterion score breakdowns for each track."""
    sorted_tracks = sorted(tracks, key=lambda t: t.quality_score, reverse=True)
    for t in sorted_tracks:
        bd = getattr(t, "score_breakdown", None)
        if bd is None:
            click.echo(f"\nTrack: {t.name} — no breakdown available")
            continue
        thresh_status = "PASS" if bd.passed_thresholds else f"FAIL ({', '.join(bd.threshold_failures)})"
        if bd.skipped_as_duplicate and bd.duplicate_of:
            skip_pct = ""
            click.echo(f"\nTrack: {t.name} (category: {bd.category})")
            click.echo(f"  Score: {bd.overall_score:.4f} | Thresholds: {thresh_status}")
            click.echo(f"  SKIPPED: near-identical to {bd.duplicate_of}")
        else:
            click.echo(f"\nTrack: {t.name} (category: {bd.category})")
            click.echo(f"  Score: {bd.overall_score:.4f} | Thresholds: {thresh_status}")
            for crit in bd.criteria:
                click.echo(
                    f"  {crit.name:<12} {crit.score:.2f}  "
                    f"({crit.measured_value:.3f}, target {crit.target_min:.2f}\u2013{crit.target_max:.2f}, "
                    f"weight {crit.weight:.2f}, contribution {crit.contribution:.4f})"
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
    "--phoneme-model", "phoneme_model", default="base",
    type=click.Choice(["tiny", "base", "small", "medium", "large-v2"], case_sensitive=False),
    help="Whisper model size for phoneme transcription (larger = more accurate, slower)",
    show_default=True,
)
@click.option(
    "--structure/--no-structure", "use_structure", default=False,
    help="Detect song structure (intro/verse/chorus/bridge/outro) using All-in-One (allin1)",
)
@click.option(
    "--no-cache", "no_cache", is_flag=True, default=False,
    help="Re-run analysis even if a cached result exists for this file",
)
@click.option(
    "--scoring-config", "scoring_config_path", default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a TOML scoring configuration file",
)
@click.option(
    "--scoring-profile", "scoring_profile_name", default=None,
    help="Name of a saved scoring profile",
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
    phoneme_model: str,
    use_structure: bool,
    no_cache: bool,
    scoring_config_path: str | None,
    scoring_profile_name: str | None,
) -> None:
    """Run all analysis algorithms on MP3_FILE and write a JSON result."""
    from src.analyzer.runner import AnalysisRunner, default_algorithms
    from src.analyzer.scorer import score_all_tracks
    from src.analyzer.scoring_config import ScoringConfig, load_profile
    from src.cache import AnalysisCache
    from src.library import Library, LibraryEntry
    import time

    # Load scoring configuration
    if scoring_config_path and scoring_profile_name:
        click.echo("ERROR: Cannot use both --scoring-config and --scoring-profile", err=True)
        sys.exit(6)

    scoring_config: ScoringConfig | None = None
    if scoring_config_path:
        try:
            scoring_config = ScoringConfig.from_toml(Path(scoring_config_path))
        except (ValueError, Exception) as exc:
            click.echo(f"ERROR: Invalid scoring config: {exc}", err=True)
            sys.exit(6)
    elif scoring_profile_name:
        try:
            scoring_config = load_profile(scoring_profile_name)
        except FileNotFoundError as exc:
            click.echo(f"ERROR: {exc}", err=True)
            sys.exit(7)
        except (ValueError, Exception) as exc:
            click.echo(f"ERROR: Invalid scoring profile: {exc}", err=True)
            sys.exit(6)

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
    result = None
    from_cache = False
    if not no_cache and cache.is_valid():
        result = cache.load()
        from_cache = True
        click.echo(f"Loading audio: {audio_path.name}")
        click.echo(
            f"Analysis cache: hit ({(result.source_hash or '')[:8]}) — skipping algorithms."
        )
        if not (use_phonemes and result.phoneme_result is None):
            from src.analyzer.scorer import score_all_tracks
            from src.analyzer.scoring_config import ScoringConfig, load_profile
            score_all_tracks(result.timing_tracks, result.duration_ms, scoring_config)
            click.echo(f"Output: {out_path}")
            _print_summary_table(result.timing_tracks)
            return
        click.echo("Phoneme data missing from cache — running phoneme analysis...")

    # ── Full analysis run ─────────────────────────────────────────────────────

    # Check output is writable
    try:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).touch()
    except OSError as exc:
        click.echo(f"ERROR: Cannot write to {out_path}: {exc}", err=True)
        sys.exit(3)

    stems = None
    if not from_cache:
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

        runner = AnalysisRunner(algo_list)

        try:
            result = runner.run(str(audio_path), progress_callback=progress, stems=stems)
        except Exception as exc:
            click.echo(f"ERROR: Analysis failed: {exc}", err=True)
            sys.exit(2)

        if not result.timing_tracks:
            click.echo("ERROR: All algorithms failed — no output written.", err=True)
            sys.exit(2)

    # Apply category-aware scoring with breakdowns
    score_all_tracks(result.timing_tracks, result.duration_ms, scoring_config)

    # Phoneme analysis (optional, requires whisperx)
    xtiming_path: str | None = None
    if use_phonemes:
        try:
            from src.analyzer.phonemes import PhonemeAnalyzer
            from src.analyzer.xtiming import XTimingWriter

            vocal_stem_path = str(audio_path)
            from src.analyzer.stems import StemCache
            vocals_file = StemCache(audio_path).stem_dir / "vocals.mp3"
            if vocals_file.exists():
                vocal_stem_path = str(vocals_file)

            click.echo("Phoneme analysis:")
            click.echo(f"  → Transcribing vocals (whisper {phoneme_model} model)...")

            analyzer = PhonemeAnalyzer(model_name=phoneme_model)
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

                # Write lyrics file if auto-transcribed and file not already present
                if phoneme_result.word_track.lyrics_source == "auto" and lyrics_path is None:
                    lyrics_out = audio_path.parent / (audio_path.stem + ".lyrics.txt")
                    if not lyrics_out.exists():
                        marks = phoneme_result.word_track.marks
                        lines: list[str] = []
                        current_line: list[str] = []
                        for i, wm in enumerate(marks):
                            current_line.append(wm.label)
                            if i + 1 < len(marks) and marks[i + 1].start_ms - wm.end_ms > 500:
                                lines.append(" ".join(current_line))
                                current_line = []
                        if current_line:
                            lines.append(" ".join(current_line))
                        lyrics_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
                        click.echo(
                            f"  → Wrote {lyrics_out.name} — edit and rerun with "
                            f"--phonemes --lyrics {lyrics_out.name}"
                        )
                    else:
                        click.echo(f"  → {lyrics_out.name} already exists — not overwritten.")
            else:
                click.echo("  → Warning: No vocals detected in audio. Skipping phoneme analysis.")

        except RuntimeError as exc:
            click.echo(f"WARNING: Phoneme analysis failed: {exc}", err=True)
        except Exception as exc:
            click.echo(f"WARNING: Phoneme analysis failed: {exc}", err=True)

    # Structure analysis (optional, requires allin1)
    if use_structure:
        try:
            from src.analyzer.structure import StructureAnalyzer
            click.echo("Structure analysis:")
            click.echo("  → Detecting segments (intro/verse/chorus/bridge/outro)...")
            song_structure = StructureAnalyzer().analyze(str(audio_path))
            if song_structure.segments:
                result.song_structure = song_structure
                labels = [s.label for s in song_structure.segments]
                click.echo(f"  → Found {len(labels)} segments: {', '.join(labels)}")
            else:
                click.echo("  → Warning: No segments detected.")
        except RuntimeError as exc:
            click.echo(f"WARNING: Structure analysis failed: {exc}", err=True)
        except Exception as exc:
            click.echo(f"WARNING: Structure analysis failed: {exc}", err=True)

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
        click.echo(f"\nAuto-selecting top {top_n} tracks by quality score (with diversity filter)...")
        top_path = str(audio_path.parent / f"{audio_path.stem}_top{top_n}.json")

        from src.analyzer.diversity import DiversityFilter
        cfg = scoring_config or __import__("src.analyzer.scoring_config", fromlist=["ScoringConfig"]).ScoringConfig.default()
        flt = DiversityFilter(
            tolerance_ms=cfg.diversity_tolerance_ms,
            threshold=cfg.diversity_threshold,
        )
        selected_tracks, skipped_tracks = flt.filter(result.timing_tracks, n=top_n)

        for t in skipped_tracks:
            bd = t.score_breakdown
            if bd and bd.duplicate_of:
                click.echo(f"  SKIPPED {t.name}: near-identical to {bd.duplicate_of}")

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
                if a.name in {t.algorithm_name for t in selected_tracks}
            ],
            timing_tracks=selected_tracks,
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
@click.option("--breakdown", "show_breakdown", is_flag=True, default=False,
              help="Show per-criterion score breakdown for each track")
def summary_cmd(analysis_json: str, top_n: int | None, show_breakdown: bool) -> None:
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

    tracks = result.timing_tracks
    if top_n is not None:
        tracks = sorted(tracks, key=lambda t: t.quality_score, reverse=True)[:top_n]

    _print_summary_table(tracks)

    if show_breakdown:
        _print_breakdown(tracks)


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


# ──────────────────────────────────────────────────────────────────────────────
# scoring subcommand group
# ──────────────────────────────────────────────────────────────────────────────

@cli.group("scoring")
def scoring_cmd() -> None:
    """Manage scoring configurations and profiles."""


@scoring_cmd.command("list")
def scoring_list_cmd() -> None:
    """List all available scoring profiles (project-local and user-global)."""
    from src.analyzer.scoring_config import list_profiles

    profiles = list_profiles()
    if not profiles:
        click.echo("No scoring profiles found.")
        click.echo("Use 'xlight-analyze scoring save <name> --from <config.toml>' to create one.")
        click.echo("Use 'xlight-analyze scoring defaults' to see the default configuration.")
        return

    click.echo("Scoring Profiles:")
    click.echo(f"  {'NAME':<20} {'SOURCE':<10}")
    for p in profiles:
        click.echo(f"  {p['name']:<20} {p['source']:<10}")
    click.echo("\n  (default)            built-in     Standard scoring weights")


@scoring_cmd.command("show")
@click.argument("name")
def scoring_show_cmd(name: str) -> None:
    """Display a scoring profile's configuration."""
    from src.analyzer.scoring_config import get_profile_path, ScoringConfig

    path = get_profile_path(name)
    if path is None:
        click.echo(f"ERROR: Profile '{name}' not found.", err=True)
        sys.exit(7)

    click.echo(f"Profile: {name} ({path})")
    click.echo(path.read_text(encoding="utf-8"))


@scoring_cmd.command("save")
@click.argument("name")
@click.option("--from", "source_path", required=True,
              type=click.Path(exists=True, dir_okay=False),
              help="Path to the TOML config file to save as a profile")
@click.option("--scope", default="project",
              type=click.Choice(["project", "user"], case_sensitive=False),
              help="Save to project-local (.scoring/) or user-global (~/.config/xlight/scoring/)")
def scoring_save_cmd(name: str, source_path: str, scope: str) -> None:
    """Save a TOML config file as a named scoring profile."""
    from src.analyzer.scoring_config import save_profile, ScoringConfig

    # Validate the config first
    try:
        ScoringConfig.from_toml(Path(source_path))
    except (ValueError, Exception) as exc:
        click.echo(f"ERROR: Invalid scoring config: {exc}", err=True)
        sys.exit(6)

    dest = save_profile(name, Path(source_path), scope=scope)
    click.echo(f"Saved profile '{name}' to {dest}")


@scoring_cmd.command("defaults")
def scoring_defaults_cmd() -> None:
    """Print the built-in default scoring configuration as TOML."""
    from src.analyzer.scoring_config import generate_default_toml

    click.echo(generate_default_toml(), nl=False)


# ──────────────────────────────────────────────────────────────────────────────
# sweep command
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("sweep")
@click.argument("audio_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--config", "config_path", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Path to sweep config JSON")
@click.option("--output", default=None, help="Output report JSON path")
@click.option("--yes", "skip_confirm", is_flag=True, default=False,
              help="Skip confirmation prompt for large sweeps")
def sweep_cmd(
    audio_file: str,
    config_path: str,
    output: str | None,
    skip_confirm: bool,
) -> None:
    """Run a parameter sweep for one Vamp algorithm against AUDIO_FILE."""
    from src.analyzer.sweep import SweepConfig, SweepRunner, build_algorithm_registry
    from src.analyzer.vamp_params import VampParamDiscovery, PluginNotFoundError

    # Load config
    try:
        config = SweepConfig.from_file(config_path)
    except (KeyError, ValueError, OSError) as exc:
        click.echo(f"ERROR: Invalid sweep config: {exc}", err=True)
        sys.exit(2)

    # Validate parameters if possible
    registry = build_algorithm_registry()
    algo_cls = registry.get(config.algorithm)
    if algo_cls is None:
        click.echo(
            f"ERROR: Algorithm '{config.algorithm}' not found. "
            f"Available Vamp algorithms: {sorted(registry)}",
            err=True,
        )
        sys.exit(2)

    plugin_key = getattr(algo_cls, "plugin_key", None)
    if plugin_key and (config.sweep_params or config.fixed_params):
        try:
            discovery = VampParamDiscovery()
            errors = config.validate(plugin_key, discovery)
            if errors:
                click.echo("ERROR: Sweep config validation failed:", err=True)
                for e in errors:
                    click.echo(f"  - {e}", err=True)
                sys.exit(2)
        except PluginNotFoundError:
            click.echo(
                f"INFO: Plugin '{plugin_key}' not installed — skipping parameter validation.",
                err=True,
            )

    # Determine output path
    audio_path = Path(audio_file)
    if output is None:
        output = str(audio_path.parent / f"{audio_path.stem}_sweep_{config.algorithm}.json")

    # Stem separation (if requested)
    stems = None
    default_stem = getattr(algo_cls, "preferred_stem", "full_mix")
    if config.stems and any(s != "full_mix" for s in config.stems):
        try:
            from src.analyzer.stems import StemSeparator
            click.echo("Stem separation: running (or loading from cache)...")
            stems = StemSeparator().separate(audio_path)
            click.echo("Stem separation: ready.")
        except Exception as exc:
            click.echo(
                f"WARNING: Stem separation failed ({exc}). "
                "Proceeding with full_mix only.",
                err=True,
            )
            config = SweepConfig(
                algorithm=config.algorithm,
                stems=[],
                sweep_params=config.sweep_params,
                fixed_params=config.fixed_params,
            )

    # Confirm permutation count
    n = config.permutation_count(default_stem=default_stem)
    if n > 20 and not skip_confirm:
        click.echo(f"Sweep will run {n} permutations. Proceed? [y/N]: ", nl=False)
        answer = click.getchar()
        click.echo(answer)
        if answer.lower() != "y":
            click.echo("Cancelled.")
            sys.exit(130)

    click.echo(f"Running sweep: {n} permutations of '{config.algorithm}'")

    def progress(idx, total, stem, params, mark_count, score):
        param_str = ", ".join(f"{k}={v}" for k, v in params.items())
        click.echo(
            f"  [{idx:>3}/{total}] stem={stem}, {param_str}"
            f" ... done ({mark_count} marks, score: {score:.2f})"
        )

    runner = SweepRunner(registry)
    try:
        report = runner.run(audio_file, config, stems, progress_callback=progress)
    except Exception as exc:
        click.echo(f"ERROR: Sweep failed: {exc}", err=True)
        sys.exit(2)

    try:
        report.write(output)
    except OSError as exc:
        click.echo(f"ERROR: Cannot write report: {exc}", err=True)
        sys.exit(3)

    stem_info = f"{len(report.stems_tested)} stem(s)" if len(report.stems_tested) > 1 else report.stems_tested[0] if report.stems_tested else "full_mix"
    click.echo(f"\nSweep complete: {n} permutations ({stem_info})\n")
    click.echo(f"  {'RANK':<5} {'SCORE':<7} {'MARKS':<7} {'AVG INTERVAL':<14} {'STEM':<12} PARAMETERS")
    for r in report.results[:10]:
        param_str = ", ".join(f"{k}={v}" for k, v in r.parameters.items())
        click.echo(
            f"  {r.rank:<5} {r.quality_score:<7.2f} {r.mark_count:<7} "
            f"{r.avg_interval_ms:<14} {r.stem:<12} {param_str}"
        )
    if len(report.results) > 10:
        click.echo(f"  ... ({len(report.results) - 10} more in report JSON)")
    click.echo(f"\nReport: {output}")
    click.echo("Use 'sweep-save' to persist the winning config (stem + parameters).")


# ──────────────────────────────────────────────────────────────────────────────
# params command
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("params")
@click.argument("plugin_key")
@click.option(
    "--suggest-steps", "suggest_steps", default=None, type=int,
    help="Also print N evenly-spaced candidate values for each numeric parameter",
)
def params_cmd(plugin_key: str, suggest_steps: int | None) -> None:
    """List all tunable parameters for an installed Vamp plugin."""
    from src.analyzer.vamp_params import VampParamDiscovery, PluginNotFoundError

    discovery = VampParamDiscovery()
    try:
        descriptors = discovery.list_params(plugin_key)
    except PluginNotFoundError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    if not descriptors:
        click.echo(f"Plugin '{plugin_key}' has no tunable parameters.")
        return

    click.echo(f"\nPlugin: {plugin_key}\n")
    click.echo(f"  {'PARAM':<16} {'TYPE':<10} {'RANGE':<22} {'DEFAULT':<10} DESCRIPTION")
    for d in descriptors:
        if d.value_names:
            type_str = "enum"
            range_str = f"0–{len(d.value_names) - 1}"
        elif d.is_quantized:
            type_str = "int"
            range_str = f"{d.min_value:.4g}–{d.max_value:.4g}"
        else:
            type_str = "float"
            range_str = f"{d.min_value:.4g}–{d.max_value:.4g}"
        default_str = f"{d.default_value:.4g}"
        click.echo(
            f"  {d.identifier:<16} {type_str:<10} {range_str:<22} {default_str:<10} {d.description or d.name}"
        )
        if d.value_names:
            labels = "  ".join(f"{i}={v}" for i, v in enumerate(d.value_names))
            click.echo(f"  {'':<16}   ({labels})")
        if suggest_steps is not None:
            try:
                vals = discovery.suggest_values(d, steps=suggest_steps)
                click.echo(f"  {'':<16}   Suggested: {[round(v, 4) for v in vals]}")
            except ValueError:
                pass

    click.echo(
        "\nUse these keys in your sweep config's \"sweep\" or \"fixed\" sections."
    )


# ──────────────────────────────────────────────────────────────────────────────
# sweep-suggest command
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("sweep-suggest")
@click.argument("plugin_key")
@click.argument("param_name")
@click.option("--steps", default=5, show_default=True, help="Number of evenly-spaced values")
def sweep_suggest_cmd(plugin_key: str, param_name: str, steps: int) -> None:
    """Print N evenly-spaced candidate values for a numeric Vamp parameter."""
    from src.analyzer.vamp_params import VampParamDiscovery, PluginNotFoundError

    discovery = VampParamDiscovery()
    try:
        descriptors = {d.identifier: d for d in discovery.list_params(plugin_key)}
    except PluginNotFoundError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    if param_name not in descriptors:
        click.echo(
            f"ERROR: Parameter '{param_name}' not found in plugin '{plugin_key}'.\n"
            f"Available: {', '.join(sorted(descriptors))}",
            err=True,
        )
        sys.exit(1)

    desc = descriptors[param_name]
    try:
        vals = discovery.suggest_values(desc, steps=steps)
    except ValueError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(2)

    rounded = [round(v, 4) for v in vals]
    click.echo(
        f"Suggested values for '{param_name}' "
        f"(range {desc.min_value:.4g}–{desc.max_value:.4g}, default {desc.default_value:.4g}):"
    )
    click.echo(f"  {rounded}")
    click.echo(f'\nAdd to your sweep config:\n  "{param_name}": {rounded}')


# ──────────────────────────────────────────────────────────────────────────────
# sweep-save command
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("sweep-save")
@click.argument("report_json", type=click.Path(exists=True, dir_okay=False))
@click.option("--name", required=True, help="Name for the saved config")
@click.option("--rank", "rank", default=1, show_default=True, type=int,
              help="Rank of the result to save (1 = best)")
def sweep_save_cmd(report_json: str, name: str, rank: int) -> None:
    """Save the ranked sweep result as a named config for future use."""
    from src.analyzer.sweep import SweepReport, SavedConfig

    try:
        report = SweepReport.read(report_json)
    except Exception as exc:
        click.echo(f"ERROR: Cannot read report: {exc}", err=True)
        sys.exit(1)

    try:
        cfg = SavedConfig.from_report(report, rank=rank, name=name)
    except ValueError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(2)

    saved_path = cfg.save()
    click.echo(
        f"Saved config '{name}' (rank {rank}): "
        f"stem={cfg.stem}, algorithm={cfg.algorithm}"
    )
    click.echo(f"  Parameters: {cfg.parameters}")
    click.echo(f"  Saved to: {saved_path}")


def main() -> None:
    cli()
