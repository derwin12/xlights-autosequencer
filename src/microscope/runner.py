"""Microscope per-song runner.

Generates a sequence with production-parity ``GenerationConfig`` defaults
(plus a pinned ``variation_seed`` for determinism), parses the resulting
XSQ, and computes every registered metric over the parsed
``SequenceSummary``.

The runner intentionally measures the on-disk XSQ rather than the
in-memory ``SequencePlan`` so that XSQ-writer bugs are visible to the
microscope. See OpenSpec change ``visual-quality-microscope`` design.md.
"""
from __future__ import annotations

import dataclasses
import datetime
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.evaluation.models import MetricValue, SequenceSummary
from src.evaluation.xsq_reader import parse
from src.generator.models import GenerationConfig
from src.generator.plan import generate_sequence

logger = logging.getLogger(__name__)


# Default ``variation_seed`` for microscope runs. Pinned so re-running
# without overrides produces byte-identical metrics.
_DEFAULT_VARIATION_SEED = 42

# Allowed ``GenerationConfig`` field names — used to validate
# ``config_overrides`` keys.
_CONFIG_FIELD_NAMES = frozenset(f.name for f in dataclasses.fields(GenerationConfig))

# Path-typed ``GenerationConfig`` fields — coerced via ``Path(...)`` if a
# string is passed in overrides, and excluded from ``config_snapshot``.
_PATH_FIELDS = frozenset({"audio_path", "layout_path", "output_dir", "story_path"})


@dataclass(frozen=True)
class MicroscopeResult:
    """A single song's microscope output: parsed XSQ + computed metrics."""

    slug: str
    audio_path: str          # absolute path string of source MP3
    xsq_path: str            # absolute path string of generated XSQ
    summary: SequenceSummary
    metrics: dict[str, MetricValue]
    generated_at: str        # ISO 8601 UTC, e.g. "2026-04-30T18:00:00Z"
    config_snapshot: dict    # non-path GenerationConfig fields, JSON-serializable

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (excludes the parsed summary)."""
        return {
            "slug": self.slug,
            "audio_path": self.audio_path,
            "xsq_path": self.xsq_path,
            "generated_at": self.generated_at,
            "config_snapshot": self.config_snapshot,
            "metrics": {
                name: {
                    "value": mv.value,
                    "kind": mv.kind,
                    "reliability": mv.reliability,
                }
                for name, mv in self.metrics.items()
            },
        }


def _import_all_metrics() -> None:
    """Import every metric module so the registry is fully populated."""
    import src.evaluation.metrics.pacing  # noqa: F401
    import src.evaluation.metrics.palette  # noqa: F401
    import src.evaluation.metrics.effects  # noqa: F401
    import src.evaluation.metrics.alignment  # noqa: F401
    import src.evaluation.metrics.sections  # noqa: F401
    import src.evaluation.metrics.internal  # noqa: F401
    import src.evaluation.metrics.vitality  # noqa: F401
    import src.evaluation.metrics.suitability  # noqa: F401


def _compute_metrics(
    summary: SequenceSummary,
    audio_context: dict[str, Any],
) -> dict[str, MetricValue]:
    """Run every registered metric. Mirrors compare._compute_metrics_for_summary
    so the microscope and the compare harness see identical metric values
    for the same XSQ.
    """
    from src.evaluation.metrics import get_registry

    registry = get_registry()
    results: dict[str, MetricValue] = {}

    beats: list[int] = audio_context.get("beats", [])
    energy_curve = audio_context.get("energy_curve", [])
    sections = audio_context.get("sections", None)
    window_ms: int = audio_context.get("window_ms", 500)

    for name, defn in registry.items():
        try:
            if name == "placements_per_minute":
                mv = defn.compute(summary)
            elif name == "density_energy_correlation":
                mv = defn.compute(
                    summary, {"energy_curve": energy_curve, "window_ms": window_ms}
                )
            elif name == "palette_top5_colors":
                mv = defn.compute(summary)
            elif name == "per_section_palette_diversity":
                mv = defn.compute(summary, sections)
            elif name == "effect_type_histogram":
                mv = defn.compute(summary)
            elif name == "beat_alignment_pct":
                mv = defn.compute(summary, beats)
            elif name == "section_transition_delta":
                mv = defn.compute(summary, sections)
            elif name == "tier_utilization":
                mv = defn.compute(summary, sections)
            elif name == "theme_assignment_consistency":
                mv = defn.compute(summary, sections)
            else:
                mv = defn.compute(summary)
        except Exception as exc:
            logger.warning("microscope: metric %r raised %s", name, exc)
            mv = MetricValue(
                name=name,
                kind="scalar",
                value=None,
                payload=None,
                reliability="error",
            )
        results[name] = mv

    return results


def _build_config(
    audio_path: Path,
    layout_path: Path,
    output_dir: Path,
    config_overrides: dict[str, Any] | None,
) -> GenerationConfig:
    """Construct the ``GenerationConfig`` for a microscope run.

    Production-parity defaults (``genre="pop"``, ``occasion="general"``,
    ``transition_mode="subtle"``, ``curves_mode="none"``) plus a pinned
    ``variation_seed=42``. Overrides are applied on top and validated
    against the ``GenerationConfig`` field set.
    """
    fields: dict[str, Any] = {
        "audio_path": Path(audio_path),
        "layout_path": Path(layout_path),
        "output_dir": Path(output_dir) / "microscope" / Path(audio_path).stem,
        "genre": "pop",
        "occasion": "general",
        "transition_mode": "subtle",
        "curves_mode": "none",
        "variation_seed": _DEFAULT_VARIATION_SEED,
    }

    if config_overrides:
        unknown = set(config_overrides) - _CONFIG_FIELD_NAMES
        if unknown:
            raise ValueError(
                f"Unknown GenerationConfig field(s) in config_overrides: "
                f"{sorted(unknown)}"
            )
        for key, value in config_overrides.items():
            if key in _PATH_FIELDS and value is not None and not isinstance(value, Path):
                value = Path(value)
            fields[key] = value

    return GenerationConfig(**fields)


def _build_config_snapshot(config: GenerationConfig) -> dict:
    """Return a JSON-serializable dict of non-path config fields."""
    raw = dataclasses.asdict(config)
    snapshot: dict = {}
    for key, value in raw.items():
        if key in _PATH_FIELDS:
            continue
        if isinstance(value, set) or isinstance(value, frozenset):
            snapshot[key] = sorted(value) if all(isinstance(v, str) for v in value) else list(value)
        else:
            snapshot[key] = value
    return snapshot


def run_song(
    audio_path: str | Path,
    layout_path: str | Path,
    output_dir: str | Path,
    config_overrides: dict[str, Any] | None = None,
) -> MicroscopeResult:
    """Generate a sequence for ``audio_path`` and measure the resulting XSQ.

    Args:
        audio_path: Source MP3.
        layout_path: xLights layout XML for prop classification.
        output_dir: Microscope writes the XSQ under
            ``output_dir/microscope/<slug>/sequence.xsq``.
        config_overrides: Optional dict of ``GenerationConfig`` field
            overrides. Unknown keys raise ``ValueError``. Path-typed
            string values are coerced via ``Path(...)``.

    Returns:
        ``MicroscopeResult`` with the parsed ``SequenceSummary`` and a
        dict of every registered metric's ``MetricValue``.
    """
    audio_path_obj = Path(audio_path)
    layout_path_obj = Path(layout_path)
    output_dir_obj = Path(output_dir)

    config = _build_config(
        audio_path=audio_path_obj,
        layout_path=layout_path_obj,
        output_dir=output_dir_obj,
        config_overrides=config_overrides,
    )

    config.output_dir.mkdir(parents=True, exist_ok=True)

    _import_all_metrics()

    xsq_path = generate_sequence(config)
    summary = parse(xsq_path)

    # Microscope measures the XSQ artifact, not the input audio. The
    # audio-context-dependent metrics receive empty defaults; they will
    # produce ``None`` or zero values, which is the documented behaviour
    # for "no audio context available."
    audio_context: dict[str, Any] = {
        "beats": [],
        "energy_curve": [],
        "sections": None,
        "window_ms": 500,
    }
    metrics = _compute_metrics(summary, audio_context)

    generated_at = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    config_snapshot = _build_config_snapshot(config)

    return MicroscopeResult(
        slug=audio_path_obj.stem,
        audio_path=str(audio_path_obj.resolve()),
        xsq_path=str(Path(xsq_path).resolve()),
        summary=summary,
        metrics=metrics,
        generated_at=generated_at,
        config_snapshot=config_snapshot,
    )
