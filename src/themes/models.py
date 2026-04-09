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
    variant: str
    blend_mode: str = "Normal"
    effect_pool: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> EffectLayer:
        return cls(
            variant=data["variant"],
            blend_mode=data.get("blend_mode", "Normal"),
            effect_pool=data.get("effect_pool", []),
        )

    def to_dict(self) -> dict:
        return {
            "variant": self.variant,
            "blend_mode": self.blend_mode,
            "effect_pool": self.effect_pool,
        }


@dataclass
class ThemeAlternate:
    """Alternate layer set for a theme — same palette/mood, different visuals."""
    layers: list[EffectLayer]

    @classmethod
    def from_dict(cls, data: dict) -> ThemeAlternate:
        return cls(
            layers=[EffectLayer.from_dict(l) for l in data["layers"]],
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
    accent_palette: list[str] = field(default_factory=list)
    alternates: list[ThemeAlternate] = field(default_factory=list)
    transition_mode: str | None = None

    def __post_init__(self) -> None:
        if self.transition_mode is not None:
            valid = ("none", "subtle", "dramatic")
            if self.transition_mode not in valid:
                raise ValueError(
                    f"transition_mode must be None or one of {valid}, "
                    f"got {self.transition_mode!r}"
                )

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
            accent_palette=data.get("accent_palette", []),
            alternates=[ThemeAlternate.from_dict(a) for a in data.get("alternates", [])],
            transition_mode=data.get("transition_mode", None),
        )

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "mood": self.mood,
            "occasion": self.occasion,
            "genre": self.genre,
            "intent": self.intent,
            "layers": [l.to_dict() for l in self.layers],
            "palette": self.palette,
            "accent_palette": self.accent_palette,
            "alternates": [{"layers": [l.to_dict() for l in a.layers]} for a in self.alternates],
        }
        if self.transition_mode is not None:
            d["transition_mode"] = self.transition_mode
        return d
