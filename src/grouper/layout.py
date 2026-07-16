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


@dataclass(frozen=True)
class SubModel:
    """A named pixel region inside a Custom xLights model.

    `name` is the subModel name as authored in xlights_rgbeffects.xml
    (e.g. "Ring 1").  `pixel_indices` holds the 1-indexed pixel positions
    parsed from the lineN attributes, in declaration order — declaration
    order matters because xLights uses it to drive intra-subModel effect
    direction.
    """
    name: str
    pixel_indices: tuple[int, ...] = ()


def parse_pixel_ranges(spec: str) -> tuple[int, ...]:
    """Parse an xLights subModel lineN attribute into 1-indexed pixel indices.

    Tokens are comma-separated; each token is either ``"N"`` or ``"N-M"``.
    Reverse ranges (``"16-15"``) are valid in xLights and yield indices in
    reverse order.  Empty / whitespace input → empty tuple.  A non-numeric
    token raises ``ValueError`` rather than being silently dropped — bad
    layout XML should fail loudly.
    """
    if not spec or not spec.strip():
        return ()
    out: list[int] = []
    for raw in spec.split(","):
        token = raw.strip()
        if not token:
            continue
        if "-" in token:
            lo_s, hi_s = token.split("-", 1)
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError as exc:
                raise ValueError(f"bad pixel-range token: {token!r}") from exc
            step = 1 if hi >= lo else -1
            out.extend(range(lo, hi + step, step))
        else:
            try:
                out.append(int(token))
            except ValueError as exc:
                raise ValueError(f"bad pixel-range token: {token!r}") from exc
    return tuple(out)


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
    sub_models: list[SubModel]
    custom_model: str = ""  # raw CustomModel grid CSV (empty for non-Custom models)
    x2: float = 0.0  # endpoint offset X (Single Line / Poly Line models)
    y2: float = 0.0  # endpoint offset Y (Single Line / Poly Line models)
    # computed by classifier
    pixel_count: int = 0
    norm_x: float = 0.0
    norm_y: float = 0.0
    aspect_ratio: float = 1.0
    # Names of NodeRange <faceInfo> definitions on this model (node-mapped
    # mouth shapes for dedicated singing props). Image-based Matrix face
    # definitions are deliberately excluded — matrices/trees with downloaded
    # face image sets should not receive auto-placed Faces effects.
    face_definitions: list[str] = field(default_factory=list)


# DisplayAs value for xLights' DMX moving-head fixture model. Not part of
# DISPLAY_AS_TO_PROP_TYPE / the 6 canonical prop-suitability keys -- a moving
# head is not an RGB pixel prop (its "pixels" are DMX channel placeholders
# for Pan/Tilt/Gobo/etc.), so it must never be routed through the generic
# prop_suitability effect-selection pipeline. See find_moving_head_groups().
MOVING_HEAD_DISPLAY_AS = "DmxMovingHeadAdv"


@dataclass(frozen=True)
class MovingHeadGroup:
    """An xLights modelGroup made up entirely of moving-head fixtures.

    ``head_names`` preserves the group's authored ``models=`` order, which
    is also the order xLights numbers MH1_Settings..MHN_Settings in the
    Moving Head effect.
    """
    name: str
    head_names: tuple[str, ...]


@dataclass
class Layout:
    props: list[Prop]
    source_path: Path
    raw_tree: ET.ElementTree


def find_moving_head_groups(layout: Layout) -> list[MovingHeadGroup]:
    """Find modelGroups made up entirely of moving-head fixtures.

    A group with a mix of moving-head and regular RGB models is skipped
    (there's no single group_effects target that's fully DMX or fully RGB
    for it), so a malformed layout produces no placements rather than a
    partially-wrong one.
    """
    moving_head_names = {p.name for p in layout.props if p.display_as == MOVING_HEAD_DISPLAY_AS}
    if not moving_head_names:
        return []
    groups: list[MovingHeadGroup] = []
    for group_elem in layout.raw_tree.getroot().findall(".//modelGroup"):
        models_attr = group_elem.get("models", "")
        member_names = [m for m in models_attr.split(",") if m]
        if member_names and all(m in moving_head_names for m in member_names):
            groups.append(MovingHeadGroup(
                name=group_elem.get("name", ""),
                head_names=tuple(member_names),
            ))
    return groups


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
        sub_models: list[SubModel] = []
        for sm in model.findall("subModel"):
            sm_name = sm.get("name", "")
            indices: list[int] = []
            # Concatenate line0, line1, line2, ... in numeric order until the
            # next attribute is missing.  xLights stacks lines for the visual
            # layout but for effect targeting the union of all referenced
            # pixels is what matters.
            i = 0
            while True:
                line = sm.get(f"line{i}")
                if line is None:
                    break
                try:
                    indices.extend(parse_pixel_ranges(line))
                except ValueError:
                    # Bad data in user XML — skip this line, keep parsing
                    # the rest of the model so a single typo doesn't break
                    # the whole layout load.
                    pass
                i += 1
            sub_models.append(SubModel(name=sm_name, pixel_indices=tuple(indices)))
        face_definitions = [
            fi.get("Name", "")
            for fi in model.findall("faceInfo")
            if fi.get("Type") == "NodeRange" and fi.get("Name")
            # Require actual mouth node data: opening the Faces dialog on a
            # prop leaves an empty NodeRange shell (all Mouth-* blank) behind,
            # which must not count as a singing face.
            and any(
                v.strip()
                for k, v in fi.attrib.items()
                if k.startswith("Mouth-") and not k.endswith("-Color")
            )
        ]
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
            face_definitions=face_definitions,
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
