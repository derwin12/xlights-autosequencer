"""Flask Blueprint for song story review API (Phases 4-7 of feature 021)."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

story_bp = Blueprint("story", __name__)

# Module-level session state (single-user server).
_session: dict = {
    "story": None,
    "story_path": None,
    "edits": None,  # initialized on first edit action
}

# Valid section roles (matches lighting_mapper._ROLE_CONFIG keys)
_VALID_ROLES = {
    "intro", "verse", "pre_chorus", "chorus", "post_chorus",
    "bridge", "instrumental_break", "climax", "ambient_bridge",
    "outro", "interlude",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _resolve_story_path(raw_path: str) -> Path | None:
    """Given a base path, prefer *_story_reviewed.json, fall back to *_story.json."""
    p = Path(raw_path)
    # If the caller gave an explicit path that exists, use it directly.
    if p.exists():
        return p
    # Try _story_reviewed.json first
    stem = p.stem
    if stem.endswith("_story"):
        reviewed = p.parent / (stem + "_reviewed.json")
        if reviewed.exists():
            return reviewed
        if (p.parent / (stem + ".json")).exists():
            return p.parent / (stem + ".json")
    return None


def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS.mmm."""
    total_ms = round(seconds * 1000)
    minutes = total_ms // 60_000
    remaining = total_ms % 60_000
    secs = remaining // 1000
    millis = remaining % 1000
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def _get_edits_path(story_path: Path) -> Path | None:
    """Derive the edits file path from the story path."""
    stem = story_path.stem
    if stem.endswith("_story_reviewed"):
        base = stem[: -len("_story_reviewed")]
    elif stem.endswith("_story"):
        base = stem[: -len("_story")]
    else:
        return None
    return story_path.parent / f"{base}_story_edits.json"


def _get_base_story_path(story_path: Path) -> Path | None:
    """Return the path to the base _story.json (not reviewed)."""
    stem = story_path.stem
    if stem.endswith("_story_reviewed"):
        base = stem[: -len("_story_reviewed")]
        return story_path.parent / f"{base}_story.json"
    elif stem.endswith("_story"):
        return story_path
    return None


def _find_section(story: dict, section_id: str) -> tuple[int, dict | None]:
    """Return (index, section) for the given section_id, or (-1, None) if not found."""
    for i, s in enumerate(story.get("sections", [])):
        if s["id"] == section_id:
            return i, s
    return -1, None


def _reassign_section_ids(sections: list[dict], moments: list[dict]) -> None:
    """Renumber sections s01, s02, … and re-bucket moments by timestamp.

    Mutates both lists in place.
    """
    # Build a time-range → new_id mapping
    id_map: dict[str, str] = {}
    for i, section in enumerate(sections, start=1):
        new_id = f"s{i:02d}"
        id_map[section["id"]] = new_id
        section["id"] = new_id

    # Re-bucket moments by timestamp falling within each section's range
    for moment in moments:
        moment_time_sec = moment.get("time", 0.0)
        assigned = False
        for section in sections:
            if section["start"] <= moment_time_sec < section["end"]:
                moment["section_id"] = section["id"]
                assigned = True
                break
        if not assigned and sections:
            # Assign to the last section if nothing matched (e.g. exactly at end)
            moment["section_id"] = sections[-1]["id"]


def _load_hierarchy(story: dict) -> dict | None:
    """Load the hierarchy JSON for the current song (cached in session)."""
    if "hierarchy" in _session and _session["hierarchy"] is not None:
        return _session["hierarchy"]
    audio_path = story.get("song", {}).get("file", "")
    if not audio_path:
        return None
    audio_p = Path(audio_path)
    # Try standard hierarchy path locations
    for candidate in [
        audio_p.parent / audio_p.stem / f"{audio_p.stem}_hierarchy.json",
        audio_p.parent / f"{audio_p.stem}_hierarchy.json",
    ]:
        if candidate.exists():
            try:
                h = json.loads(candidate.read_text(encoding="utf-8"))
                _session["hierarchy"] = h
                return h
            except Exception:
                pass
    return None


def _quick_profile(section: dict, story: dict) -> dict:
    """Rebuild section character, stems, accents, and lighting.

    Tries to load the hierarchy for full re-profiling (energy, texture,
    brightness, drum pattern, accents). Falls back to lighting-only
    update if the hierarchy isn't available.
    """
    from src.story.lighting_mapper import map_lighting

    hierarchy = _load_hierarchy(story)
    if hierarchy is not None:
        from src.story.section_profiler import profile_section
        start_ms = int(section["start"] * 1000)
        end_ms = int(section["end"] * 1000)
        profile = profile_section(start_ms, end_ms, hierarchy)
        section["character"] = profile["character"]
        section["stems"] = {**section.get("stems", {}), **profile["stems"]}

    energy_level = section["character"]["energy_level"]
    role = section["role"]
    new_lighting = map_lighting(role, energy_level)
    new_lighting["moment_count"] = section.get("lighting", {}).get("moment_count", 0)
    new_lighting["moment_pattern"] = section.get("lighting", {}).get("moment_pattern", "isolated")
    section["lighting"] = new_lighting
    return section


def _init_edits(story: dict, story_path: str) -> dict:
    """Create a fresh edits dict seeded from the story's source_hash."""
    now = datetime.now(timezone.utc).isoformat()
    story_bytes = json.dumps(story, sort_keys=True, ensure_ascii=False).encode()
    base_story_hash = hashlib.md5(story_bytes).hexdigest()
    return {
        "schema_version": "1.0.0",
        "source_hash": story.get("song", {}).get("source_hash", ""),
        "base_story_hash": base_story_hash,
        "created_at": now,
        "updated_at": now,
        "preferences": {},
        "section_edits": [],
        "moment_edits": [],
        "reviewer_notes": None,
    }


def _ensure_edits(story: dict, story_path: str) -> dict:
    """Return the session edits dict, initializing it if needed."""
    if _session["edits"] is None:
        _session["edits"] = _init_edits(story, story_path)
    return _session["edits"]


def _touch_edits(edits: dict) -> None:
    """Update the updated_at timestamp on the edits dict."""
    edits["updated_at"] = datetime.now(timezone.utc).isoformat()


def _track_section_edit(edits: dict, entry: dict) -> None:
    """Append a section edit entry, deduplicating by (section_id, action)."""
    sid = entry.get("section_id")
    action = entry.get("action")
    # Remove any existing entry with the same section_id + action to avoid duplicates
    edits["section_edits"] = [
        e for e in edits["section_edits"]
        if not (e.get("section_id") == sid and e.get("action") == action)
    ]
    edits["section_edits"].append(entry)
    _touch_edits(edits)


def _track_moment_edit(edits: dict, moment_id: str, dismissed: bool) -> None:
    """Append or update a moment dismiss edit."""
    edits["moment_edits"] = [
        e for e in edits["moment_edits"] if e.get("moment_id") != moment_id
    ]
    edits["moment_edits"].append({"moment_id": moment_id, "dismissed": dismissed})
    _touch_edits(edits)


# ── Routes ─────────────────────────────────────────────────────────────────────

@story_bp.route("/load")
def story_load():
    """Load a song story from disk.

    Query param: ``path`` — absolute path to the story JSON file.
    Prefers ``<stem>_story_reviewed.json`` over ``<stem>_story.json``.
    Stores the loaded story in the module-level ``_session`` dict.
    """
    raw_path = request.args.get("path", "").strip()
    if not raw_path:
        return jsonify({"error": "path query parameter is required"}), 400

    # Try to resolve a real file on disk.
    p = Path(raw_path)

    # If caller gave exact file path that exists, use it.
    # Otherwise try the _story_reviewed / _story fallback dance.
    resolved: Path | None = None
    if p.exists():
        resolved = p
    else:
        # Try adding _story_reviewed.json / _story.json suffixes if the path
        # looks like an audio file or bare stem.
        stem = p.stem
        parent = p.parent
        for candidate_name in (
            f"{stem}_story_reviewed.json",
            f"{stem}_story.json",
        ):
            candidate = parent / candidate_name
            if candidate.exists():
                resolved = candidate
                break

    if resolved is None:
        return jsonify({"error": f"Story file not found: {raw_path}"}), 404

    try:
        story = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return jsonify({"error": f"Cannot read story file: {exc}"}), 500

    _session["story"] = story
    _session["story_path"] = str(resolved)
    _session["edits"] = None  # reset edits on fresh load

    # T054: Stale edits detection — check if _story_edits.json exists and its
    # base_story_hash still matches the current _story.json MD5.
    stale_edits = False
    edits_path = _get_edits_path(resolved)
    if edits_path and edits_path.exists():
        try:
            edits_data = json.loads(edits_path.read_text(encoding="utf-8"))
            # Locate the base _story.json (not _reviewed) to hash
            base_path = _get_base_story_path(resolved)
            if base_path and base_path.exists():
                current_hash = hashlib.md5(base_path.read_bytes()).hexdigest()
                saved_hash = edits_data.get("base_story_hash", "")
                stale_edits = saved_hash != current_hash and bool(saved_hash)
        except Exception:
            pass

    response_data = dict(story)
    response_data["_meta"] = {"stale_edits": stale_edits, "has_edits": edits_path.exists() if edits_path else False}
    return jsonify(response_data)


@story_bp.route("/current")
def story_current():
    """Return the current in-memory story (including any unsaved edits)."""
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded"}), 404
    return jsonify(story)


@story_bp.route("/audio")
def story_audio():
    """Stream the audio file referenced by the loaded song story."""
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded. Call /story/load first."}), 404

    audio_path_str = story.get("song", {}).get("file", "")
    if not audio_path_str:
        return jsonify({"error": "Story has no audio file path (song.file is empty)"}), 404

    audio_path = Path(audio_path_str)
    if not audio_path.exists():
        # Try to find the audio file relative to the story file location
        story_dir = Path(_session.get("story_path", "")).parent
        # Try same directory as the story
        candidate = story_dir / audio_path.name
        if candidate.exists():
            audio_path = candidate
        else:
            # Try parent directory of the story
            candidate = story_dir.parent / audio_path.name
            if candidate.exists():
                audio_path = candidate
    if not audio_path.exists():
        return jsonify({"error": f"Audio file not found: {audio_path_str}"}), 404

    # Detect MIME type by extension
    mime = "audio/mpeg"
    suffix = audio_path.suffix.lower()
    if suffix in (".wav", ".wave"):
        mime = "audio/wav"
    elif suffix == ".flac":
        mime = "audio/flac"
    elif suffix == ".ogg":
        mime = "audio/ogg"

    resp = send_file(str(audio_path), mimetype=mime, conditional=True)
    resp.headers["Accept-Ranges"] = "bytes"
    return resp


@story_bp.route("/stems")
def story_stems():
    """Return the stem curve data from the loaded song story."""
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded. Call /story/load first."}), 400

    stems = story.get("stems", {})
    return jsonify(stems)


@story_bp.route("/stem-audio/<stem_name>")
def story_stem_audio(stem_name: str):
    """Stream a stem audio file (WAV or MP3) from the stems cache directory.

    The stems directory is located by checking the hierarchy's stems cache
    (typically .stems/<md5>/ adjacent to the source audio file, or a 'stems/'
    subdirectory next to the hierarchy).
    """
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded"}), 404

    # full_mix is the original audio file, not a stem
    if stem_name == "full_mix":
        return story_audio()

    # Locate stems directory — check several common patterns
    audio_path_str = story.get("song", {}).get("file", "")
    story_path_str = _session.get("story_path", "")
    source_hash = story.get("song", {}).get("source_hash", "")

    # Extract the audio filename stem (without extension) for directory matching
    audio_stem_name = Path(audio_path_str).stem if audio_path_str else ""

    candidates = []

    # Primary: search relative to the story file on disk (works across machines)
    if story_path_str:
        story_p = Path(story_path_str)
        story_dir = story_p.parent
        # <story_dir>/<audio_stem>/stems/  (most common: story beside audio, stems in subdir)
        if audio_stem_name:
            candidates.append(story_dir / audio_stem_name / "stems")
        # <story_dir>/stems/
        candidates.append(story_dir / "stems")
        # <story_dir>/.stems/<hash>/
        candidates.append(story_dir / ".stems" / source_hash)

    # Secondary: search relative to audio path (works if audio path is valid on this machine)
    if audio_path_str:
        audio_p = Path(audio_path_str)
        candidates.append(audio_p.parent / audio_p.stem / "stems")
        candidates.append(audio_p.parent / ".stems" / source_hash)
        candidates.append(audio_p.parent / "stems")

    stem_file = None
    for stems_dir in candidates:
        if not stems_dir.is_dir():
            continue
        for ext in (".mp3", ".wav", ".flac"):
            candidate = stems_dir / f"{stem_name}{ext}"
            if candidate.exists():
                stem_file = candidate
                break
        if stem_file:
            break

    if stem_file is None:
        return jsonify({"error": f"Stem file not found: {stem_name}"}), 404

    mime = "audio/mpeg"
    suffix = stem_file.suffix.lower()
    if suffix in (".wav", ".wave"):
        mime = "audio/wav"
    elif suffix == ".flac":
        mime = "audio/flac"

    resp = send_file(str(stem_file), mimetype=mime, conditional=True)
    resp.headers["Accept-Ranges"] = "bytes"
    return resp


@story_bp.route("/stem-list")
def story_stem_list():
    """Return a list of available stem audio files."""
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded"}), 404

    available = [s for s in story.get("global", {}).get("stems_available", []) if s != "full_mix"]
    return jsonify({"stems": available})


@story_bp.route("/reprofile", methods=["POST"])
def story_reprofile():
    """Re-profile affected sections after a boundary edit (stub — Phase 5 full impl).

    Body: ``{"sections": [{"id": str, "start": float, "end": float}]}``
    Returns the submitted sections unchanged for now.
    """
    body = request.get_json(force=True) or {}
    sections = body.get("sections", [])
    if not isinstance(sections, list):
        return jsonify({"error": "sections must be a list"}), 400

    # Phase 5 will re-run section_profiler and lighting_mapper for each affected section.
    return jsonify({"status": "ok", "sections": sections})


# ── Phase 5: Section Editing ───────────────────────────────────────────────────

@story_bp.route("/rename", methods=["POST"])
def story_rename():
    """Rename a section's role and re-run lighting mapper.

    Body: ``{"section_id": "s03", "new_role": "pre_chorus"}``
    Returns: ``{"section": updated_section_dict}``
    """
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded"}), 400

    body = request.get_json(force=True) or {}
    section_id = body.get("section_id", "").strip()
    new_role = body.get("new_role", "").strip()

    if not section_id:
        return jsonify({"error": "section_id is required"}), 400
    if not new_role:
        return jsonify({"error": "new_role is required"}), 400
    if new_role not in _VALID_ROLES:
        return jsonify({"error": f"Invalid role '{new_role}'. Valid roles: {sorted(_VALID_ROLES)}"}), 400

    idx, section = _find_section(story, section_id)
    if section is None:
        return jsonify({"error": f"Section '{section_id}' not found"}), 404

    original_role = section["role"]
    section["role"] = new_role
    _quick_profile(section, story)

    edits = _ensure_edits(story, _session["story_path"])
    _track_section_edit(edits, {
        "section_id": section_id,
        "action": "rename",
        "original_role": original_role,
        "new_role": new_role,
    })

    return jsonify({"section": section})


@story_bp.route("/split", methods=["POST"])
def story_split():
    """Split a section at a given timestamp.

    Body: ``{"section_id": "s05", "split_time": 45.2}``
    Returns: ``{"sections": [section1, section2]}``
    """
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded"}), 400

    body = request.get_json(force=True) or {}
    section_id = body.get("section_id", "").strip()
    split_time = body.get("split_time")

    if not section_id:
        return jsonify({"error": "section_id is required"}), 400
    if split_time is None:
        return jsonify({"error": "split_time is required"}), 400

    try:
        split_time = float(split_time)
    except (TypeError, ValueError):
        return jsonify({"error": "split_time must be a number"}), 400

    idx, section = _find_section(story, section_id)
    if section is None:
        return jsonify({"error": f"Section '{section_id}' not found"}), 404

    if not (section["start"] < split_time < section["end"]):
        return jsonify({
            "error": f"split_time {split_time} is outside section range "
                     f"[{section['start']}, {section['end']}]"
        }), 400

    MIN_DURATION = 4.0
    if split_time - section["start"] < MIN_DURATION:
        return jsonify({"error": f"Left half would be shorter than {MIN_DURATION}s"}), 400
    if section["end"] - split_time < MIN_DURATION:
        return jsonify({"error": f"Right half would be shorter than {MIN_DURATION}s"}), 400

    # Build the two new sections from the existing one
    s1 = copy.deepcopy(section)
    s1["end"] = round(split_time, 3)
    s1["end_fmt"] = _fmt_time(split_time)
    s1["duration"] = round(split_time - s1["start"], 3)

    s2 = copy.deepcopy(section)
    s2["start"] = round(split_time, 3)
    s2["start_fmt"] = _fmt_time(split_time)
    s2["duration"] = round(s2["end"] - split_time, 3)
    # IDs will be reassigned below
    s2["id"] = section["id"] + "_b"

    # Re-run lighting on both halves
    _quick_profile(s1, story)
    _quick_profile(s2, story)

    # Replace the original section with the two halves
    sections = story["sections"]
    sections[idx:idx + 1] = [s1, s2]

    # Reassign all IDs and re-bucket moments
    moments = story.get("moments", [])
    _reassign_section_ids(sections, moments)

    edits = _ensure_edits(story, _session["story_path"])
    _track_section_edit(edits, {
        "section_id": section_id,
        "action": "split",
        "split_time": split_time,
        "original_start": section["start"],
        "original_end": section["end"],
    })

    return jsonify({"sections": [sections[idx], sections[idx + 1]]})


@story_bp.route("/merge", methods=["POST"])
def story_merge():
    """Merge two adjacent sections.

    Body: ``{"section_id": "s07", "merge_with": "s08"}``
    Returns: ``{"section": merged_section}``
    """
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded"}), 400

    body = request.get_json(force=True) or {}
    section_id = body.get("section_id", "").strip()
    merge_with = body.get("merge_with", "").strip()

    if not section_id or not merge_with:
        return jsonify({"error": "section_id and merge_with are required"}), 400

    idx1, s1 = _find_section(story, section_id)
    idx2, s2 = _find_section(story, merge_with)

    if s1 is None:
        return jsonify({"error": f"Section '{section_id}' not found"}), 404
    if s2 is None:
        return jsonify({"error": f"Section '{merge_with}' not found"}), 404

    # Must be adjacent
    sections = story["sections"]
    if abs(idx1 - idx2) != 1:
        return jsonify({"error": "Sections are not adjacent"}), 400

    # Ensure idx1 < idx2
    if idx1 > idx2:
        idx1, idx2 = idx2, idx1
        s1, s2 = s2, s1

    # Check they are contiguous
    if abs(s1["end"] - s2["start"]) > 0.01:
        return jsonify({"error": "Sections are not contiguous"}), 400

    # Build merged section: inherit from s1, extend end to s2's end
    merged = copy.deepcopy(s1)
    merged["end"] = round(s2["end"], 3)
    merged["end_fmt"] = _fmt_time(s2["end"])
    merged["duration"] = round(s2["end"] - merged["start"], 3)

    # Decide role: keep s1's role (spec says use "role of first section")
    # but use higher-energy one if they differ in energy
    e1 = s1["character"].get("energy_score", 0)
    e2 = s2["character"].get("energy_score", 0)
    if e2 > e1 and s1["role"] != s2["role"]:
        merged["role"] = s2["role"]

    _quick_profile(merged, story)

    # Replace both sections with the merged one
    sections[idx1:idx2 + 1] = [merged]

    moments = story.get("moments", [])
    _reassign_section_ids(sections, moments)

    edits = _ensure_edits(story, _session["story_path"])
    _track_section_edit(edits, {
        "section_id": section_id,
        "action": "merge",
        "merged_with": merge_with,
    })

    return jsonify({"section": sections[idx1]})


@story_bp.route("/boundary", methods=["POST"])
def story_boundary():
    """Adjust section boundary (end of one section = start of next).

    Body: ``{"section_id": "s04", "new_end": 38.00}``
    Returns: ``{"sections": [updated_section1, updated_section2]}``
    """
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded"}), 400

    body = request.get_json(force=True) or {}
    section_id = body.get("section_id", "").strip()
    new_end = body.get("new_end")

    if not section_id:
        return jsonify({"error": "section_id is required"}), 400
    if new_end is None:
        return jsonify({"error": "new_end is required"}), 400

    try:
        new_end = float(new_end)
    except (TypeError, ValueError):
        return jsonify({"error": "new_end must be a number"}), 400

    sections = story["sections"]
    idx, section = _find_section(story, section_id)
    if section is None:
        return jsonify({"error": f"Section '{section_id}' not found"}), 404

    # Must have a next section
    if idx + 1 >= len(sections):
        return jsonify({"error": "Cannot adjust boundary of the last section"}), 400

    next_section = sections[idx + 1]
    original_end = section["end"]

    MIN_DURATION = 4.0
    if new_end - section["start"] < MIN_DURATION:
        return jsonify({"error": f"Adjusted section would be shorter than {MIN_DURATION}s"}), 400
    if next_section["end"] - new_end < MIN_DURATION:
        return jsonify({"error": f"Next section would be shorter than {MIN_DURATION}s"}), 400

    # Update the boundary
    section["end"] = round(new_end, 3)
    section["end_fmt"] = _fmt_time(new_end)
    section["duration"] = round(new_end - section["start"], 3)

    next_section["start"] = round(new_end, 3)
    next_section["start_fmt"] = _fmt_time(new_end)
    next_section["duration"] = round(next_section["end"] - new_end, 3)

    # Re-run lighting for both
    _quick_profile(section, story)
    _quick_profile(next_section, story)

    # Re-bucket moments
    moments = story.get("moments", [])
    _reassign_section_ids(sections, moments)

    edits = _ensure_edits(story, _session["story_path"])
    _track_section_edit(edits, {
        "section_id": section_id,
        "action": "boundary",
        "original_end": original_end,
        "new_end": new_end,
    })

    return jsonify({"sections": [section, next_section]})


# ── Phase 6: Moment Curation + Save/Export ─────────────────────────────────────

@story_bp.route("/moment/dismiss", methods=["POST"])
def story_moment_dismiss():
    """Toggle the dismissed flag on a moment.

    Body: ``{"moment_id": "m005", "dismissed": true}``
    Returns: ``{"moment": updated_moment}``
    """
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded"}), 400

    body = request.get_json(force=True) or {}
    moment_id = body.get("moment_id", "").strip()
    dismissed = body.get("dismissed")

    if not moment_id:
        return jsonify({"error": "moment_id is required"}), 400
    if dismissed is None:
        return jsonify({"error": "dismissed is required"}), 400

    moment = next(
        (m for m in story.get("moments", []) if m["id"] == moment_id),
        None,
    )
    if moment is None:
        return jsonify({"error": f"Moment '{moment_id}' not found"}), 404

    moment["dismissed"] = bool(dismissed)

    edits = _ensure_edits(story, _session["story_path"])
    _track_moment_edit(edits, moment_id, bool(dismissed))

    return jsonify({"moment": moment})


@story_bp.route("/section/highlight", methods=["POST"])
def story_section_highlight():
    """Toggle the is_highlight override on a section.

    Body: ``{"section_id": "s03", "is_highlight": true}``
    Returns: ``{"section": updated_section}``
    """
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded"}), 400

    body = request.get_json(force=True) or {}
    section_id = body.get("section_id", "").strip()
    is_highlight = body.get("is_highlight")

    if not section_id:
        return jsonify({"error": "section_id is required"}), 400
    if is_highlight is None:
        return jsonify({"error": "is_highlight is required"}), 400

    idx, section = _find_section(story, section_id)
    if section is None:
        return jsonify({"error": f"Section '{section_id}' not found"}), 404

    section.setdefault("overrides", {})["is_highlight"] = bool(is_highlight)

    edits = _ensure_edits(story, _session["story_path"])
    _track_section_edit(edits, {
        "section_id": section_id,
        "action": "override",
        "overrides": {"is_highlight": bool(is_highlight)},
    })

    return jsonify({"section": section})


@story_bp.route("/save", methods=["POST"])
def story_save():
    """Save current session edits to ``<base>_story_edits.json``.

    Returns: ``{"status": "saved", "path": str}``
    """
    story = _session.get("story")
    story_path = _session.get("story_path")
    if story is None or story_path is None:
        return jsonify({"error": "No story loaded"}), 400

    edits = _ensure_edits(story, story_path)
    _touch_edits(edits)

    # Derive edits path from story path
    sp = Path(story_path)
    # Strip any _reviewed suffix, then replace _story.json with _story_edits.json
    stem = sp.stem  # e.g. "Magic_story" or "Magic_story_reviewed"
    if stem.endswith("_reviewed"):
        stem = stem[: -len("_reviewed")]
    if stem.endswith("_story"):
        base = stem[: -len("_story")]
    else:
        base = stem
    edits_path = sp.parent / f"{base}_story_edits.json"

    from src.story.builder import write_edits
    write_edits(edits, str(edits_path))

    return jsonify({"status": "saved", "path": str(edits_path)})


@story_bp.route("/export", methods=["POST"])
def story_export():
    """Export the merged (base + edits) story to ``<base>_story_reviewed.json``.

    Returns: ``{"status": "exported", "path": str}``
    """
    story = _session.get("story")
    story_path = _session.get("story_path")
    if story is None or story_path is None:
        return jsonify({"error": "No story loaded"}), 400

    edits = _ensure_edits(story, story_path)
    _touch_edits(edits)

    sp = Path(story_path)
    stem = sp.stem
    if stem.endswith("_reviewed"):
        stem = stem[: -len("_reviewed")]
    if stem.endswith("_story"):
        base = stem[: -len("_story")]
    else:
        base = stem
    reviewed_path = sp.parent / f"{base}_story_reviewed.json"

    from src.story.builder import merge_story_with_edits, write_edits

    # Merge in-session story (may have structural edits) with tracked edits dict
    # Use the current in-session story as base since structural edits are live
    merged = merge_story_with_edits(story, edits)
    merged.setdefault("review", {})["status"] = "reviewed"
    merged["review"]["reviewed_at"] = datetime.now(timezone.utc).isoformat()

    reviewed_path.write_text(
        json.dumps(merged, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return jsonify({"status": "exported", "path": str(reviewed_path)})


# ── Phase 7: Creative Preferences ─────────────────────────────────────────────

@story_bp.route("/preferences", methods=["POST"])
def story_preferences():
    """Update song-wide preferences.

    Body: ``{"mood": "aggressive", "intensity": 1.2, "occasion": "christmas",
             "focus_stem": "guitar", "theme": null, "genre": null}``
    Returns: ``{"preferences": updated_preferences}``
    """
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded"}), 400

    body = request.get_json(force=True) or {}

    # Only update keys that are explicitly present in body (allow null to clear a field)
    prefs = story.setdefault("preferences", {})
    allowed_keys = {"mood", "theme", "focus_stem", "intensity", "occasion", "genre"}
    for key in allowed_keys:
        if key in body:
            prefs[key] = body[key]

    edits = _ensure_edits(story, _session["story_path"])
    # Store all currently non-null preferences in edits
    edits["preferences"] = {k: v for k, v in prefs.items() if v is not None}
    _touch_edits(edits)

    return jsonify({"preferences": prefs})


@story_bp.route("/section/overrides", methods=["POST"])
def story_section_overrides():
    """Update per-section overrides (merge, not replace).

    Body: ``{"section_id": "s03",
             "overrides": {"mood": "structural", "theme": "Inferno",
                           "focus_stem": "guitar", "intensity": 1.2}}``
    Returns: ``{"section": updated_section}``
    """
    story = _session.get("story")
    if story is None:
        return jsonify({"error": "No story loaded"}), 400

    body = request.get_json(force=True) or {}
    section_id = body.get("section_id", "").strip()
    overrides_in = body.get("overrides")

    if not section_id:
        return jsonify({"error": "section_id is required"}), 400
    if not isinstance(overrides_in, dict):
        return jsonify({"error": "overrides must be an object"}), 400

    idx, section = _find_section(story, section_id)
    if section is None:
        return jsonify({"error": f"Section '{section_id}' not found"}), 404

    # Merge overrides
    section.setdefault("overrides", {}).update(overrides_in)

    edits = _ensure_edits(story, _session["story_path"])
    _track_section_edit(edits, {
        "section_id": section_id,
        "action": "override",
        "overrides": overrides_in,
    })

    return jsonify({"section": section})
