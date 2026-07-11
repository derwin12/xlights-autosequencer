"""Layout endpoints — T053.

GET  /api/v1/layout  — return current layout or null
POST /api/v1/layout  — import xlights_rgbeffects.xml
"""
from __future__ import annotations

import datetime
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path

from flask import jsonify, request

from . import api_v1
from src.review.storage.library import load_library, save_library
from src.review.storage.paths import layout_xml_path


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


@api_v1.route("/layout", methods=["GET"])
def get_layout():
    lib = load_library()
    layout = lib.get("layout")
    if layout is None:
        return jsonify({"layout": None}), 200
    return jsonify(layout), 200


@api_v1.route("/layout", methods=["POST"])
def post_layout():
    if "layout_xml" not in request.files:
        return jsonify({"error": {"code": "missing_file",
                                   "message": "No layout_xml file provided"}}), 400

    f = request.files["layout_xml"]
    xml_bytes = f.read()

    if len(xml_bytes) > 20 * 1024 * 1024:
        return jsonify({"error": {"code": "file_too_large",
                                   "message": "File exceeds 20 MB limit"}}), 413

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        return jsonify({"error": {"code": "invalid_xml",
                                   "message": f"XML parse error: {exc}"}}), 400

    props = _parse_props(root)
    if not props:
        return jsonify({"error": {"code": "no_props_found",
                                   "message": "No xLights models found in the layout file"}}), 400

    layout_id = "layout_" + hashlib.sha256(xml_bytes).hexdigest()[:6]
    display_name = request.form.get("display_name") or (
        root.get("name") or root.findtext("layoutGroup") or "xLights Layout"
    )
    total_pixels = sum(p["pixel_count"] for p in props)

    # Persist the raw XML so the generator pipeline (which needs a real file
    # path to re-parse full model geometry, not just this summary) can find it.
    saved_path = layout_xml_path(layout_id)
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    saved_path.write_bytes(xml_bytes)

    from src.settings import save_settings
    save_settings({"layout_path": str(saved_path)})

    layout = {
        "layout_id": layout_id,
        "display_name": display_name,
        "imported_at": _now_iso(),
        "props": props,
        "total_pixels": total_pixels,
        "xml_path": str(saved_path),
    }

    lib = load_library()
    replaced_prior = lib.get("layout") is not None
    lib["layout"] = layout
    if "preferences" in lib:
        lib["preferences"]["layout_id"] = layout_id
    save_library(lib)

    resp = {
        "layout": layout,
        "replaced_prior": replaced_prior,
    }
    if replaced_prior:
        resp["warning"] = "Re-exporting any prior song against the new layout may produce different output."

    return jsonify(resp), 201
