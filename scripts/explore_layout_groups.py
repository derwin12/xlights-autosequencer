#!/usr/bin/env python3
"""Layout-group derivation explorer.

Reads an xLights ``xlights_rgbeffects.xml`` and prints, side by side:

  1. The user-defined modelGroups already in the layout
  2. Prop-family groups derived from name patterns
  3. Spatial bands derived from ``WorldPosY`` (top / middle / bottom)
  4. Cross-instance sub-prop groups (sub-models with the same name across
     siblings)
  5. Overlap report: which derived groups have membership identical to a
     user-defined modelGroup (name-reuse candidates)

This is a one-off exploration tool, not production code. The output drives
the decision about whether to enrich the generator's group derivation
with spatial / cross-instance axes (see conversation log).

Usage:
    python3 scripts/explore_layout_groups.py path/to/xlights_rgbeffects.xml
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. Parse the layout
# ---------------------------------------------------------------------------

def load_layout(path: Path):
    tree = ET.parse(path)
    root = tree.getroot()
    models = root.find("models")
    groups = root.find("modelGroups")
    return models, groups


def model_name(elem: ET.Element) -> str:
    return elem.attrib.get("name", "")


def model_y(elem: ET.Element) -> float | None:
    raw = elem.attrib.get("WorldPosY")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 2. User-defined modelGroups
# ---------------------------------------------------------------------------

def user_groups(groups_elem: ET.Element | None) -> dict[str, list[str]]:
    """Return ``name -> [model_names]`` for every <modelGroup> in the file."""
    if groups_elem is None:
        return {}
    out: dict[str, list[str]] = {}
    for g in groups_elem.findall("modelGroup"):
        name = g.attrib.get("name", "")
        if not name:
            continue
        models = [m.strip() for m in g.attrib.get("models", "").split(",") if m.strip()]
        out[name] = models
    return out


# ---------------------------------------------------------------------------
# 3. Prop-family derivation (common-prefix grouping)
# ---------------------------------------------------------------------------

# Strip trailing duplicate / index markers:
#   "Spinner 23 inch Right-3"     -> "Spinner 23 inch Right"
#   "Arch - Right - 4"            -> "Arch - Right"
#   "GE Flake A 1"                -> "GE Flake A"  (single trailing digit token)
#   "Door - 1 Car Garage - Left"  -> kept (Left/Right are not numeric)
_TAIL_NUM = re.compile(r"(?:\s*-\s*\d+|-\d+|\s+\d+)$")


def family_base(name: str) -> str:
    """Best-effort base for a prop-family bucket. Strips one trailing index."""
    return _TAIL_NUM.sub("", name).strip()


def derive_prop_families(model_names: list[str]) -> dict[str, list[str]]:
    """Group model names by family base. Only families with 2+ members are kept."""
    buckets: dict[str, list[str]] = defaultdict(list)
    for n in model_names:
        buckets[family_base(n)].append(n)
    return {b: sorted(ms) for b, ms in buckets.items() if len(ms) >= 2}


# ---------------------------------------------------------------------------
# 4. Spatial bands (WorldPosY tertiles)
# ---------------------------------------------------------------------------

def derive_spatial_bands(models_elem: ET.Element) -> dict[str, list[str]]:
    """Cluster models into Bottom / Middle / Top by WorldPosY tertile."""
    pairs: list[tuple[str, float]] = []
    for m in models_elem.findall("model"):
        y = model_y(m)
        if y is None:
            continue
        pairs.append((model_name(m), y))
    if len(pairs) < 3:
        return {}
    pairs.sort(key=lambda p: p[1])
    n = len(pairs)
    cut1, cut2 = n // 3, (2 * n) // 3
    return {
        "Bottom (derived)": sorted(p[0] for p in pairs[:cut1]),
        "Middle (derived)": sorted(p[0] for p in pairs[cut1:cut2]),
        "Top (derived)":    sorted(p[0] for p in pairs[cut2:]),
    }


# ---------------------------------------------------------------------------
# 5. Cross-instance sub-prop derivation
# ---------------------------------------------------------------------------

def derive_cross_instance_subprops(models_elem: ET.Element) -> dict[str, list[str]]:
    """For sub-model names shared across 3+ parents, build aggregate groups.

    Output value is a list of fully-qualified ``Parent/Sub`` references.
    """
    by_subname: dict[str, list[str]] = defaultdict(list)
    for m in models_elem.findall("model"):
        parent = model_name(m)
        for sm in m.findall("subModel"):
            sn = sm.attrib.get("name", "")
            if sn:
                by_subname[sn].append(f"{parent}/{sn}")
    return {
        f"{sn} (cross-instance)": sorted(refs)
        for sn, refs in by_subname.items()
        if len({r.split("/", 1)[0] for r in refs}) >= 3
    }


# ---------------------------------------------------------------------------
# 6. Overlap report (derived membership == user-defined modelGroup membership)
# ---------------------------------------------------------------------------

def overlap_report(
    derived: dict[str, list[str]],
    user: dict[str, list[str]],
) -> list[tuple[str, str, int]]:
    """Return (derived_name, user_name, member_count) for exact-match groups."""
    user_sets = {name: frozenset(members) for name, members in user.items()}
    out: list[tuple[str, str, int]] = []
    for d_name, d_members in derived.items():
        d_set = frozenset(d_members)
        for u_name, u_set in user_sets.items():
            if d_set == u_set and len(d_set) > 0:
                out.append((d_name, u_name, len(d_set)))
    return out


# ---------------------------------------------------------------------------
# 7. Pretty printing
# ---------------------------------------------------------------------------

def print_section(title: str, groups: dict[str, list[str]], limit_members: int = 10) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")
    print(f"  {len(groups)} groups total\n")
    for name in sorted(groups):
        members = groups[name]
        head = ", ".join(members[:limit_members])
        suffix = f", ... (+{len(members) - limit_members} more)" if len(members) > limit_members else ""
        print(f"  [{len(members):>3}] {name}")
        print(f"        {head}{suffix}")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: explore_layout_groups.py <xlights_rgbeffects.xml>", file=sys.stderr)
        return 2

    path = Path(argv[1])
    if not path.is_file():
        print(f"Not a file: {path}", file=sys.stderr)
        return 2

    models_elem, groups_elem = load_layout(path)
    if models_elem is None:
        print("No <models> element in layout XML.", file=sys.stderr)
        return 2

    all_model_names = [model_name(m) for m in models_elem.findall("model") if model_name(m)]

    user = user_groups(groups_elem)
    families = derive_prop_families(all_model_names)
    spatial = derive_spatial_bands(models_elem)
    sub_cross = derive_cross_instance_subprops(models_elem)

    print(f"\nLayout: {path}")
    print(f"  {len(all_model_names)} models, {len(user)} user-defined modelGroups")

    print_section("USER-DEFINED MODELGROUPS", user, limit_members=8)
    print_section("DERIVED: PROP FAMILIES (common-prefix)", families, limit_members=8)
    print_section("DERIVED: SPATIAL BANDS (WorldPosY tertiles)", spatial, limit_members=8)
    print_section("DERIVED: CROSS-INSTANCE SUB-PROPS", sub_cross, limit_members=10)

    print(f"\n{'=' * 78}\nOVERLAP REPORT (derived membership identical to user-defined group)\n{'=' * 78}")
    matches = (
        overlap_report(families, user)
        + overlap_report(spatial, user)
        + overlap_report(sub_cross, user)
    )
    if not matches:
        print("  (no exact overlaps — derived names would all be new)")
    else:
        print(f"  {len(matches)} derived groups whose membership matches a user-defined group:\n")
        for d_name, u_name, count in sorted(matches):
            print(f"  [{count:>3}] derived '{d_name}'  ==  user '{u_name}'")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
