"""Library endpoints — GET /library, folder CRUD, song delete + purge (T045, T090, T092, T094).
Export/import portability (T128). Relocate endpoint (T133).
"""
from __future__ import annotations

import hashlib
import io
import shutil
from pathlib import Path

from flask import jsonify, request, send_file

from . import api_v1
from src.review.storage.bundle import BundleInvalidError, pack, unpack
from src.review.storage.library import load_library, save_library
from src.review.storage.paths import song_session_path, library_root

# Registry of song_ids that have been deleted but not yet purged.
# Stored in library.json under a top-level "deleted_songs" key.
_DELETED_SONGS_KEY = "deleted_songs"


def _song_with_source_exists(song: dict) -> dict:
    """Add computed source_exists field to a song dict."""
    paths = song.get("source_paths") or []
    source_exists = any(Path(p).exists() for p in paths)
    return {**song, "source_exists": source_exists}


def _normalize_folder(folder: dict) -> dict:
    """Normalize folder dict to use folder_id instead of id."""
    if "folder_id" not in folder and "id" in folder:
        folder = {**folder, "folder_id": folder["id"]}
    return folder


def _generate_folder_id() -> str:
    import secrets
    return "folder_" + secrets.token_urlsafe(6)


@api_v1.route("/library", methods=["GET"])
def get_library():
    lib = load_library()
    songs = [_song_with_source_exists(s) for s in lib.get("songs", [])]
    folders = [_normalize_folder(f) for f in lib.get("folders", [])]
    return jsonify({"schema_version": lib.get("schema_version", 1), "songs": songs, "folders": folders}), 200


# ─── Folder CRUD ─────────────────────────────────────────────────────────────

@api_v1.route("/folders", methods=["POST"])
def create_folder():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name or len(name) > 64:
        return jsonify({"error": {"code": "invalid_name", "message": "Folder name must be 1–64 characters"}}), 400

    lib = load_library()
    folders = lib.get("folders", [])

    # Case-insensitive duplicate check
    existing_names = {_normalize_folder(f).get("name", "").lower() for f in folders}
    if name.lower() in existing_names:
        return jsonify({"error": {"code": "folder_name_taken", "message": "A folder with this name already exists"}}), 409

    folder_id = _generate_folder_id()
    order = len(folders)
    new_folder = {"folder_id": folder_id, "name": name, "collapsed": False, "order": order}
    lib.setdefault("folders", []).append(new_folder)
    save_library(lib)
    return jsonify(new_folder), 201


@api_v1.route("/folders/<folder_id>", methods=["PATCH"])
def patch_folder(folder_id: str):
    lib = load_library()
    folders = lib.get("folders", [])

    folder = next((f for f in folders if _normalize_folder(f).get("folder_id") == folder_id), None)
    if folder is None:
        return jsonify({"error": {"code": "folder_not_found", "message": "Folder not found"}}), 404

    # Determine if reserved — check for reserved flag OR id=="unfiled"
    is_reserved = folder.get("reserved") or folder.get("id") == "unfiled" or folder.get("folder_id") == "unfiled"
    body = request.get_json(silent=True) or {}

    if "name" in body and is_reserved:
        return jsonify({"error": {"code": "reserved_folder", "message": "Cannot rename a reserved folder"}}), 400

    if "name" in body:
        name = (body["name"] or "").strip()
        if not name or len(name) > 64:
            return jsonify({"error": {"code": "invalid_name", "message": "Folder name must be 1–64 characters"}}), 400
        folder["name"] = name

    if "collapsed" in body:
        folder["collapsed"] = bool(body["collapsed"])

    if "order" in body:
        folder["order"] = int(body["order"])

    # Normalize folder_id field
    if "folder_id" not in folder and "id" in folder:
        folder["folder_id"] = folder.pop("id")

    save_library(lib)
    return jsonify(_normalize_folder(folder)), 200


@api_v1.route("/folders/<folder_id>", methods=["DELETE"])
def delete_folder(folder_id: str):
    lib = load_library()
    folders = lib.get("folders", [])

    folder = next((f for f in folders if _normalize_folder(f).get("folder_id") == folder_id), None)
    if folder is None:
        return jsonify({"error": {"code": "folder_not_found", "message": "Folder not found"}}), 404

    is_reserved = folder.get("reserved") or folder.get("id") == "unfiled" or folder.get("folder_id") == "unfiled"
    if is_reserved:
        return jsonify({"error": {"code": "reserved_folder", "message": "Cannot delete the unfiled folder"}}), 400

    # Move all songs in this folder to unfiled
    for song in lib.get("songs", []):
        if song.get("folder_id") == folder_id:
            song["folder_id"] = "unfiled"

    lib["folders"] = [f for f in folders if _normalize_folder(f).get("folder_id") != folder_id]
    save_library(lib)
    return "", 204


# ─── Song → Folder move ──────────────────────────────────────────────────────

@api_v1.route("/songs/<song_id>/folder", methods=["PATCH"])
def patch_song_folder(song_id: str):
    lib = load_library()
    body = request.get_json(silent=True) or {}

    song = next((s for s in lib.get("songs", []) if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": {"code": "song_not_found", "message": "Song not found"}}), 404

    target_folder_id = body.get("folder_id")
    folders = lib.get("folders", [])
    folder_ids = {_normalize_folder(f).get("folder_id") for f in folders}
    if target_folder_id not in folder_ids:
        return jsonify({"error": {"code": "folder_not_found", "message": "Folder not found"}}), 404

    song["folder_id"] = target_folder_id
    save_library(lib)
    return jsonify(_song_with_source_exists(song)), 200


# ─── Song delete + cache purge ───────────────────────────────────────────────

def _analysis_cache_path(song_id: str) -> Path:
    """Return the analysis cache directory for a song (if any)."""
    return library_root() / "songs" / song_id


def _stems_cache_path(song_id: str) -> Path:
    """Return the stems cache directory for a song (if any)."""
    # Stems are cached in .stems/<song_id>/ adjacent to library root
    return library_root().parent / ".stems" / song_id


def _cache_size(song_id: str) -> int:
    """Compute total bytes of analysis cache + stems for a song."""
    total = 0
    for p in [_analysis_cache_path(song_id), _stems_cache_path(song_id)]:
        if p.exists():
            for f in p.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
    return total


def _cache_exists(song_id: str) -> bool:
    return (
        _analysis_cache_path(song_id).exists()
        or _stems_cache_path(song_id).exists()
    )


@api_v1.route("/songs/<song_id>", methods=["DELETE"])
def delete_song(song_id: str):
    lib = load_library()
    songs = lib.get("songs", [])

    song = next((s for s in songs if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": {"code": "song_not_found", "message": "Song not found"}}), 404

    # Compute cache info before removing
    cache_size = _cache_size(song_id)
    cache_available = _cache_exists(song_id)

    # Remove song from library
    lib["songs"] = [s for s in songs if s["song_id"] != song_id]

    # Track deleted song for purge eligibility
    deleted = lib.setdefault(_DELETED_SONGS_KEY, [])
    if song_id not in deleted:
        deleted.append(song_id)

    # Remove session file
    session_path = song_session_path(song_id)
    if session_path.exists():
        try:
            session_path.unlink()
        except OSError:
            pass

    # Remove per-song preferences (last_playhead entry)
    prefs = lib.get("preferences", {})
    playhead_map = prefs.get("last_playhead_ms_by_song", {})
    playhead_map.pop(song_id, None)

    save_library(lib)
    return jsonify({
        "song_id": song_id,
        "cache_purge_available": cache_available,
        "cache_size_bytes": cache_size,
    }), 200


@api_v1.route("/songs/<song_id>/purge", methods=["POST"])
def purge_song_cache(song_id: str):
    lib = load_library()

    # Cannot purge a song that's still in the library
    if any(s["song_id"] == song_id for s in lib.get("songs", [])):
        return jsonify({"error": {"code": "song_still_imported", "message": "Remove the song from the library before purging its cache"}}), 409

    # Song must be in deleted list to be eligible for purge
    deleted = lib.get(_DELETED_SONGS_KEY, [])
    if song_id not in deleted:
        return jsonify({"error": {"code": "cache_not_found", "message": "No cache found for this song"}}), 404

    body = request.get_json(silent=True) or {}
    purge_analysis = body.get("analysis", True)
    purge_stems = body.get("stems", True)

    freed = 0
    if purge_analysis:
        p = _analysis_cache_path(song_id)
        if p.exists():
            freed += _dir_size(p)
            shutil.rmtree(p, ignore_errors=True)
    if purge_stems:
        p = _stems_cache_path(song_id)
        if p.exists():
            freed += _dir_size(p)
            shutil.rmtree(p, ignore_errors=True)

    # Remove from deleted list
    lib[_DELETED_SONGS_KEY] = [sid for sid in deleted if sid != song_id]
    save_library(lib)

    return jsonify({"freed_bytes": freed}), 200


def _dir_size(path: Path) -> int:
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


# ─── Library portability: export / import (T128) ─────────────────────────────


@api_v1.route("/library/export", methods=["POST"])
def export_library():
    """Pack the library + all song sessions into a .xonset-bundle zip."""
    lib = load_library()

    sessions: dict[str, dict] = {}
    for song in lib.get("songs", []):
        song_id = song["song_id"]
        sess_path = song_session_path(song_id)
        if sess_path.exists():
            import json as _json
            try:
                sessions[song_id] = _json.loads(sess_path.read_text(encoding="utf-8"))
            except Exception:
                pass

    bundle_bytes = pack(lib, sessions)
    return send_file(
        io.BytesIO(bundle_bytes),
        mimetype="application/zip",
        as_attachment=True,
        download_name="library.xonset",
    )


@api_v1.route("/library/import", methods=["POST"])
def import_library():
    """Import a .xonset-bundle zip.

    Accepts multipart/form-data with:
      - bundle: the zip file
      - mode: "replace" (default) | "merge"
    """
    if "bundle" not in request.files:
        return jsonify({"error": {"code": "missing_bundle", "message": "No bundle file provided"}}), 400

    mode = (request.form.get("mode") or "replace").lower()
    if mode not in ("replace", "merge"):
        return jsonify({"error": {"code": "invalid_mode", "message": "mode must be 'replace' or 'merge'"}}), 400

    bundle_file = request.files["bundle"]
    bundle_bytes = bundle_file.read()

    try:
        imported_lib, imported_sessions = unpack(bundle_bytes)
    except BundleInvalidError as exc:
        return jsonify({"error": {"code": "bundle_invalid", "message": str(exc)}}), 400

    import json as _json

    current_lib = load_library()

    if mode == "replace":
        merged_songs = imported_lib.get("songs", [])
        merged_folders = imported_lib.get("folders", current_lib.get("folders", []))
    else:
        # Merge: keep existing songs, add bundle songs (dedup by song_id)
        existing_ids = {s["song_id"] for s in current_lib.get("songs", [])}
        new_songs = [s for s in imported_lib.get("songs", []) if s["song_id"] not in existing_ids]
        merged_songs = current_lib.get("songs", []) + new_songs
        merged_folders = current_lib.get("folders", [])

    current_lib["songs"] = merged_songs
    current_lib["folders"] = merged_folders
    save_library(current_lib)

    # Write imported sessions
    for song_id, session in imported_sessions.items():
        if mode == "replace" or song_id in {s["song_id"] for s in merged_songs}:
            sess_path = song_session_path(song_id)
            sess_path.parent.mkdir(parents=True, exist_ok=True)
            sess_path.write_text(_json.dumps(session, indent=2), encoding="utf-8")

    # Identify songs whose audio source is missing
    source_missing_songs = []
    for song in merged_songs:
        paths = song.get("source_paths") or []
        if not paths or not any(Path(p).exists() for p in paths):
            source_missing_songs.append(song["song_id"])

    return jsonify({
        "songs": merged_songs,
        "source_missing_songs": source_missing_songs,
    }), 200


# ─── Song relocate (T133) ─────────────────────────────────────────────────────


@api_v1.route("/songs/<song_id>/relocate", methods=["POST"])
def relocate_song(song_id: str):
    """Let the user point to a new audio file path for a song.

    Verifies that the file at the given path hashes (SHA-256, first 16 hex chars)
    to the stored song_id.  On success, appends the path to source_paths and
    clears source_missing status.
    """
    lib = load_library()
    song = next((s for s in lib.get("songs", []) if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": {"code": "song_not_found", "message": "Song not found"}}), 404

    body = request.get_json(silent=True) or {}
    new_path = (body.get("path") or "").strip()
    if not new_path:
        return jsonify({"error": {"code": "missing_path", "message": "'path' field is required"}}), 400

    file = Path(new_path)
    if not file.exists():
        return jsonify({"error": {"code": "file_not_found", "message": "File not found at provided path"}}), 404

    # Verify hash matches song_id
    file_bytes = file.read_bytes()
    computed_id = hashlib.sha256(file_bytes).hexdigest()[:16]
    if computed_id != song_id:
        return jsonify({
            "error": {
                "code": "hash_mismatch",
                "message": (
                    f"File at '{new_path}' has song_id '{computed_id}', "
                    f"expected '{song_id}'"
                ),
            }
        }), 409

    # Append path (no duplicates)
    source_paths: list[str] = song.get("source_paths") or []
    if new_path not in source_paths:
        source_paths.append(new_path)
    song["source_paths"] = source_paths

    # Clear source_missing status
    if song.get("status") == "source_missing":
        song["status"] = "draft"

    save_library(lib)
    return jsonify(_song_with_source_exists(song)), 200


# ─── Audio file serving ───────────────────────────────────────────────────────


@api_v1.route("/songs/<song_id>/audio", methods=["GET"])
def serve_audio(song_id: str):
    """Stream the audio file for a song so the browser can play it."""
    lib = load_library()
    song = next((s for s in lib.get("songs", []) if s["song_id"] == song_id), None)
    if song is None:
        return jsonify({"error": {"code": "song_not_found", "message": "Song not found"}}), 404

    source_paths = song.get("source_paths") or []
    audio_path = next((p for p in source_paths if Path(p).exists()), None)
    if audio_path is None:
        return jsonify({"error": {"code": "source_file_missing", "message": "Audio file not found"}}), 404

    return send_file(audio_path, conditional=True)
