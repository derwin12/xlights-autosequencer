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
