"""Section endpoints — GET/edit/split/merge/promote-ghost/delete/rename/reset.

T049: GET /api/v1/songs/<song_id>/sections
T102: POST   .../sections/split
       POST   .../sections/merge
       POST   .../sections/promote-ghost
       DELETE .../sections/<idx>
       PATCH  .../sections/<idx>
       POST   .../sections/reset
"""
from __future__ import annotations

from flask import jsonify, request

from . import api_v1
from src.review.storage.library import load_library
from src.review.storage.assignments import load_session, save_session, save_full_session

# Re-use the same default-assignment builder as the analysis module.
from src.review.api.v1.analysis import _auto_assign_defaults

_MIN_SECTION_MS = 500  # FR-021: reject splits that produce < 500ms halves


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_song(song_id: str):
    """Return (song, lib) or None if not found."""
    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    return song, lib


def _reindex(sections: list[dict]) -> list[dict]:
    """Re-assign contiguous index values to a mutable section list in place."""
    for i, sec in enumerate(sections):
        sec["index"] = i
    return sections


def _sync_assignments(
    sections: list[dict],
    old_assignments: list[dict],
    new_section_themes: list[str | None],
) -> list[dict]:
    """Build a fresh assignment list aligned to the new section list.

    new_section_themes[i] is the theme_id to assign to sections[i].
    Inherits overrides from old_assignments when the theme is the same.
    """
    from src.review.api.v1.analysis import _default_overrides

    def _overrides_for(idx: int, theme_id: str | None) -> dict:
        if idx < len(old_assignments):
            old = old_assignments[idx]
            if old.get("theme_id") == theme_id:
                return old.get("overrides", _default_overrides())
        return _default_overrides()

    assignments = []
    for i, sec in enumerate(sections):
        theme_id = new_section_themes[i]
        assignments.append({
            "section_index": i,
            "theme_id": theme_id,
            "overrides": _overrides_for(i, theme_id),
            "user_confirmed": False,
        })
    return assignments


# ---------------------------------------------------------------------------
# GET /api/v1/songs/<song_id>/sections  (T049)
# ---------------------------------------------------------------------------

@api_v1.route("/songs/<song_id>/sections", methods=["GET"])
def get_sections(song_id: str):
    song, _lib = _load_song(song_id)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    if song.get("status") == "draft":
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "Song has not been analyzed yet"}}), 409

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No analysis result available"}}), 409

    sections = session.get("sections", [])
    return jsonify({
        "sections": sections,
        "ghost_boundaries": session.get("ghost_boundaries", []),
    }), 200


# ---------------------------------------------------------------------------
# POST .../sections/split  (T102, FR-021)
# ---------------------------------------------------------------------------

@api_v1.route("/songs/<song_id>/sections/split", methods=["POST"])
def split_section(song_id: str):
    song, _lib = _load_song(song_id)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No analysis result available"}}), 409

    body = request.get_json(silent=True) or {}
    at_ms = body.get("at_ms")
    if at_ms is None:
        return jsonify({"error": {"code": "missing_field",
                                   "message": "at_ms is required"}}), 400

    sections = list(session.get("sections", []))
    assignments = list(session.get("assignments", []))

    # Find the section that contains at_ms
    target_idx: int | None = None
    for i, sec in enumerate(sections):
        if sec["start_ms"] < at_ms < sec["end_ms"]:
            target_idx = i
            break

    if target_idx is None:
        # at_ms is at or outside a boundary
        return jsonify({"error": {"code": "split_at_boundary",
                                   "message": "Split point is at or outside an existing boundary"}}), 422

    sec = sections[target_idx]

    # Check both halves are at least MIN_SECTION_MS
    left_dur = at_ms - sec["start_ms"]
    right_dur = sec["end_ms"] - at_ms
    if left_dur < _MIN_SECTION_MS or right_dur < _MIN_SECTION_MS:
        return jsonify({"error": {"code": "section_too_short",
                                   "message": "Split would create a section shorter than 500ms"}}), 422

    # Build the two replacement sections
    original_label = sec.get("label", sec.get("kind", "Section"))
    left = {
        "index": 0,  # will be reindexed
        "start_ms": sec["start_ms"],
        "end_ms": at_ms,
        "kind": sec.get("kind", "unknown"),
        "label": original_label,
    }
    right = {
        "index": 0,
        "start_ms": at_ms,
        "end_ms": sec["end_ms"],
        "kind": sec.get("kind", "unknown"),
        "label": original_label,
    }

    # Splice
    new_sections = sections[:target_idx] + [left, right] + sections[target_idx + 1:]
    _reindex(new_sections)

    # Build theme list: both halves inherit original theme
    original_theme = assignments[target_idx]["theme_id"] if target_idx < len(assignments) else None
    old_themes = [a["theme_id"] for a in assignments]
    new_themes = old_themes[:target_idx] + [original_theme, original_theme] + old_themes[target_idx + 1:]
    new_assignments = _sync_assignments(new_sections, assignments, new_themes)

    save_full_session(song_id, {
        **session,
        "sections": new_sections,
        "detected_sections": session.get("detected_sections", session.get("sections", [])),
        "assignments": new_assignments,
        "ghost_boundaries": session.get("ghost_boundaries", []),
    })

    return jsonify({
        "sections": new_sections,
        "assignments": new_assignments,
    }), 200


# ---------------------------------------------------------------------------
# POST .../sections/merge  (T102, FR-022)
# ---------------------------------------------------------------------------

@api_v1.route("/songs/<song_id>/sections/merge", methods=["POST"])
def merge_sections(song_id: str):
    song, _lib = _load_song(song_id)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No analysis result available"}}), 409

    body = request.get_json(silent=True) or {}
    section_index = body.get("section_index")
    if section_index is None:
        return jsonify({"error": {"code": "missing_field",
                                   "message": "section_index is required"}}), 400

    sections = list(session.get("sections", []))
    assignments = list(session.get("assignments", []))

    if section_index < 0 or section_index >= len(sections):
        return jsonify({"error": {"code": "section_not_found",
                                   "message": "Section index out of range"}}), 404

    if section_index == len(sections) - 1:
        return jsonify({"error": {"code": "no_follower",
                                   "message": "Cannot merge the last section — no following section"}}), 422

    sec_a = sections[section_index]
    sec_b = sections[section_index + 1]

    merged = {
        "index": 0,
        "start_ms": sec_a["start_ms"],
        "end_ms": sec_b["end_ms"],
        "kind": sec_a.get("kind", "unknown"),
        "label": sec_a.get("label", ""),
    }

    new_sections = sections[:section_index] + [merged] + sections[section_index + 2:]
    _reindex(new_sections)

    # First-wins: keep theme from section_index
    old_themes = [a["theme_id"] for a in assignments]
    first_theme = old_themes[section_index] if section_index < len(old_themes) else None
    new_themes = old_themes[:section_index] + [first_theme] + old_themes[section_index + 2:]
    new_assignments = _sync_assignments(new_sections, assignments, new_themes)

    save_full_session(song_id, {
        **session,
        "sections": new_sections,
        "detected_sections": session.get("detected_sections", session.get("sections", [])),
        "assignments": new_assignments,
        "ghost_boundaries": session.get("ghost_boundaries", []),
    })

    return jsonify({"sections": new_sections, "assignments": new_assignments}), 200


# ---------------------------------------------------------------------------
# POST .../sections/promote-ghost  (T102, FR-025)
# ---------------------------------------------------------------------------

@api_v1.route("/songs/<song_id>/sections/promote-ghost", methods=["POST"])
def promote_ghost(song_id: str):
    song, _lib = _load_song(song_id)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No analysis result available"}}), 409

    body = request.get_json(silent=True) or {}
    at_ms = body.get("at_ms")
    if at_ms is None:
        return jsonify({"error": {"code": "missing_field",
                                   "message": "at_ms is required"}}), 400

    # Find a ghost boundary at this time (within a small tolerance)
    ghost_boundaries = session.get("ghost_boundaries", [])
    _TOLERANCE_MS = 50
    ghost = next(
        (g for g in ghost_boundaries if abs(g["at_ms"] - at_ms) <= _TOLERANCE_MS),
        None,
    )
    if ghost is None:
        return jsonify({"error": {"code": "ghost_not_found",
                                   "message": "No ghost boundary at this time"}}), 404

    # Perform the split at ghost at_ms
    sections = list(session.get("sections", []))
    assignments = list(session.get("assignments", []))

    target_idx: int | None = None
    for i, sec in enumerate(sections):
        if sec["start_ms"] < ghost["at_ms"] < sec["end_ms"]:
            target_idx = i
            break

    if target_idx is None:
        return jsonify({"error": {"code": "ghost_not_found",
                                   "message": "Ghost boundary falls outside any section"}}), 404

    sec = sections[target_idx]
    left_dur = ghost["at_ms"] - sec["start_ms"]
    right_dur = sec["end_ms"] - ghost["at_ms"]
    if left_dur < _MIN_SECTION_MS or right_dur < _MIN_SECTION_MS:
        return jsonify({"error": {"code": "section_too_short",
                                   "message": "Promoted ghost boundary would create a section shorter than 500ms"}}), 422

    original_label = sec.get("label", sec.get("kind", "Section"))
    left = {
        "index": 0,
        "start_ms": sec["start_ms"],
        "end_ms": ghost["at_ms"],
        "kind": sec.get("kind", "unknown"),
        "label": original_label,
    }
    right = {
        "index": 0,
        "start_ms": ghost["at_ms"],
        "end_ms": sec["end_ms"],
        "kind": sec.get("kind", "unknown"),
        "label": original_label,
    }

    new_sections = sections[:target_idx] + [left, right] + sections[target_idx + 1:]
    _reindex(new_sections)

    # Both halves inherit original theme
    original_theme = assignments[target_idx]["theme_id"] if target_idx < len(assignments) else None
    old_themes = [a["theme_id"] for a in assignments]
    new_themes = old_themes[:target_idx] + [original_theme, original_theme] + old_themes[target_idx + 1:]
    new_assignments = _sync_assignments(new_sections, assignments, new_themes)

    # Remove the promoted ghost boundary
    new_ghosts = [g for g in ghost_boundaries if abs(g["at_ms"] - at_ms) > _TOLERANCE_MS]

    save_full_session(song_id, {
        **session,
        "sections": new_sections,
        "detected_sections": session.get("detected_sections", session.get("sections", [])),
        "assignments": new_assignments,
        "ghost_boundaries": new_ghosts,
    })

    return jsonify({
        "sections": new_sections,
        "assignments": new_assignments,
        "ghost_boundaries": new_ghosts,
    }), 200


# ---------------------------------------------------------------------------
# DELETE .../sections/<section_index>  (T102, FR-023)
# ---------------------------------------------------------------------------

@api_v1.route("/songs/<song_id>/sections/<int:section_index>", methods=["DELETE"])
def delete_section(song_id: str, section_index: int):
    song, _lib = _load_song(song_id)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No analysis result available"}}), 409

    sections = list(session.get("sections", []))
    assignments = list(session.get("assignments", []))

    if section_index < 0 or section_index >= len(sections):
        return jsonify({"error": {"code": "section_not_found",
                                   "message": "Section index out of range"}}), 404

    if len(sections) == 1:
        return jsonify({"error": {"code": "last_section_required",
                                   "message": "Cannot delete the only remaining section"}}), 422

    sec = sections[section_index]

    # Merge time range into the previous section if it exists, otherwise into the next
    new_sections = [s.copy() for s in sections]
    if section_index > 0:
        # Absorb into previous: extend its end_ms
        new_sections[section_index - 1]["end_ms"] = sec["end_ms"]
    else:
        # Absorb into next: extend its start_ms
        new_sections[section_index + 1]["start_ms"] = sec["start_ms"]

    # Remove the deleted section
    new_sections.pop(section_index)
    _reindex(new_sections)

    # Remove corresponding assignment and rebuild
    old_themes = [a["theme_id"] for a in assignments]
    new_themes = old_themes[:section_index] + old_themes[section_index + 1:]
    new_assignments = _sync_assignments(new_sections, assignments, new_themes)

    save_full_session(song_id, {
        **session,
        "sections": new_sections,
        "detected_sections": session.get("detected_sections", session.get("sections", [])),
        "assignments": new_assignments,
        "ghost_boundaries": session.get("ghost_boundaries", []),
    })

    return jsonify({"sections": new_sections, "assignments": new_assignments}), 200


# ---------------------------------------------------------------------------
# PATCH .../sections/<section_index>  (T102, FR-024)
# ---------------------------------------------------------------------------

@api_v1.route("/songs/<song_id>/sections/<int:section_index>", methods=["PATCH"])
def rename_section(song_id: str, section_index: int):
    song, _lib = _load_song(song_id)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No analysis result available"}}), 409

    sections = list(session.get("sections", []))
    assignments = list(session.get("assignments", []))

    if section_index < 0 or section_index >= len(sections):
        return jsonify({"error": {"code": "section_not_found",
                                   "message": "Section index out of range"}}), 404

    body = request.get_json(silent=True) or {}
    label = body.get("label")
    if label is None:
        return jsonify({"error": {"code": "missing_field",
                                   "message": "label is required"}}), 400

    label = str(label)
    if not label.strip() or len(label) > 64:
        return jsonify({"error": {"code": "invalid_label",
                                   "message": "Label must be 1–64 non-whitespace characters"}}), 400

    sections[section_index]["label"] = label
    save_full_session(song_id, {
        **session,
        "sections": sections,
        "detected_sections": session.get("detected_sections", sections),
        "assignments": assignments,
        "ghost_boundaries": session.get("ghost_boundaries", []),
    })

    return jsonify({"section": sections[section_index]}), 200


# ---------------------------------------------------------------------------
# POST .../sections/reset  (T102, FR-026)
# ---------------------------------------------------------------------------

@api_v1.route("/songs/<song_id>/sections/reset", methods=["POST"])
def reset_sections(song_id: str):
    song, _lib = _load_song(song_id)
    if song is None:
        return jsonify({"error": {"code": "song_not_found",
                                   "message": "Song not found"}}), 404

    if song.get("status") == "draft":
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "Song has not been analyzed yet"}}), 409

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No analysis result available"}}), 409

    detected = session.get("detected_sections") or session.get("sections", [])
    ghost_boundaries = session.get("original_ghost_boundaries") or session.get("ghost_boundaries", [])

    # Re-derive default assignments per FR-012a
    new_assignments = _auto_assign_defaults(song_id, detected)

    save_session(song_id, detected, new_assignments)

    return jsonify({
        "sections": detected,
        "ghost_boundaries": ghost_boundaries,
        "assignments": new_assignments,
        "user_confirmed": False,
    }), 200
