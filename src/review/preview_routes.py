"""Flask blueprint for short-section preview render (spec 049)."""
from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request, send_file

from src.generator.preview import (
    CancelToken,
    PreviewCancelled,
    PreviewJob,
    PreviewResult,
    _PreviewCache,
    _canonical_brief_hash,
    pick_representative_section,
    run_section_preview,
)
from src.library import Library
from src.settings import get_layout_path

logger = logging.getLogger(__name__)

preview_bp = Blueprint("preview", __name__)

# ── Module-level dispatcher state ─────────────────────────────────────────

_preview_jobs: dict[str, PreviewJob] = {}
_active_by_song: dict[str, str] = {}   # song_hash -> active job_id
_dispatch_lock = threading.Lock()
_preview_cache: _PreviewCache = _PreviewCache(max_entries=16)
_preview_dir: Path = Path(tempfile.mkdtemp(prefix="xlight_preview_"))


# ── Brief loading helper ──────────────────────────────────────────────────


def _load_saved_brief(source_hash: str) -> Optional[dict]:
    """Load the persisted Brief for a song.

    Reads <audio_stem>_brief.json from the song's analysis directory.
    spec 047 (brief_routes.py) is not yet merged; this is a standalone fallback.
    Returns None if no saved Brief exists.
    """
    from src.library import Library
    entry = Library().find_by_hash(source_hash)
    if entry is None:
        return None

    audio_path = Path(entry.source_file)
    brief_path = audio_path.parent / (audio_path.stem + "_brief.json")
    if not brief_path.exists():
        return None

    try:
        return json.loads(brief_path.read_text())
    except Exception:
        return None


def _sanitize_error(e: Exception) -> str:
    """Convert an exception to a user-readable error string."""
    if isinstance(e, FileNotFoundError):
        return "Layout or analysis file not found."
    if isinstance(e, ValueError):
        return str(e)
    return f"Preview generation failed: {type(e).__name__}"


# ── Background thread ──────────────────────────────────────────────────────


def _run_preview(job: PreviewJob, config: object, output_path: Path) -> None:
    """Background thread target: run run_section_preview and update job state."""
    job.status = "running"
    job.started_at = time.time()

    try:
        result = run_section_preview(
            config=config,
            section_index=job.section_index,
            output_path=output_path,
            cancel_token=job.cancel_token,
        )
        # Fill in the artifact URL (route handler can't know job_id yet when
        # it builds the result inside run_section_preview)
        result.artifact_url = f"/api/song/{job.song_hash}/preview/{job.job_id}/download"
        result.warnings.extend(job.warnings)

        job.artifact_path = output_path
        job.result = result
        job.status = "done"
        job.completed_at = time.time()

        # Insert into LRU cache
        cache_key = (job.song_hash, job.section_index, job.brief_hash)
        _preview_cache.put(cache_key, result, output_path)

    except PreviewCancelled:
        job.status = "cancelled"
        job.completed_at = time.time()
        # Clean up partial artifact
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass

    except Exception as e:  # noqa: BLE001
        job.error_message = _sanitize_error(e)
        job.status = "failed"
        job.completed_at = time.time()
        logger.exception("Preview job %s failed", job.job_id)
        # Clean up partial artifact
        try:
            output_path.unlink(missing_ok=True)
        except Exception:
            pass


# ── Endpoints ─────────────────────────────────────────────────────────────


@preview_bp.route("/<source_hash>/preview", methods=["POST"])
def start_preview(source_hash: str):
    """Launch a scoped section preview job.

    POST body (JSON):
      {
        "section_index": <int|null>,  // null = auto-select representative
        "brief": <dict|"saved">       // inline brief or "saved" to load persisted
      }

    Returns 202 {job_id} on success, or 200 with cached result on cache hit.
    """
    from src.generator.models import GenerationConfig

    # Validate song exists
    entry = Library().find_by_hash(source_hash)
    if entry is None:
        return jsonify({"error": "Song not found in library"}), 404

    # Validate analysis exists
    analysis_path = Path(entry.analysis_path)
    if not analysis_path.exists():
        return jsonify({"error": "Song has not been analyzed. Run analysis first."}), 400

    # Validate layout is configured
    layout_path = get_layout_path()
    if layout_path is None or not layout_path.exists():
        return jsonify({
            "error": "No layout configured. Set up layout groups first.",
            "setup_required": True,
        }), 409

    # Parse request body
    body = request.get_json(silent=True) or {}
    section_index_raw = body.get("section_index")
    brief_raw = body.get("brief", "saved")

    # Resolve brief
    if brief_raw == "saved":
        brief = _load_saved_brief(source_hash)
        if brief is None:
            # No saved brief — use an empty dict (config defaults will apply)
            brief = {}
    elif isinstance(brief_raw, dict):
        brief = brief_raw
    else:
        return jsonify({"error": "brief must be an object or the string 'saved'"}), 400

    # Resolve section index
    audio_path = Path(entry.source_file)
    story_path = audio_path.parent / (audio_path.stem + "_story.json")
    if not story_path.exists():
        story_path = None

    # Build config — used to load analysis and run the preview
    config = GenerationConfig(
        audio_path=audio_path,
        layout_path=layout_path,
        output_dir=_preview_dir,
        genre=brief.get("genre", "pop"),
        occasion=brief.get("occasion", "general"),
        transition_mode=brief.get("transition_mode", "subtle"),
        story_path=story_path,
        curves_mode=brief.get("curves_mode", "none"),
        focused_vocabulary=bool(brief.get("focused_vocabulary", True)),
        embrace_repetition=bool(brief.get("embrace_repetition", True)),
        palette_restraint=bool(brief.get("palette_restraint", True)),
        duration_scaling=bool(brief.get("duration_scaling", True)),
        beat_accent_effects=bool(brief.get("beat_accent_effects", True)),
        tier_selection=bool(brief.get("tier_selection", True)),
    )

    # Determine section index — auto-select if null
    if section_index_raw is None:
        # Load sections from analysis to pick representative
        try:
            from src.analyzer.orchestrator import run_orchestrator
            from src.generator.energy import derive_section_energies
            from src.story.builder import load_song_story

            hierarchy = run_orchestrator(str(audio_path), fresh=False)
            if story_path is not None and Path(story_path).exists():
                story = load_song_story(story_path)
                from src.generator.plan import _section_energies_from_story
                section_energies = _section_energies_from_story(story)
            else:
                section_energies = derive_section_energies(
                    hierarchy.sections,
                    hierarchy.energy_curves,
                    hierarchy.energy_impacts,
                    song_duration_ms=hierarchy.duration_ms,
                )
            section_index = pick_representative_section(section_energies)
        except Exception:
            section_index = 0
    else:
        try:
            section_index = int(section_index_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "section_index must be an integer or null"}), 400

    # Validate section_index range (basic sanity — full validation in preview runner)
    if section_index < 0:
        return jsonify({"error": "section_index must be >= 0"}), 400

    # Compute brief hash for cache key
    brief_hash = _canonical_brief_hash(brief)
    cache_key = (source_hash, section_index, brief_hash)

    with _dispatch_lock:
        # Check cache first
        cached = _preview_cache.get(cache_key)
        if cached is not None:
            result, artifact_path = cached
            # Verify file still exists (could have been evicted from disk separately)
            if artifact_path.exists():
                return jsonify({
                    "cached": True,
                    "status": "done",
                    "result": result.to_json(),
                }), 200

        # Cancel any in-flight job for this song (supersede semantics)
        prior_job_id = _active_by_song.get(source_hash)
        if prior_job_id is not None:
            prior_job = _preview_jobs.get(prior_job_id)
            if prior_job is not None and prior_job.status in ("pending", "running"):
                prior_job.cancel_token.cancel()
            # Remove from active (prior job stays in _preview_jobs for diagnostic polling)
            del _active_by_song[source_hash]

        # Create new job
        job_id = str(uuid.uuid4())
        job = PreviewJob(
            job_id=job_id,
            song_hash=source_hash,
            section_index=section_index,
            brief_snapshot=dict(brief),
            brief_hash=brief_hash,
            status="pending",
            started_at=time.time(),
        )
        _preview_jobs[job_id] = job
        _active_by_song[source_hash] = job_id

    # Output path for this job's artifact
    output_path = _preview_dir / f"preview_{job_id}.xsq"

    # Launch background thread
    t = threading.Thread(
        target=_run_preview,
        args=(job, config, output_path),
        daemon=True,
    )
    t.start()

    return jsonify({"job_id": job_id, "status": "pending"}), 202


@preview_bp.route("/<source_hash>/preview/<job_id>", methods=["GET"])
def preview_status(source_hash: str, job_id: str):
    """Poll the status of a preview job.

    Returns JSON with status + result metadata when done, or error when failed.
    404 when job_id is unknown; 400 when hash does not match the job.
    """
    job = _preview_jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404

    if job.song_hash != source_hash:
        return jsonify({"error": "song hash mismatch"}), 400

    payload: dict = {
        "job_id": job.job_id,
        "status": job.status,
        "song_hash": job.song_hash,
        "section_index": job.section_index,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }

    if job.status == "done" and job.result is not None:
        payload["result"] = job.result.to_json()

    if job.status == "failed":
        payload["error"] = job.error_message or "Preview generation failed"

    if job.status == "cancelled":
        payload["error"] = "Preview was superseded by a newer request"

    return jsonify(payload), 200


@preview_bp.route("/<source_hash>/preview/<job_id>/download", methods=["GET"])
def download_preview(source_hash: str, job_id: str):
    """Download the preview .xsq artifact for a completed job.

    409 if job is not done, 410 if cancelled, 404 if artifact missing.
    """
    job = _preview_jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404

    if job.song_hash != source_hash:
        return jsonify({"error": "song hash mismatch"}), 400

    if job.status == "cancelled":
        return jsonify({"error": "Preview was superseded — no artifact available"}), 410

    if job.status != "done":
        return jsonify({"error": f"Preview is not complete (status: {job.status})"}), 409

    if job.artifact_path is None or not job.artifact_path.exists():
        return jsonify({"error": "Artifact file missing"}), 404

    return send_file(
        job.artifact_path,
        as_attachment=True,
        download_name=f"preview_{source_hash}_s{job.section_index}.xsq",
        mimetype="application/octet-stream",
    )
