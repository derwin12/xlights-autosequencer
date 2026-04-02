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
@click.argument("path", type=click.Path(exists=True))
@click.option("--fresh", is_flag=True, default=False, help="Ignore cache and re-run analysis")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would run without executing")
def analyze_cmd(
    path: str,
    fresh: bool,
    dry_run: bool,
) -> None:
    """Run hierarchical analysis on an MP3 file or directory of MP3s."""

    from src.analyzer.orchestrator import run_orchestrator

    input_path = Path(path)

    # ── Directory mode (batch) ────────────────────────────────────────────────
    if input_path.is_dir():
        mp3s = sorted(input_path.glob("*.mp3"))
        if not mp3s:
            click.echo(f"ERROR: No MP3 files found in {path}", err=True)
            sys.exit(1)
        click.echo(f"Batch: {len(mp3s)} MP3 files found")
        succeeded, failed = 0, 0
        for i, mp3 in enumerate(mp3s, 1):
            click.echo(f"[{i}/{len(mp3s)}] {mp3.name}...", nl=False)
            try:
                result = run_orchestrator(str(mp3), fresh=fresh, dry_run=dry_run)
                # Check if it was cached
                click.echo(" done")
                succeeded += 1
            except SystemExit:
                raise
            except Exception as exc:
                click.echo(f" FAILED: {exc}")
                failed += 1
        click.echo(f"\nComplete: {succeeded}/{len(mp3s)} succeeded, {failed} failed")
        if failed:
            sys.exit(4)
        return

    # ── Single file mode ──────────────────────────────────────────────────────
    if not input_path.suffix.lower() == ".mp3":
        # Accept non-.mp3 files too (e.g. WAV) but warn
        click.echo(f"WARNING: {input_path.name} is not an MP3 — attempting analysis anyway", err=True)

    try:
        run_orchestrator(str(input_path), fresh=fresh, dry_run=dry_run)
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
    except PermissionError as exc:
        click.echo(f"ERROR: Cannot write output: {exc}", err=True)
        sys.exit(3)
    except Exception as exc:
        click.echo(f"ERROR: Analysis failed: {exc}", err=True)
        sys.exit(2)


# ──────────────────────────────────────────────────────────────────────────────
# full command
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("full")
@click.argument("mp3_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", default=None, help="Output JSON path (default: analysis/<stem>_analysis.json)")
@click.option("--top", "top_n", default=None, type=int, help="Auto-export top N tracks")
@click.option(
    "--lyrics", "lyrics_path", default=None, type=click.Path(dir_okay=False),
    help="Lyrics text file for improved word alignment",
)
@click.option(
    "--phoneme-model", "phoneme_model", default="base",
    type=click.Choice(["tiny", "base", "small", "medium", "large-v2"], case_sensitive=False),
    help="Whisper model size for phoneme transcription",
    show_default=True,
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
@click.pass_context
def full_cmd(
    ctx: click.Context,
    mp3_file: str,
    output: str | None,
    top_n: int | None,
    lyrics_path: str | None,
    phoneme_model: str,
    no_cache: bool,
    scoring_config_path: str | None,
    scoring_profile_name: str | None,
) -> None:
    """Run a full analysis: all algorithms + stems + phonemes + song structure."""
    # Delegate to the new zero-flag orchestrator.
    # Phoneme/structure analysis are now separate optional steps.
    ctx.invoke(
        analyze_cmd,
        path=mp3_file,
        fresh=no_cache,
        dry_run=False,
    )


# ──────────────────────────────────────────────────────────────────────────────
# wizard command (FR-014)
# ──────────────────────────────────────────────────────────────────────────────

def _run_analysis_from_config(
    ctx: click.Context,
    config: "WizardConfig",
    audio_path: Path,
    output: str | None = None,
    scoring_config_path: str | None = None,
    scoring_profile_name: str | None = None,
) -> None:
    """Bridge WizardConfig selections → analyze_cmd (FR-014 flag parity, T020)."""
    from src.wizard import WizardConfig  # noqa: F401 — type reference

    # T020: use_existing → load cached result directly, skip analysis
    if config.cache_strategy == "use_existing":
        from src.cache import AnalysisCache, CacheStatus
        status = CacheStatus.from_audio_path(audio_path, Path(output) if output else None)
        if status.exists and status.is_valid and status.cache_path:
            cache = AnalysisCache(audio_path, status.cache_path)
            try:
                result = cache.load()
            except Exception as exc:
                click.echo(f"ERROR: Cannot load cache: {exc}", err=True)
                sys.exit(1)
            click.echo(f"\nLoaded from cache: {status.cache_path}")
            _print_summary_table(result.timing_tracks)
            return
        else:
            click.echo("Cache is no longer valid — running fresh analysis.", err=True)
            config.cache_strategy = "regenerate"

    # T025: offline guard — check network if phonemes requested with an uncached model
    if config.use_phonemes:
        from src.wizard import whisper_model_list
        model_info = {m.name: m for m in whisper_model_list()}
        chosen = model_info.get(config.whisper_model)
        if chosen and not chosen.is_cached:
            import socket
            reachable = False
            try:
                socket.setdefaulttimeout(3)
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(
                    ("huggingface.co", 443)
                )
                reachable = True
            except (OSError, socket.error):
                reachable = False
            if not reachable:
                click.echo(
                    f"ERROR: Model '{config.whisper_model}' is not cached locally "
                    "and no network is available. Select a cached model or connect "
                    "to the internet.",
                    err=True,
                )
                sys.exit(1)

    kwargs = config.to_analyze_kwargs()
    ctx.invoke(
        analyze_cmd,
        mp3_file=str(audio_path),
        output=output,
        algorithms="all",
        no_vamp=not kwargs["include_vamp"],
        no_madmom=not kwargs["include_madmom"],
        top_n=None,
        use_stems=kwargs["use_stems"],
        use_phonemes=kwargs["use_phonemes"],
        lyrics_path=None,
        phoneme_model=kwargs["phoneme_model"],
        use_structure=kwargs["use_structure"],
        use_genius=kwargs["genius"],
        no_cache=kwargs["no_cache"],
        scoring_config_path=scoring_config_path,
        scoring_profile_name=scoring_profile_name,
    )


@cli.command("wizard")
@click.argument("audio_file", type=click.Path(dir_okay=False))
@click.option("--output", default=None, help="Output JSON path (default: auto)")
@click.option(
    "--non-interactive", "non_interactive", is_flag=True, default=False,
    help="Skip interactive prompts; apply flag defaults",
)
@click.option("--use-cache", "use_cache", is_flag=True, default=False,
              help="Use existing cache without prompting")
@click.option("--no-cache", "no_cache", is_flag=True, default=False,
              help="Re-run analysis, ignoring any cached result")
@click.option("--skip-cache-write", "skip_cache_write", is_flag=True, default=False,
              help="Run fresh analysis but do not persist result to cache")
@click.option("--no-vamp", "no_vamp", is_flag=True, default=False,
              help="Exclude Vamp plugin algorithms")
@click.option("--no-madmom", "no_madmom", is_flag=True, default=False,
              help="Exclude madmom algorithms")
@click.option("--stems/--no-stems", "use_stems", default=True,
              help="Enable/disable stem separation")
@click.option("--phonemes/--no-phonemes", "use_phonemes", default=True,
              help="Enable/disable vocal phoneme analysis")
@click.option(
    "--phoneme-model", "phoneme_model", default="base",
    type=click.Choice(["tiny", "base", "small", "medium", "large-v2"], case_sensitive=False),
    help="Whisper model size for phoneme transcription",
    show_default=True,
)
@click.option("--structure/--no-structure", "use_structure", default=True,
              help="Enable/disable song structure detection")
@click.option("--genius/--no-genius", "use_genius", is_flag=True, default=False,
              help="Enable/disable Genius lyrics fetch")
@click.option("--scoring-config", "scoring_config_path", default=None,
              type=click.Path(exists=True, dir_okay=False),
              help="Path to a TOML scoring configuration file")
@click.option("--scoring-profile", "scoring_profile_name", default=None,
              help="Name of a saved scoring profile")
@click.pass_context
def wizard_cmd(
    ctx: click.Context,
    audio_file: str,
    output: str | None,
    non_interactive: bool,
    use_cache: bool,
    no_cache: bool,
    skip_cache_write: bool,
    no_vamp: bool,
    no_madmom: bool,
    use_stems: bool,
    use_phonemes: bool,
    phoneme_model: str,
    use_structure: bool,
    use_genius: bool,
    scoring_config_path: str | None,
    scoring_profile_name: str | None,
) -> None:
    """Interactive wizard for configuring and launching analysis.

    AUDIO_FILE is the input MP3 (or WAV) to analyse.  In a TTY the wizard
    walks you through cache, scope, and Whisper-model selection with
    arrow-key menus.  Pass --non-interactive (or pipe stdin) to apply flag
    defaults and skip all prompts.
    """
    from src.wizard import WizardRunner

    # T010: validate file existence before launching wizard
    audio_path = Path(audio_file)
    if not audio_path.exists() or not audio_path.is_file():
        from src.paths import PathContext
        suggestion = PathContext().suggest_path(str(audio_path))
        msg = f"ERROR: File not found: {audio_file}"
        if suggestion:
            msg += f"\n  Did you mean: {suggestion}"
        click.echo(msg, err=True)
        sys.exit(1)

    flags = {
        "non_interactive": non_interactive,
        "use_cache": use_cache,
        "no_cache": no_cache,
        "skip_cache_write": skip_cache_write,
        "include_vamp": not no_vamp,
        "include_madmom": not no_madmom,
        "use_stems": use_stems,
        "use_phonemes": use_phonemes,
        "phoneme_model": phoneme_model,
        "use_structure": use_structure,
        "genius": use_genius,
    }

    runner = WizardRunner(flags=flags)
    config = runner.run(audio_path)

    if config is None:
        sys.exit(130)  # user cancelled (Ctrl-C or Esc)

    _run_analysis_from_config(ctx, config, audio_path, output, scoring_config_path, scoring_profile_name)

    # Offer to launch the review UI after analysis completes
    if sys.stdin.isatty() and not non_interactive:
        try:
            import questionary
            launch = questionary.confirm(
                "Open the review UI in your browser?", default=True
            ).ask()
        except (KeyboardInterrupt, EOFError):
            launch = False
        if launch:
            # Resolve the analysis JSON path the same way analyze_cmd does
            resolved = audio_path.resolve()
            analysis_dir = resolved.parent / "analysis"
            if not analysis_dir.is_dir():
                analysis_dir = resolved.parent / resolved.stem
            if output:
                json_path = str(Path(output).resolve())
            else:
                json_path = str(analysis_dir / (resolved.stem + "_analysis.json"))
            ctx.invoke(review_cmd, audio_or_json=json_path)


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

    ss = result.song_structure
    if ss is not None and ss.segments:
        click.echo(f"\nSong Structure ({len(ss.segments)} segments):")
        for seg in ss.segments:
            start = _format_duration(seg.start_ms)
            end = _format_duration(seg.end_ms)
            duration_s = (seg.end_ms - seg.start_ms) / 1000
            click.echo(f"  {start} – {end}  ({duration_s:.1f}s)  {seg.label}")

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
@click.argument("audio_or_json", required=False, default=None, type=click.Path())
def review_cmd(audio_or_json: str | None) -> None:
    """Launch the track review UI in the default browser.

    AUDIO_OR_JSON can be:
      - A directory: scans for *_hierarchy.json files and shows a scored library
      - A *_hierarchy.json file: opens the timeline directly for that song
      - An audio (.mp3) file: looks up cached analysis via the library
      - Omitted: opens the library home page
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

    # ── Directory: scan for hierarchy files and open library view ─────────────
    if given_path.is_dir():
        app = create_app(scan_dir=str(given_path.resolve()))
        url = "http://127.0.0.1:5173/library-view"
        click.echo(f"Starting library UI at {url} (scanning {given_path})")
        click.echo("Press Ctrl-C to stop.")
        threading.Timer(0.5, webbrowser.open, args=[url]).start()
        try:
            app.run(host="127.0.0.1", port=5173, use_reloader=False, debug=False)
        except OSError as exc:
            if exc.errno == errno.EADDRINUSE:
                click.echo("ERROR: Port 5173 is already in use.", err=True)
                sys.exit(5)
            raise
        return

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
        # Resolve relative paths against the analysis JSON's directory
        audio_resolved = Path(audio_path_str)
        if not audio_resolved.is_absolute():
            audio_resolved = (analysis_path.parent / audio_resolved).resolve()
        audio_path_str = str(audio_resolved)
        if not audio_resolved.exists():
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


@cli.command("stem-inspect")
@click.argument("mp3_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--stem-dir", type=click.Path(file_okay=False), default=None,
              help="Explicit path to stem directory (default: auto-detect)")
def stem_inspect_cmd(mp3_file: str, stem_dir: str | None) -> None:
    """Evaluate which stems are worth analyzing (KEEP / REVIEW / SKIP)."""
    from src.analyzer.stem_inspector import inspect_stems

    stem_dir_path = Path(stem_dir) if stem_dir else None
    try:
        metrics = inspect_stems(mp3_file, stem_dir=stem_dir_path)
    except Exception as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    click.echo(f"\nStem Inspection: {Path(mp3_file).name}")
    click.echo(f"  {'STEM':<12} {'VERDICT':<8} {'RMS dB':>8}  {'CREST dB':>9}  {'COVERAGE':>9}  {'CENTROID':>10}  REASON")
    click.echo("  " + "-" * 90)
    for m in metrics:
        verdict_style = {"keep": "green", "review": "yellow", "skip": "red"}.get(m.verdict, "white")
        verdict_str = click.style(m.verdict.upper(), fg=verdict_style, bold=True)
        click.echo(
            f"  {m.name:<12} {verdict_str:<8}  {m.rms_db:>7.1f}  {m.crest_db:>9.1f}  "
            f"{m.coverage * 100:>8.0f}%  {m.spectral_centroid_hz:>9.0f} Hz  {m.reason}"
        )
    click.echo()


@cli.command("stem-review")
@click.argument("mp3_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--stem-dir", type=click.Path(file_okay=False), default=None,
              help="Explicit path to stem directory (default: auto-detect)")
@click.option("--yes", "auto_accept", is_flag=True, default=False,
              help="Accept all automatic verdicts without prompting")
def stem_review_cmd(mp3_file: str, stem_dir: str | None, auto_accept: bool) -> None:
    """Interactively review stem verdicts and confirm the final selection.

    Shows each stem's KEEP/REVIEW/SKIP verdict with audio measurements, then
    prompts to accept or override each verdict. Prints the final stem selection.
    """
    from src.analyzer.stem_inspector import inspect_stems, interactive_review

    stem_dir_path = Path(stem_dir) if stem_dir else None
    try:
        metrics = inspect_stems(mp3_file, stem_dir=stem_dir_path)
    except Exception as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    click.echo(f"\nStem Review: {Path(mp3_file).name}\n")
    selection = interactive_review(metrics, auto_accept=auto_accept)

    click.echo("\n── Final Selection ──────────────────────────────────")
    for stem, verdict in selection.stems.items():
        marker = "✓" if verdict == "keep" else "✗"
        override_note = " (overridden)" if stem in selection.overrides else ""
        click.echo(f"  {marker} {stem:<12} {verdict.upper()}{override_note}")
    if selection.fallback_to_mix:
        click.echo("\n  [fallback] All stems skipped — full_mix will be used.")
    kept = selection.kept_stems
    click.echo(f"\nKept {len(kept)} stem(s): {', '.join(kept) if kept else '(none)'}")


@cli.command("sweep-init")
@click.argument("mp3_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output-dir", "-o", type=click.Path(file_okay=False), default=None,
              help="Directory to write sweep config JSONs (default: analysis/ next to MP3)")
@click.option("--stem-dir", type=click.Path(file_okay=False), default=None,
              help="Explicit path to stem directory")
@click.option("--algorithms", default=None,
              help="Comma-separated list of algorithms to generate configs for (default: all)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Print configs without writing files")
def sweep_init_cmd(
    mp3_file: str,
    output_dir: str | None,
    stem_dir: str | None,
    algorithms: str | None,
    dry_run: bool,
) -> None:
    """Generate intelligent sweep configs for an MP3 based on its audio characteristics."""
    from src.analyzer.stem_inspector import inspect_stems, generate_sweep_configs

    audio_path = Path(mp3_file)
    stem_dir_path = Path(stem_dir) if stem_dir else None
    alg_list = [a.strip() for a in algorithms.split(",")] if algorithms else None

    click.echo(f"Inspecting stems for {audio_path.name}…")
    try:
        stem_metrics = inspect_stems(str(audio_path), stem_dir=stem_dir_path)
    except Exception as exc:
        click.echo(f"ERROR: stem inspection failed: {exc}", err=True)
        sys.exit(1)

    # Print stem summary
    for m in stem_metrics:
        verdict_style = {"keep": "green", "review": "yellow", "skip": "red"}.get(m.verdict, "white")
        click.echo(
            f"  {m.name:<12} {click.style(m.verdict.upper(), fg=verdict_style):<8}  {m.reason}"
        )

    click.echo(f"\nGenerating sweep configs…")
    try:
        configs, bpm = generate_sweep_configs(str(audio_path), stem_metrics, algorithms=alg_list)
    except Exception as exc:
        click.echo(f"ERROR: config generation failed: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Estimated BPM: {bpm:.1f}")
    click.echo(f"Generated {len(configs)} configs\n")

    if dry_run:
        for cfg in configs:
            meta = cfg.pop("_meta", {})
            click.echo(f"  [{cfg['algorithm']}]")
            click.echo(f"    stems:   {cfg['stems']}")
            click.echo(f"    sweep:   {cfg['sweep']}")
            click.echo(f"    fixed:   {cfg['fixed']}")
            click.echo(f"    rationale: {meta.get('rationale', '')}")
            cfg["_meta"] = meta  # restore
        return

    out_dir = Path(output_dir) if output_dir else audio_path.parent / "analysis" / "sweep_configs"
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for cfg in configs:
        alg_name = cfg["algorithm"]
        out_path = out_dir / f"{audio_path.stem}_{alg_name}.json"
        # Remove _meta before writing (SweepConfig.from_file ignores it anyway, but keep clean)
        payload = {k: v for k, v in cfg.items() if k != "_meta"}
        out_path.write_text(json.dumps(payload, indent=2))
        written.append(out_path)
        meta = cfg.get("_meta", {})
        click.echo(
            f"  {alg_name:<24}  stems={payload['stems']}  "
            f"sweep={list(payload['sweep'].keys()) or '—'}"
        )
        if meta.get("rationale"):
            click.echo(f"    → {meta['rationale']}")

    click.echo(f"\nWrote {len(written)} config files to: {out_dir}")


@cli.command("pipeline")
@click.argument("audio_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--stem-dir", type=click.Path(file_okay=False), default=None,
              help="Explicit path to stem directory")
@click.option("--output-dir", "-o", type=click.Path(file_okay=False), default=None,
              help="Output directory for all exported files (default: analysis/ next to audio)")
@click.option("--fps", default=20, show_default=True, type=int,
              help="Target frame rate for value curves")
@click.option("--top", "top_n", default=5, show_default=True, type=int,
              help="Export only the top N timing tracks by quality score")
@click.option("--interactive", is_flag=True, default=False,
              help="Pause after stem inspection for manual review")
@click.option("--no-sweep", is_flag=True, default=False,
              help="Skip parameter sweep; use default algorithm settings")
@click.option("--scoring-config", default=None,
              help="Path to custom scoring TOML config")
def pipeline_cmd(
    audio_file: str,
    stem_dir: str | None,
    output_dir: str | None,
    fps: int,
    top_n: int,
    interactive: bool,
    no_sweep: bool,
    scoring_config: str | None,
) -> None:
    """Run the full xLights export pipeline end-to-end.

    Stages: stem inspection → (optional review) → analysis →
    interaction detection → conditioning → .xtiming + .xvc export.
    """
    from src.analyzer.pipeline import run_pipeline

    click.echo(f"Pipeline: {Path(audio_file).name}")

    try:
        manifest = run_pipeline(
            audio_path=audio_file,
            stem_dir=stem_dir,
            output_dir=output_dir,
            fps=fps,
            top_n=top_n,
            interactive=interactive,
            no_sweep=no_sweep,
        )
    except Exception as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1)

    # ── Summary output (T050) ─────────────────────────────────────────────────
    click.echo(f"\nStems used ({len(manifest.stems_used)}): {', '.join(manifest.stems_used)}")
    click.echo(f"Timing tracks exported: {len(manifest.timing_tracks)}")
    click.echo(f"Value curves exported:  {len(manifest.value_curves)}")

    if manifest.warnings:
        click.echo(f"\nWarnings ({len(manifest.warnings)}):")
        for w in manifest.warnings:
            click.echo(f"  ! {w}")

    click.echo(f"\nOutput: {manifest.export_dir}/")
    click.echo(f"Manifest: {manifest.export_dir}/export_manifest.json")


@cli.command("export-xlights")
@click.argument("analysis_json", type=click.Path(exists=True, dir_okay=False))
@click.option("--output-dir", "-o", type=click.Path(file_okay=False), default=None,
              help="Directory for .xtiming and .xvc files (default: analysis/ next to JSON)")
def export_xlights_cmd(analysis_json: str, output_dir: str | None) -> None:
    """Export timing tracks and feature curves for xLights import.

    Reads ANALYSIS_JSON, exports all timing tracks as .xtiming files and
    writes export_manifest.json to the output directory.
    """
    import datetime
    import json as _json
    from src.analyzer.xtiming import write_timing_tracks
    from src.analyzer.result import ExportManifest, TimingTrackExport

    json_path = Path(analysis_json)
    result = AnalysisResult.from_dict(_json.loads(json_path.read_text(encoding="utf-8")))

    if output_dir is None:
        out_dir = json_path.parent / "analysis"
    else:
        out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Export timing tracks ──────────────────────────────────────────────────
    xtiming_path = str(out_dir / f"{json_path.stem}_timing.xtiming")
    write_timing_tracks(result.timing_tracks, xtiming_path)
    timing_exports = [
        TimingTrackExport(
            file_path=xtiming_path,
            track_name=t.name,
            source_stem=getattr(t, "stem_source", None) or "full_mix",
            element_type=t.element_type,
            mark_count=t.mark_count,
        )
        for t in result.timing_tracks
    ]
    click.echo(f"Wrote timing tracks → {xtiming_path}  ({len(result.timing_tracks)} tracks)")

    # ── Write manifest ────────────────────────────────────────────────────────
    stems_used = list({
        getattr(t, "stem_source", None) or "full_mix"
        for t in result.timing_tracks
    })
    manifest = ExportManifest(
        song_file=str(json_path),
        export_dir=str(out_dir),
        exported_at=datetime.datetime.now().isoformat(),
        stems_used=stems_used,
        timing_tracks=timing_exports,
        value_curves=[],
    )
    manifest_path = out_dir / "export_manifest.json"
    manifest_path.write_text(
        _json.dumps(manifest.to_dict(), indent=2), encoding="utf-8"
    )
    click.echo(f"Wrote manifest → {manifest_path}")


# ──────────────────────────────────────────────────────────────────────────────
# sweep-matrix command (015)
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("sweep-matrix")
@click.argument("audio_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--algorithms", default=None, help="Comma-separated algorithm names (default: all)")
@click.option("--stems", "stems_filter", default=None, help="Comma-separated stem names (overrides affinity)")
@click.option("--max-permutations", "max_perm", default=500, type=int, show_default=True,
              help="Safety cap — warn if matrix exceeds this count")
@click.option("--dry-run", "dry_run", is_flag=True, default=False, help="Show matrix without running")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True, dir_okay=False),
              help="TOML sweep configuration file")
@click.option("--output-dir", default=None, type=click.Path(file_okay=False), help="Output directory for results")
@click.option("--sample-start", "sample_start", default=None, type=int, help="Segment start (ms)")
@click.option("--sample-duration", "sample_duration", default=30000, type=int, show_default=True,
              help="Sample segment duration (ms)")
@click.option("--yes", "skip_confirm", is_flag=True, default=False, help="Skip confirmation prompts")
def sweep_matrix_cmd(
    audio_file: str,
    algorithms: str | None,
    stems_filter: str | None,
    max_perm: int,
    dry_run: bool,
    config_path: str | None,
    output_dir: str | None,
    sample_start: int | None,
    sample_duration: int,
    skip_confirm: bool,
) -> None:
    """Run a comprehensive parameter sweep across all algorithms and stems."""
    from pathlib import Path as _Path
    from src.analyzer.sweep_matrix import SweepMatrixConfig, MatrixSweepRunner
    from src.analyzer.segment_selector import select_representative_segment
    from src.analyzer.stem_inspector import inspect_stems

    audio_path = _Path(audio_file)

    # Discover available stems
    click.echo(f"Inspecting stems for {audio_path.name}...")
    try:
        metrics = inspect_stems(str(audio_path))
        available = {m.name for m in metrics if m.verdict in ("keep", "review")}
        available.add("full_mix")
        click.echo(f"  Available stems: {', '.join(sorted(available))}")
    except Exception:
        available = {"full_mix"}
        click.echo("  No stems found — using full_mix only.")

    # Build config
    if config_path:
        config = SweepMatrixConfig.from_toml(config_path, available_stems=available)
        click.echo(f"  Loaded config from {config_path}")
    else:
        algo_list = None
        if algorithms:
            algo_list = [a.strip() for a in algorithms.split(",")]
        if stems_filter:
            stem_set = {s.strip() for s in stems_filter.split(",")}
            stem_set.add("full_mix")
            available = available & stem_set | {"full_mix"}

        config = SweepMatrixConfig(
            algorithms=algo_list or list(
                __import__("src.analyzer.stem_affinity", fromlist=["AFFINITY_TABLE"]).AFFINITY_TABLE.keys()
            ),
            available_stems=available,
            max_permutations=max_perm,
            sample_duration_s=sample_duration / 1000,
        )

    # Build matrix
    matrix = config.build_matrix()
    click.echo(f"\nSweep matrix: {matrix.total_count} permutations")

    if dry_run:
        click.echo(f"\n  {'ALGORITHM':<25} {'STEM':<12} {'PARAMS'}")
        click.echo("  " + "-" * 60)
        for p in matrix.permutations:
            param_str = ", ".join(f"{k}={v}" for k, v in p.parameters.items()) or "(none)"
            click.echo(f"  {p.algorithm:<25} {p.stem:<12} {param_str}")
        click.echo(f"\nTotal: {matrix.total_count} permutations (dry run — nothing executed)")
        return

    if matrix.exceeds_cap and not skip_confirm:
        click.echo(f"\n⚠️  Matrix exceeds safety cap ({matrix.total_count} > {matrix.cap}). Proceed? [y/N]: ", nl=False)
        answer = click.getchar()
        click.echo(answer)
        if answer.lower() != "y":
            click.echo("Cancelled.")
            sys.exit(130)

    # Select representative segment
    if sample_start is not None:
        seg_start = sample_start
        seg_end = sample_start + sample_duration
    else:
        click.echo("Selecting representative audio segment...")
        seg_start, seg_end = select_representative_segment(str(audio_path), config.sample_duration_s)
    click.echo(f"  Segment: {seg_start}ms – {seg_end}ms ({(seg_end - seg_start) / 1000:.0f}s)")

    # Run sweep
    click.echo(f"\nRunning {matrix.total_count} permutations...")

    def progress(idx, total, perm, result):
        status = click.style("✓", fg="green") if result.status == "success" else click.style("✗", fg="red")
        param_str = ", ".join(f"{k}={v}" for k, v in perm.parameters.items()) or ""
        click.echo(
            f"  [{idx:>3}/{total}] {status} {perm.algorithm:<25} {perm.stem:<12} "
            f"score={result.quality_score:.2f}  {param_str}"
        )

    runner = MatrixSweepRunner(
        audio_path=str(audio_path),
        matrix=matrix,
        output_dir=output_dir,
        sample_start_ms=seg_start,
        sample_end_ms=seg_end,
    )
    results = runner.run(progress_callback=progress)

    # Summary
    from src.analyzer.sweep_matrix import auto_select_best
    success = sum(1 for r in results if r.status == "success")
    failed = sum(1 for r in results if r.status == "failed")
    click.echo(f"\nSweep complete: {success} succeeded, {failed} failed")

    best = auto_select_best(results)
    if best:
        click.echo(f"\nBest per algorithm:")
        click.echo(f"  {'ALGORITHM':<25} {'STEM':<12} {'SCORE':<7} {'MARKS':<7} PARAMS")
        for algo, r in sorted(best.items()):
            param_str = ", ".join(f"{k}={v}" for k, v in r.parameters.items()) or "(none)"
            marks = str(r.mark_count) if r.result_type == "timing" else f"{r.sample_count} samples"
            click.echo(f"  {algo:<25} {r.stem:<12} {r.quality_score:<7.2f} {marks:<7} {param_str}")

    if output_dir:
        out_dir = output_dir
    elif audio_path.parent.name == audio_path.stem:
        out_dir = str(audio_path.parent / "sweep")
    else:
        out_dir = str(audio_path.parent / audio_path.stem / "sweep")
    click.echo(f"\nResults: {out_dir}/sweep_report.json")

    # Offer to re-run winners on full song and export
    if best and sys.stdin.isatty() and not skip_confirm:
        click.echo("")
        if click.confirm("Re-run winners on full song and export?", default=True):
            from src.analyzer.sweep_matrix import rerun_winners_full_song
            click.echo("Re-running winners on full song...")
            full_results = rerun_winners_full_song(
                str(audio_path), best, out_dir,
            )
            click.echo(f"\nExported {len(full_results)} winners to {out_dir}/winners/")
            for algo, r in sorted(full_results.items()):
                click.echo(f"  ✓ {algo}_{r.stem} — score {r.quality_score:.2f}")


# ──────────────────────────────────────────────────────────────────────────────
# sweep-results command (015)
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("sweep-results")
@click.argument("sweep_report", type=click.Path(exists=True, dir_okay=False))
@click.option("--algorithm", default=None, help="Filter by algorithm name")
@click.option("--stem", default=None, help="Filter by stem name")
@click.option("--best", "show_best", is_flag=True, default=False, help="Show only best result per algorithm")
@click.option("--top", "top_n", default=None, type=int, help="Show only top N results globally")
@click.option("--type", "result_type", default=None, type=click.Choice(["timing", "value_curve"]),
              help="Filter by result type")
@click.option("--export", "do_export", is_flag=True, default=False,
              help="Re-run displayed results on full song and export as .xtiming/.xvc")
def sweep_results_cmd(
    sweep_report: str,
    algorithm: str | None,
    stem: str | None,
    show_best: bool,
    top_n: int | None,
    result_type: str | None,
    do_export: bool,
) -> None:
    """Display ranked sweep results from a sweep report."""
    import json

    with open(sweep_report, "r", encoding="utf-8") as fh:
        report = json.load(fh)

    results = report.get("results", [])

    # Filter
    if algorithm:
        results = [r for r in results if r["algorithm"] == algorithm]
    if stem:
        results = [r for r in results if r["stem"] == stem]
    if result_type:
        results = [r for r in results if r["result_type"] == result_type]

    # Only successful
    results = [r for r in results if r.get("status") == "success"]

    # Sort by quality score descending
    results.sort(key=lambda r: r.get("quality_score", 0), reverse=True)

    if show_best:
        # One per algorithm
        seen = set()
        filtered = []
        for r in results:
            if r["algorithm"] not in seen:
                seen.add(r["algorithm"])
                filtered.append(r)
        results = filtered

    if top_n is not None:
        results = results[:top_n]

    if not results:
        click.echo("No results match the filters.")
        return

    # Display table
    click.echo(f"\n  {'RANK':<5} {'SCORE':<7} {'TYPE':<12} {'ALGORITHM':<25} {'STEM':<12} {'MARKS':<7} {'AVG INT':<9} PARAMETERS")
    click.echo("  " + "-" * 90)
    for i, r in enumerate(results):
        param_str = ", ".join(f"{k}={v}" for k, v in r.get("parameters", {}).items()) or "(none)"
        rtype = r.get("result_type", "timing")
        marks = str(r.get("mark_count", 0)) if rtype == "timing" else f"{r.get('sample_count', 0)}s"
        avg_int = f"{r.get('avg_interval_ms', 0)}ms" if rtype == "timing" else "–"
        click.echo(
            f"  {i + 1:<5} {r.get('quality_score', 0):<7.2f} {rtype:<12} "
            f"{r['algorithm']:<25} {r['stem']:<12} {marks:<7} {avg_int:<9} {param_str}"
        )

    click.echo(f"\n  {len(results)} results shown from {sweep_report}")

    if do_export and results:
        # Find audio path from the report
        audio_path = report.get("audio_path", "")
        if not audio_path or not Path(audio_path).exists():
            click.echo("ERROR: Cannot find audio file for full-song re-run.", err=True)
            sys.exit(1)

        # Build winners dict from displayed results (best per algorithm)
        from src.analyzer.sweep_matrix import PermutationResult, rerun_winners_full_song
        winners = {}
        for r in results:
            algo = r["algorithm"]
            if algo not in winners:
                winners[algo] = PermutationResult(
                    algorithm=algo,
                    stem=r["stem"],
                    parameters=r.get("parameters", {}),
                    result_type=r.get("result_type", "timing"),
                    quality_score=r.get("quality_score", 0),
                    mark_count=r.get("mark_count", 0),
                )

        sweep_dir = str(Path(sweep_report).parent)
        click.echo(f"\nRe-running {len(winners)} winners on full song...")
        full_results = rerun_winners_full_song(audio_path, winners, sweep_dir)
        click.echo(f"Exported {len(full_results)} winners to {sweep_dir}/winners/")
        for algo, r in sorted(full_results.items()):
            click.echo(f"  ✓ {algo}_{r.stem} — score {r.quality_score:.2f}")


# ──────────────────────────────────────────────────────────────────────────────
# library command
# ──────────────────────────────────────────────────────────────────────────────

def _bar(score: float, width: int = 8) -> str:
    filled = int(round(score * width))
    return "[" + "#" * filled + "." * (width - filled) + f"] {score:.2f}"


def _load_hierarchy_summary(json_path: Path) -> dict | None:
    """Load a _hierarchy.json and extract the summary fields needed for the library table."""
    try:
        import json as _json
        data = _json.loads(json_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != "2.0.0":
            return None
        v = data.get("validation", {})
        dur_ms = data.get("duration_ms", 0)
        minutes, seconds = divmod(dur_ms // 1000, 60)

        bars_score = v.get("bars", {}).get("score")
        beats_score = v.get("beats", {}).get("score")
        sections_rate = v.get("sections", {}).get("bar_alignment_rate")
        events = v.get("events", {})
        l4_mean = (sum(ev["transient_rate"] for ev in events.values()) / len(events)
                   if events else None)
        overall = v.get("overall_score")

        return {
            "path": json_path,
            "name": json_path.stem.replace("_hierarchy", ""),
            "duration": f"{minutes}:{seconds:02d}",
            "bpm": data.get("estimated_bpm", 0),
            "stems": len(data.get("stems_available", ["full_mix"])),
            "bars": bars_score,
            "beats": beats_score,
            "sections": sections_rate,
            "l4": l4_mean,
            "overall": overall,
        }
    except Exception:
        return None


@cli.command("library")
@click.argument("directory", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--min-score", default=0.0, type=float, show_default=True,
              help="Only show songs with overall_score >= this value")
@click.option("--flag-below", default=0.6, type=float, show_default=True,
              help="Flag songs with overall_score below this threshold")
@click.option("--sort", "sort_by", default="overall",
              type=click.Choice(["overall", "bars", "beats", "sections", "l4", "name"]),
              show_default=True, help="Sort column")
def library_cmd(directory: str, min_score: float, flag_below: float, sort_by: str) -> None:
    """Scan a directory tree for analyzed songs and show a ranked quality table.

    Finds all *_hierarchy.json files (schema 2.0.0) under DIRECTORY and prints
    a table sorted by overall validation score.  Rows with a low score are
    flagged with '!' to highlight songs that may need re-analysis.
    """
    root = Path(directory)
    json_files = sorted(root.rglob("*_hierarchy.json"))

    if not json_files:
        click.echo(f"No *_hierarchy.json files found under {root}", err=True)
        sys.exit(1)

    entries = []
    skipped = 0
    for jf in json_files:
        summary = _load_hierarchy_summary(jf)
        if summary is None:
            skipped += 1
            continue
        if summary["overall"] is None or summary["overall"] < min_score:
            continue
        entries.append(summary)

    if not entries:
        click.echo("No songs match the filter criteria.", err=True)
        sys.exit(1)

    # Sort
    reverse = sort_by != "name"
    def _sort_key(e):
        v = e.get(sort_by)
        return (v is not None, v or 0)
    entries.sort(key=_sort_key, reverse=reverse)

    # Header
    click.echo(f"\nSong Library  ({len(entries)} songs")
    if skipped:
        click.echo(f", {skipped} skipped (old schema)", nl=False)
    click.echo(")")
    click.echo(
        f"  {'':1} {'SONG':<40} {'DUR':>5}  {'BPM':>5}  {'ST':>2}  "
        f"{'BARS':>13}  {'BEATS':>13}  {'SECT':>13}  {'L4':>13}  {'OVERALL':>13}"
    )
    click.echo("  " + "-" * 127)

    for e in entries:
        flag = "!" if (e["overall"] or 0) < flag_below else " "

        def _cell(v) -> str:
            return _bar(v) if v is not None else "         n/a"

        click.echo(
            f"  {flag} {e['name']:<40} {e['duration']:>5}  {e['bpm']:>5.0f}  "
            f"{e['stems']:>2}  {_cell(e['bars'])}  {_cell(e['beats'])}  "
            f"{_cell(e['sections'])}  {_cell(e['l4'])}  {_cell(e['overall'])}"
        )

    # Summary stats
    overalls = [e["overall"] for e in entries if e["overall"] is not None]
    if overalls:
        mean = sum(overalls) / len(overalls)
        low = sum(1 for s in overalls if s < flag_below)
        click.echo(f"\n  Mean overall: {mean:.3f}  |  Flagged (< {flag_below}): {low}/{len(overalls)}")


# ──────────────────────────────────────────────────────────────────────────────
# group-layout command
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("group-layout")
@click.argument("layout_file", type=click.Path(dir_okay=False))
@click.option(
    "--profile",
    type=click.Choice(["energetic", "cinematic", "technical"]),
    default=None,
    help="Show profile: energetic, cinematic, or technical (default: all tiers).",
)
@click.option("--dry-run", "dry_run", is_flag=True, default=False,
              help="Preview groups without modifying any files.")
@click.option("--output", "output_path", default=None, type=click.Path(),
              help="Write output to a different path (default: in-place).")
@click.option("--hero", "extra_heroes", multiple=True,
              help="Explicitly add a prop as a hero (repeatable). Use exact prop name.")
@click.option("--no-auto-heroes", "no_auto_heroes", is_flag=True, default=False,
              help="Disable pixel-count-based automatic hero detection.")
def group_layout_cmd(
    layout_file: str,
    profile: str | None,
    dry_run: bool,
    output_path: str | None,
    extra_heroes: tuple[str, ...],
    no_auto_heroes: bool,
) -> None:
    """Generate xLights Power Groups from LAYOUT_FILE (xlights_rgbeffects.xml)."""
    import xml.etree.ElementTree as ET
    from src.grouper.layout import parse_layout
    from src.grouper.classifier import normalize_coords, classify_props
    from src.grouper.grouper import generate_groups
    from src.grouper.writer import inject_groups, write_layout

    # ── Input validation ──────────────────────────────────────────────────────
    path = Path(layout_file)
    if not path.exists() or not path.is_file():
        click.echo(f"ERROR: File not found or not readable: {layout_file}", err=True)
        sys.exit(1)

    try:
        layout = parse_layout(path)
    except ET.ParseError as exc:
        click.echo(f"ERROR: XML parse error in {layout_file}: {exc}", err=True)
        sys.exit(2)

    if not layout.props:
        click.echo(f"ERROR: No <model> elements found in {layout_file}", err=True)
        sys.exit(3)

    # ── Pipeline ──────────────────────────────────────────────────────────────
    normalize_coords(layout.props)
    classify_props(layout.props)
    heroes_list = list(extra_heroes) if extra_heroes else None
    groups = generate_groups(
        layout.props,
        profile=profile,
        extra_heroes=heroes_list,
        auto_heroes=not no_auto_heroes,
    )

    profile_label = profile if profile else "(all)"

    # ── Dry-run output ────────────────────────────────────────────────────────
    if dry_run:
        click.echo(f"xLights Layout Grouping — Dry Run")
        click.echo(f"Layout:  {path}")
        click.echo(f"Profile: {profile_label}")
        click.echo(f"Props:   {len(layout.props)}")
        click.echo("")
        click.echo(f"{'Tier':<6}{'Group Name':<30}{'Members':>7}")
        click.echo(f"{'----':<6}{'----------':<30}{'-------':>7}")
        for g in groups:
            click.echo(f"{g.tier:02d}    {g.name:<30}{len(g.members):>7}")
        click.echo("")
        click.echo(f"Total groups: {len(groups)}")
        click.echo("No files modified (dry run).")
        return

    # ── Write output ──────────────────────────────────────────────────────────
    # Count how many old auto-groups exist before injection
    from src.grouper.writer import AUTO_PREFIXES
    root = layout.raw_tree.getroot()
    # Check both modern (<modelGroups><modelGroup>) and legacy (<ModelGroup>) formats
    old_groups_el = root.find("modelGroups")
    if old_groups_el is not None:
        old_mgs = old_groups_el.findall("modelGroup")
    else:
        old_mgs = root.findall("ModelGroup")
    old_count = sum(
        1 for mg in old_mgs
        if any(mg.get("name", "").startswith(p) for p in AUTO_PREFIXES)
    )

    inject_groups(layout.raw_tree, groups)
    dest = Path(output_path) if output_path else path
    write_layout(layout, dest)

    click.echo(f"xLights Layout Grouping")
    click.echo(f"Layout:  {path}")
    click.echo(f"Profile: {profile_label}")
    click.echo(f"Props:   {len(layout.props)}")
    click.echo("")
    click.echo(f"Generated {len(groups)} groups across {len({g.tier for g in groups})} tiers.")
    click.echo(f"Removed {old_count} previous auto-groups.")
    click.echo(f"Written: {dest}")


# ──────────────────────────────────────────────────────────────────────────────
# Sequence generation
# ──────────────────────────────────────────────────────────────────────────────


def _load_curves_mode_from_config() -> str:
    """Read curves_mode from ~/.xlight/generation.toml if present.

    Returns "all" if the file does not exist or has no [generation].curves_mode.
    """
    import tomllib

    config_path = Path.home() / ".xlight" / "generation.toml"
    if not config_path.exists():
        return "all"
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        mode = data.get("generation", {}).get("curves_mode", "all")
        return str(mode)
    except Exception:
        return "all"


@cli.command("generate")
@click.argument("audio_file", type=click.Path(exists=True, dir_okay=False))
@click.argument("layout_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output-dir", "-o", type=click.Path(file_okay=False), default=None,
              help="Output directory (default: same as audio file)")
@click.option("--genre", default=None, help="Song genre (default: auto-detect from ID3)")
@click.option("--occasion", default="general",
              type=click.Choice(["general", "christmas", "halloween"]),
              help="Occasion tag for theme selection")
@click.option("--fresh", is_flag=True, default=False,
              help="Force re-analysis (skip cache)")
@click.option("--no-wizard", "no_wizard", is_flag=True, default=False,
              help="Skip interactive wizard, use defaults/flags")
@click.option("--section", "target_section", default=None,
              help="Regenerate only this section type (e.g., 'chorus')")
@click.option("--theme-override", "theme_overrides_raw", multiple=True,
              help="Override theme: 'chorus=Inferno' (repeatable)")
@click.option("--tiers", "tiers_raw", default=None,
              help="Comma-separated tiers to include (1-8 or names: "
                   "base,geo,type,beat,fidelity,prop,compound,hero)")
@click.option("--story", "story_path", default=None, type=click.Path(dir_okay=False),
              help="Path to song story JSON (uses _story_reviewed.json if exists, "
                   "falls back to _story.json)")
@click.option("--curves", "curves_mode", default=None,
              type=click.Choice(["all", "brightness", "speed", "color", "none"]),
              help="Value curve generation mode (default: all). Overrides config file.")
def generate_cmd(audio_file, layout_file, output_dir, genre, occasion,
                 fresh, no_wizard, target_section, theme_overrides_raw,
                 tiers_raw, story_path, curves_mode):
    """Generate an xLights .xsq sequence from an MP3 and layout file."""
    from src.generator.models import GenerationConfig
    from src.generator.plan import generate_sequence, read_song_metadata
    from src.generator.xsq_writer import fseq_guidance

    audio_path = Path(audio_file)
    layout_path = Path(layout_file)

    # Auto-detect genre from ID3 if not specified
    if genre is None:
        profile = read_song_metadata(audio_path)
        genre = profile.genre
        click.echo(f"Detected genre: {genre}")

    # Resolve curves_mode: CLI flag > config file > default "all"
    if curves_mode is None:
        curves_mode = _load_curves_mode_from_config()

    _VALID_CURVES_MODES = {"all", "brightness", "speed", "color", "none"}
    if curves_mode not in _VALID_CURVES_MODES:
        curves_mode = "all"

    # Parse theme overrides
    theme_overrides = None
    if theme_overrides_raw:
        theme_overrides = {}
        for override in theme_overrides_raw:
            if "=" in override:
                label, theme_name = override.split("=", 1)
                # We'll map label to index later in the pipeline
                theme_overrides[label.strip()] = theme_name.strip()

    # Parse tiers filter
    _TIER_NAMES = {
        "base": 1, "geo": 2, "type": 3, "beat": 4,
        "fidelity": 5, "prop": 6, "compound": 7, "hero": 8,
    }
    tiers = None
    if tiers_raw:
        tiers = set()
        for part in tiers_raw.split(","):
            part = part.strip().lower()
            if part in _TIER_NAMES:
                tiers.add(_TIER_NAMES[part])
            elif part.isdigit() and 1 <= int(part) <= 8:
                tiers.add(int(part))
            else:
                raise click.BadParameter(
                    f"Unknown tier '{part}'. Use 1-8 or: {', '.join(_TIER_NAMES)}",
                    param_hint="--tiers",
                )

    config = GenerationConfig(
        audio_path=audio_path,
        layout_path=layout_path,
        output_dir=Path(output_dir) if output_dir else None,
        genre=genre,
        occasion=occasion,
        force_reanalyze=fresh,
        target_sections=[target_section] if target_section else None,
        tiers=tiers,
        story_path=Path(story_path) if story_path else None,
        curves_mode=curves_mode,
    )

    tiers_label = ", ".join(sorted(
        n for n, t in _TIER_NAMES.items() if tiers and t in tiers
    )) if tiers else "all"

    click.echo(f"\nGenerating sequence for: {audio_path.name}")
    click.echo(f"Layout: {layout_path.name}")
    click.echo(f"Genre: {genre} | Occasion: {occasion} | Tiers: {tiers_label}")
    click.echo("")

    output_path = generate_sequence(config)

    click.echo(f"\n✓ Sequence written: {output_path}")
    click.echo(fseq_guidance(output_path))


@cli.command("generate-wizard")
@click.argument("audio_file", required=False, default=None,
                type=click.Path(dir_okay=False))
def generate_wizard_cmd(audio_file):
    """Interactive wizard for sequence generation."""
    from src.generator_wizard import GenerationWizard
    from src.generator.plan import generate_sequence
    from src.generator.xsq_writer import fseq_guidance

    audio_path = Path(audio_file) if audio_file else None

    wizard = GenerationWizard()
    config = wizard.run(audio_path=audio_path)

    if config is None:
        raise SystemExit(130)

    click.echo(f"\nGenerating sequence for: {config.audio_path.name}")
    click.echo(f"Genre: {config.genre} | Occasion: {config.occasion}")
    click.echo("")

    output_path = generate_sequence(config)

    click.echo(f"\n✓ Sequence written: {output_path}")
    click.echo(fseq_guidance(output_path))


@cli.command("chord-stats")
@click.argument("analysis_json", type=click.Path(exists=True, dir_okay=False))
def chord_stats_cmd(analysis_json: str) -> None:
    """Show chordino change frequency and label distribution from an analysis JSON."""
    from src.analyzer.result import TimingMark

    try:
        data = json.loads(Path(analysis_json).read_text(encoding="utf-8"))
    except Exception as exc:
        click.echo(f"ERROR: Cannot read {analysis_json}: {exc}", err=True)
        sys.exit(1)

    # Support both hierarchy (schema 2.0.0) and flat analysis formats
    marks: list[TimingMark] = []
    source_name = ""
    duration_ms = 0
    estimated_bpm = 0.0

    if data.get("schema_version") == "2.0.0":
        # Hierarchy format — chords are in the top-level "chords" field
        source_name = Path(data.get("source_file", analysis_json)).name
        duration_ms = data.get("duration_ms", 0)
        estimated_bpm = data.get("estimated_bpm", 0.0)
        chords = data.get("chords")
        if chords and isinstance(chords, dict):
            raw_marks = chords.get("marks", [])
            marks = [
                TimingMark(
                    time_ms=m["time_ms"],
                    confidence=m.get("confidence"),
                    label=m.get("label"),
                )
                for m in raw_marks
            ]
    else:
        # Flat AnalysisResult format
        try:
            result = export_mod.read(analysis_json)
        except Exception as exc:
            click.echo(f"ERROR: Cannot parse {analysis_json}: {exc}", err=True)
            sys.exit(1)
        source_name = result.filename
        duration_ms = result.duration_ms
        estimated_bpm = result.estimated_tempo_bpm or 0.0
        tracks = [t for t in result.timing_tracks if t.name == "chordino_chords"]
        if tracks:
            marks = tracks[0].marks

    if not marks:
        click.echo("No chordino chord data found in this analysis.", err=True)
        sys.exit(1)

    click.echo(f"\nSource: {source_name}  ({_format_duration(duration_ms)})")
    click.echo(f"Chordino changes: {len(marks)}")

    if len(marks) >= 2:
        intervals = [
            marks[i + 1].time_ms - marks[i].time_ms
            for i in range(len(marks) - 1)
        ]
        avg_ms = sum(intervals) / len(intervals)
        min_ms = min(intervals)
        max_ms = max(intervals)
        click.echo(f"Avg interval:     {avg_ms:.0f} ms  ({avg_ms / 1000:.2f} s)")
        click.echo(f"Min / Max:        {min_ms} ms / {max_ms} ms")
        if estimated_bpm:
            beat_ms = 60_000 / estimated_bpm
            click.echo(f"Beats per change: {avg_ms / beat_ms:.1f}  (at {estimated_bpm} BPM)")
    elif len(marks) == 1:
        click.echo("Only one chord detected — interval stats not available.")

    labels = [m.label for m in marks if m.label]
    if labels:
        from collections import Counter
        counts = Counter(labels).most_common()
        click.echo(f"\nLabel distribution ({len(labels)} labelled / {len(marks)} total):")
        for label, count in counts:
            pct = count / len(marks) * 100
            bar = "#" * int(pct / 2)
            click.echo(f"  {label:<14}  {count:>4}  ({pct:4.1f}%)  {bar}")
    else:
        click.echo("\nNo labels on marks (chordino output may not include chord names).")


# ──────────────────────────────────────────────────────────────────────────────
# cross-song parameter tuning commands
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("tune")
@click.argument("audio_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--batch", "-b", type=int, default=None,
              help="Run a specific batch (1-4). Omit to run all sequentially.")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output directory for tuning results")
@click.option("--sample-duration", type=float, default=30.0,
              help="Duration of audio sample to analyze (seconds)")
@click.option("--sample-start", type=float, default=30.0,
              help="Start offset for audio sample (seconds)")
@click.option("--resume", type=click.Path(exists=True), default=None,
              help="Resume from a previous tuning_session.json")
def tune_cmd(
    audio_files: tuple[str, ...],
    batch: int | None,
    output: str | None,
    sample_duration: float,
    sample_start: float,
    resume: str | None,
) -> None:
    """Run cross-song parameter tuning across multiple audio files.

    Sweeps parameters in prioritized batches (onset detection first, then
    beat/tempo, pitch/melody, and envelope/percussion). Each batch locks
    in optimal values before the next batch runs.

    Examples:

        xlight-analyze tune song1.mp3 song2.mp3 song3.mp3

        xlight-analyze tune *.mp3 --batch 1

        xlight-analyze tune *.mp3 --resume tuning_results/tuning_session.json
    """
    from src.analyzer.cross_song_tuner import (
        CrossSongTuner, OptimalDefaults, TUNING_BATCHES, TuningSession,
    )

    songs = list(audio_files)
    click.echo(f"\nCross-song parameter tuning")
    click.echo(f"  Songs:           {len(songs)}")
    for s in songs:
        click.echo(f"    - {Path(s).name}")
    click.echo(f"  Sample:          {sample_start:.0f}s offset, {sample_duration:.0f}s duration")

    tuner = CrossSongTuner(
        song_paths=songs,
        output_dir=output,
        sample_duration_s=sample_duration,
        sample_start_s=sample_start,
    )

    # Resume from previous session
    if resume:
        prev = TuningSession.read(resume)
        tuner._locked_params = dict(prev.locked_params)
        tuner._session.locked_params = dict(prev.locked_params)
        tuner._session.batch_reports = list(prev.batch_reports)
        completed_ids = {br.batch_id for br in prev.batch_reports}
        click.echo(f"  Resumed:         batches {sorted(completed_ids)} already done")
        click.echo(f"  Locked params:   {prev.locked_params}")

    batches_to_run = [batch] if batch else [b.batch_id for b in TUNING_BATCHES]

    # Skip already-completed batches when resuming
    if resume:
        batches_to_run = [b for b in batches_to_run if b not in completed_ids]

    click.echo(f"  Batches to run:  {batches_to_run}")
    click.echo()

    def _progress(event, *args):
        if event == "song_start":
            idx, total, name, batch_name = args
            click.echo(f"  [{idx}/{total}] {name} — {batch_name}...")
        elif event == "song_done":
            idx, total, name, info = args
            click.echo(f"  [{idx}/{total}] {name} — {info}")

    for bid in batches_to_run:
        from src.analyzer.cross_song_tuner import get_batch
        b = get_batch(bid)
        click.echo(f"{'=' * 60}")
        click.echo(f"BATCH {bid}: {b.name}")
        click.echo(f"  {b.description}")
        params_str = ", ".join(p.name for p in b.params)
        click.echo(f"  Parameters: {params_str}")
        if tuner.locked_params:
            click.echo(f"  Locked from previous: {tuner.locked_params}")
        click.echo()

        report = tuner.run_batch(bid, progress_callback=_progress)

        # Display recommendations
        click.echo(f"\n  Results for Batch {bid}:")
        click.echo(f"  {'PARAMETER':<20} {'OPTIMAL':>10} {'DEFAULT':>10} {'IMPROVE':>10} {'AGREE':>8}")
        click.echo(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*10} {'-'*8}")
        for rec in report.recommendations:
            click.echo(
                f"  {rec.param_name:<20} {rec.optimal_value:>10.4f} "
                f"{rec.default_value:>10.4f} {rec.improvement_pct:>9.1f}% "
                f"{rec.agreement_score:>7.0%}"
            )
            click.echo(f"    {rec.notes}")

        # Lock in optimal values
        newly_locked = tuner.lock_recommendations(report)
        if newly_locked:
            click.echo(f"\n  Locked: {newly_locked}")
        click.echo()

    # Generate final optimal defaults
    defaults = OptimalDefaults.from_session(tuner.session)
    defaults_path = tuner._output_dir / "optimal_defaults.json"
    defaults.write(defaults_path)

    click.echo(f"{'=' * 60}")
    click.echo("OPTIMAL DEFAULTS (across all songs)")
    click.echo(f"  {'PARAMETER':<20} {'VALUE':>12} {'vs DEFAULT':>12}")
    click.echo(f"  {'-'*20} {'-'*12} {'-'*12}")
    for param, value in defaults.params.items():
        meta = defaults.metadata[param]
        change = f"{meta['improvement_pct']:+.1f}%"
        click.echo(f"  {param:<20} {value:>12.4f} {change:>12}")

    click.echo(f"\n  Results saved to: {tuner._output_dir}")
    click.echo(f"  Session:  tuning_session.json")
    click.echo(f"  Defaults: optimal_defaults.json")


@cli.command("tune-status")
@click.argument("session_json", type=click.Path(exists=True))
def tune_status_cmd(session_json: str) -> None:
    """Show the status of a tuning session."""
    from src.analyzer.cross_song_tuner import TuningSession, OptimalDefaults

    session = TuningSession.read(session_json)

    click.echo(f"\nTuning Session: {session.session_id}")
    click.echo(f"  Songs: {', '.join(session.songs)}")
    click.echo(f"  Created: {session.created_at}")
    click.echo(f"  Updated: {session.updated_at}")
    click.echo(f"  Batches completed: {len(session.batch_reports)}/4")

    if session.locked_params:
        click.echo(f"\n  Locked Parameters:")
        for k, v in session.locked_params.items():
            click.echo(f"    {k}: {v}")

    for report in session.batch_reports:
        click.echo(f"\n  Batch {report.batch_id}: {report.batch_name}")
        for rec in report.recommendations:
            arrow = ">>>" if rec.improvement_pct > 5 else "-->" if rec.improvement_pct > 0 else "==="
            click.echo(
                f"    {rec.param_name:<20} {rec.default_value:.4f} {arrow} "
                f"{rec.optimal_value:.4f}  ({rec.improvement_pct:+.1f}%, "
                f"agreement: {rec.agreement_score:.0%})"
            )

    if session.batch_reports:
        defaults = OptimalDefaults.from_session(session)
        click.echo(f"\n  Current optimal defaults:")
        for k, v in defaults.params.items():
            click.echo(f"    {k}: {v}")


@cli.command("tune-apply")
@click.argument("defaults_json", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Show what would change without modifying files")
def tune_apply_cmd(defaults_json: str, dry_run: bool) -> None:
    """Show how to apply optimal defaults to the algorithm configs.

    Reads optimal_defaults.json and displays the algorithm parameter
    updates that would result from applying these values.
    """
    from src.analyzer.cross_song_tuner import OptimalDefaults

    defaults = OptimalDefaults(
        params={}, metadata={}, songs_tested=[], generated_at=""
    )
    import json as _json
    data = _json.loads(Path(defaults_json).read_text(encoding="utf-8"))
    defaults.params = data["optimal_defaults"]
    defaults.metadata = data.get("metadata", {})
    defaults.songs_tested = data.get("songs_tested", [])

    updates = defaults.apply_to_affinity_table()

    click.echo(f"\nOptimal defaults from: {defaults_json}")
    click.echo(f"Songs tested: {', '.join(defaults.songs_tested)}")
    click.echo(f"\nAlgorithm parameter updates:")

    for algo, params in sorted(updates.items()):
        click.echo(f"\n  {algo}:")
        for param, value in sorted(params.items()):
            meta = defaults.metadata.get(param, {})
            default = meta.get("default_value", "?")
            click.echo(f"    {param}: {default} -> {value}")

    if dry_run:
        click.echo("\n  (dry-run — no files modified)")
    else:
        click.echo("\n  To apply: update algorithm default parameters in their class definitions,")
        click.echo("  or pass these values via sweep configs / CLI overrides.")


@cli.command("grouper-edit")
@click.argument("layout_path", type=click.Path(exists=True))
@click.option("--port", default=5173, show_default=True, help="Port for the local review server")
@click.option("--no-browser", is_flag=True, help="Do not open browser automatically")
def grouper_edit_cmd(layout_path: str, port: int, no_browser: bool) -> None:
    """Open the interactive layout group editor in a browser.

    LAYOUT_PATH is the path to xlights_rgbeffects.xml.
    """
    from src.review.server import create_app

    abs_path = str(Path(layout_path).resolve())
    app = create_app()
    url = f"http://localhost:{port}/grouper?path={abs_path}"

    click.echo(f"Starting layout group editor for: {abs_path}")
    click.echo(f"Open in browser: {url}")

    if not no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(host="127.0.0.1", port=port, debug=False)


# ──────────────────────────────────────────────────────────────────────────────
# story command (FR-021)
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# story command (FR-021)
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("story")
@click.argument("audio_path", type=click.Path(dir_okay=False))
@click.option(
    "--output", default=None,
    help="Path to write story JSON (default: <audio_stem>_story.json alongside audio file)",
)
@click.option(
    "--force", is_flag=True, default=False,
    help="Overwrite even if a reviewed story already exists at the output path",
)
@click.option(
    "--review", "launch_review", is_flag=True, default=False,
    help="After generation, launch the story-review server and open browser",
)
def story_cmd(
    audio_path: str,
    output: str | None,
    force: bool,
    launch_review: bool,
) -> None:
    """Build a song story interpretation from an existing hierarchy analysis.

    AUDIO_PATH is the source audio file. The command looks for a matching
    `<stem>_hierarchy.json` file beside the audio file.
    """
    from src.story.builder import build_song_story, write_song_story

    audio_p = Path(audio_path)
    if not audio_p.exists():
        click.echo(f"ERROR: Audio file not found: {audio_path}", err=True)
        sys.exit(1)

    # Locate hierarchy JSON — check beside the audio file, then in a subdirectory
    hierarchy_path = audio_p.parent / (audio_p.stem + "_hierarchy.json")
    if not hierarchy_path.exists():
        # Also check <stem>/<stem>_hierarchy.json (analysis cache directory pattern)
        hierarchy_path = audio_p.parent / audio_p.stem / (audio_p.stem + "_hierarchy.json")
    if not hierarchy_path.exists():
        click.echo(
            f"ERROR: Hierarchy file not found.\n"
            f"  Checked: {audio_p.parent / (audio_p.stem + '_hierarchy.json')}\n"
            f"  Checked: {hierarchy_path}\n"
            "Run 'xlight-analyze analyze' first to generate the hierarchy.",
            err=True,
        )
        sys.exit(1)

    # Determine output path
    if output is None:
        output_path = str(audio_p.parent / (audio_p.stem + "_story.json"))
    else:
        output_path = output

    # Load hierarchy
    click.echo(f"Analyzing sections...")
    try:
        import json as _json
        hierarchy_dict = _json.loads(Path(hierarchy_path).read_text(encoding="utf-8"))
    except Exception as exc:
        click.echo(f"ERROR: Cannot read hierarchy file: {exc}", err=True)
        sys.exit(1)

    # Build song story
    click.echo("Building song story...")
    try:
        story = build_song_story(hierarchy_dict, audio_path)
    except Exception as exc:
        click.echo(f"ERROR: Story build failed: {exc}", err=True)
        sys.exit(2)

    # Write to output (skip overwrite protection when --force)
    if force and Path(output_path).exists():
        # Remove so write_song_story doesn't see a reviewed file
        import json as _json
        try:
            existing = _json.loads(Path(output_path).read_text(encoding="utf-8"))
            if existing.get("review", {}).get("status") == "reviewed":
                # Stamp as draft so write_song_story allows the overwrite
                Path(output_path).unlink()
        except Exception:
            Path(output_path).unlink(missing_ok=True)

    try:
        write_song_story(story, output_path)
    except FileExistsError as exc:
        click.echo(
            f"ERROR: {exc}\nUse --force to overwrite a reviewed story.",
            err=True,
        )
        sys.exit(3)
    except Exception as exc:
        click.echo(f"ERROR: Cannot write story file: {exc}", err=True)
        sys.exit(3)

    click.echo(f"Story written to: {output_path}")

    n_sections = len(story.get("sections", []))
    n_moments = len(story.get("moments", []))
    click.echo(f"  {n_sections} sections, {n_moments} moments detected")

    if launch_review:
        # Delegate to story-review command logic
        ctx = click.get_current_context()
        ctx.invoke(story_review_cmd, story_path=output_path, port=5173, no_browser=False)


# ──────────────────────────────────────────────────────────────────────────────
# story-review command (FR-021, Phase 4)
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("story-review")
@click.argument("story_path", type=click.Path(dir_okay=False))
@click.option("--port", default=5173, help="Port to serve on")
@click.option("--no-browser", is_flag=True, default=False, help="Don't auto-open browser")
def story_review_cmd(story_path: str, port: int, no_browser: bool) -> None:
    """Open the song story review UI in the browser.

    STORY_PATH is the path to a *_story.json or *_story_reviewed.json file.
    The server prefers *_story_reviewed.json if it exists alongside *_story.json.
    """
    from src.review.server import create_app

    story_p = Path(story_path).resolve()

    # If user passed an audio file instead of a story JSON, find the story
    if story_p.suffix.lower() in (".mp3", ".wav", ".flac", ".ogg", ".m4a"):
        for candidate_name in (
            story_p.stem + "_story_reviewed.json",
            story_p.stem + "_story.json",
        ):
            candidate = story_p.parent / candidate_name
            if candidate.exists():
                story_p = candidate
                break
        else:
            click.echo(
                f"ERROR: No story file found for {story_p.name}\n"
                f"Run 'story' command first to generate one.",
                err=True,
            )
            sys.exit(4)

    if not story_p.exists():
        click.echo(f"ERROR: Story file not found: {story_path}", err=True)
        sys.exit(4)

    app = create_app()
    url = f"http://127.0.0.1:{port}/story-review?path={story_p}"
    click.echo(f"Starting story review UI at {url}")
    click.echo("Press Ctrl-C to stop.")

    if not no_browser:
        threading.Timer(0.5, webbrowser.open, args=[url]).start()

    try:
        app.run(host="127.0.0.1", port=port, use_reloader=False, debug=False)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            click.echo(
                f"ERROR: Port {port} is already in use.\n"
                "Kill the process using that port or use --port to choose another.",
                err=True,
            )
            sys.exit(5)
        raise


# ──────────────────────────────────────────────────────────────────────────────
# variant subcommand group (FR-028)
# ──────────────────────────────────────────────────────────────────────────────

_variant_library_override = None
_variant_effect_library_override = None
_variant_custom_dir_override = None


def _get_variant_lib():
    if _variant_library_override is not None:
        return _variant_library_override
    from src.variants.library import load_variant_library
    return load_variant_library(effect_library=_get_variant_effect_lib())


def _get_variant_effect_lib():
    if _variant_effect_library_override is not None:
        return _variant_effect_library_override
    from src.effects.library import load_effect_library
    return load_effect_library()


def _get_variant_custom_dir() -> Path:
    if _variant_custom_dir_override is not None:
        return Path(_variant_custom_dir_override)
    return Path.home() / ".xlight" / "custom_variants"


@cli.group("variant")
def variant_group() -> None:
    """Manage the effect variant library."""


@variant_group.command("list")
@click.option("--effect", default=None, help="Filter by base effect name")
@click.option("--energy", default=None, help="Filter by energy level (low/medium/high)")
@click.option("--tier", default=None, help="Filter by tier affinity")
@click.option("--section", default=None, help="Filter by section role")
@click.option("--prop", default=None, help="(reserved, not yet applied)")
@click.option("--scope", default=None, help="Filter by scope (single-prop/group)")
@click.option("--format", "fmt", default="table", type=click.Choice(["table", "json"]))
def variant_list(
    effect: str | None,
    energy: str | None,
    tier: str | None,
    section: str | None,
    prop: str | None,
    scope: str | None,
    fmt: str,
) -> None:
    """List variants with optional filtering."""
    import json as _json
    lib = _get_variant_lib()
    results = lib.query(
        base_effect=effect,
        energy_level=energy,
        tier_affinity=tier,
        section_role=section,
        scope=scope,
    )
    if fmt == "json":
        click.echo(_json.dumps({"variants": [v.to_dict() for v in results]}, indent=2))
        return
    if not results:
        click.echo("No variants found matching the specified filters.")
        return
    header = f"{'Name':<30} {'Base Effect':<15} {'Energy':<10} {'Tier':<12} {'Scope':<12} {'Description'}"
    click.echo(header)
    click.echo("-" * len(header))
    for v in results:
        click.echo(
            f"{v.name:<30} {v.base_effect:<15} "
            f"{(v.tags.energy_level or ''):<10} "
            f"{(v.tags.tier_affinity or ''):<12} "
            f"{(v.tags.scope or ''):<12} "
            f"{v.description}"
        )


@variant_group.command("show")
@click.argument("name")
def variant_show(name: str) -> None:
    """Show full detail for a variant by name."""
    lib = _get_variant_lib()
    effect_lib = _get_variant_effect_lib()
    v = lib.get(name)
    if v is None:
        click.echo(f"ERROR: Variant not found: {name}", err=True)
        sys.exit(1)
    click.echo(f"Name:          {v.name}")
    click.echo(f"Base Effect:   {v.base_effect}")
    click.echo(f"Description:   {v.description}")
    click.echo(f"Energy Level:  {v.tags.energy_level}")
    click.echo(f"Tier Affinity: {v.tags.tier_affinity}")
    click.echo(f"Speed Feel:    {v.tags.speed_feel}")
    click.echo(f"Direction:     {v.tags.direction}")
    click.echo(f"Section Roles: {', '.join(v.tags.section_roles)}")
    click.echo(f"Scope:         {v.tags.scope}")
    click.echo(f"Genre Affinity:{v.tags.genre_affinity}")
    click.echo(f"Parameter Overrides:")
    for k, val in v.parameter_overrides.items():
        click.echo(f"  {k} = {val}")
    base_defn = effect_lib.get(v.base_effect)
    if base_defn:
        click.echo(f"Base Effect Info:")
        click.echo(f"  Category:     {base_defn.category}")
        click.echo(f"  Layer Role:   {base_defn.layer_role}")
        click.echo(f"  Duration Type:{base_defn.duration_type}")
        click.echo(f"  Prop Suitability: {base_defn.prop_suitability}")


@variant_group.command("coverage")
@click.option("--format", "fmt", default="table", type=click.Choice(["table", "json"]))
def variant_coverage(fmt: str) -> None:
    """Show variant coverage by base effect."""
    import json as _json
    lib = _get_variant_lib()
    effect_lib = _get_variant_effect_lib()

    by_effect: dict[str, list] = {}
    for v in lib.variants.values():
        by_effect.setdefault(v.base_effect, []).append(v)

    coverage = []
    for effect_name, defn in effect_lib.effects.items():
        variants = by_effect.get(effect_name, [])
        if variants:
            complete = sum(
                1 for v in variants
                if v.tags.energy_level and v.tags.tier_affinity
                and v.tags.scope and v.tags.speed_feel
            )
            tag_completeness = round(complete / len(variants), 2)
        else:
            tag_completeness = 0.0
        coverage.append({
            "effect": effect_name,
            "category": defn.category,
            "variant_count": len(variants),
            "tag_completeness": tag_completeness,
        })

    coverage.sort(key=lambda x: (-x["variant_count"], x["effect"]))
    total = sum(x["variant_count"] for x in coverage)

    if fmt == "json":
        click.echo(_json.dumps({
            "coverage": coverage,
            "total_variants": total,
            "effects_with_variants": sum(1 for x in coverage if x["variant_count"] > 0),
            "effects_without_variants": sum(1 for x in coverage if x["variant_count"] == 0),
        }, indent=2))
        return

    click.echo(f"{'Effect':<20} {'Category':<15} {'Variants':>8}  {'Tag Complete':>12}")
    click.echo("-" * 60)
    for entry in coverage:
        if entry["variant_count"] > 0:
            click.echo(
                f"{entry['effect']:<20} {entry['category']:<15} "
                f"{entry['variant_count']:>8}  {entry['tag_completeness']:>12.0%}"
            )
    click.echo(f"\nTotal variants: {total}")


@variant_group.command("import")
@click.argument("xsq_path", type=click.Path(exists=True, dir_okay=False))
@click.option("--dry-run", is_flag=True, default=False, help="Preview without saving")
@click.option("--skip-duplicates", is_flag=True, default=False, help="Omit duplicates from output")
@click.option("--format", "fmt", default="table", type=click.Choice(["table", "json"]))
def variant_import(xsq_path: str, dry_run: bool, skip_duplicates: bool, fmt: str) -> None:
    """Import effect variants from an .xsq sequence file."""
    import json as _json
    from src.variants.importer import extract_variants_from_xsq

    lib = _get_variant_lib()
    effect_lib = _get_variant_effect_lib()
    custom_dir = _get_variant_custom_dir()

    try:
        results = extract_variants_from_xsq(
            xsq_path,
            effect_lib,
            skip_duplicates=skip_duplicates,
            existing_library=lib if not dry_run else None,
            dry_run=dry_run,
            custom_dir=custom_dir,
        )
    except ValueError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    if fmt == "json":
        click.echo(_json.dumps(results, indent=2))
    else:
        if not results:
            click.echo("No variants found in file.")
        else:
            click.echo(f"{'Status':<12} {'Name':<35} {'Base Effect':<15} {'Params':>6}")
            click.echo("-" * 72)
            for r in results:
                click.echo(
                    f"{r['status']:<12} {r['name']:<35} {r['base_effect']:<15} "
                    f"{len(r['parameter_overrides']):>6}"
                )

    imported = sum(1 for r in results if r["status"] == "imported")
    duplicates = sum(1 for r in results if r["status"] == "duplicate")
    unknown = sum(1 for r in results if r["status"] == "unknown")
    click.echo(f"Imported: {imported} | Duplicates: {duplicates} | Unknown: {unknown}")


@variant_group.command("create")
@click.option("--name", required=True, help="Variant name")
@click.option("--effect", "--base-effect", "base_effect", default=None, help="Base effect name")
@click.option("--description", default="", help="Description")
@click.option("--from-file", "from_file", default=None, type=click.Path(exists=True, dir_okay=False))
def variant_create(
    name: str,
    base_effect: str | None,
    description: str,
    from_file: str | None,
) -> None:
    """Create a new custom variant."""
    import json as _json
    from src.variants.validator import validate_variant
    from src.variants.models import EffectVariant

    custom_dir = _get_variant_custom_dir()
    lib = _get_variant_lib()
    effect_lib = _get_variant_effect_lib()

    if from_file:
        data = _json.loads(Path(from_file).read_text(encoding="utf-8"))
    else:
        data = {"name": name, "base_effect": base_effect or "", "description": description,
                "parameter_overrides": {}, "tags": {}}

    if not from_file and not data.get("parameter_overrides"):
        click.echo("WARNING: Creating variant with no parameter overrides (identical to base effect defaults)", err=True)

    # CLI flags override file contents
    data["name"] = name
    if base_effect:
        data["base_effect"] = base_effect
    if description:
        data["description"] = description

    errors = validate_variant(data, effect_lib)
    if errors:
        for e in errors:
            click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    if lib.get(data["name"]) is not None:
        click.echo(f"ERROR: Variant '{data['name']}' already exists", err=True)
        sys.exit(1)

    variant = EffectVariant.from_dict(data)
    lib.save_custom_variant(variant, custom_dir)
    click.echo(f"Created variant '{variant.name}'")


@variant_group.command("edit")
@click.argument("name")
@click.option("--from-file", "from_file", required=True, type=click.Path(exists=True, dir_okay=False))
def variant_edit(name: str, from_file: str) -> None:
    """Edit an existing custom variant from a JSON file."""
    import json as _json
    from src.variants.validator import validate_variant
    from src.variants.models import EffectVariant

    custom_dir = _get_variant_custom_dir()
    lib = _get_variant_lib()
    effect_lib = _get_variant_effect_lib()

    existing = lib.get(name)
    if existing is None:
        click.echo(f"ERROR: Variant '{name}' not found", err=True)
        sys.exit(1)

    if existing.name in lib.builtin_names:
        click.echo(f"ERROR: Cannot edit built-in variant '{name}'", err=True)
        sys.exit(1)

    data = _json.loads(Path(from_file).read_text(encoding="utf-8"))
    data["name"] = existing.name

    errors = validate_variant(data, effect_lib)
    if errors:
        for e in errors:
            click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)

    variant = EffectVariant.from_dict(data)
    lib.save_custom_variant(variant, custom_dir)
    click.echo(f"Updated variant '{variant.name}'")


@variant_group.command("delete")
@click.argument("name")
@click.option("--yes", is_flag=True, default=False, help="Skip confirmation prompt")
def variant_delete(name: str, yes: bool) -> None:
    """Delete a custom variant."""
    custom_dir = _get_variant_custom_dir()
    lib = _get_variant_lib()

    existing = lib.get(name)
    if existing is None:
        click.echo(f"ERROR: Variant '{name}' not found", err=True)
        sys.exit(1)

    if existing.name in lib.builtin_names:
        click.echo(f"ERROR: Cannot delete built-in variant '{name}'", err=True)
        sys.exit(1)

    if not yes:
        click.confirm(f"Delete variant '{existing.name}'?", abort=True)

    lib.delete_custom_variant(name, custom_dir)
    click.echo(f"Deleted variant '{existing.name}'")


@cli.command("rotation-report")
@click.argument("plan_path", type=click.Path(exists=True))
@click.option("--section", default=None, help="Filter to section label")
@click.option("--group", default=None, help="Filter to group name")
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
def rotation_report_cmd(plan_path: str, section: str | None, group: str | None, fmt: str) -> None:
    """Display the rotation plan for a generated sequence."""
    with open(plan_path) as f:
        data = json.load(f)

    rp = data.get("rotation_plan")
    if not rp:
        click.echo("No rotation plan found in this file.", err=True)
        raise SystemExit(2)

    entries = rp.get("entries", [])

    # Apply filters
    if section:
        entries = [e for e in entries if e["section_label"] == section]
    if group:
        entries = [e for e in entries if e["group_name"] == group]

    if fmt == "json":
        click.echo(json.dumps({"rotation_plan": {**rp, "entries": entries}}, indent=2))
    else:
        # Table format
        click.echo(
            f"{'Section':<15} {'Group':<25} {'Variant':<25} {'Score':>6}  {'Top Factors'}"
        )
        click.echo("\u2500" * 100)
        for e in entries:
            bd = e.get("score_breakdown", {})
            top = sorted(bd.items(), key=lambda x: x[1], reverse=True)[:2]
            factors = ", ".join(f"{k}={v:.2f}" for k, v in top)
            click.echo(
                f"{e['section_label']:<15} {e['group_name']:<25} "
                f"{e['variant_name']:<25} {e['score']:>6.2f}  {factors}"
            )

        # Summary
        sym = rp.get("symmetry_pairs", [])
        unique_variants = len(set(e["variant_name"] for e in entries))
        click.echo(f"\nSymmetry pairs: {len(sym)}")
        click.echo(
            f"Sections: {rp.get('sections_count', 0)} | "
            f"Groups: {rp.get('groups_count', 0)} | "
            f"Unique variants: {unique_variants}"
        )


def main() -> None:
    cli()
