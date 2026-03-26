"""Classify props: normalize coordinates, compute aspect ratio / pixel count."""
from __future__ import annotations

import re

from src.grouper.layout import Prop

_HERO_PATTERN = re.compile(
    r"face|megatree|mega[_ ]tree",
    re.IGNORECASE,
)

# Auto-hero: examine top N props and cut where the biggest pixel-count ratio gap is
_AUTO_HERO_CANDIDATES = 10
_MIN_RATIO_GAP = 1.5  # minimum ratio between adjacent sorted counts to consider a cut


def normalize_coords(props: list[Prop]) -> None:
    """Mutate Prop.norm_x / norm_y to [0.0, 1.0] based on bounding box.

    If all props share the same X or Y coordinate, defaults to 0.5 (mid-range).
    """
    if not props:
        return

    x_min = min(p.world_x for p in props)
    x_max = max(p.world_x for p in props)
    y_min = min(p.world_y for p in props)
    y_max = max(p.world_y for p in props)

    x_range = x_max - x_min
    y_range = y_max - y_min

    for p in props:
        p.norm_x = (p.world_x - x_min) / x_range if x_range > 0 else 0.5
        p.norm_y = (p.world_y - y_min) / y_range if y_range > 0 else 0.5
        p.norm_x = max(0.0, min(1.0, p.norm_x))
        p.norm_y = max(0.0, min(1.0, p.norm_y))


def classify_props(props: list[Prop]) -> None:
    """Mutate Prop.aspect_ratio and Prop.pixel_count.

    For Custom models, pixel_count is the number of non-empty cells in the
    CustomModel grid (parm1*parm2 is just the grid dimensions, mostly empty).

    For Single Line / Poly Line models, aspect_ratio is derived from X2/Y2
    endpoint offsets rather than ScaleX/ScaleY (which are always 1.0 on lines).
    """
    for p in props:
        # Pixel count
        if p.custom_model:
            p.pixel_count = sum(
                1 for row in p.custom_model.split(";")
                for cell in row.split(",")
                if cell.strip()
            )
        else:
            p.pixel_count = p.parm1 * p.parm2

        # Aspect ratio — use X2/Y2 for line-based models
        if p.x2 != 0.0 or p.y2 != 0.0:
            abs_x = abs(p.x2)
            abs_y = abs(p.y2)
            p.aspect_ratio = (abs_y / abs_x) if abs_x > 0 else (999.0 if abs_y > 0 else 1.0)
        else:
            p.aspect_ratio = (p.scale_y / p.scale_x) if p.scale_x > 0 else 1.0


def _sanitize_group_label(name: str) -> str:
    """Replace non-word characters with underscores for xLights compatibility."""
    return re.sub(r"[^\w]", "_", name)


def _find_pixel_outliers(props: list[Prop], max_candidates: int = _AUTO_HERO_CANDIDATES) -> set[str]:
    """Find hero candidates by looking for the largest gap in the top props by pixel count.

    Sorts all props by pixel_count descending, examines the top max_candidates,
    and cuts at the position with the biggest ratio gap (>= _MIN_RATIO_GAP).
    If no significant gap exists, returns nothing (no auto-heroes).
    """
    ranked = sorted(props, key=lambda p: p.pixel_count, reverse=True)
    top = ranked[:max_candidates]

    if len(top) < 2:
        return set()

    # Find the biggest ratio gap in the top N
    best_gap_ratio = 1.0
    best_cut = 0  # cut after this index (props above the cut are heroes)
    for i in range(len(top) - 1):
        lower = top[i + 1].pixel_count
        if lower <= 0:
            continue
        ratio = top[i].pixel_count / lower
        if ratio > best_gap_ratio:
            best_gap_ratio = ratio
            best_cut = i + 1

    if best_gap_ratio < _MIN_RATIO_GAP:
        return set()

    return {p.name for p in top[:best_cut]}


def detect_heroes(
    props: list[Prop],
    extra_heroes: list[str] | None = None,
    auto_heroes: bool = True,
) -> list:
    """Return PowerGroup objects for hero props.

    Hero detection uses three sources (combined, deduplicated):
    1. Keyword matching — props with 'face', 'megatree', 'mega tree' in name
    2. Pixel outlier detection — top N props above the biggest pixel-count gap
       (only when auto_heroes=True)
    3. Explicit names — props listed in extra_heroes
    """
    from src.grouper.grouper import PowerGroup

    hero_names: set[str] = set()

    # 1. Keyword detection
    for p in props:
        if _HERO_PATTERN.search(p.name):
            hero_names.add(p.name)

    # 2. Pixel outlier detection (natural gap method)
    if auto_heroes and len(props) >= 3:
        hero_names |= _find_pixel_outliers(props)

    # 3. Explicit hero names
    if extra_heroes:
        prop_names = {p.name for p in props}
        for name in extra_heroes:
            if name in prop_names:
                hero_names.add(name)

    # Build groups in prop order (stable)
    groups = []
    for p in props:
        if p.name in hero_names:
            members = p.sub_models if p.sub_models else [p.name]
            label = _sanitize_group_label(p.name)
            groups.append(PowerGroup(
                name=f"08_HERO_{label}",
                tier=8,
                members=members,
            ))
    return groups
