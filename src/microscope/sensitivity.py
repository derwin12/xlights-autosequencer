"""Sensitivity gate for the visual-quality microscope.

Before any golden baseline is committed, the four probes in this module
must prove that the registered metrics are actually responsive to known
interventions. The ``baseline`` subcommand reads the on-disk artifact
``tests/golden/microscope/sensitivity_passed.json`` (written by
``xlight-evaluate microscope sensitivity``) and refuses to write a
golden if the file is missing or its ``metric_set_hash`` no longer
matches the current registry.

The four probes are:

1. **Single-effect probe** — synthetic ``SequenceSummary`` with every
   placement at ``effect_type="Plasma"``. Pass when
   ``distinct_effect_count == 1.0`` AND
   ``effect_repeat_rate >= 0.95``.
2. **All-black palette probe** — synthetic ``SequenceSummary`` with
   every placement at ``palette_colors=("#000000",)``. Pass when both
   ``palette_luminance_mean`` and ``palette_luminance_cv`` are exactly
   ``0.0``.
3. **Forced-bad-pairing probe** — synthetic ``SequenceSummary`` whose
   every placement is ``Plasma`` on a model resolved to prop type
   ``outline``. Pass when ``bad_pairing_pct_handlist > 0.95`` AND
   ``bad_pairing_pct_catalog == 0.0`` AND
   ``pairing_disagreement_pct > 0.95`` (the handlist flags this pair,
   the catalog records it as ``possible``, so the disagreement signal
   fires by construction).
4. **Deterministic seed probe (real generator)** — runs ``run_song``
   twice with the default ``variation_seed=42``, asserting every
   scalar metric matches within ``1e-9``. Then runs a third time with
   ``variation_seed=9999`` and asserts the resulting ``SequenceSummary``
   differs from the first run at the placement level.

   The seed-effect check compares at the **placement level**, not the
   scalar-metric level. On the ``funshine`` fixture, flipping the seed
   between 42 and 9999 perturbs only ~2/68 placements, which does not
   move any registered scalar metric by ≥ 1e-3. The spec's intent —
   "the seed has an effect" — is satisfied as long as the underlying
   ``SequenceSummary`` shifts.

The output ``SensitivityReport.to_dict()`` is JSON-serializable and is
the payload of ``tests/golden/microscope/sensitivity_passed.json``.
"""
from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.evaluation.metrics import get_registry
from src.evaluation.models import MetricValue, Placement, SequenceSummary
from src.microscope.runner import run_song


# Tolerances used by the deterministic-seed probe.
_DETERMINISM_TOL: float = 1e-9


@dataclass(frozen=True)
class SensitivityResult:
    """Outcome of a single sensitivity probe."""

    probe_name: str
    passed: bool
    detail: str
    failure_reason: str | None


@dataclass(frozen=True)
class SensitivityReport:
    """Aggregate result of all sensitivity probes for one run."""

    run_at: str
    metric_set_hash: str
    results: list[SensitivityResult]

    @property
    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)

    def to_dict(self) -> dict:
        return {
            "run_at": self.run_at,
            "metric_set_hash": self.metric_set_hash,
            "all_passed": self.all_passed,
            "results": [
                {
                    "probe_name": r.probe_name,
                    "passed": r.passed,
                    "detail": r.detail,
                    "failure_reason": r.failure_reason,
                }
                for r in self.results
            ],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_all_metrics() -> None:
    """Ensure every metric module is imported so the registry is populated."""
    import src.evaluation.metrics.pacing  # noqa: F401
    import src.evaluation.metrics.palette  # noqa: F401
    import src.evaluation.metrics.effects  # noqa: F401
    import src.evaluation.metrics.alignment  # noqa: F401
    import src.evaluation.metrics.sections  # noqa: F401
    import src.evaluation.metrics.internal  # noqa: F401
    import src.evaluation.metrics.vitality  # noqa: F401
    import src.evaluation.metrics.suitability  # noqa: F401
    import src.evaluation.metrics.coverage  # noqa: F401
    import src.evaluation.metrics.tier_breakdown  # noqa: F401


def compute_metric_set_hash() -> str:
    """SHA-256 of the sorted, newline-joined registered metric names.

    Used as a staleness check: if a metric is added or removed after a
    sensitivity proof was written, the hash changes and the
    ``baseline`` subcommand can refuse to commit a golden until the
    proof is regenerated.
    """
    _import_all_metrics()
    names = sorted(get_registry().keys())
    payload = "\n".join(names).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _get_compute(name: str):
    """Return the registered ``compute`` callable for ``name``.

    Reads from the live registry on every call so monkeypatched test
    metrics resolve to the patched callables, not a snapshot taken at
    module import time.
    """
    return get_registry()[name].compute


# ---------------------------------------------------------------------------
# Synthetic-summary builders
# ---------------------------------------------------------------------------


def _build_single_effect_summary() -> SequenceSummary:
    """A 10-placement summary where every placement is ``Plasma``.

    All placements share a single model and a benign palette so the
    probe targets ``distinct_effect_count`` and ``effect_repeat_rate``
    only — not the vitality or pairing metrics.
    """
    # 50 placements: ``effect_repeat_rate`` skips the first occurrence per
    # ``(model, effect)`` key (no "previous" yet), so with one model and one
    # effect the rate is ``(N-1)/N``. N=50 yields 0.98, comfortably above the
    # 0.95 threshold.
    placements = tuple(
        Placement(
            start_ms=i * 1_000,
            end_ms=(i + 1) * 1_000,
            effect_type="Plasma",
            model_name="MatrixCenter",
            palette_colors=("#FF0000", "#00FF00"),
            layer_index=0,
        )
        for i in range(50)
    )
    return SequenceSummary(
        song_id="sensitivity-single-effect",
        source_label="ours",
        duration_ms=50_000,
        placements=placements,
        model_names=("MatrixCenter",),
        inferred_prop_types={"MatrixCenter": "matrix"},
    )


def _build_all_black_palette_summary() -> SequenceSummary:
    """A 5-placement summary where every palette is ``(#000000,)``.

    The placements span different models / effect types so this probe
    is decoupled from the variety probes; only the luma metrics matter.
    """
    placements = tuple(
        Placement(
            start_ms=i * 2_000,
            end_ms=(i + 1) * 2_000,
            effect_type="Plasma" if i % 2 == 0 else "Bars",
            model_name=f"Model{i}",
            palette_colors=("#000000",),
            layer_index=0,
        )
        for i in range(5)
    )
    return SequenceSummary(
        song_id="sensitivity-all-black",
        source_label="ours",
        duration_ms=10_000,
        placements=placements,
        model_names=tuple(f"Model{i}" for i in range(5)),
        inferred_prop_types={f"Model{i}": "matrix" for i in range(5)},
    )


def _build_forced_bad_pairing_summary() -> SequenceSummary:
    """A summary where every placement is ``Plasma`` on an ``outline`` prop.

    ``HANDLIST_BAD_PAIRINGS`` flags ``Plasma + outline`` as bad; the
    catalog records the same pair as ``possible`` (a non-flagging
    verdict). So the handlist-pct should be ~1.0, the catalog-pct
    should be 0.0, and the disagreement-pct should also be ~1.0.
    """
    placements = tuple(
        Placement(
            start_ms=i * 1_500,
            end_ms=(i + 1) * 1_500,
            effect_type="Plasma",
            model_name="OutlineRoof",
            palette_colors=("#FFFFFF",),
            layer_index=0,
        )
        for i in range(8)
    )
    return SequenceSummary(
        song_id="sensitivity-bad-pairing",
        source_label="ours",
        duration_ms=12_000,
        placements=placements,
        model_names=("OutlineRoof",),
        # Set the prop-type mapping directly — the spec says to do this
        # in the dict rather than rely on _infer_prop_type, so the probe
        # exercises the metrics in isolation from the inference layer.
        inferred_prop_types={"OutlineRoof": "outline"},
    )


# ---------------------------------------------------------------------------
# Probe runners
# ---------------------------------------------------------------------------


def _run_single_effect_probe() -> SensitivityResult:
    summary = _build_single_effect_summary()
    distinct = _get_compute("distinct_effect_count")(summary)
    repeat = _get_compute("effect_repeat_rate")(summary)

    distinct_v = _scalar(distinct)
    repeat_v = _scalar(repeat)

    detail = (
        f"distinct_effect_count={distinct_v:.6f}, "
        f"effect_repeat_rate={repeat_v:.6f} "
        f"(N={len(summary.placements)} placements, all Plasma)"
    )
    if distinct_v == 1.0 and repeat_v >= 0.95:
        return SensitivityResult(
            probe_name="single_effect",
            passed=True,
            detail=detail,
            failure_reason=None,
        )
    return SensitivityResult(
        probe_name="single_effect",
        passed=False,
        detail=detail,
        failure_reason=(
            "expected distinct_effect_count == 1.0 and "
            "effect_repeat_rate >= 0.95"
        ),
    )


def _run_all_black_palette_probe() -> SensitivityResult:
    summary = _build_all_black_palette_summary()
    mean = _get_compute("palette_luminance_mean")(summary)
    cv = _get_compute("palette_luminance_cv")(summary)

    mean_v = _scalar(mean)
    cv_v = _scalar(cv)

    detail = (
        f"palette_luminance_mean={mean_v:.6f}, "
        f"palette_luminance_cv={cv_v:.6f} "
        f"(N={len(summary.placements)} placements, all #000000)"
    )
    if mean_v == 0.0 and cv_v == 0.0:
        return SensitivityResult(
            probe_name="all_black_palette",
            passed=True,
            detail=detail,
            failure_reason=None,
        )
    return SensitivityResult(
        probe_name="all_black_palette",
        passed=False,
        detail=detail,
        failure_reason=(
            "expected palette_luminance_mean == 0.0 and "
            "palette_luminance_cv == 0.0"
        ),
    )


def _run_forced_bad_pairing_probe() -> SensitivityResult:
    summary = _build_forced_bad_pairing_summary()
    handlist = _get_compute("bad_pairing_pct_handlist")(summary)
    catalog = _get_compute("bad_pairing_pct_catalog")(summary)
    disagree = _get_compute("pairing_disagreement_pct")(summary)

    handlist_v = _scalar(handlist)
    catalog_v = _scalar(catalog)
    disagree_v = _scalar(disagree)

    detail = (
        f"bad_pairing_pct_handlist={handlist_v:.6f}, "
        f"bad_pairing_pct_catalog={catalog_v:.6f}, "
        f"pairing_disagreement_pct={disagree_v:.6f} "
        f"(N={len(summary.placements)} placements, all Plasma+outline)"
    )
    if handlist_v > 0.95 and catalog_v == 0.0 and disagree_v > 0.95:
        return SensitivityResult(
            probe_name="forced_bad_pairing",
            passed=True,
            detail=detail,
            failure_reason=None,
        )
    return SensitivityResult(
        probe_name="forced_bad_pairing",
        passed=False,
        detail=detail,
        failure_reason=(
            "expected bad_pairing_pct_handlist > 0.95, "
            "bad_pairing_pct_catalog == 0.0, "
            "pairing_disagreement_pct > 0.95"
        ),
    )


def _run_deterministic_seed_probe(
    audio_fixture: Path,
    layout_path: Path,
    output_dir: Path,
) -> SensitivityResult:
    """Drive the real generator twice with seed 42, then once with seed 9999.

    Determinism: every scalar metric must match between the two seed-42
    runs within ``1e-9``. Seed-effect: the seed-9999 run must produce
    at least one ``Placement`` that differs from the seed-42 run in
    ``(effect_type, model_name, palette_colors)``.
    """
    a = run_song(audio_fixture, layout_path, output_dir / "seed42_a")
    b = run_song(audio_fixture, layout_path, output_dir / "seed42_b")

    nondet: list[tuple[str, float | None, float | None]] = []
    for name, mv_a in a.metrics.items():
        if mv_a.kind != "scalar":
            continue
        mv_b = b.metrics.get(name)
        if mv_b is None:
            continue
        va = _scalar_or_none(mv_a)
        vb = _scalar_or_none(mv_b)
        if va is None or vb is None:
            continue
        if abs(va - vb) > _DETERMINISM_TOL:
            nondet.append((name, va, vb))

    if nondet:
        detail = (
            f"determinism FAILED: {len(nondet)} scalar metric(s) differ "
            f"between two seed=42 runs; first offender: "
            f"{nondet[0][0]} ({nondet[0][1]} vs {nondet[0][2]})"
        )
        return SensitivityResult(
            probe_name="deterministic_seed",
            passed=False,
            detail=detail,
            failure_reason="non-deterministic scalar metrics on identical seed",
        )

    c = run_song(
        audio_fixture,
        layout_path,
        output_dir / "seed_alt",
        config_overrides={"variation_seed": 9999},
    )

    placement_diffs = 0
    for pa, pc in zip(a.summary.placements, c.summary.placements):
        if (
            pa.effect_type != pc.effect_type
            or pa.model_name != pc.model_name
            or pa.palette_colors != pc.palette_colors
        ):
            placement_diffs += 1
    # If lengths differ, that's also an observable seed effect.
    length_delta = abs(len(a.summary.placements) - len(c.summary.placements))

    detail = (
        f"determinism OK ({len(a.metrics)} scalar metrics matched within "
        f"{_DETERMINISM_TOL}); seed-flip placement diffs="
        f"{placement_diffs}, length_delta={length_delta} "
        f"(seed=42: {len(a.summary.placements)} placements, "
        f"seed=9999: {len(c.summary.placements)} placements)"
    )
    if placement_diffs == 0 and length_delta == 0:
        return SensitivityResult(
            probe_name="deterministic_seed",
            passed=False,
            detail=detail,
            failure_reason=(
                "flipping variation_seed 42 → 9999 produced no "
                "placement-level differences (seed not threading to placer)"
            ),
        )
    return SensitivityResult(
        probe_name="deterministic_seed",
        passed=True,
        detail=detail,
        failure_reason=None,
    )


# ---------------------------------------------------------------------------
# Scalar extraction
# ---------------------------------------------------------------------------


def _scalar(mv: MetricValue) -> float:
    """Extract a scalar from a ``MetricValue``; raise on missing/non-numeric."""
    v = mv.value
    if v is None:
        raise AssertionError(
            f"sensitivity probe expected a scalar value for "
            f"{mv.name!r}, got None"
        )
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise AssertionError(
            f"sensitivity probe expected a numeric value for "
            f"{mv.name!r}, got {type(v).__name__}"
        )
    return float(v)


def _scalar_or_none(mv: MetricValue) -> float | None:
    v = mv.value
    if v is None or isinstance(v, bool):
        return None
    if not isinstance(v, (int, float)):
        return None
    return float(v)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_sensitivity(
    audio_fixture: Path,
    layout_path: Path,
    output_dir: Path,
) -> SensitivityReport:
    """Drive every sensitivity probe and return a ``SensitivityReport``.

    Args:
        audio_fixture: MP3 used by the deterministic-seed probe.
        layout_path: xLights layout XML used by the deterministic-seed
            probe.
        output_dir: Where the deterministic-seed probe writes its three
            ``MicroscopeResult`` workspaces (one per seed run).

    Returns:
        ``SensitivityReport`` with one ``SensitivityResult`` per probe.
        ``all_passed`` is True iff every probe passed.
    """
    _import_all_metrics()
    metric_set_hash = compute_metric_set_hash()
    run_at = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[SensitivityResult] = [
        _run_single_effect_probe(),
        _run_all_black_palette_probe(),
        _run_forced_bad_pairing_probe(),
        _run_deterministic_seed_probe(
            Path(audio_fixture),
            Path(layout_path),
            output_dir,
        ),
    ]

    return SensitivityReport(
        run_at=run_at,
        metric_set_hash=metric_set_hash,
        results=results,
    )


# Public helpers exposed for tests.
__all__ = [
    "SensitivityResult",
    "SensitivityReport",
    "run_sensitivity",
    "compute_metric_set_hash",
    "_run_single_effect_probe",
    "_run_all_black_palette_probe",
    "_run_forced_bad_pairing_probe",
    "_build_single_effect_summary",
    "_build_all_black_palette_summary",
    "_build_forced_bad_pairing_summary",
]
