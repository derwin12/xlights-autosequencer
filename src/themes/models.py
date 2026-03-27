"""Data models for the effect themes library."""
from __future__ import annotations

from dataclasses import dataclass, field

VALID_MOODS: list[str] = ["ethereal", "aggressive", "dark", "structural"]
VALID_OCCASIONS: list[str] = ["christmas", "halloween", "general"]
VALID_GENRES: list[str] = ["rock", "pop", "classical", "any"]

VALID_BLEND_MODES: list[str] = [
    "Normal", "Effect 1", "Effect 2",
    "1 is Mask", "2 is Mask",
    "1 is Unmask", "2 is Unmask",
    "1 is True Unmask", "2 is True Unmask",
    "1 reveals 2", "2 reveals 1",
    "Layered", "Average", "Bottom-Top", "Left-Right",
    "Shadow 1 on 2", "Shadow 2 on 1",
    "Additive", "Subtractive",
    "Brightness", "Max", "Min",
    "Highlight", "Highlight Vibrant",
]


@dataclass
class EffectLayer:
    effect: str
    blend_mode: str = "Normal"
    parameter_overrides: dict[str, int | float | bool | str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> EffectLayer:
        return cls(
            effect=data["effect"],
            blend_mode=data.get("blend_mode", "Normal"),
            parameter_overrides=data.get("parameter_overrides", {}),
        )


@dataclass
class Theme:
    name: str
    mood: str
    occasion: str
    genre: str
    intent: str
    layers: list[EffectLayer]
    palette: list[str]

    @classmethod
    def from_dict(cls, data: dict) -> Theme:
        return cls(
            name=data["name"],
            mood=data["mood"],
            occasion=data.get("occasion", "general"),
            genre=data.get("genre", "any"),
            intent=data["intent"],
            layers=[EffectLayer.from_dict(l) for l in data["layers"]],
            palette=data["palette"],
        )
