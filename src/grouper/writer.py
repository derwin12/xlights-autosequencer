"""Inject PowerGroups into an ET.ElementTree and write to disk."""
from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from src.grouper.grouper import PowerGroup
from src.grouper.layout import Layout

AUTO_PREFIXES = (
    "01_BASE_",
    "02_GEO_",
    "03_TYPE_",
    "04_BEAT_",
    "05_TEX_",
    "06_PROP_",
    "07_COMP_",
    "08_HERO_",
)


def _is_auto_group(name: str) -> bool:
    return any(name.startswith(p) for p in AUTO_PREFIXES)


def inject_groups(raw_tree: ET.ElementTree, groups: list[PowerGroup]) -> None:
    """Remove old auto-groups and append new group elements in place.

    Handles both formats:
    - Legacy/test: <ModelGroup> elements directly under root
    - Modern xLights: <modelGroup> elements under <modelGroups>

    Manual groups (no auto prefix) are preserved unchanged.
    Empty groups (no members) are omitted.
    """
    root = raw_tree.getroot()

    # Detect format: modern xLights nests groups in <modelGroups>
    groups_container = root.find("modelGroups")
    is_modern = groups_container is not None

    if is_modern:
        # Modern format: <modelGroups><modelGroup .../></modelGroups>
        for mg in groups_container.findall("modelGroup"):
            if _is_auto_group(mg.get("name", "")):
                groups_container.remove(mg)

        for group in groups:
            if not group.members:
                continue
            el = ET.SubElement(groups_container, "modelGroup")
            el.set("name", group.name)
            el.set("models", ",".join(group.members))
    else:
        # Legacy/test format: <ModelGroup .../> directly under root
        for mg in root.findall("ModelGroup"):
            if _is_auto_group(mg.get("name", "")):
                root.remove(mg)

        for group in groups:
            if not group.members:
                continue
            el = ET.SubElement(root, "ModelGroup")
            el.set("name", group.name)
            el.set("models", ",".join(group.members))


def write_layout(layout: Layout, output_path: str | Path) -> None:
    """Write the raw_tree to output_path, creating a .xml.bak backup for in-place writes."""
    output_path = Path(output_path)

    # Create backup before in-place overwrite (preserves pristine original)
    bak_path = output_path.with_name(output_path.name + ".bak")
    if output_path == layout.source_path and not bak_path.exists():
        shutil.copy2(output_path, bak_path)

    ET.indent(layout.raw_tree, space="    ")
    with open(output_path, "w", encoding="UTF-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        layout.raw_tree.write(fh, encoding="unicode", xml_declaration=False)
