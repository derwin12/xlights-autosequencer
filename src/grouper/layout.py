"""Parse xlights_rgbeffects.xml into a Layout of Prop objects."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Maps xLights DisplayAs values to the 6 canonical prop suitability keys
# used in builtin_effects.json prop_suitability ratings.
DISPLAY_AS_TO_PROP_TYPE: dict[str, str] = {
    # Matrix / grid types
    "Matrix": "matrix",
    # Tree types
    "Tree 360": "tree",
    "Tree Flat": "tree",
    "Tree Ribbon": "tree",
    "Tree": "tree",
    # Arch types
    "Arch": "arch",
    "Arches": "arch",
    "Candy Cane": "arch",
    "Candy Canes": "arch",
    # Radial / spinner types
    "Circle": "radial",
    "Spinner": "radial",
    "Star": "radial",
    "Wreath": "radial",
    # Vertical types
    "Icicles": "vertical",
    "Window Frame": "vertical",
    # Outline / linear types (default for most props)
    "Single Line": "outline",
    "Poly Line": "outline",
    "Custom": "outline",
    "Channel Block": "outline",
    "Image": "outline",
    "Cube": "outline",
    "Sphere": "outline",
}


@dataclass
class Prop:
    name: str
    display_as: str
    world_x: float
    world_y: float
    world_z: float
    scale_x: float
    scale_y: float
    parm1: int
    parm2: int
    sub_models: list[str]
    custom_model: str = ""  # raw CustomModel grid CSV (empty for non-Custom models)
    x2: float = 0.0  # endpoint offset X (Single Line / Poly Line models)
    y2: float = 0.0  # endpoint offset Y (Single Line / Poly Line models)
    # computed by classifier
    pixel_count: int = 0
    norm_x: float = 0.0
    norm_y: float = 0.0
    aspect_ratio: float = 1.0


@dataclass
class Layout:
    props: list[Prop]
    source_path: Path
    raw_tree: ET.ElementTree


def parse_layout(path: str | Path) -> Layout:
    """Parse xlights_rgbeffects.xml and return a Layout.

    Handles both legacy flat format (<xlights_rgbeffects><model .../>)
    and modern nested format (<xrgb><models><model .../></models></xrgb>).
    """
    path = Path(path)
    tree = ET.parse(path)
    root = tree.getroot()

    # Find all <model> elements — try nested <models>/<model> first, then flat
    model_elems = root.findall(".//model")

    props: list[Prop] = []
    for model in model_elems:
        name = model.get("name", "")
        sub_models = [sm.get("name", "") for sm in model.findall("subModel")]
        prop = Prop(
            name=name,
            display_as=model.get("DisplayAs", ""),
            world_x=float(model.get("WorldPosX", "0.0")),
            world_y=float(model.get("WorldPosY", "0.0")),
            world_z=float(model.get("WorldPosZ", "0.0")),
            scale_x=float(model.get("ScaleX", "1.0")),
            scale_y=float(model.get("ScaleY", "1.0")),
            parm1=int(model.get("parm1", "1")),
            parm2=int(model.get("parm2", "1")),
            sub_models=sub_models,
            custom_model=model.get("CustomModel", ""),
            x2=float(model.get("X2", "0.0")),
            y2=float(model.get("Y2", "0.0")),
        )
        props.append(prop)

    return Layout(props=props, source_path=path, raw_tree=tree)


def prop_type_for_display_as(display_as: str) -> str:
    """Map an xLights DisplayAs value to a canonical prop suitability key.

    Returns "outline" for unknown display types — the safest default since
    most linear/custom props behave like outlines.
    """
    return DISPLAY_AS_TO_PROP_TYPE.get(display_as, "outline")


def dominant_prop_type(props: list[Prop]) -> str:
    """Determine the most common prop suitability type among a list of props.

    Returns the canonical prop type key (matrix, outline, arch, etc.) that
    appears most frequently. Ties are broken alphabetically.
    """
    if not props:
        return "outline"
    counts = Counter(prop_type_for_display_as(p.display_as) for p in props)
    # most_common returns [(key, count), ...]; break ties alphabetically
    max_count = counts.most_common(1)[0][1]
    tied = sorted(k for k, v in counts.items() if v == max_count)
    return tied[0]
