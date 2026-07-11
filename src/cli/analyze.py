"""Analyze, full, and wizard commands."""
from __future__ import annotations

import sys
from pathlib import Path

import click

from src.cli import cli
from src.cli.helpers import _format_duration, _print_summary_table, _rich_error


# ──────────────────────────────────────────────────────────────────────────────
# analyze command
# ──────────────────────────────────────────────────────────────────────────────

@cli.command("analyze")
@click.argument("path", type=click.Path(exists=True))
@click.option("--fresh", is_flag=True, default=False, help="Ignore cache and re-run analysis")
@click.option("--dry-run", is_flag=True, default=False, help="Show what would run without executing")
@click.option(
    "--profile", "profile", default=None,
    type=click.Choice(["quick", "standard", "full"], case_sensitive=False),
    help="Analysis preset: quick (librosa-only, fast), standard (auto-detect), full (all available)",
)
def analyze_cmd(
    path: str,
    fresh: bool,
    dry_run: bool,
    profile: str | None,
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
                result = run_orchestrator(str(mp3), fresh=fresh, dry_run=dry_run, profile=profile)
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
        run_orchestrator(str(input_path), fresh=fresh, dry_run=dry_run, profile=profile)
    except SystemExit:
        raise
    except FileNotFoundError as exc:
        msg = str(exc)
        if "ffmpeg" in msg.lower():
            click.echo(_rich_error(
                msg,
                causes=["ffmpeg is not installed or not in PATH"],
                fixes=[
                    "macOS:   brew install ffmpeg",
                    "Linux:   sudo apt-get install ffmpeg",
                    "Windows: choco install ffmpeg",
                ],
            ), err=True)
        else:
            click.echo(_rich_error(
                msg,
                fixes=["Check the file path and try again"],
            ), err=True)
        sys.exit(1)
    except PermissionError as exc:
        click.echo(_rich_error(
            f"Cannot write output: {exc}",
            fixes=[
                "Check write permissions on the output directory",
                "Try specifying a different output path with --output",
            ],
        ), err=True)
        sys.exit(3)
    except MemoryError:
        click.echo(_rich_error(
            "Out of memory during analysis",
            causes=[
                "Audio file is very large",
                "Too many algorithms running in parallel",
                "Stem separation requires significant memory",
            ],
            fixes=[
                "Close other applications and retry",
                "Try analyzing without stems: xlight-analyze analyze song.mp3",
                "Use a shorter audio file or reduce quality settings",
            ],
        ), err=True)
        sys.exit(2)
    except Exception as exc:
        click.echo(_rich_error(
            f"Analysis failed: {exc}",
            fixes=[
                "Re-run with XLIGHT_VERBOSE=1 for full traceback",
                "Check that all dependencies are installed: pip install -r requirements.txt",
                "See docs/troubleshooting.md for common issues",
            ],
        ), err=True)
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
    """Bridge WizardConfig selections -> analyze_cmd (FR-014 flag parity, T020)."""
    from src.wizard import WizardConfig  # noqa: F401 — type reference

    # T020: use_existing -> load cached result directly, skip analysis
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
    from src.cli.review import review_cmd

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
