"""Assignment endpoints — T051.

GET  /api/v1/songs/<song_id>/assignments
PUT  /api/v1/songs/<song_id>/assignments/<section_index>
POST /api/v1/songs/<song_id>/assignments/accept-all
POST /api/v1/songs/<song_id>/assignments/reset-defaults
POST /api/v1/songs/<song_id>/load-bundle
"""
from __future__ import annotations

from flask import jsonify, request

from . import api_v1
from .themes import _load_themes
from src.review.storage.library import load_library, save_library
from src.review.storage.assignments import load_session, save_session, save_full_session

_DEFAULT_OVERRIDES = {
    "brightness": 1.0,
    "hit_strength": 0.5,
    "dwell_time": 1.0,
    "color_shift": 0.0,
}


def _valid_theme_ids() -> set[str]:
    """Real theme catalog IDs (built-in + custom), loaded live so this never goes stale."""
    return {theme["theme_id"] for theme in _load_themes()}


def _get_song_or_error(song_id: str):
    """Return (song, None) or (None, error_response)."""
    lib = load_library()
    song = next((s for s in lib["songs"] if s["song_id"] == song_id), None)
    if song is None:
        return None, None, (jsonify({"error": {"code": "song_not_found",
                                                "message": "Song not found"}}), 404)
    return song, lib, None


@api_v1.route("/songs/<song_id>/assignments", methods=["GET"])
def get_assignments(song_id: str):
    song, lib, err = _get_song_or_error(song_id)
    if err:
        return err

    if song.get("status") == "draft":
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "Song has not been analyzed yet"}}), 409

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No session data available"}}), 409

    return jsonify({
        "assignments": session.get("assignments", []),
        "song_status": song.get("status", "analyzed"),
    }), 200


@api_v1.route("/songs/<song_id>/assignments/<int:section_index>", methods=["PUT"])
def put_assignment(song_id: str, section_index: int):
    song, lib, err = _get_song_or_error(song_id)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    theme_id = body.get("theme_id")
    overrides_patch = body.get("overrides") or {}

    if theme_id and theme_id not in _valid_theme_ids():
        return jsonify({"error": {"code": "theme_not_found",
                                   "message": f"Theme '{theme_id}' not found"}}), 404

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No session data available"}}), 409

    assignments = session.get("assignments", [])
    sections = session.get("sections", [])

    assignment = next((a for a in assignments if a["section_index"] == section_index), None)
    if assignment is None:
        return jsonify({"error": {"code": "section_not_found",
                                   "message": f"Section {section_index} not found"}}), 404

    # FR-032a: changing theme_id resets overrides to defaults first
    if theme_id and theme_id != assignment.get("theme_id"):
        assignment["overrides"] = dict(_DEFAULT_OVERRIDES)
        assignment["theme_id"] = theme_id
        assignment["user_confirmed"] = True

    # Apply any explicit override patches
    if overrides_patch:
        for k, v in overrides_patch.items():
            if k in assignment["overrides"]:
                assignment["overrides"][k] = v

    if theme_id:
        assignment["user_confirmed"] = True

    save_session(song_id, sections, assignments)

    # Check if all sections now confirmed — flip status to "themed"
    all_confirmed = all(
        a.get("user_confirmed") and a.get("theme_id")
        for a in assignments
    )
    song_status = song.get("status", "analyzed")
    if all_confirmed and song_status == "analyzed":
        for s in lib["songs"]:
            if s["song_id"] == song_id:
                s["status"] = "themed"
                song_status = "themed"
                break
        save_library(lib)

    return jsonify({
        "assignment": assignment,
        "song_status": song_status,
    }), 200


@api_v1.route("/songs/<song_id>/assignments/accept-all", methods=["POST"])
def accept_all_assignments(song_id: str):
    song, lib, err = _get_song_or_error(song_id)
    if err:
        return err

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No session data available"}}), 409

    assignments = session.get("assignments", [])
    sections = session.get("sections", [])

    # Check all assignments have a theme_id
    incomplete = [a for a in assignments if not a.get("theme_id")]
    if incomplete:
        return jsonify({"error": {"code": "incomplete_assignments",
                                   "message": "Some sections have no theme assigned"}}), 409

    count = 0
    for a in assignments:
        if not a.get("user_confirmed"):
            a["user_confirmed"] = True
            count += 1
        else:
            count += 1  # count all confirmed

    save_session(song_id, sections, assignments)

    # Flip song status to "themed"
    for s in lib["songs"]:
        if s["song_id"] == song_id:
            s["status"] = "themed"
            break
    save_library(lib)

    return jsonify({"song_status": "themed", "confirmed_count": count}), 200


@api_v1.route("/songs/<song_id>/assignments/reset-defaults", methods=["POST"])
def reset_assignments_to_defaults(song_id: str):
    """Discard every section's theme/parameter choice and restore the AI's
    smart-default pick (same selector used at initial analysis). Applies to
    ALL sections, including manually confirmed ones -- no partial reset
    mode (user decision, 2026-07-18). Song status flips back to
    "analyzed" since defaults are unconfirmed again; Accept must be
    clicked before exporting."""
    song, lib, err = _get_song_or_error(song_id)
    if err:
        return err

    session = load_session(song_id)
    if session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "No session data available"}}), 409

    sections = session.get("sections", [])

    # hierarchy.sections uses the raw QM-boundary segmentation (often a
    # DIFFERENT count than the session's story-labeled sections -- e.g. 11
    # vs 10 on a real song), so the story must be rebuilt here too, not
    # just the hierarchy: _smart_default_theme_ids falls back to deriving
    # energies straight from hierarchy.sections when story is None, and a
    # section-count mismatch there makes it abort and use the crude static
    # kind->theme map for every section (collapsing all sections to the
    # same generic fallback theme -- caught 2026-07-18 via a real reset
    # producing visually uncolored section chips). Rebuild story the same
    # way the initial analyze flow does (src/review/api/v1/analysis.py),
    # not load_song_story -- that loads a `_story.json` FILE path, which
    # this flow never writes to disk.
    hierarchy = None
    story = None
    source_paths = song.get("source_paths") or []
    audio_path = source_paths[0] if source_paths else None
    if audio_path:
        try:
            from src.analyzer.orchestrator import run_orchestrator
            hierarchy = run_orchestrator(audio_path, fresh=False)
        except Exception:
            hierarchy = None
        if hierarchy is not None:
            try:
                from src.story.builder import build_song_story
                story = build_song_story(hierarchy.to_dict(), audio_path)
            except Exception:
                story = None

    from .analysis import _auto_assign_defaults
    assignments = _auto_assign_defaults(song_id, sections, hierarchy=hierarchy, story=story)

    save_session(song_id, sections, assignments)

    # Defaults are unconfirmed again -- drop song status back to "analyzed"
    # so Accept is required before exporting, mirroring the fresh-analysis
    # state.
    for s in lib["songs"]:
        if s["song_id"] == song_id:
            s["status"] = "analyzed"
            break
    save_library(lib)

    return jsonify({"assignments": assignments, "song_status": "analyzed"}), 200


@api_v1.route("/songs/<song_id>/load-bundle", methods=["POST"])
def load_song_bundle(song_id: str):
    """Apply a previously-saved single-song bundle (see save_song_bundle in
    export.py) onto the current song: restores title/artist and merges the
    bundle's session (theme assignments + every extra it carried) into
    this song's session.

    User request 2026-08-04: recovers a song's theme work after the app
    state gets wiped (e.g. this devcontainer's ephemeral home dir),
    replacing the old Theme screen's assignments-only Load Mappings with
    one bundle covering title/artist too. Assignment entries only apply to
    section_index values that exist in THIS song's current session -- a
    bundle saved from a differently-segmented analysis run shouldn't
    create phantom assignments (same guard the old Theme.tsx importer
    used). Every other session field (lyrics, words, phonemes, ignored
    occurrences, keyword motions, shadow text, ...) merges over the
    current session wholesale, since those are song-content-derived
    rather than section-index-keyed.
    """
    song, lib, err = _get_song_or_error(song_id)
    if err:
        return err

    body = request.get_json(silent=True) or {}
    bundle_song = body.get("song") or {}
    bundle_session = body.get("session")
    if not isinstance(bundle_session, dict):
        return jsonify({"error": {"code": "invalid_bundle",
                                   "message": "Bundle is missing a session object"}}), 400

    current_session = load_session(song_id)
    if current_session is None:
        return jsonify({"error": {"code": "not_analyzed",
                                   "message": "Song must be analyzed before a bundle can be applied"}}), 409

    title = str(bundle_song.get("title") or "").strip()
    artist = str(bundle_song.get("artist") or "").strip()
    if title:
        song["title"] = title
    if artist:
        song["artist"] = artist
    if title or artist:
        save_library(lib)

    current_assignments = current_session.get("assignments", [])
    existing_indices = {a["section_index"] for a in current_assignments}
    by_index = {a["section_index"]: a for a in current_assignments}
    applied = 0
    for a in bundle_session.get("assignments", []):
        idx = a.get("section_index")
        if not isinstance(idx, int) or idx not in existing_indices:
            continue
        target = by_index[idx]
        target["theme_id"] = a.get("theme_id", target.get("theme_id"))
        target["overrides"] = a.get("overrides", target.get("overrides", {}))
        target["user_confirmed"] = a.get("user_confirmed", target.get("user_confirmed", False))
        applied += 1

    merged = {
        **current_session,
        **{k: v for k, v in bundle_session.items() if k not in ("sections", "assignments")},
        "assignments": current_assignments,
    }
    save_full_session(song_id, merged)

    return jsonify({
        "song": song,
        "assignments": current_assignments,
        "assignments_applied": applied,
        "assignments_skipped": len(bundle_session.get("assignments", [])) - applied,
    }), 200
