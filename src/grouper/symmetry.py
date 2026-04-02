"""Symmetry pair detection for power groups."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any


_SUFFIX_PATTERN = re.compile(r'[_\s-]*(Left|Right|L|R|[12]|A|B)\s*$', re.IGNORECASE)


def _strip_suffix(name: str) -> str:
    """Strip symmetry-indicating suffixes (Left/Right, L/R, 1/2, A/B)."""
    return _SUFFIX_PATTERN.sub('', name).strip('_- ')


@dataclass
class SymmetryGroup:
    """A pair of power groups that should receive mirrored effect assignments."""

    group_a: str
    group_b: str
    detection_method: str  # "name", "spatial", or "manual"
    mirror_direction: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_a": self.group_a,
            "group_b": self.group_b,
            "detection_method": self.detection_method,
            "mirror_direction": self.mirror_direction,
        }


def detect_symmetry_pairs(
    groups: list,
    props: list | None = None,
    overrides: list[tuple[str, str]] | None = None,
) -> list[SymmetryGroup]:
    """Detect symmetry pairs among power groups.

    Detection methods (in priority order):
    1. Manual overrides — explicit (group_a, group_b) tuples
    2. Name-based — groups differing only by Left/Right, L/R, 1/2, A/B suffixes
    3. Spatial — groups at same tier with mirrored X positions

    Args:
        groups: List of PowerGroup objects.
        props: Optional list of Prop objects for spatial detection.
        overrides: Optional list of (group_a_name, group_b_name) manual pairs.

    Returns:
        List of SymmetryGroup objects.
    """
    pairs: list[SymmetryGroup] = []
    matched_names: set[str] = set()

    # 1. Manual overrides
    if overrides:
        for name_a, name_b in overrides:
            pairs.append(SymmetryGroup(
                group_a=name_a,
                group_b=name_b,
                detection_method="manual",
            ))
            matched_names.add(name_a)
            matched_names.add(name_b)

    # 2. Name-based matching: group by (tier, stripped_name)
    tier_stripped: dict[tuple[int, str], list] = defaultdict(list)
    for g in groups:
        if g.name in matched_names:
            continue
        stripped = _strip_suffix(g.name)
        # Only consider groups whose name actually has a suffix to strip
        if stripped != g.name:
            tier_stripped[(g.tier, stripped)].append(g)

    for (_tier, _stripped), candidates in tier_stripped.items():
        if len(candidates) >= 2:
            # Pair the first two candidates
            pairs.append(SymmetryGroup(
                group_a=candidates[0].name,
                group_b=candidates[1].name,
                detection_method="name",
            ))
            matched_names.add(candidates[0].name)
            matched_names.add(candidates[1].name)

    # 3. Spatial matching: mirrored X positions at same tier
    if props:
        props_by_name = {p.name: p for p in props}

        # Group unmatched groups by tier
        tier_groups: dict[int, list] = defaultdict(list)
        for g in groups:
            if g.name not in matched_names:
                tier_groups[g.tier].append(g)

        for _tier, tier_list in tier_groups.items():
            # Compute average norm_x for each group
            group_positions: list[tuple[float, float, Any]] = []
            for g in tier_list:
                member_props = [props_by_name[m] for m in g.members if m in props_by_name]
                if not member_props:
                    continue
                avg_x = sum(p.norm_x for p in member_props) / len(member_props)
                avg_y = sum(p.norm_y for p in member_props) / len(member_props)
                group_positions.append((avg_x, avg_y, g))

            # Find pairs: one avg_x < 0.35, other > 0.65, similar avg_y
            left_groups = [(x, y, g) for x, y, g in group_positions if x < 0.35]
            right_groups = [(x, y, g) for x, y, g in group_positions if x > 0.65]

            for lx, ly, lg in left_groups:
                if lg.name in matched_names:
                    continue
                for rx, ry, rg in right_groups:
                    if rg.name in matched_names:
                        continue
                    if abs(ly - ry) < 0.15:
                        pairs.append(SymmetryGroup(
                            group_a=lg.name,
                            group_b=rg.name,
                            detection_method="spatial",
                        ))
                        matched_names.add(lg.name)
                        matched_names.add(rg.name)
                        break

    return pairs
