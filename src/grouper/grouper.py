"""Generate Power Groups from a list of classified Props.

8-tier hierarchy (render order — higher tiers override lower):
  1 Canvas      01_BASE_   Whole-house wash
  2 Spatial     02_GEO_    Position-based zones
  3 Architecture 03_TYPE_  Vertical / horizontal orientation
  4 Rhythm      04_BEAT_   Beat-sync chase groups of 4
  5 Fidelity    05_TEX_    Hi / lo pixel density
  6 Prop Type   06_PROP_   All of a kind (all candy canes)
  7 Compound    07_COMP_   Multi-piece fixture (one window frame)
  8 Heroes      08_HERO_   Primary focus elements
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from src.grouper.layout import Prop

# Show profile → set of active tier numbers
PROFILE_TIERS: dict[str, set[int]] = {
    "energetic": {3, 4, 6, 8},
    "cinematic": {1, 2, 7, 8},
    "technical": {1, 5},
}
ALL_TIERS: set[int] = {1, 2, 3, 4, 5, 6, 7, 8}

# Spatial bin thresholds (normalized coordinates)
_TOP_Y = 0.66
_BOT_Y = 0.33
_RIGHT_X = 0.66
_LEFT_X = 0.33

# Pixel density threshold
_HI_DENS_THRESHOLD = 500


@dataclass
class PowerGroup:
    name: str
    tier: int
    members: list[str] = field(default_factory=list)


def generate_groups(
    props: list[Prop],
    profile: str | None = None,
    extra_heroes: list[str] | None = None,
    auto_heroes: bool = True,
) -> list[PowerGroup]:
    """Generate all applicable Power Groups, filtered by show profile.

    Props must already have norm_x, norm_y, aspect_ratio, pixel_count set
    (i.e. normalize_coords() and classify_props() must have been called first).
    """
    active_tiers = PROFILE_TIERS.get(profile, ALL_TIERS) if profile else ALL_TIERS
    groups: list[PowerGroup] = []

    if 1 in active_tiers:
        groups.extend(_tier1_canvas(props))
    if 2 in active_tiers:
        groups.extend(_tier2_spatial(props))
    if 3 in active_tiers:
        groups.extend(_tier3_architecture(props))
    if 4 in active_tiers:
        groups.extend(_tier4_rhythm(props))
    if 5 in active_tiers:
        groups.extend(_tier5_fidelity(props))
    if 6 in active_tiers:
        groups.extend(_tier6_prop_type(props))
    if 7 in active_tiers:
        groups.extend(_tier7_compound(props))
    if 8 in active_tiers:
        groups.extend(_tier8_heroes(props, extra_heroes=extra_heroes, auto_heroes=auto_heroes))

    # Remove empty groups
    return [g for g in groups if g.members]


# ─── Tier generators ──────────────────────────────────────────────────────────

def _tier1_canvas(props: list[Prop]) -> list[PowerGroup]:
    return [PowerGroup(name="01_BASE_All", tier=1, members=[p.name for p in props])]


def _tier2_spatial(props: list[Prop]) -> list[PowerGroup]:
    bins: dict[str, list[str]] = {
        "02_GEO_Top": [],
        "02_GEO_Mid": [],
        "02_GEO_Bot": [],
        "02_GEO_Left": [],
        "02_GEO_Center": [],
        "02_GEO_Right": [],
    }

    # Use quantile-based thresholds so each zone gets ~1/3 of props
    ys = sorted(p.norm_y for p in props)
    xs = sorted(p.norm_x for p in props)
    n = len(props)
    y_low = ys[n // 3] if n >= 3 else 0.33
    y_high = ys[2 * n // 3] if n >= 3 else 0.66
    x_low = xs[n // 3] if n >= 3 else 0.33
    x_high = xs[2 * n // 3] if n >= 3 else 0.66

    for p in props:
        if p.norm_y > y_high:
            bins["02_GEO_Top"].append(p.name)
        elif p.norm_y <= y_low:
            bins["02_GEO_Bot"].append(p.name)
        else:
            bins["02_GEO_Mid"].append(p.name)

        if p.norm_x < x_low:
            bins["02_GEO_Left"].append(p.name)
        elif p.norm_x >= x_high:
            bins["02_GEO_Right"].append(p.name)
        else:
            bins["02_GEO_Center"].append(p.name)

    return [PowerGroup(name=name, tier=2, members=members) for name, members in bins.items()]


def _tier3_architecture(props: list[Prop]) -> list[PowerGroup]:
    verticals = [p.name for p in props if p.aspect_ratio >= 1.5]
    horizontals = [p.name for p in props if p.aspect_ratio < 1.5]
    return [
        PowerGroup(name="03_TYPE_Vertical", tier=3, members=verticals),
        PowerGroup(name="03_TYPE_Horizontal", tier=3, members=horizontals),
    ]


def _tier4_rhythm(props: list[Prop]) -> list[PowerGroup]:
    """Create exactly 4 beat groups with props distributed evenly by type.

    Each prop type is dealt round-robin across the 4 groups so that, e.g.,
    candy cane 1 → group 1, candy cane 2 → group 2, candy cane 3 → group 3,
    candy cane 4 → group 4. A rotating offset prevents remainders from
    always landing in group 1.
    """
    def _type_name(name: str) -> str:
        s = name.split(" - ")[0]
        s = re.sub(r"[\s-]*\d+\s*$", "", s)
        s = re.sub(r"\s+[A-Z]\s*$", "", s)
        return s.strip(" -")

    buckets: dict[str, list[str]] = {}
    for p in props:
        key = _type_name(p.name)
        buckets.setdefault(key, []).append(p.name)

    members: dict[int, list[str]] = {1: [], 2: [], 3: [], 4: []}
    offset = 0
    for key in sorted(buckets, key=lambda k: -len(buckets[k])):
        for i, name in enumerate(buckets[key]):
            members[((i + offset) % 4) + 1].append(name)
        offset += len(buckets[key])

    return [
        PowerGroup(name=f"04_BEAT_{g}", tier=4, members=members[g])
        for g in sorted(members)
    ]


def _tier5_fidelity(props: list[Prop]) -> list[PowerGroup]:
    hi = [p.name for p in props if p.pixel_count > _HI_DENS_THRESHOLD]
    lo = [p.name for p in props if p.pixel_count <= _HI_DENS_THRESHOLD]
    return [
        PowerGroup(name="05_TEX_HiDens", tier=5, members=hi),
        PowerGroup(name="05_TEX_LoDens", tier=5, members=lo),
    ]


def _tier6_prop_type(props: list[Prop]) -> list[PowerGroup]:
    """Group all props of the same kind — e.g. all candy canes, all windows, all flakes.

    Extracts the broadest category name by stripping trailing numbers,
    single-letter variants, and the first ' - ' suffix.
    """
    def _type_name(name: str) -> str:
        s = name.split(" - ")[0]               # strip after first ' - '
        s = re.sub(r"[\s-]*\d+\s*$", "", s)    # trailing numbers
        s = re.sub(r"\s+[A-Z]\s*$", "", s)     # trailing single letter variant
        return s.strip(" -")

    types: dict[str, list[str]] = defaultdict(list)
    for p in props:
        t = _type_name(p.name)
        types[t].append(p.name)

    return [
        PowerGroup(name=f"06_PROP_{_sanitize_label(type_name)}", tier=6, members=members)
        for type_name, members in sorted(types.items())
        if len(members) >= 2
    ]


def _tier7_compound(props: list[Prop]) -> list[PowerGroup]:
    """Detect props that share a name prefix (before the last ' - ') and group them.

    These are multi-piece single fixtures — e.g. the 5 pieces of one window frame.
    """
    compounds: dict[str, list[str]] = defaultdict(list)
    for p in props:
        parts = p.name.rsplit(" - ", 1)
        if len(parts) == 2:
            compounds[parts[0]].append(p.name)

    return [
        PowerGroup(name=f"07_COMP_{_sanitize_label(prefix)}", tier=7, members=members)
        for prefix, members in sorted(compounds.items())
        if len(members) >= 2
    ]


def _tier8_heroes(
    props: list[Prop],
    extra_heroes: list[str] | None = None,
    auto_heroes: bool = True,
) -> list[PowerGroup]:
    from src.grouper.classifier import detect_heroes
    return detect_heroes(props, extra_heroes=extra_heroes, auto_heroes=auto_heroes)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _sanitize_label(name: str) -> str:
    return re.sub(r"[^\w]", "_", name)


def _chunks(items: list, size: int):
    """Yield successive chunks of length `size` (last chunk may be smaller)."""
    for i in range(0, len(items), size):
        yield items[i : i + size]
