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
        click.echo(f"ERROR: File not found: {audio_file}", err=True)
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


def main() -> None:
    cli()
