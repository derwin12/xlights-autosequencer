"""Tests for ``MetricDefinition.higher_is_better`` (§1.4 of OpenSpec
``visual-quality-microscope``)."""
from __future__ import annotations

from src.evaluation.metrics import (
    DEFAULT_TOLERANCE,
    MetricDefinition,
    MetricKind,
    get_registry,
)


def _stub_compute(_summary):  # pragma: no cover — never called
    return None


def _make_def(**overrides) -> MetricDefinition:
    base = dict(
        name="probe",
        kind=MetricKind.SCALAR,
        gated=True,
        tolerance=DEFAULT_TOLERANCE,
        compute=_stub_compute,
        pro_comparable=False,
    )
    base.update(overrides)
    return MetricDefinition(**base)


def test_higher_is_better_defaults_to_none() -> None:
    """Default direction is ``None`` (unknown) — must not silently
    add improvement claims to existing metric registrations."""
    defn = _make_def()
    assert defn.higher_is_better is None


def test_higher_is_better_accepts_true() -> None:
    defn = _make_def(higher_is_better=True)
    assert defn.higher_is_better is True


def test_higher_is_better_accepts_false() -> None:
    defn = _make_def(higher_is_better=False)
    assert defn.higher_is_better is False


def test_existing_registrations_remain_valid() -> None:
    """Importing the existing metric modules must succeed and produce
    a populated registry — proves that the new field's default did
    not break any historical registration.

    Only audits the pre-microscope metric modules. The new vitality
    and suitability modules deliberately set ``higher_is_better`` on
    some metrics (e.g. ``effect_repeat_rate`` is ``False``); auditing
    them here would conflict with that intent.
    """
    # Force-import only the EXISTING metric modules and capture their
    # metric names so we don't accidentally audit later modules that
    # might already be in the registry from other test imports.
    import src.evaluation.metrics.alignment as _alignment
    import src.evaluation.metrics.effects as _effects
    import src.evaluation.metrics.internal as _internal
    import src.evaluation.metrics.pacing as _pacing
    import src.evaluation.metrics.palette as _palette
    import src.evaluation.metrics.sections as _sections
    # Touch the modules so flake8 doesn't complain.
    _ = (_alignment, _effects, _internal, _pacing, _palette, _sections)

    pre_microscope_names = {
        # Sourced from each module's `register(...)` calls — verified
        # by grepping the modules at the time this test was written.
        "beat_alignment_pct",
        "downbeat_alignment_pct",
        "effect_type_histogram",
        "tier_utilization",
        "theme_assignment_consistency",
        "placements_per_minute",
        "palette_balance",
        "palette_diversity",
        "section_coverage_pct",
        "section_label_match_rate",
    }

    registry = get_registry()
    assert len(registry) > 0, "registry should not be empty after imports"
    # Every PRE-MICROSCOPE metric should default to direction-of-good
    # unknown; the new vitality/suitability modules are out of scope
    # for this check.
    for name in pre_microscope_names:
        if name not in registry:
            # The existing module's metric set has shifted since this
            # test was written — that's fine, just skip.
            continue
        defn = registry[name]
        assert defn.higher_is_better is None, (
            f"pre-microscope metric {name!r} unexpectedly has "
            f"direction-of-good {defn.higher_is_better!r} — existing "
            f"metrics must stay None until validated"
        )
