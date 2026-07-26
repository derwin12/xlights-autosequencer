"""Data models for the xLights effect variant library."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

# Immutable tuples prevent accidental mutation from corrupting validation
VALID_TIER_AFFINITIES: tuple[str, ...] = ("background", "mid", "foreground", "hero")
VALID_ENERGY_LEVELS: tuple[str, ...] = ("low", "medium", "high")
VALID_SPEED_FEELS: tuple[str, ...] = ("slow", "moderate", "fast")
VALID_SECTION_ROLES: tuple[str, ...] = (
    "verse", "chorus", "bridge", "intro", "outro", "build", "drop"
)
VALID_SCOPES: tuple[str, ...] = ("single-prop", "group")


@dataclass
class VariantTags:
    tier_affinity: str | None = None
    energy_level: str | None = None
    speed_feel: str | None = None
    direction: str | None = None
    section_roles: list[str] = field(default_factory=list)
    scope: str | None = None
    genre_affinity: str = "any"
    # True for effects/shaders whose own rendered content is achromatic
    # (white/gray, no real saturation) -- e.g. a GLSL shader with no color
    # uniform of its own. Neither the theme palette nor C_SLIDER_Color_
    # HueAdjust can recolor these (a hue rotation of a desaturated pixel is a
    # no-op); the only way to theme-match them is a colored layer beneath
    # using a Mask/subtractive blend so the achromatic pattern reads through
    # the color. See _HUE_RESPONSIVE_SHADER_BASELINES in xsq_writer.py for
    # the shaders that respond to hue_adjust instead (mutually exclusive with
    # this flag). User-confirmed via live xLights A/B renders, 2026-07-26.
    requires_color_mask: bool = False
    # Base-effect name (e.g. "Single Strand", "Butterfly") that must be
    # auto-placed on the layer beneath this variant when the generator picks
    # it -- for Warp-type shaders that distort/tile whatever renders beneath
    # them rather than carrying their own color. Without a companion base,
    # these render blank/flat white (user-confirmed, 2026-07-26 -- see
    # Shader.json's Warp Kaleidoscope Tile/Warp Vincent'sStorm entries). None
    # for variants that render standalone.
    companion_base_effect: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> VariantTags:
        return cls(
            tier_affinity=data.get("tier_affinity"),
            energy_level=data.get("energy_level"),
            speed_feel=data.get("speed_feel"),
            direction=data.get("direction"),
            section_roles=data.get("section_roles") or [],
            scope=data.get("scope"),
            genre_affinity=data.get("genre_affinity", "any"),
            requires_color_mask=data.get("requires_color_mask", False),
            companion_base_effect=data.get("companion_base_effect"),
        )

    def get(self, key: str, default=None):
        """Dict-like access to tag fields."""
        return getattr(self, key, default)

    def to_dict(self) -> dict:
        return {
            "tier_affinity": self.tier_affinity,
            "energy_level": self.energy_level,
            "speed_feel": self.speed_feel,
            "direction": self.direction,
            "section_roles": self.section_roles,
            "scope": self.scope,
            "genre_affinity": self.genre_affinity,
            "requires_color_mask": self.requires_color_mask,
            "companion_base_effect": self.companion_base_effect,
        }


@dataclass
class EffectVariant:
    name: str
    base_effect: str
    description: str
    parameter_overrides: dict[str, int | float | bool | str]
    tags: VariantTags
    direction_cycle: dict | None = None  # {"param": str, "values": [str], "mode": str}

    @classmethod
    def from_dict(cls, data: dict) -> EffectVariant:
        return cls(
            name=data["name"],
            base_effect=data["base_effect"],
            description=data["description"],
            parameter_overrides=dict(data.get("parameter_overrides", {})),
            tags=VariantTags.from_dict(data.get("tags") or {}),
            direction_cycle=data.get("direction_cycle"),
        )

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "base_effect": self.base_effect,
            "description": self.description,
            "parameter_overrides": self.parameter_overrides,
            "tags": self.tags.to_dict(),
        }
        if self.direction_cycle is not None:
            d["direction_cycle"] = self.direction_cycle
        return d

    def identity_key(self) -> str:
        """Stable key based on base_effect + sorted parameter_overrides.

        Two variants with the same base effect and identical parameter values
        are considered duplicates regardless of name, description, or tags.

        Booleans are normalized to ints (True→1, False→0) so that a checkbox
        value loaded as a Python bool and the same value loaded as an int
        produce the same key.
        """
        normalized = {}
        for k, v in self.parameter_overrides.items():
            if isinstance(v, bool):
                v = int(v)
            elif isinstance(v, float) and v == int(v):
                v = int(v)
            normalized[k] = v
        payload = json.dumps(
            {"base_effect": self.base_effect, "params": normalized},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()
