"""Metric registry for the quality calibration harness."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class MetricKind(str, Enum):
    SCALAR = "scalar"
    DISTRIBUTION = "distribution"
    PER_SECTION = "per_section"
    STRUCTURED = "structured"


@dataclass(frozen=True)
class MetricTolerance:
    kind: str    # "relative" or "absolute"
    value: float


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    kind: MetricKind
    gated: bool
    tolerance: MetricTolerance | None   # None -> use DEFAULT_TOLERANCE
    compute: Callable                    # signature varies by metric
    pro_comparable: bool
    # Direction-of-good for the metric's scalar value.
    # ``None`` (the default) means the direction has not been validated
    # against rendered output; the diff tool renders movement arrows
    # without improvement claims. ``True``/``False`` are reserved for
    # metrics whose direction has been validated. See OpenSpec change
    # ``visual-quality-microscope`` design.md.
    higher_is_better: bool | None = None


DEFAULT_TOLERANCE = MetricTolerance(kind="relative", value=0.10)

# Module-level registry: name -> MetricDefinition
_REGISTRY: dict[str, MetricDefinition] = {}


def register(defn: MetricDefinition) -> None:
    """Register a metric definition. Called by each metric module at import."""
    _REGISTRY[defn.name] = defn


def get_registry() -> dict[str, MetricDefinition]:
    """Return a copy of the current metric registry."""
    return dict(_REGISTRY)


def get_metric(name: str) -> MetricDefinition:
    """Retrieve a metric by name; raises KeyError if not found."""
    return _REGISTRY[name]
