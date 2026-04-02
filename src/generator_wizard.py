"""Interactive wizard for sequence generation."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import click

from src.generator.models import GenerationConfig, SequencePlan, SectionAssignment
from src.generator.plan import read_song_metadata
from src.themes.models import VALID_OCCASIONS


class GenerationWizard:
    """Guides the user through sequence generation setup.

    Follows the WizardRunner pattern from src/wizard.py:
    step methods with questionary prompts, returning a config dataclass.
    """

    def detect_metadata(self, audio_path: Path) -> dict[str, str]:
        """Read song metadata from ID3 tags via mutagen.

        Returns dict with title, artist, genre (best-effort).
        """
        profile = read_song_metadata(audio_path)
        return {"title": profile.title, "artist": profile.artist, "genre": profile.genre}

    def build_config(
        self,
        audio_path: Path,
        layout_path: Path,
        genre: Optional[str] = None,
        occasion: Optional[str] = None,
        output_dir: Optional[Path] = None,
        force_reanalyze: bool = False,
        curves_mode: str = "all",
    ) -> GenerationConfig:
        """Build a GenerationConfig from provided or default values."""
        if genre is None:
            metadata = self.detect_metadata(audio_path)
            genre = metadata["genre"]
        if occasion is None:
            occasion = "general"

        return GenerationConfig(
            audio_path=audio_path,
            layout_path=layout_path,
            output_dir=output_dir,
            genre=genre,
            occasion=occasion,
            force_reanalyze=force_reanalyze,
            curves_mode=curves_mode,
        )

    def show_plan_preview(self, plan: SequencePlan) -> None:
        """Display a rich table showing section-to-theme mappings."""
        try:
            from rich.console import Console
            from rich.table import Table

            console = Console()
            table = Table(title="Generation Plan", show_lines=True)
            table.add_column("Section", style="bold")
            table.add_column("Time Range")
            table.add_column("Energy", justify="right")
            table.add_column("Mood")
            table.add_column("Theme", style="cyan")
            table.add_column("Colors")

            for assignment in plan.sections:
                s = assignment.section
                t = assignment.theme
                start = f"{s.start_ms / 1000:.1f}s"
                end = f"{s.end_ms / 1000:.1f}s"
                colors = " ".join(t.palette[:4])
                table.add_row(
                    s.label.capitalize(),
                    f"{start} — {end}",
                    str(s.energy_score),
                    s.mood_tier,
                    t.name,
                    colors,
                )

            console.print(table)

            # Group-to-effect summary
            effect_counts: dict[str, int] = {}
            for assignment in plan.sections:
                for group_name, placements in assignment.group_effects.items():
                    effect_counts[group_name] = effect_counts.get(group_name, 0) + len(placements)

            if effect_counts:
                click.echo("\nEffects per group:")
                for group, count in sorted(effect_counts.items()):
                    click.echo(f"  {group}: {count} effects")
                click.echo("")

        except ImportError:
            # Fallback without rich
            click.echo("\nGeneration Plan:")
            for assignment in plan.sections:
                s = assignment.section
                click.echo(
                    f"  {s.label:>8s} ({s.start_ms/1000:.1f}s-{s.end_ms/1000:.1f}s) "
                    f"energy={s.energy_score} mood={s.mood_tier} "
                    f"theme={assignment.theme.name}"
                )
            click.echo("")

    def prompt_theme_overrides(
        self, plan: SequencePlan
    ) -> Optional[dict[int, str]]:
        """Prompt the user to override theme assignments for specific sections.

        Returns dict of section_index -> theme_name, or None if no changes.
        """
        try:
            import questionary
        except ImportError:
            return None

        change = questionary.confirm(
            "Would you like to change any theme assignments?", default=False
        ).ask()
        if not change:
            return None

        from src.themes.library import load_theme_library

        theme_lib = load_theme_library()
        all_theme_names = sorted(theme_lib.themes.keys())

        overrides: dict[int, str] = {}
        for i, assignment in enumerate(plan.sections):
            s = assignment.section
            current = assignment.theme.name
            new_theme = questionary.select(
                f"  {s.label} ({s.mood_tier}) — current: {current}",
                choices=["(keep)"] + all_theme_names,
                default="(keep)",
            ).ask()
            if new_theme is None:
                return None
            if new_theme != "(keep)":
                overrides[i] = new_theme

        return overrides if overrides else None

    def run(self, audio_path: Optional[Path] = None) -> Optional[GenerationConfig]:
        """Execute the interactive wizard flow.

        Returns GenerationConfig or None if cancelled.
        """
        if not _detect_tty():
            return None

        try:
            import questionary

            # Step 1: Audio file
            if audio_path is None or not audio_path.exists():
                audio_str = questionary.path(
                    "MP3 file:",
                    validate=lambda p: Path(p).exists() and Path(p).suffix.lower() == ".mp3",
                ).ask()
                if audio_str is None:
                    return None
                audio_path = Path(audio_str)

            # Step 2: Layout file
            layout_str = questionary.path(
                "xLights layout file (xlights_rgbeffects.xml):",
                validate=lambda p: Path(p).exists(),
            ).ask()
            if layout_str is None:
                return None
            layout_path = Path(layout_str)

            # Report layout info
            try:
                from src.grouper.layout import parse_layout
                from src.grouper.grouper import generate_groups

                layout = parse_layout(layout_path)
                groups = generate_groups(layout.props)
                click.echo(f"\n  Found {len(layout.props)} models, {len(groups)} power groups\n")
            except Exception:
                click.echo("\n  (Could not parse layout for preview)\n")

            # Step 3: Metadata detection
            metadata = self.detect_metadata(audio_path)
            click.echo(f"  Detected: {metadata['title']} — {metadata['artist']}")
            click.echo(f"  Genre: {metadata['genre']}")

            genre = questionary.text(
                "Genre:",
                default=metadata["genre"],
            ).ask()
            if genre is None:
                return None

            # Step 4: Occasion
            occasion = questionary.select(
                "Occasion:",
                choices=VALID_OCCASIONS,
                default="general",
            ).ask()
            if occasion is None:
                return None

            # Step 5: Value curves mode
            curves_mode = questionary.select(
                "Value curves:",
                choices=["all", "brightness", "speed", "color", "none"],
                default="all",
            ).ask()
            if curves_mode is None:
                return None

            # Step 6: Confirm
            click.echo(f"\n  Audio:    {audio_path.name}")
            click.echo(f"  Layout:   {layout_path.name}")
            click.echo(f"  Genre:    {genre}")
            click.echo(f"  Occasion: {occasion}")
            click.echo(f"  Curves:   {curves_mode}")

            proceed = questionary.confirm("Generate sequence?", default=True).ask()
            if not proceed:
                return None

            return self.build_config(
                audio_path=audio_path,
                layout_path=layout_path,
                genre=genre,
                occasion=occasion,
                curves_mode=curves_mode,
            )

        except KeyboardInterrupt:
            return None


def _detect_tty() -> bool:
    """Check if stdin is a TTY (interactive terminal)."""
    return hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
