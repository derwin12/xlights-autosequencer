"""Flask blueprint for sequence generation from the song library."""
from __future__ import annotations

import json
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request, send_file

from src.library import Library
from src.settings import get_layout_path

generate_bp = Blueprint("generate", __name__)

# In-memory job store — persists for the server process lifetime
_jobs: dict[str, "GenerationJob"] = {}

# Temp directory for generated .xsq files
_temp_dir: Path = Path(tempfile.mkdtemp(prefix="xlight_gen_"))

# Valid option values — shared with brief_routes.py
_VALID_GENRES = {"any", "pop", "rock", "classical"}
_VALID_OCCASIONS = {"general", "christmas", "halloween"}
_VALID_TRANSITIONS = {"none", "subtle", "dramatic"}
_VALID_CURVES_MODES = {"all", "brightness", "speed", "color", "none"}
_VALID_MOOD_INTENTS = {"auto", "party", "emotional", "dramatic", "playful"}
_VALID_DURATION_FEELS = {"auto", "snappy", "balanced", "flowing"}
_VALID_ACCENT_STRENGTHS = {"auto", "subtle", "strong"}


@dataclass
class GenerationJob:
    """State for a single sequence generation run."""

    job_id: str
    source_hash: str
    status: str  # pending / running / complete / failed
    output_path: Optional[Path]
    error_message: Optional[str]
    genre: str
    occasion: str
    transition_mode: str
    created_at: float
    brief_snapshot: Optional[dict] = None  # FR-044 — snapshot of the Brief that produced this job


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sanitize_error(e: Exception) -> str:
    """Convert an exception to a user-readable error string (no raw traceback)."""
    if isinstance(e, FileNotFoundError):
        return "Layout file not found — reconfigure your layout in the grouper first."
    if isinstance(e, ValueError):
        return str(e)
    return "Sequence generation failed — check your layout configuration and try again."


def _run_generation(job: GenerationJob, config: object) -> None:
    """Background thread target: run generate_sequence and update job state."""
    from src.generator.plan import generate_sequence

    try:
        job.status = "running"
        output_path = generate_sequence(config)
        job.output_path = output_path
        job.status = "complete"
    except Exception as e:  # noqa: BLE001
        job.error_message = _sanitize_error(e)
        job.status = "failed"


def _load_prefs_from_story(story_path: Path | None) -> tuple[str, str, str]:
    """Load genre/occasion/transition_mode from a story-reviewed JSON file.

    Returns the defaults (pop / general / subtle) if the file is absent or
    malformed.  Used as a last-resort fallback only when neither the POST body
    nor the on-disk Brief JSON supplies these fields (spec 047 §3).
    """
    defaults = ("pop", "general", "subtle")
    if story_path is None or not story_path.exists():
        return defaults
    try:
        with open(story_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        genre = data.get("genre", defaults[0])
        occasion = data.get("occasion", defaults[1])
        transition_mode = data.get("transition_mode", defaults[2])
        return genre, occasion, transition_mode
    except (OSError, json.JSONDecodeError, KeyError):
        return defaults


def _load_brief_from_disk(source_hash: str, audio_path: Path) -> dict:
    """Load the on-disk Brief JSON for a song.  Returns {} if not present."""
    brief_path = audio_path.parent / f"{audio_path.stem}_brief.json"
    if not brief_path.exists():
        return {}
    try:
        with open(brief_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_brief_field(body: dict, on_disk_brief: dict, field_name: str, default: object) -> object:
    """Return the first non-None, non-'auto' source for a Brief-capable field.

    Priority: POST body → on-disk Brief → default.
    'auto' is treated as absent (the caller should use the default instead).
    """
    val = body.get(field_name)
    if val is not None and val != "auto":
        return val
    val = on_disk_brief.get(field_name)
    if val is not None and val != "auto":
        return val
    return default


def _resolve_bool_field(body: dict, on_disk_brief: dict, field_name: str, default: bool) -> bool:
    """Resolve a boolean Brief field with POST body > on-disk Brief > default priority."""
    val = body.get(field_name)
    if val is not None:
        if isinstance(val, bool):
            return val
        return str(val).lower() in {"true", "1", "yes"}
    val = on_disk_brief.get(field_name)
    if val is not None:
        if isinstance(val, bool):
            return val
        return str(val).lower() in {"true", "1", "yes"}
    return default


def _resolve_theme_overrides(body: dict, on_disk_brief: dict) -> Optional[dict[int, str]]:
    """Resolve theme_overrides from body or on-disk brief.

    theme_overrides in the POST body is already {int: str} (from resolveBriefToPost).
    In the on-disk brief it is stored as per_section_overrides list.
    """
    if "theme_overrides" in body and body["theme_overrides"]:
        raw = body["theme_overrides"]
        if isinstance(raw, dict):
            return {int(k): v for k, v in raw.items() if v and v != "auto"}
        return None

    overrides_list = on_disk_brief.get("per_section_overrides") or []
    if overrides_list:
        result = {}
        for row in overrides_list:
            if isinstance(row, dict):
                idx = row.get("section_index")
                slug = row.get("theme_slug")
                if idx is not None and slug and slug != "auto":
                    result[int(idx)] = slug
        return result if result else None

    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@generate_bp.route("/settings", methods=["GET"])
def generation_settings():
    """Return the current installation-wide generation settings."""
    layout_path = get_layout_path()
    configured = layout_path is not None and layout_path.exists()
    return jsonify({
        "layout_path": str(layout_path) if layout_path else None,
        "layout_configured": configured,
    })


@generate_bp.route("/<source_hash>", methods=["POST"])
def start_generation(source_hash: str):
    """Start a new sequence generation job for the given song.

    Accepts an optional JSON body with Brief fields (spec 047).  Priority
    order for each field: POST body → on-disk Brief JSON → story-prefs
    legacy fallback (genre/occasion/transition_mode only) → GenerationConfig
    default.  All fields are optional; an empty body reproduces today's
    dashboard-Generate behavior (SC-002, SC-007).
    """
    from src.generator.models import GenerationConfig

    # Validate the song exists in the library
    entry = Library().find_by_hash(source_hash)
    if entry is None:
        return jsonify({"error": "Song not found in library"}), 404

    # Validate analysis exists
    if not Path(entry.analysis_path).exists():
        return jsonify({"error": "Song has not been analyzed. Run analysis first."}), 400

    # Validate layout is configured
    layout_path = get_layout_path()
    if layout_path is None or not layout_path.exists():
        return jsonify({
            "error": "No layout groups configured. Set up layout groups in the grouper first.",
            "setup_required": True,
        }), 409

    # Parse POST body and on-disk Brief
    body = request.get_json(silent=True) or {}
    audio_path = Path(entry.source_file)
    on_disk_brief = _load_brief_from_disk(source_hash, audio_path)

    # Resolve story-prefs (legacy fallback for genre/occasion/transition_mode)
    story_path = audio_path.parent / (audio_path.stem + "_story_reviewed.json")
    if not story_path.exists():
        story_path = audio_path.parent / (audio_path.stem + "_story.json")
    legacy_genre, legacy_occasion, legacy_transition = _load_prefs_from_story(
        story_path if story_path.exists() else None
    )

    # Resolve each field: POST body → on-disk Brief → legacy/default
    genre = _resolve_brief_field(body, on_disk_brief, "genre", legacy_genre)
    occasion = _resolve_brief_field(body, on_disk_brief, "occasion", legacy_occasion)
    transition_mode = _resolve_brief_field(body, on_disk_brief, "transition_mode", legacy_transition)
    curves_mode = _resolve_brief_field(body, on_disk_brief, "curves_mode", "none")
    mood_intent = _resolve_brief_field(body, on_disk_brief, "mood_intent", "auto")
    duration_feel = _resolve_brief_field(body, on_disk_brief, "duration_feel", "auto")
    accent_strength = _resolve_brief_field(body, on_disk_brief, "accent_strength", "auto")

    focused_vocabulary = _resolve_bool_field(body, on_disk_brief, "focused_vocabulary", True)
    embrace_repetition = _resolve_bool_field(body, on_disk_brief, "embrace_repetition", True)
    palette_restraint = _resolve_bool_field(body, on_disk_brief, "palette_restraint", True)
    duration_scaling = _resolve_bool_field(body, on_disk_brief, "duration_scaling", True)
    beat_accent_effects = _resolve_bool_field(body, on_disk_brief, "beat_accent_effects", True)
    tier_selection = _resolve_bool_field(body, on_disk_brief, "tier_selection", True)

    theme_overrides = _resolve_theme_overrides(body, on_disk_brief)

    # Validate resolved values — return 400 with field-level error on failure
    if genre not in _VALID_GENRES:
        return jsonify({"field": "genre", "error": f"Invalid genre: {genre!r}"}), 400
    if occasion not in _VALID_OCCASIONS:
        return jsonify({"field": "occasion", "error": f"Invalid occasion: {occasion!r}"}), 400
    if transition_mode not in _VALID_TRANSITIONS:
        return jsonify({"field": "transition_mode", "error": f"Invalid transition_mode: {transition_mode!r}"}), 400
    if curves_mode not in _VALID_CURVES_MODES:
        return jsonify({"field": "curves_mode", "error": f"Invalid curves_mode: {curves_mode!r}"}), 400
    if mood_intent not in _VALID_MOOD_INTENTS:
        return jsonify({"field": "mood_intent", "error": f"Invalid mood_intent: {mood_intent!r}"}), 400
    if duration_feel not in _VALID_DURATION_FEELS:
        return jsonify({"field": "duration_feel", "error": f"Invalid duration_feel: {duration_feel!r}"}), 400
    if accent_strength not in _VALID_ACCENT_STRENGTHS:
        return jsonify({"field": "accent_strength", "error": f"Invalid accent_strength: {accent_strength!r}"}), 400

    # Create job
    job_id = str(uuid.uuid4())
    brief_snapshot = dict(body) if body else None
    job = GenerationJob(
        job_id=job_id,
        source_hash=source_hash,
        status="pending",
        output_path=None,
        error_message=None,
        genre=genre,
        occasion=occasion,
        transition_mode=transition_mode,
        created_at=time.time(),
        brief_snapshot=brief_snapshot,
    )
    _jobs[job_id] = job

    # Resolve story path for generation (the story analysis, not the reviewed prefs)
    analysis_story_path = audio_path.parent / (audio_path.stem + "_story.json")
    if not analysis_story_path.exists():
        analysis_story_path = None

    # Build config and start background thread
    config = GenerationConfig(
        audio_path=audio_path,
        layout_path=layout_path,
        output_dir=_temp_dir,
        genre=genre,
        occasion=occasion,
        transition_mode=transition_mode,
        curves_mode=curves_mode,
        focused_vocabulary=focused_vocabulary,
        embrace_repetition=embrace_repetition,
        palette_restraint=palette_restraint,
        duration_scaling=duration_scaling,
        beat_accent_effects=beat_accent_effects,
        tier_selection=tier_selection,
        theme_overrides=theme_overrides,
        story_path=analysis_story_path,
        mood_intent=mood_intent,
        duration_feel=duration_feel,
        accent_strength=accent_strength,
    )
    t = threading.Thread(target=_run_generation, args=(job, config), daemon=True)
    t.start()

    return jsonify({"job_id": job_id, "status": "pending"}), 202


@generate_bp.route("/<source_hash>/status", methods=["GET"])
def job_status(source_hash: str):
    """Poll the status of a generation job."""
    job_id = request.args.get("job_id", "")
    job = _jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "job_id": job.job_id,
        "status": job.status,
        "source_hash": job.source_hash,
        "genre": job.genre,
        "occasion": job.occasion,
        "transition_mode": job.transition_mode,
        "created_at": job.created_at,
        "error": job.error_message,
    })


@generate_bp.route("/<source_hash>/download/<job_id>", methods=["GET"])
def download_sequence(source_hash: str, job_id: str):
    """Download the generated .xsq file for a completed job."""
    job = _jobs.get(job_id)
    if job is None or job.status != "complete" or job.output_path is None:
        return jsonify({"error": "No completed sequence found for this job"}), 404

    return send_file(
        job.output_path,
        as_attachment=True,
        download_name=f"{source_hash}.xsq",
        mimetype="application/octet-stream",
    )


@generate_bp.route("/<source_hash>/history", methods=["GET"])
def generation_history(source_hash: str):
    """List all generation jobs for a song, newest-first.

    Spec 046: includes in-flight jobs (pending/running) so the workspace
    Generate tab can re-attach to a job that started before a page reload.
    Completed jobs carry a ``download_url``; failed jobs carry an ``error``.
    """
    jobs = [j for j in _jobs.values() if j.source_hash == source_hash]
    jobs.sort(key=lambda j: j.created_at, reverse=True)

    payload = []
    for j in jobs:
        entry = {
            "job_id": j.job_id,
            "status": j.status,
            "genre": j.genre,
            "occasion": j.occasion,
            "transition_mode": j.transition_mode,
            "created_at": j.created_at,
        }
        if j.status == "complete":
            entry["download_url"] = (
                f"/generate/{source_hash}/download/{j.job_id}"
            )
        if j.status == "failed":
            entry["error"] = j.error_message or "Generation failed"
        payload.append(entry)

    return jsonify({"jobs": payload})
