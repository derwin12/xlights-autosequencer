"""Microscope panel runner.

Drives ``run_song`` over a manifest of CC0 fixtures and returns the
``MicroscopeResult`` list in manifest order. The only public entry point
is :func:`run_panel`.

Fixture resolution: each slug must be present at
``tests/fixtures/cc0_music/<slug>.mp3``. If any are missing, the panel
calls :func:`tests.validation.download_fixtures.download_all` exactly
once for the entire run, then re-checks. A still-missing slug raises
``FileNotFoundError`` rather than silently dropping the song.

Parallelism: ``parallel=True`` runs ``run_song`` calls in a
``ProcessPoolExecutor`` with ``max_workers=3``. ``MicroscopeResult`` and
the ``SequenceSummary`` it carries are frozen dataclasses with
JSON-friendly fields, so they pickle cleanly across process boundaries.
"""
from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path
from typing import Any

from src.microscope.runner import MicroscopeResult, run_song

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CC0_DIR = _REPO_ROOT / "tests" / "fixtures" / "cc0_music"


def _resolve_slug_paths(slugs: list[str]) -> tuple[dict[str, Path], list[str]]:
    """Return ``(resolved, missing)`` for the given slug list."""
    resolved: dict[str, Path] = {}
    missing: list[str] = []
    for slug in slugs:
        candidate = _CC0_DIR / f"{slug}.mp3"
        if candidate.is_file():
            resolved[slug] = candidate
        else:
            missing.append(slug)
    return resolved, missing


def run_panel(
    manifest_path: str | Path,
    output_dir: str | Path,
    config_overrides: dict[str, Any] | None = None,
    parallel: bool = False,
) -> list[MicroscopeResult]:
    """Run the microscope over every slug listed in a panel manifest.

    Args:
        manifest_path: JSON file describing the panel. Required keys:
            ``slugs`` (list of CC0 slugs) and ``layout`` (path to the
            xLights layout XML, resolved relative to the repo root).
        output_dir: Per-song XSQ artifacts are written under
            ``output_dir/microscope/<slug>/``.
        config_overrides: Forwarded verbatim to every ``run_song`` call.
        parallel: When ``True``, fan out across a
            ``ProcessPoolExecutor`` with ``max_workers=3``. Results are
            re-ordered to match the manifest's slug list.

    Returns:
        List of :class:`MicroscopeResult` in manifest order.

    Raises:
        FileNotFoundError: Manifest, layout, or a fixture MP3 is missing
            after the one ``download_all`` retry.
        json.JSONDecodeError: Manifest is not valid JSON.
    """
    manifest_path_obj = Path(manifest_path)
    if not manifest_path_obj.is_file():
        raise FileNotFoundError(f"Panel manifest not found: {manifest_path_obj}")

    manifest = json.loads(manifest_path_obj.read_text())
    slugs: list[str] = list(manifest["slugs"])
    layout_rel = manifest["layout"]

    layout_path = (_REPO_ROOT / layout_rel).resolve()
    if not layout_path.is_file():
        raise FileNotFoundError(f"Layout file not found: {layout_path}")

    resolved, missing = _resolve_slug_paths(slugs)
    if missing:
        # Single fixture-download retry for the whole run.
        from tests.validation.download_fixtures import download_all

        download_all()
        resolved, missing = _resolve_slug_paths(slugs)
        if missing:
            raise FileNotFoundError(
                "Missing CC0 fixture(s) after download_all(): "
                + ", ".join(missing)
            )

    output_dir_obj = Path(output_dir)

    if not parallel:
        return [
            run_song(resolved[slug], layout_path, output_dir_obj, config_overrides)
            for slug in slugs
        ]

    results: list[MicroscopeResult | None] = [None] * len(slugs)
    with concurrent.futures.ProcessPoolExecutor(max_workers=3) as pool:
        future_to_index = {
            pool.submit(
                run_song,
                resolved[slug],
                layout_path,
                output_dir_obj,
                config_overrides,
            ): idx
            for idx, slug in enumerate(slugs)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            idx = future_to_index[future]
            results[idx] = future.result()

    # All slots filled — narrow the type for the caller.
    return [r for r in results if r is not None]
