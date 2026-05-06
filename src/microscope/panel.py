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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.microscope.runner import MicroscopeResult, run_song

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CC0_DIR = _REPO_ROOT / "tests" / "fixtures" / "cc0_music"


@dataclass(frozen=True)
class PanelFixtureResult:
    """Per-fixture panel output: the song's ``MicroscopeResult`` plus the
    panel-level ``tier_intent`` declared for it in the manifest.

    The wrapper keeps tier_intent — which is panel metadata — out of
    ``MicroscopeResult``, which is per-song and reused by single-song
    callers (``microscope run``, ``microscope sensitivity``) that have
    no manifest. See OpenSpec change ``microscope-panel-tier-coverage``
    review feedback for the rationale.
    """

    result: MicroscopeResult
    tier_intent: tuple[str, ...]


@dataclass(frozen=True)
class _ParsedSlug:
    slug: str
    tier_intent: tuple[str, ...]


def _parse_slug_entries(raw_slugs: list) -> list[_ParsedSlug]:
    """Accept either string or {slug, tier_intent} object entries.

    Raises ``ValueError`` (with the offending key/index named) when an
    entry is malformed: missing ``slug`` field, ``tier_intent`` not a
    list, or any other shape we don't recognise.
    """
    parsed: list[_ParsedSlug] = []
    for i, entry in enumerate(raw_slugs):
        if isinstance(entry, str):
            parsed.append(_ParsedSlug(slug=entry, tier_intent=()))
            continue
        if not isinstance(entry, dict):
            raise ValueError(
                f"panel manifest entry [{i}] must be a string slug or "
                f"object with 'slug'; got {type(entry).__name__}"
            )
        slug = entry.get("slug")
        if not isinstance(slug, str) or not slug:
            raise ValueError(
                f"panel manifest entry [{i}] missing 'slug' string field"
            )
        intent = entry.get("tier_intent", [])
        if not isinstance(intent, list) or not all(
            isinstance(t, str) for t in intent
        ):
            raise ValueError(
                f"panel manifest entry [{i}] (slug={slug!r}) has invalid "
                f"'tier_intent': must be a list of tier-prefix strings"
            )
        parsed.append(_ParsedSlug(slug=slug, tier_intent=tuple(intent)))
    return parsed


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
    parsed = _parse_slug_entries(list(manifest["slugs"]))
    slugs: list[str] = [p.slug for p in parsed]
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


def run_panel_with_intent(
    manifest_path: str | Path,
    output_dir: str | Path,
    config_overrides: dict[str, Any] | None = None,
    parallel: bool = False,
) -> list[PanelFixtureResult]:
    """Variant of :func:`run_panel` that also returns each fixture's
    declared ``tier_intent`` from the manifest.

    Used by :mod:`src.microscope.verify` to assert that each fixture's
    actual tier breakdown is a superset of its declared intent.
    Callers that don't need ``tier_intent`` (most of them) can keep
    using :func:`run_panel`.
    """
    manifest_path_obj = Path(manifest_path)
    if not manifest_path_obj.is_file():
        raise FileNotFoundError(f"Panel manifest not found: {manifest_path_obj}")

    manifest = json.loads(manifest_path_obj.read_text())
    parsed = _parse_slug_entries(list(manifest["slugs"]))

    results = run_panel(manifest_path, output_dir, config_overrides, parallel)
    intent_by_slug = {p.slug: p.tier_intent for p in parsed}
    return [
        PanelFixtureResult(result=r, tier_intent=intent_by_slug.get(r.slug, ()))
        for r in results
    ]


def parse_panel_manifest_slugs(manifest_path: str | Path) -> list[_ParsedSlug]:
    """Public-ish helper: read a panel manifest and return the parsed
    slug entries.

    Exposed for the verify-coverage subcommand which needs the slug
    universe and tier_intent without running the panel. Returns
    :class:`_ParsedSlug` tuples; callers should treat the type as
    opaque (slug + tier_intent).
    """
    manifest_path_obj = Path(manifest_path)
    if not manifest_path_obj.is_file():
        raise FileNotFoundError(f"Panel manifest not found: {manifest_path_obj}")
    manifest = json.loads(manifest_path_obj.read_text())
    return _parse_slug_entries(list(manifest["slugs"]))
