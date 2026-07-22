"""Layout endpoints — T053.

GET    /api/v1/layout — return the active layout (an uploaded override if
                         present, else the repo-committed
                         layout/xlights_rgbeffects.xml)
POST   /api/v1/layout — upload a replacement xlights_rgbeffects.xml
                         (optionally paired with xlights_networks.xml),
                         stored at ~/.xlight/layout/ so it survives a
                         ``git pull`` and doesn't need repo write access.
DELETE /api/v1/layout — remove the uploaded override, reverting to the
                         repo-committed layout.

Every song exports against whichever layout GET currently returns.
"""
from __future__ import annotations

import datetime
import hashlib
import xml.etree.ElementTree as ET

from flask import jsonify, request

from . import api_v1
from src.paths import (
    get_committed_layout_xml_path,
    get_uploaded_layout_dir,
    get_uploaded_layout_xml_path,
    get_uploaded_networks_xml_path,
)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_mtime_iso(path) -> str:
    """ISO timestamp of a file's last modification — reflects when the
    active layout (an upload, or a git checkout/pull) last changed."""
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


_active_layout_cache: dict | None = None


def _invalidate_active_layout_cache() -> None:
    global _active_layout_cache
    _active_layout_cache = None


def _active_layout_xml_path():
    """The layout xLights actually reads: an uploaded override if one
    exists, else the repo-committed file."""
    uploaded = get_uploaded_layout_xml_path()
    if uploaded.exists():
        return uploaded
    return get_committed_layout_xml_path()


def get_active_layout() -> dict | None:
    """Return the parsed active layout, or None if nothing is available.

    Cached per-process; the cache is invalidated explicitly by the upload
    and delete routes below (never silently stale — swapping which file is
    active always clears it, unlike the old committed-only cache which
    relied on a full server restart).
    """
    global _active_layout_cache
    if _active_layout_cache is not None:
        return _active_layout_cache

    path = _active_layout_xml_path()
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

    _active_layout_cache = {
        "layout_id": layout_id,
        "display_name": display_name,
        "imported_at": _file_mtime_iso(path),
        "props": props,
        "total_pixels": total_pixels,
        "xml_path": str(path),
        "is_uploaded": path == get_uploaded_layout_xml_path(),
    }
    return _active_layout_cache


@api_v1.route("/layout", methods=["GET"])
def get_layout():
    layout = get_active_layout()
    if layout is None:
        return jsonify({"layout": None}), 200
    return jsonify(layout), 200


@api_v1.route("/layout", methods=["POST"])
def upload_layout():
    """Upload a replacement layout, stored outside the repo checkout.

    Expects multipart/form-data with a ``rgbeffects`` file field (required)
    and an optional ``networks`` file field. Validated by parsing as XML
    with at least one <model> element before it's accepted — a malformed
    upload must not silently become the active layout.
    """
    upload = request.files.get("rgbeffects")
    if upload is None or not upload.filename:
        return jsonify({"error": {"code": "missing_file",
                                   "message": "No 'rgbeffects' file in the upload"}}), 400

    xml_bytes = upload.read()
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        return jsonify({"error": {"code": "invalid_xml",
                                   "message": f"Not valid XML: {exc}"}}), 400

    if not root.findall(".//model"):
        return jsonify({"error": {"code": "no_models",
                                   "message": "No <model> elements found — is this an xlights_rgbeffects.xml?"}}), 400

    dest_dir = get_uploaded_layout_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    get_uploaded_layout_xml_path().write_bytes(xml_bytes)

    networks_upload = request.files.get("networks")
    if networks_upload is not None and networks_upload.filename:
        get_uploaded_networks_xml_path().write_bytes(networks_upload.read())

    _invalidate_active_layout_cache()
    layout = get_active_layout()
    return jsonify(layout), 200


@api_v1.route("/layout", methods=["DELETE"])
def delete_uploaded_layout():
    """Remove the uploaded override, reverting to the repo-committed layout."""
    for path in (get_uploaded_layout_xml_path(), get_uploaded_networks_xml_path()):
        if path.exists():
            path.unlink()

    _invalidate_active_layout_cache()
    layout = get_active_layout()
    if layout is None:
        return jsonify({"layout": None}), 200
    return jsonify(layout), 200
