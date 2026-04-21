"""Core data model for the quality calibration harness."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Placement:
    start_ms: int
    end_ms: int
    effect_type: str          # e.g. "Marquee", "Plasma", or "Unknown"
    model_name: str
    palette_colors: tuple[str, ...]  # "#RRGGBB" hex strings, may be empty
    layer_index: int

    def to_dict(self) -> dict:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "effect_type": self.effect_type,
            "model_name": self.model_name,
            "palette_colors": list(self.palette_colors),
            "layer_index": self.layer_index,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Placement:
        return cls(
            start_ms=d["start_ms"],
            end_ms=d["end_ms"],
            effect_type=d["effect_type"],
            model_name=d["model_name"],
            palette_colors=tuple(d.get("palette_colors", [])),
            layer_index=d["layer_index"],
        )


@dataclass(frozen=True)
class SequenceSummary:
    song_id: str
    source_label: str         # "pro:<pro_id>" or "ours"
    duration_ms: int
    placements: tuple[Placement, ...]
    model_names: tuple[str, ...]
    inferred_prop_types: dict[str, str]  # model_name -> prop-type hint

    def to_dict(self) -> dict:
        return {
            "song_id": self.song_id,
            "source_label": self.source_label,
            "duration_ms": self.duration_ms,
            "placements": [p.to_dict() for p in self.placements],
            "model_names": list(self.model_names),
            "inferred_prop_types": dict(self.inferred_prop_types),
        }

    @classmethod
    def from_dict(cls, d: dict) -> SequenceSummary:
        return cls(
            song_id=d["song_id"],
            source_label=d["source_label"],
            duration_ms=d["duration_ms"],
            placements=tuple(Placement.from_dict(p) for p in d.get("placements", [])),
            model_names=tuple(d.get("model_names", [])),
            inferred_prop_types=dict(d.get("inferred_prop_types", {})),
        )


def load_sequence_summary(path: Path) -> SequenceSummary:
    """Read a JSON file and return a SequenceSummary."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return SequenceSummary.from_dict(data)


@dataclass
class MetricValue:
    name: str
    kind: str                 # "scalar", "distribution", "per_section", "structured"
    value: float | None       # primary numeric; None for empty/degenerate cases
    payload: object           # None or additional structured data
    reliability: str          # "ok" or "reduced"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "value": self.value,
            "payload": self.payload,
            "reliability": self.reliability,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MetricValue:
        return cls(
            name=d["name"],
            kind=d["kind"],
            value=d.get("value"),
            payload=d.get("payload"),
            reliability=d.get("reliability", "ok"),
        )
