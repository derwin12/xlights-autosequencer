"""Layout endpoints — T053.

GET /api/v1/layout — return the repo-committed xlights_rgbeffects.xml's layout

The layout is a fixed file committed at layout/xlights_rgbeffects.xml — there
is no per-session upload/replace; every song exports against this one layout.
"""
from __future__ import annotations

import datetime
import hashlib
import xml.etree.ElementTree as ET

from flask import jsonify

from . import api_v1
from src.paths import get_committed_layout_xml_path


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_mtime_iso(path) -> str:
    """ISO timestamp of a file's last modification — reflects when a git
    checkout/pull last wrote it to disk, i.e. the layout's last refresh."""
    return datetime.datetime.fromtimestamp(
        path.stat().st_mtime, tz=datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_props(root: ET.Element) -> list[dict]:
    """Extract prop list from xlights_rgbeffects root element."""
    model_elems = root.findall(".//model")
    props = []
    pixel_offset = 0
    for m in model_elems:
        name = m.get("name", "")
        display_as = m.get("DisplayAs", "SingleLine")
        parm1 = int(m.get("parm1", "1") or "1")
        parm2 = int(m.get("parm2", "1") or "1")
        pixel_count = max(parm1 * parm2, 1)
        prop = {
            "name": name,
            "display_type": display_as,
            "pixel_count": pixel_count,
            "pixel_range": [pixel_offset, pixel_offset + pixel_count - 1],
        }
        props.append(prop)
        pixel_offset += pixel_count
    return props


_committed_layout_cache: dict | None = None


def get_committed_layout() -> dict | None:
    """Return the parsed committed layout, or None if the file is missing/unreadable.

    Cached after first parse — the committed file only changes via a repo
    checkout + server restart, never at runtime.
    """
    global _committed_layout_cache
    if _committed_layout_cache is not None:
        return _committed_layout_cache

    path = get_committed_layout_xml_path()
    if not path.exists():
        return None

    xml_bytes = path.read_bytes()
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    props = _parse_props(root)
    total_pixels = sum(p["pixel_count"] for p in props)
    layout_id = "layout_" + hashlib.sha256(xml_bytes).hexdigest()[:6]
    display_name = root.get("name") or root.findtext("layoutGroup") or path.name

    _committed_layout_cache = {
        "layout_id": layout_id,
        "display_name": display_name,
        "imported_at": _file_mtime_iso(path),
        "props": props,
        "total_pixels": total_pixels,
        "xml_path": str(path),
    }
    return _committed_layout_cache


@api_v1.route("/layout", methods=["GET"])
def get_layout():
    layout = get_committed_layout()
    if layout is None:
        return jsonify({"layout": None}), 200
    return jsonify(layout), 200
