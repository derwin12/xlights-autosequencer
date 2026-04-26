"""xLights layout parser.

Reads xlights_rgbeffects.xml (models) + xlights_networks.xml (controllers) and
returns Models with their per-pixel positions in canonical local coords plus
the world-space transform parameters (Scale / Rotate / Translate).

The Renderer takes these and produces the final 2D screen positions.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Controller:
    name: str
    start: int   # absolute 0-based start channel in the FSEQ
    length: int


@dataclass
class Model:
    name: str
    display_as: str
    start_channel: int   # absolute, 0-based
    n_pixels: int
    parm1: int
    parm2: int
    parm3: int
    world_x: float
    world_y: float
    world_z: float
    scale_x: float
    scale_y: float
    scale_z: float
    rotate_x: float   # degrees
    rotate_y: float
    rotate_z: float
    custom_grid: list[list[int]] = field(default_factory=list)
    custom_w: int = 0
    custom_h: int = 0


def parse_controllers(networks_path: Path) -> dict[str, Controller]:
    """Walk xlights_networks.xml, sort by Id, accumulate channel ranges."""
    tree = ET.parse(networks_path)
    root = tree.getroot()
    items = []
    for c in root.findall("Controller"):
        idn = int(c.attrib.get("Id", 0))
        name = c.attrib["Name"]
        max_ch = 0
        net = c.find("network")
        if net is not None:
            max_ch = int(net.attrib.get("MaxChannels", 0))
        protocol = c.attrib.get("Protocol", "")
        items.append((idn, name, max_ch, protocol))
    items.sort()
    out = {}
    cursor = 0
    for _, name, max_ch, proto in items:
        if proto == "Player Only" or max_ch == 0:
            out[name] = Controller(name=name, start=cursor, length=0)
            continue
        out[name] = Controller(name=name, start=cursor, length=max_ch)
        cursor += max_ch
    return out


_START_PAT = re.compile(r"!([^:]+):(\d+)")


def resolve_start_channel(start_str: str, controllers: dict[str, Controller]) -> int | None:
    """Resolve `!Controller:N` to absolute 0-based channel; or parse a plain int."""
    m = _START_PAT.match(start_str.strip())
    if not m:
        try:
            return int(start_str) - 1
        except ValueError:
            return None
    name, ch = m.group(1), int(m.group(2))
    ctl = controllers.get(name)
    if ctl is None:
        return None
    return ctl.start + ch - 1


def _parse_custom_model(s: str) -> tuple[list[list[int]], int, int]:
    """xLights CustomModel string: rows separated by ;, cells by ,. Empty cell = no pixel."""
    rows = []
    width = 0
    for raw_row in s.split(";"):
        cells = []
        for c in raw_row.split(","):
            c = c.strip()
            if not c:
                cells.append(0)
            else:
                try:
                    cells.append(int(c))
                except ValueError:
                    cells.append(0)
        rows.append(cells)
        width = max(width, len(cells))
    for r in rows:
        while len(r) < width:
            r.append(0)
    return rows, width, len(rows)


def parse_models(rgbeffects_path: Path, controllers: dict[str, Controller]) -> list[Model]:
    """Walk xlights_rgbeffects.xml and return one Model per top-level <model>."""
    tree = ET.parse(rgbeffects_path)
    root = tree.getroot()
    out = []
    for m in root.find("models").findall("model"):
        sc = resolve_start_channel(m.attrib.get("StartChannel", "1"), controllers)
        if sc is None:
            continue
        try:
            p1 = int(m.attrib.get("parm1", 1))
            p2 = int(m.attrib.get("parm2", 1))
            p3 = int(m.attrib.get("parm3", 1))
        except ValueError:
            continue

        display_as = m.attrib.get("DisplayAs", "Single Line")
        if display_as == "Custom":
            grid_str = m.attrib.get("CustomModel", "")
            grid, gw, gh = _parse_custom_model(grid_str) if grid_str else ([], 0, 0)
            n_pix = max((max(row) for row in grid if row), default=0)
        elif display_as == "Cube":
            n_pix = p1 * p2 * p3
            grid, gw, gh = [], 0, 0
        else:
            n_pix = p1 * p2
            grid, gw, gh = [], 0, 0

        try:
            wx = float(m.attrib.get("WorldPosX", 0))
            wy = float(m.attrib.get("WorldPosY", 0))
            wz = float(m.attrib.get("WorldPosZ", 0))
            sx = float(m.attrib.get("ScaleX", 1))
            sy = float(m.attrib.get("ScaleY", 1))
            sz = float(m.attrib.get("ScaleZ", 1))
            rx = float(m.attrib.get("RotateX", 0))
            ry = float(m.attrib.get("RotateY", 0))
            rz = float(m.attrib.get("RotateZ", 0))
        except ValueError:
            continue

        out.append(Model(
            name=m.attrib.get("name", "?"),
            display_as=display_as, start_channel=sc, n_pixels=n_pix,
            parm1=p1, parm2=p2, parm3=p3,
            world_x=wx, world_y=wy, world_z=wz,
            scale_x=sx, scale_y=sy, scale_z=sz,
            rotate_x=rx, rotate_y=ry, rotate_z=rz,
            custom_grid=grid, custom_w=gw, custom_h=gh,
        ))
    return out


# ---- Per-model pixel placement in canonical local coords ----
#
# Each model returns its pixels in a [0..default_size_X, 0..default_size_Y, 0..default_size_Z]
# box plus the default_size tuple. Caller centers, scales, rotates, and translates
# to world coords.

def model_local_pixels(model: Model) -> tuple[np.ndarray, tuple[float, float, float]]:
    n = model.n_pixels
    if n <= 0:
        return np.zeros((0, 3), dtype=np.float32), (1.0, 1.0, 1.0)

    da = model.display_as

    if da == "Custom" and model.custom_grid:
        positions = np.zeros((n, 3), dtype=np.float32)
        for r, row in enumerate(model.custom_grid):
            for c, pix in enumerate(row):
                if 0 < pix <= n:
                    # Flip Y so row 0 is at top of model
                    positions[pix - 1] = (c, model.custom_h - 1 - r, 0)
        return positions, (model.custom_w, model.custom_h, 1)

    if da in ("Horiz Matrix", "Vert Matrix"):
        # parm1 = strings, parm2 = pixels per string, parm3 = strands per string
        # (zigzag count). Total width/height = strings * strands × pixels-per-strand.
        strings = max(model.parm1, 1)
        per_string = max(model.parm2, 1)
        strands = max(model.parm3, 1)
        per_strand = max(per_string // strands, 1)
        positions = np.zeros((n, 3), dtype=np.float32)
        if da == "Vert Matrix":
            cols = strings * strands
            rows = per_strand
            for i in range(n):
                if i >= n:
                    break
                string = i // per_string
                in_string = i % per_string
                strand = in_string // per_strand
                in_strand = in_string % per_strand
                col = string * strands + strand
                # Zigzag: even strands go top-to-bottom, odd strands bottom-to-top
                row = in_strand if strand % 2 == 0 else (per_strand - 1 - in_strand)
                positions[i] = (col, rows - 1 - row, 0)
        else:  # Horiz Matrix
            cols = per_strand
            rows = strings * strands
            for i in range(n):
                string = i // per_string
                in_string = i % per_string
                strand = in_string // per_strand
                in_strand = in_string % per_strand
                row = string * strands + strand
                col = in_strand if strand % 2 == 0 else (per_strand - 1 - in_strand)
                positions[i] = (col, rows - 1 - row, 0)
        return positions, (cols, rows, 1)

    if da == "Cube":
        w, h, d = model.parm1, model.parm2, model.parm3
        positions = np.zeros((n, 3), dtype=np.float32)
        per_face = w * h
        for i in range(n):
            slab = i // per_face
            within = i % per_face
            r = within // w
            c = within % w
            positions[i] = (c, h - 1 - r, slab)
        return positions, (w, h, d)

    if da == "Star":
        positions = np.zeros((n, 3), dtype=np.float32)
        center = 0.5
        for i in range(n):
            ring = i // model.parm2
            within = i % model.parm2
            ratio = (ring + 1) / max(model.parm1, 1)
            radius = 0.5 * ratio
            angle = 2 * np.pi * within / max(model.parm2, 1) - np.pi / 2
            positions[i] = (
                center + radius * np.cos(angle),
                center + radius * np.sin(angle),
                0,
            )
        return positions, (1, 1, 1)

    if da.startswith("Tree"):
        positions = np.zeros((n, 3), dtype=np.float32)
        strings = max(model.parm1, 1)
        per = max(model.parm2, 1)
        for s in range(strings):
            base_angle = 2 * np.pi * s / strings
            for j in range(per):
                idx = s * per + j
                if idx >= n:
                    break
                t = j / max(per - 1, 1)
                radius = 0.5 * (1 - t)
                angle = base_angle + t * np.pi
                positions[idx] = (
                    0.5 + radius * np.cos(angle),
                    t,
                    0.5 + radius * np.sin(angle),
                )
        return positions, (1, 1, 1)

    if da == "Arches":
        per = max(model.parm2, 1)
        arches = max(model.parm1, 1)
        positions = np.zeros((n, 3), dtype=np.float32)
        for ai in range(arches):
            arch_x_center = (ai + 0.5) / arches
            for j in range(per):
                idx = ai * per + j
                if idx >= n:
                    break
                angle = np.pi * j / max(per - 1, 1)
                arch_radius = 0.5 / arches
                positions[idx] = (
                    arch_x_center + arch_radius * np.cos(np.pi - angle),
                    arch_radius * np.sin(angle),
                    0,
                )
        return positions, (1, 1, 1)

    # Single Line and fallthrough — strip along +X axis
    positions = np.zeros((n, 3), dtype=np.float32)
    for i in range(n):
        positions[i] = (i / max(n - 1, 1), 0, 0)
    return positions, (max(n, 1), 1, 1)
