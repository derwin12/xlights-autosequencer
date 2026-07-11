"""Deterministic wrapper around the xLights sequence generator."""
from __future__ import annotations

import io
import random
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np


class GeneratorError(Exception):
    """Raised when the generator pipeline fails."""


def _derive_seed(audio_hash: str) -> int:
    """Derive a deterministic integer seed from an audio hash string.

    audio_hash format: "md5:3f4b..." — take first 8 hex chars after the prefix.
    """
    hex_part = audio_hash.removeprefix("md5:")[:8]
    return int(hex_part, 16)


def run(
    song_id: str,
    audio_path: Path | str,
    audio_hash: str,
    layout_path: Optional[Path] = None,
    theme_overrides: Optional[dict[int, str]] = None,
    lyrics: Optional[list[dict]] = None,
) -> bytes:
    """Run the generator deterministically and return .xsq bytes.

    Args:
        song_id: The song identifier (used for logging / diagnostics).
        audio_path: Path to the source MP3 or WAV.
        audio_hash: "md5:..." hash string used to derive the seed.
        layout_path: Optional path to xlights_rgbeffects.xml layout.
                     If None, reads from settings.
        theme_overrides: Optional {section_index: theme_name} map — forces
                         specific sections to a caller-chosen theme instead
                         of the auto-selected one (see GenerationConfig).
        lyrics: Optional synced-lyrics lines (``{t_ms, duration_ms, text}``)
                embedded as a "Lyrics" timing track in the output .xsq.

    Returns:
        Raw .xsq XML bytes.

    Raises:
        GeneratorError: If the generator pipeline fails.
    """
    audio_path = Path(audio_path)

    if not audio_path.exists():
        raise GeneratorError(f"audio_path does not exist: {audio_path}")

    # Resolve layout path
    if layout_path is None:
        try:
            from src.settings import get_layout_path
            layout_path = get_layout_path()
        except Exception as exc:
            raise GeneratorError("No layout path available") from exc

    if layout_path is None:
        raise GeneratorError("No layout path available")

    layout_path = Path(layout_path)
    if not layout_path.exists():
        raise GeneratorError(f"layout_path does not exist: {layout_path}")

    # Seed all RNG sources deterministically from the audio hash
    seed = _derive_seed(audio_hash)
    random.seed(seed)
    np.random.seed(seed % (2**32))

    try:
        return _run_pipeline(audio_path, layout_path, seed, theme_overrides=theme_overrides,
                              lyrics=lyrics)
    except GeneratorError:
        raise
    except Exception as exc:
        raise GeneratorError(f"Generator pipeline failed: {exc}") from exc


def _run_pipeline(
    audio_path: Path,
    layout_path: Path,
    seed: int,
    theme_overrides: Optional[dict[int, str]] = None,
    lyrics: Optional[list[dict]] = None,
) -> bytes:
    """Execute the full generation pipeline and return .xsq bytes."""
    from src.analyzer.orchestrator import run_orchestrator
    from src.effects.library import load_effect_library
    from src.generator.models import GenerationConfig
    from src.generator.plan import build_plan
    from src.generator.xsq_writer import write_xsq
    from src.grouper.classifier import classify_props, normalize_coords
    from src.grouper.grouper import generate_groups
    from src.grouper.layout import parse_layout
    from src.themes.library import load_theme_library
    from src.variants.library import load_variant_library

    # Run analysis (uses cache when available)
    hierarchy = run_orchestrator(str(audio_path), fresh=False)

    # Parse layout
    layout = parse_layout(layout_path)
    props = layout.props
    normalize_coords(props)
    classify_props(props)
    groups = generate_groups(props)

    # Load libraries
    effect_library = load_effect_library()
    variant_library = load_variant_library(effect_library=effect_library)
    theme_library = load_theme_library(
        effect_library=effect_library,
        variant_library=variant_library,
    )

    # Build GenerationConfig — use a temp dir as output_dir so no files leak
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = GenerationConfig(
            audio_path=audio_path,
            layout_path=layout_path,
            output_dir=Path(tmp_dir),
            theme_overrides=theme_overrides,
        )

        # Re-seed after config construction (which may trigger path resolution calls)
        random.seed(seed)
        np.random.seed(seed % (2**32))

        # Build plan
        plan = build_plan(config, hierarchy, props, groups, effect_library, theme_library)

        # Write .xsq to a temp file, then read back as bytes
        output_path = Path(tmp_dir) / "output.xsq"
        write_xsq(plan, output_path, hierarchy=hierarchy, audio_path=audio_path, lyrics=lyrics)

        return output_path.read_bytes()
