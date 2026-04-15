"""Flask review server for xlight-analyze review UI."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory, stream_with_context
from werkzeug.utils import secure_filename

# Spec 045: imported at module scope so tests can patch
# `src.review.server.get_layout_path` via unittest.mock.patch.
from src.settings import get_layout_path  # noqa: E402


# Spec 045: module-level MD5 cache for /library staleness check.
# Keyed by (source_path, mtime_ns, size) so a touched-but-unchanged file
# reuses the cached hash and a modified file recomputes automatically.
_library_md5_cache: dict[tuple[str, int, int], str] = {}


# ── UI adaptation ─────────────────────────────────────────────────────────────

def _adapt_hierarchy_for_ui(data: dict) -> dict:
    """Convert HierarchyResult (schema 2.0.0) to a format the review UI can display.

    The existing JS UI expects a flat ``timing_tracks`` list.  This function
    assembles one from all hierarchy levels so the timeline still renders.
    Non-2.0.0 data is returned unchanged.
    """
    if data.get("schema_version") != "2.0.0":
        return data

    tracks = []

    def _push(track_dict):
        if track_dict:
            tracks.append(track_dict)

    # L2 bars, L3 beats
    _push(data.get("bars"))
    _push(data.get("beats"))

    # L1 sections → synthetic track
    sections = data.get("sections") or []
    if sections:
        tracks.append({
            "name": "sections",
            "algorithm_name": "segmentino",
            "element_type": "structure",
            "marks": sections,
            "quality_score": 0.9,
            "stem_source": "full_mix",
        })

    # L4 events (per stem)
    for track_dict in (data.get("events") or {}).values():
        _push(track_dict)

    # L6 harmony
    _push(data.get("chords"))
    _push(data.get("key_changes"))

    # L0 derived marks as synthetic tracks
    for level_name, element_type in [
        ("energy_impacts", "onset"),
        ("energy_drops", "onset"),
        ("gaps", "gap"),
    ]:
        marks = data.get(level_name) or []
        if marks:
            tracks.append({
                "name": level_name,
                "algorithm_name": level_name,
                "element_type": element_type,
                "marks": marks,
                "quality_score": 0.8,
                "stem_source": "full_mix",
            })

    return {
        "schema_version": data.get("schema_version"),
        "filename": Path(data.get("source_file", "")).name,
        "duration_ms": data.get("duration_ms", 0),
        "estimated_tempo_bpm": data.get("estimated_bpm"),
        "timing_tracks": tracks,
        "stems_available": data.get("stems_available", []),
        "capabilities": data.get("capabilities", {}),
        "warnings": data.get("warnings", []),
        # Preserve full hierarchy for any new UI features
        "hierarchy": data,
    }


# ── Upload-mode shared state ──────────────────────────────────────────────────

class AnalysisJob:
    """State for a single upload-triggered analysis run."""

    def __init__(self, mp3_path: str, build_story: bool = False) -> None:
        self.mp3_path = mp3_path
        self.build_story = build_story
        self.status: str = "running"  # "running" | "done" | "error"
        self.events: list[dict] = []
        self.total: int = 6  # orchestrator has ~6 stages
        self.result_path: str | None = None
        self.story_path: str | None = None
        self.error_message: str | None = None
        self.summary: dict | None = None
        self.lock = threading.Lock()
        # Genius retry: background thread waits on this event
        self._genius_event = threading.Event()
        self.genius_artist: str | None = None
        self.genius_title: str | None = None

    def record_progress(self, idx: int, total: int, name: str, mark_count: int = 0) -> None:
        with self.lock:
            self.total = total
            self.events.append({
                "idx": idx,
                "total": total,
                "name": name,
                "mark_count": mark_count,
            })

    def record_warning(self, message: str) -> None:
        with self.lock:
            self.events.append({"warning": message})

    def record_stage(self, stage: str, label: str) -> None:
        with self.lock:
            self.events.append({"stage": stage, "label": label})

    def prompt_genius(self, guessed_title: str, guessed_artist: str) -> None:
        """Emit a genius_prompt event and clear the wait flag."""
        with self.lock:
            self._genius_event.clear()
            self.events.append({
                "genius_prompt": True,
                "guessed_title": guessed_title,
                "guessed_artist": guessed_artist,
            })

    def wait_for_genius_response(self, timeout: float = 120.0) -> tuple[str | None, str | None]:
        """Block until the user submits artist/title or timeout expires."""
        self._genius_event.wait(timeout=timeout)
        return self.genius_artist, self.genius_title

    def submit_genius_response(self, artist: str, title: str) -> None:
        """Called by the /genius-retry endpoint to unblock the waiting thread."""
        self.genius_artist = artist
        self.genius_title = title
        self._genius_event.set()


_current_job: AnalysisJob | None = None
_job_lock = threading.Lock()


def _run_analysis(app: Flask, job: AnalysisJob) -> None:
    """Background thread: run orchestrator pipeline and update job state."""
    with app.app_context():
        try:
            from src.analyzer.orchestrator import run_orchestrator, _hierarchy_json_path

            # ── Stage 1: Stem separation (runs inside orchestrator) ───────────
            job.record_stage("stems", "Separating stems…")

            first_algo = True

            def _progress(idx: int, total: int, name: str, mark_count: int = 0) -> None:
                nonlocal first_algo
                if first_algo:
                    job.record_stage("analysis", "Analyzing audio…")
                    first_algo = False
                job.record_progress(idx, total, name, mark_count)

            # ── Stage 2: Analysis ─────────────────────────────────────────────
            result = run_orchestrator(
                job.mp3_path,
                fresh=True,
                progress_callback=_progress,
            )

            mp3 = Path(job.mp3_path)
            out_path = str(_hierarchy_json_path(mp3))

            # Register in library (best-effort)
            try:
                from src.library import Library, LibraryEntry
                from src.paths import to_show_relative
                abs_src = str(mp3.resolve())
                abs_ana = str(Path(out_path).resolve())
                lib_entry = LibraryEntry(
                    source_hash=result.source_hash,
                    source_file=abs_src,
                    filename=mp3.name,
                    analysis_path=abs_ana,
                    duration_ms=result.duration_ms,
                    estimated_tempo_bpm=result.estimated_bpm,
                    track_count=len(result.beats.marks) if result.beats else 0,
                    stem_separation=bool(result.stems_available),
                    analyzed_at=int(time.time() * 1000),
                    relative_source_file=to_show_relative(abs_src),
                    relative_analysis_path=to_show_relative(abs_ana),
                )
                Library().upsert(lib_entry)
            except Exception:
                pass

            # ── Stage 3: Story building (optional) ───────────────────────────
            story_path: str | None = None
            if job.build_story:
                job.record_stage("story", "Building song story…")
                try:
                    from src.story.builder import build_song_story
                    hierarchy_dict = json.loads(Path(out_path).read_text(encoding="utf-8"))

                    # First attempt: automatic Genius lookup
                    story_dict = build_song_story(hierarchy_dict, job.mp3_path)
                    section_source = story_dict.get("global", {}).get("section_source", "")

                    # If Genius failed, prompt user for artist/title and retry
                    if section_source != "genius":
                        # Extract what we guessed from the filename/ID3
                        guessed_title = story_dict.get("song", {}).get("title", "")
                        guessed_artist = story_dict.get("song", {}).get("artist", "")
                        job.prompt_genius(guessed_title, guessed_artist)

                        user_artist, user_title = job.wait_for_genius_response(timeout=120)
                        if (user_artist is not None and user_title is not None
                                and user_title != "__skip__"):
                            # Retry with user-provided info
                            import os as _os
                            _os.environ["_GENIUS_OVERRIDE_ARTIST"] = user_artist
                            _os.environ["_GENIUS_OVERRIDE_TITLE"] = user_title
                            try:
                                story_dict = build_song_story(hierarchy_dict, job.mp3_path)
                            finally:
                                _os.environ.pop("_GENIUS_OVERRIDE_ARTIST", None)
                                _os.environ.pop("_GENIUS_OVERRIDE_TITLE", None)

                    story_out = str(mp3.parent / (mp3.stem + "_story.json"))
                    Path(story_out).write_text(
                        json.dumps(story_dict, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    story_path = story_out
                    n_sections = len(story_dict.get("sections", []))
                    job.record_progress(1, 1, "Song story complete", n_sections)
                except Exception as exc:
                    job.record_warning(f"Story building failed: {exc}")

            # Update library entry with resolved title/artist
            try:
                from src.library import Library
                _title = None
                _artist = None
                _filename_stem = mp3.stem
                # Prefer story metadata (Genius-resolved)
                if story_path:
                    try:
                        _story = json.loads(Path(story_path).read_text(encoding="utf-8"))
                        _song = _story.get("song") or {}
                        _t = _song.get("title") or None
                        if _t and _t != _filename_stem:
                            _title = _t
                        _artist = _song.get("artist") or None
                    except Exception:
                        pass
                # Fallback: hierarchy JSON song metadata
                if not _title or not _artist:
                    try:
                        _hier = json.loads(Path(out_path).read_text(encoding="utf-8"))
                        _song = _hier.get("song") or {}
                        if not _title:
                            _t = _song.get("title") or None
                            if _t and _t != _filename_stem:
                                _title = _t
                        if not _artist:
                            _artist = _song.get("artist") or None
                    except Exception:
                        pass
                # Fallback: ID3 tags
                if not _title or not _artist:
                    try:
                        from mutagen.easyid3 import EasyID3
                        tags = EasyID3(str(mp3))
                        if not _title and tags.get("title"):
                            _title = tags["title"][0]
                        if not _artist and tags.get("artist"):
                            _artist = tags["artist"][0]
                    except Exception:
                        pass
                if _title or _artist:
                    existing = Library().find_by_hash(result.source_hash)
                    if existing:
                        existing.title = _title
                        existing.artist = _artist
                        Library().upsert(existing)
            except Exception:
                pass

            # Build analysis summary for the UI
            track_count = len(result.algorithms_run)
            has_phonemes = False
            try:
                hier_data = json.loads(Path(out_path).read_text(encoding="utf-8"))
                has_phonemes = hier_data.get("phoneme_result") is not None
            except Exception:
                pass
            summary = {
                "track_count": track_count,
                "stems_available": result.stems_available,
                "has_phonemes": has_phonemes,
                "has_story": story_path is not None,
                "warnings": result.warnings,
            }

            with job.lock:
                job.result_path = out_path
                job.story_path = story_path
                job.summary = summary
                job.status = "done"

        except Exception as exc:
            with job.lock:
                job.status = "error"
                job.error_message = str(exc)


def _progress_generator(job: AnalysisJob):
    """SSE generator: yields progress events from a running or completed job."""
    idx = 0
    while True:
        # Snapshot event count and status atomically so we never miss
        # events appended just before a terminal status change.
        with job.lock:
            event_count = len(job.events)
            status = job.status
            # Capture terminal fields while we hold the lock
            result_path = job.result_path
            story_path = job.story_path
            error_msg = job.error_message
            summary = job.summary

        # Drain any new events (safe: events list is append-only and we
        # read up to a count captured under the lock)
        while idx < event_count:
            yield f"data: {json.dumps(job.events[idx])}\n\n"
            idx += 1

        if status != "running":
            # All events drained — now send the terminal event
            if status == "done":
                done_payload = {'done': True, 'result_path': result_path, 'story_path': story_path}
                if summary:
                    done_payload['summary'] = summary
                yield f"data: {json.dumps(done_payload)}\n\n"
            else:
                yield f"data: {json.dumps({'error': error_msg or 'Analysis failed'})}\n\n"
            return

        time.sleep(0.2)


# ── App factory ────────────────────────────────────────────────────────────────

def _hierarchy_summary_for_server(json_path: Path) -> dict | None:
    """Load a _hierarchy.json and return a summary dict for the library API."""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if data.get("schema_version") != "2.0.0":
            return None
        v = data.get("validation", {})
        dur_ms = data.get("duration_ms", 0)
        minutes, seconds = divmod(dur_ms // 1000, 60)
        events = v.get("events", {})
        l4_mean = (sum(e["transient_rate"] for e in events.values()) / len(events)
                   if events else None)
        return {
            "json_path": str(json_path),
            "source_file": data.get("source_file", ""),
            "name": json_path.stem.replace("_hierarchy", ""),
            "duration": f"{minutes}:{seconds:02d}",
            "duration_ms": dur_ms,
            "bpm": data.get("estimated_bpm", 0),
            "stems": len(data.get("stems_available", ["full_mix"])),
            "bars": v.get("bars", {}).get("score"),
            "beats": v.get("beats", {}).get("score"),
            "sections": v.get("sections", {}).get("bar_alignment_rate"),
            "l4": l4_mean,
            "overall": v.get("overall_score"),
        }
    except Exception:
        return None


def create_app(analysis_path: str | None = None, audio_path: str | None = None,
               scan_dir: str | None = None, story_mode: bool = False) -> Flask:
    """
    Create the Flask application.

    The dashboard (homepage, library, upload, themes) is always available.
    When analysis_path + audio_path are provided, review-mode routes are
    also registered for direct file viewing.
    """
    app = Flask(__name__, static_folder=str(Path(__file__).parent / "static"), static_url_path="")
    app.config["ANALYSIS_PATH"] = analysis_path
    app.config["AUDIO_PATH"] = audio_path
    app.config["SCAN_DIR"] = scan_dir

    # ── Register blueprints ──────────────────────────────────────────────────
    from src.review.story_routes import story_bp  # noqa: PLC0415
    app.register_blueprint(story_bp, url_prefix="/story")

    # ── Register the theme editor blueprint (always available) ────────────────
    from src.review.theme_routes import theme_bp  # noqa: PLC0415
    app.register_blueprint(theme_bp)

    # ── Register the variant library blueprint (always available) ─────────────
    from src.review.variant_routes import variant_bp  # noqa: PLC0415
    app.register_blueprint(variant_bp)

    # ── Register the sequence generation blueprint (always available) ─────────
    from src.review.generate_routes import generate_bp  # noqa: PLC0415
    app.register_blueprint(generate_bp, url_prefix="/generate")

    # ── Register the creative brief blueprint (spec 047) ─────────────────────
    from src.review.brief_routes import brief_bp  # noqa: PLC0415
    app.register_blueprint(brief_bp)

    # ── Register the section preview blueprint (spec 049) ─────────────────────
    from src.review.preview_routes import preview_bp  # noqa: PLC0415
    app.register_blueprint(preview_bp, url_prefix="/api/song")

    # ── Story review SPA route (always available) ─────────────────────────────
    @app.route("/story-review")
    def story_review_spa():
        return send_from_directory(app.static_folder, "story-review.html")

    # ══════════════════════════════════════════════════════════════════════════
    # Dashboard routes — always available regardless of mode
    # ══════════════════════════════════════════════════════════════════════════

    @app.route("/")
    def dashboard_index():
        return send_from_directory(app.static_folder, "dashboard.html")

    @app.route("/library-view")
    def library_view_redirect():
        from flask import redirect
        return redirect("/", code=302)

    @app.route("/timeline")
    def timeline():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/phonemes-view")
    def phonemes_view():
        return send_from_directory(app.static_folder, "phonemes.html")

    # Spec 046: per-song workspace shell served at /song/<source_hash>.
    # Resolves via Library().find_by_hash and gates 404 before serving the
    # static HTML; client-side JS re-reads the hash from location.pathname.
    @app.route("/song/<source_hash>")
    def song_workspace(source_hash):
        from src.library import Library
        if Library().find_by_hash(source_hash) is None:
            return (
                "Song not found in library. "
                "<a href=\"/\">Return to the library view.</a>",
                404,
            )
        return send_from_directory(app.static_folder, "song-workspace.html")

    @app.route("/song/<source_hash>/sections")
    def song_sections(source_hash):
        """Return the detected section list for a song (for the Brief per-section table).

        Reads sections from ``_story.json`` or ``_analysis.json`` (whichever
        contains a ``sections`` list).  Returns an empty list when neither
        exists rather than a 404, so the Brief tab degrades gracefully.
        """
        import json as _json
        entry = Library().find_by_hash(source_hash)
        if entry is None:
            return jsonify({"error": "Song not found"}), 404

        audio_path = Path(entry.source_file)
        sections = []

        # Try story JSON first — it carries richer section metadata
        for stem in ("_story.json", "_hierarchy.json", "_analysis.json"):
            candidate = audio_path.parent / (audio_path.stem + stem)
            if not candidate.exists():
                continue
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                raw_sections = data.get("sections") or []
                if raw_sections:
                    for i, sec in enumerate(raw_sections):
                        sections.append({
                            "section_index": sec.get("section_index", i),
                            "label": sec.get("label", sec.get("role", f"Section {i}")),
                            "start_ms": sec.get("start_ms", 0),
                            "end_ms": sec.get("end_ms", 0),
                            "energy_score": sec.get("energy_score", sec.get("energy", 0)),
                        })
                    break
            except (OSError, _json.JSONDecodeError, KeyError):
                continue

        return jsonify({"sections": sections})

    @app.route("/library")
    def library_index():
        from datetime import datetime, timezone
        from src.library import Library
        from src.review.generate_routes import _jobs
        lib = Library()
        entries = lib.all_entries()

        # Spec 045: compute Zone A layout status once per request (same value
        # for every entry — the dashboard reads entries[0].layout_configured).
        _layout_path = get_layout_path()
        layout_configured = _layout_path is not None and _layout_path.exists()

        # Spec 045: map source_hash → newest completed job timestamp (ISO-8601).
        _last_gen_by_hash: dict[str, str] = {}
        for _job in _jobs.values():
            if _job.status != "complete":
                continue
            _iso = datetime.fromtimestamp(_job.created_at, tz=timezone.utc).isoformat()
            _prev = _last_gen_by_hash.get(_job.source_hash)
            if _prev is None or _iso > _prev:
                _last_gen_by_hash[_job.source_hash] = _iso

        # Spec 045: MD5 stale-check cache, keyed by (path, mtime_ns, size).
        # Keeps /library <100ms for repeated polls on large libraries.
        _md5_cache: dict[tuple[str, int, int], str] = _library_md5_cache

        def _is_stale_for(e) -> bool:
            import hashlib
            src = Path(e.source_file)
            if not src.exists():
                return False
            try:
                stat = src.stat()
                key = (str(src), stat.st_mtime_ns, stat.st_size)
                cached = _md5_cache.get(key)
                if cached is None:
                    h = hashlib.md5()
                    with open(src, "rb") as fh:
                        for chunk in iter(lambda: fh.read(1 << 20), b""):
                            h.update(chunk)
                    cached = h.hexdigest()
                    _md5_cache[key] = cached
                return cached != e.source_hash
            except OSError:
                return False

        def _clean_filename_title(filename: str) -> str:
            """Turn '12_-_Carmina_Burana.mp3' into 'Carmina Burana'."""
            import re
            name = Path(filename).stem
            # Strip leading track number patterns: "12 - ", "12_-_", "12. "
            name = re.sub(r'^\d+[\s._-]+', '', name)
            # Strip leading "- " left over from "12 - Title"
            name = re.sub(r'^-[\s_]+', '', name)
            # Replace underscores and multiple spaces
            name = name.replace('_', ' ').strip()
            name = re.sub(r'\s{2,}', ' ', name)
            # Title-case if all lowercase
            if name == name.lower():
                name = name.title()
            return name or filename

        def _enrich(e):
            """Enrich a library entry with dashboard display fields."""
            entry_dict = {**e.__dict__}
            entry_dict["source_file_exists"] = Path(e.source_file).exists()
            entry_dict["file_exists"] = entry_dict["source_file_exists"]
            entry_dict["analysis_exists"] = Path(e.analysis_path).exists()

            # Title/artist: prefer stored values from library entry
            title = e.title
            artist = e.artist
            album = None
            genre = None
            year = None
            has_cover = False
            quality_score = None
            has_phonemes = False
            has_story = False

            # Check for story file (independent of analysis file)
            mp3 = Path(e.source_file)
            story_path = mp3.parent / (mp3.stem + "_story.json")
            has_story = story_path.exists()
            entry_dict["story_path"] = str(story_path) if has_story else None

            # Helper: reject titles that are just the filename stem
            filename_stem = Path(e.filename).stem

            def _is_real_title(t: str | None) -> bool:
                return bool(t) and t != filename_stem

            try:
                with open(e.analysis_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                has_phonemes = data.get("phoneme_result") is not None
                quality_score = (data.get("validation") or {}).get("overall_score")
                song_meta = data.get("song") or {}
                if not title and _is_real_title(song_meta.get("title")):
                    title = song_meta["title"]
                if not artist and song_meta.get("artist") and song_meta["artist"] != "Unknown":
                    artist = song_meta["artist"]
            except Exception:
                pass

            # Story JSON: Genius-resolved title/artist
            if has_story and (not title or not artist):
                try:
                    story_data = json.loads(story_path.read_text(encoding="utf-8"))
                    song_meta = story_data.get("song") or {}
                    if not title and _is_real_title(song_meta.get("title")):
                        title = song_meta["title"]
                    if not artist and song_meta.get("artist") and song_meta["artist"] != "Unknown":
                        artist = song_meta["artist"]
                except Exception:
                    pass

            # ID3 tags: album, genre, year, cover art + title/artist fallback
            if mp3.exists():
                try:
                    import mutagen as _mutagen
                    mf = _mutagen.File(str(mp3))
                    if mf is not None and mf.tags is not None:
                        tags = mf.tags
                        # Title/artist from tags
                        if not title:
                            v = tags.get("TIT2") or tags.get("title")
                            if v:
                                title = str(v[0]) if isinstance(v, list) else str(v)
                        if not artist:
                            v = tags.get("TPE1") or tags.get("artist")
                            if v:
                                artist = str(v[0]) if isinstance(v, list) else str(v)
                        # Album
                        v = tags.get("TALB") or tags.get("album")
                        if v:
                            album = str(v[0]) if isinstance(v, list) else str(v)
                        # Genre
                        v = tags.get("TCON") or tags.get("genre")
                        if v:
                            genre = str(v[0]) if isinstance(v, list) else str(v)
                        # Year
                        v = tags.get("TDRC") or tags.get("TYER") or tags.get("date")
                        if v:
                            year = (str(v[0]) if isinstance(v, list) else str(v))[:4]
                        # Cover art
                        has_cover = any(
                            k.startswith("APIC") for k in tags.keys()
                        ) if hasattr(tags, 'keys') else False
                        if not has_cover and hasattr(mf, 'pictures'):
                            has_cover = len(mf.pictures) > 0
                except Exception:
                    pass

            entry_dict["title"] = title or _clean_filename_title(e.filename)
            entry_dict["artist"] = artist or "Unknown"
            entry_dict["album"] = album
            entry_dict["genre"] = genre
            entry_dict["year"] = year
            entry_dict["has_cover"] = has_cover
            entry_dict["quality_score"] = quality_score
            entry_dict["has_phonemes"] = has_phonemes
            # Spec 045 consumes has_story (already populated above) along with
            # three new fields below for the stateful workflow strip and
            # Zone A setup banner.
            entry_dict["has_story"] = has_story
            entry_dict["layout_configured"] = layout_configured
            entry_dict["last_generated_at"] = _last_gen_by_hash.get(e.source_hash)
            entry_dict["is_stale"] = _is_stale_for(e)
            return entry_dict

        result = {
            "version": "1.0",
            "entries": [_enrich(e) for e in entries],
        }
        return jsonify(result)

    @app.route("/library/debug")
    def library_debug():
        """Debug endpoint: show what metadata extraction finds for each song."""
        from src.library import Library
        entries = Library().all_entries()
        results = []
        for e in entries:
            mp3 = Path(e.source_file)
            info = {
                "filename": e.filename,
                "source_file": e.source_file,
                "source_exists": mp3.exists(),
                "analysis_path": e.analysis_path,
                "analysis_exists": Path(e.analysis_path).exists(),
                "stored_title": e.title,
                "stored_artist": e.artist,
            }
            # Check story JSON
            story_path = mp3.parent / (mp3.stem + "_story.json")
            info["story_exists"] = story_path.exists()
            if story_path.exists():
                try:
                    sd = json.loads(story_path.read_text(encoding="utf-8"))
                    info["story_song"] = sd.get("song")
                except Exception as exc:
                    info["story_error"] = str(exc)
            # Check analysis JSON
            if Path(e.analysis_path).exists():
                try:
                    ad = json.loads(Path(e.analysis_path).read_text(encoding="utf-8"))
                    info["analysis_song"] = ad.get("song")
                except Exception as exc:
                    info["analysis_error"] = str(exc)
            # Check mutagen
            if mp3.exists():
                try:
                    import mutagen as _mutagen
                    mf = _mutagen.File(str(mp3))
                    info["mutagen_type"] = type(mf).__name__ if mf else None
                    info["mutagen_tags_type"] = type(mf.tags).__name__ if mf and mf.tags else None
                    if mf and mf.tags:
                        info["mutagen_keys"] = list(mf.tags.keys())[:20]
                        # Try reading specific tags
                        for key in ["TIT2", "TPE1", "TALB", "TCON", "TDRC", "TYER"]:
                            v = mf.tags.get(key)
                            if v:
                                info[f"tag_{key}"] = str(v)
                except Exception as exc:
                    info["mutagen_error"] = str(exc)
            results.append(info)
        return jsonify(results)

    @app.route("/library/<source_hash>/cover")
    def library_cover(source_hash):
        """Serve embedded cover art from the MP3's tags."""
        from src.library import Library
        entry = Library().find_by_hash(source_hash)
        if entry is None:
            abort(404)
        try:
            import mutagen as _mutagen
            mf = _mutagen.File(entry.source_file)
            if mf is not None and mf.tags is not None:
                # ID3v2 APIC frames
                for key in mf.tags.keys():
                    if key.startswith("APIC"):
                        apic = mf.tags[key]
                        return Response(apic.data, mimetype=apic.mime or "image/jpeg")
                # FLAC/OGG style pictures
                if hasattr(mf, 'pictures') and mf.pictures:
                    pic = mf.pictures[0]
                    return Response(pic.data, mimetype=pic.mime or "image/jpeg")
        except Exception:
            pass
        abort(404)

    @app.route("/library/<source_hash>", methods=["DELETE"])
    def library_delete(source_hash):
        from src.library import Library
        lib = Library()
        entry = lib.find_by_hash(source_hash)
        if entry is None:
            return jsonify({"error": "Entry not found", "source_hash": source_hash}), 404

        delete_files = request.args.get("delete_files", "false").lower() == "true"
        lib.remove_entry(source_hash)

        files_deleted = False
        if delete_files:
            from src.library import delete_files_for_entry
            delete_files_for_entry(entry)
            files_deleted = True

        return jsonify({"status": "deleted", "source_hash": source_hash, "files_deleted": files_deleted})

    @app.route("/phonemes")
    def phonemes():
        hash_param = request.args.get("hash")
        if hash_param:
            from src.library import Library
            entry = Library().find_by_hash(hash_param)
            if entry is None:
                return jsonify({"error": f"No analysis found for hash {hash_param}"}), 404
            _analysis_path = entry.analysis_path
            mp3_path = entry.source_file
        elif analysis_path is not None:
            _analysis_path = analysis_path
            mp3_path = audio_path
        else:
            job = _current_job
            if job is None or job.result_path is None:
                return jsonify({"error": "No analysis available"}), 404
            _analysis_path = job.result_path
            mp3_path = job.mp3_path

        try:
            with open(_analysis_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            return jsonify({"error": f"Cannot read analysis: {exc}"}), 500

        phoneme_result = data.get("phoneme_result")
        if phoneme_result is None:
            return jsonify({"error": "No phoneme data in this analysis"}), 404

        vocals_path = Path(mp3_path).parent / "stems" / "vocals.mp3"
        phoneme_result["duration_ms"] = data.get("duration_ms", 0)
        phoneme_result["filename"] = data.get("filename", "")
        phoneme_result["has_vocals_audio"] = vocals_path.exists()

        # Detect MP3 encoder padding so the UI can compensate
        try:
            import subprocess
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", str(mp3_path)],
                capture_output=True, text=True,
            )
            import json as _json
            fmt = _json.loads(probe.stdout).get("format", {})
            phoneme_result["audio_offset_ms"] = round(float(fmt.get("start_time", 0)) * 1000)
        except Exception:
            phoneme_result["audio_offset_ms"] = 0

        return jsonify(phoneme_result)

    @app.route("/vocal-audio")
    def vocal_audio():
        # Try current job first, then review-mode audio path
        mp3_path = None
        job = _current_job
        if job is not None:
            mp3_path = job.mp3_path
        elif audio_path is not None:
            mp3_path = audio_path

        if mp3_path is None:
            return jsonify({"error": "No audio available"}), 404

        audio_p = Path(mp3_path)
        for stem_dir in [audio_p.parent / "stems",
                         audio_p.parent / audio_p.stem / "stems",
                         audio_p.parent / ".stems"]:
            vocals = stem_dir / "vocals.mp3"
            if vocals.exists():
                resp = send_file(str(vocals), mimetype="audio/mpeg", conditional=True)
                resp.headers["Accept-Ranges"] = "bytes"
                return resp
        return jsonify({"error": "Vocals stem not found"}), 404

    @app.route("/stem-audio")
    def stem_audio():
        import re as _re
        stem_name = request.args.get("stem", "")
        if not stem_name:
            return jsonify({"error": "No stem specified"}), 400
        # Sanitize stem_name to prevent path traversal
        if not _re.match(r'^[a-zA-Z0-9_-]+$', stem_name):
            return jsonify({"error": "Invalid stem name"}), 400

        # Determine audio source: current job or review-mode path
        mp3_path = None
        job = _current_job
        if job is not None:
            mp3_path = job.mp3_path
        elif audio_path is not None:
            mp3_path = audio_path

        if mp3_path is None:
            return jsonify({"error": "No audio available"}), 404

        audio_p = Path(mp3_path)
        for stem_dir in [
            audio_p.parent / "stems",
            audio_p.parent / audio_p.stem / "stems",
            audio_p.parent / ".stems",
        ]:
            candidate = stem_dir / f"{stem_name}.mp3"
            if candidate.exists():
                resp = send_file(str(candidate), mimetype="audio/mpeg", conditional=True)
                resp.headers["Accept-Ranges"] = "bytes"
                return resp
        return jsonify({"error": f"Stem {stem_name} not found"}), 404

    @app.route("/open-from-library", methods=["POST"])
    def open_from_library():
        global _current_job
        hash_param = request.args.get("hash", "")
        if not hash_param:
            return jsonify({"error": "hash query param required"}), 400
        from src.library import Library
        entry = Library().find_by_hash(hash_param)
        if entry is None:
            return jsonify({"error": f"No analysis found for hash {hash_param}"}), 404
        job = AnalysisJob.__new__(AnalysisJob)
        job.mp3_path = entry.source_file
        job.build_story = False
        job.status = "done"
        job.result_path = entry.analysis_path
        # Resolve story path from source file
        mp3 = Path(entry.source_file)
        story_path = mp3.parent / (mp3.stem + "_story.json")
        story_path_str = str(story_path) if story_path.exists() else None
        job.story_path = story_path_str
        job.events = []
        job.total = 0
        job.error_message = None
        job.lock = threading.Lock()
        job._genius_event = threading.Event()
        job.genius_artist = None
        job.genius_title = None
        with _job_lock:
            _current_job = job
        return jsonify({"ok": True, "story_path": story_path_str}), 200

    @app.route("/hierarchy-library")
    def hierarchy_library():
        sd = app.config.get("SCAN_DIR") or scan_dir
        if not sd or not Path(sd).is_dir():
            return jsonify({"entries": [], "scan_dir": sd})
        entries = []
        for json_path in sorted(Path(sd).rglob("*_hierarchy.json")):
            summary = _hierarchy_summary_for_server(json_path)
            if summary:
                entries.append(summary)
        entries.sort(key=lambda e: e.get("overall") or 0, reverse=True)
        return jsonify({"entries": entries, "scan_dir": str(sd)})

    @app.route("/open-hierarchy", methods=["POST"])
    def open_hierarchy():
        global _current_job
        body = request.get_json(force=True) or {}
        json_path = body.get("json_path", "")
        if not json_path or not Path(json_path).exists():
            return jsonify({"error": "json_path not found"}), 400

        # Validate the path is a hierarchy JSON file (prevent arbitrary file reads)
        resolved = Path(json_path).resolve()
        if not resolved.name.endswith("_hierarchy.json"):
            return jsonify({"error": "Only _hierarchy.json files can be opened"}), 400

        try:
            with open(str(resolved), "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

        # Validate schema — must look like an actual hierarchy result
        if data.get("schema_version") != "2.0.0":
            return jsonify({"error": "Not a valid hierarchy file (missing schema_version 2.0.0)"}), 400

        mp3_path = data.get("source_file", "")
        if not mp3_path or not Path(mp3_path).exists():
            return jsonify({"error": f"source_file not found: {mp3_path}"}), 404

        # Validate the source file is actually an audio file
        mp3_resolved = Path(mp3_path).resolve()
        if mp3_resolved.suffix.lower() not in (".mp3", ".mp4", ".wav", ".flac", ".m4a"):
            return jsonify({"error": "source_file is not a recognized audio format"}), 400
        job = AnalysisJob.__new__(AnalysisJob)
        job.mp3_path = mp3_path
        job.build_story = False
        job.status = "done"
        job.result_path = json_path
        job.story_path = None
        job.events = []
        job.total = 0
        job.error_message = None
        job.lock = threading.Lock()
        job._genius_event = threading.Event()
        job.genius_artist = None
        job.genius_title = None
        with _job_lock:
            _current_job = job
        return jsonify({"ok": True})

    @app.route("/genius-retry", methods=["POST"])
    def genius_retry():
        job = _current_job
        if job is None or job.status != "running":
            return jsonify({"error": "No active analysis job"}), 400
        data = request.get_json(silent=True) or {}
        artist_val = (data.get("artist") or "").strip()
        title_val = (data.get("title") or "").strip()
        if not title_val:
            return jsonify({"error": "Title is required"}), 400
        job.submit_genius_response(artist_val, title_val)
        return jsonify({"ok": True})

    @app.route("/upload", methods=["POST"])
    def upload():
        global _current_job
        with _job_lock:
            if _current_job is not None and _current_job.status == "running":
                return jsonify({"error": "Analysis already running. Please wait."}), 409

        if "mp3" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        f = request.files["mp3"]
        if not f.filename or not f.filename.lower().endswith(".mp3"):
            return jsonify({"error": "Only .mp3 files are accepted"}), 400

        filename = secure_filename(f.filename)
        song_stem = Path(filename).stem
        song_dir = Path(os.getcwd()) / "songs" / song_stem
        try:
            song_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return jsonify({"error": f"Failed to create song directory: {exc}"}), 500
        save_path = str(song_dir / filename)
        try:
            f.save(save_path)
        except OSError as exc:
            return jsonify({"error": f"Failed to save file: {exc}"}), 500

        build_story = request.form.get("story", "false").lower() == "true"
        job = AnalysisJob(mp3_path=save_path, build_story=build_story)
        with _job_lock:
            _current_job = job

        t = threading.Thread(target=_run_analysis, args=(app, job), daemon=True)
        t.start()

        return jsonify({"status": "started", "filename": filename, "total": 6}), 202

    @app.route("/progress")
    def progress():
        job = _current_job
        if job is None:
            def no_job():
                yield f"data: {json.dumps({'error': 'No active job'})}\n\n"
            return Response(no_job(), mimetype="text/event-stream",
                            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        return Response(
            stream_with_context(_progress_generator(job)),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.route("/job-status")
    def job_status():
        job = _current_job
        if job is None:
            return jsonify({"status": "idle"})
        return jsonify({
            "status": job.status,
            "events_count": len(job.events),
            "total": job.total,
            "result_path": job.result_path,
            "story_path": getattr(job, "story_path", None),
            "error": job.error_message,
        })

    @app.route("/analysis")
    def analysis_data():
        hash_param = request.args.get("hash")
        if hash_param:
            from src.library import Library
            entry = Library().find_by_hash(hash_param)
            if entry is None:
                return jsonify({"error": f"No analysis found for hash {hash_param}"}), 404
            try:
                with open(entry.analysis_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                return jsonify({"error": f"Cannot read analysis: {exc}"}), 500
            return jsonify(_adapt_hierarchy_for_ui(data))
        # Review mode: use config path
        if analysis_path is not None:
            with open(analysis_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return jsonify(_adapt_hierarchy_for_ui(data))
        # Upload mode: use current job
        job = _current_job
        if job is None or job.result_path is None:
            return jsonify({"error": "No analysis available"}), 404
        with open(job.result_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return jsonify(_adapt_hierarchy_for_ui(data))

    @app.route("/audio")
    def audio_data():
        # Review mode: use config path
        if audio_path is not None:
            resp = send_file(audio_path, mimetype="audio/mpeg", conditional=True)
            resp.headers["Accept-Ranges"] = "bytes"
            return resp
        # Upload mode: use current job
        job = _current_job
        if job is None:
            return jsonify({"error": "No audio available"}), 404
        resp = send_file(job.mp3_path, mimetype="audio/mpeg", conditional=True)
        resp.headers["Accept-Ranges"] = "bytes"
        return resp

    @app.route("/export", methods=["POST"])
    def export_tracks():
        body = request.get_json(force=True) or {}
        selected_names = body.get("selected_track_names", [])
        overwrite = body.get("overwrite", False)

        if not selected_names:
            return jsonify({"error": "No tracks selected"}), 400

        # Determine source path
        if analysis_path is not None:
            src_file = analysis_path
        else:
            job = _current_job
            if job is None or job.result_path is None:
                return jsonify({"error": "No analysis available"}), 404
            src_file = job.result_path

        with open(src_file, "r", encoding="utf-8") as fh:
            source = json.load(fh)

        name_set = set(selected_names)
        all_tracks = source.get("timing_tracks", []) + source.get("sweep_tracks", [])
        selected_tracks = [t for t in all_tracks if t.get("name") in name_set]

        src_path = Path(src_file)
        stem = src_path.stem
        if stem.endswith("_analysis"):
            out_stem = stem[: -len("_analysis")] + "_selected"
        else:
            out_stem = stem + "_selected"
        out_path = src_path.parent / (out_stem + ".json")

        if out_path.exists() and not overwrite:
            return jsonify({"warning": "File exists", "path": str(out_path)}), 409

        output = dict(source)
        output["timing_tracks"] = selected_tracks
        selected_algo_names = {t["algorithm_name"] for t in selected_tracks}
        output["algorithms"] = [
            a for a in source.get("algorithms", [])
            if a["name"] in selected_algo_names
        ]

        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(output, fh, indent=2, ensure_ascii=False)

        return jsonify({"path": str(out_path)}), 200

    # ══════════════════════════════════════════════════════════════════════════
    # Review-mode-only routes (when analysis_path is provided)
    # ══════════════════════════════════════════════════════════════════════════

    if analysis_path is not None:

        @app.route("/sweep-view")
        def sweep_view():
            return send_from_directory(app.static_folder, "sweep.html")

        @app.route("/sweep-report")
        def sweep_report():
            ap = Path(app.config["AUDIO_PATH"])
            for sweep_dir in [ap.parent / "sweep",
                              ap.parent / ap.stem / "sweep",
                              ap.parent / "analysis" / "sweep"]:
                report_path = sweep_dir / "sweep_report.json"
                if report_path.exists():
                    with open(report_path, "r", encoding="utf-8") as fh:
                        return jsonify(json.load(fh))
            return jsonify({"error": "No sweep results found."}), 404

        @app.route("/sweep-winners")
        def sweep_winners():
            ap = Path(app.config["AUDIO_PATH"])
            for sweep_dir in [ap.parent / "sweep",
                              ap.parent / ap.stem / "sweep",
                              ap.parent / "analysis" / "sweep"]:
                winners_path = sweep_dir / "winners" / "winners.json"
                if winners_path.exists():
                    with open(winners_path, "r", encoding="utf-8") as fh:
                        return jsonify(json.load(fh))
            return jsonify({"error": "No winners found."}), 404

        @app.route("/sweep-algo-detail")
        def sweep_algo_detail():
            algo_name = request.args.get("algorithm", "")
            if not algo_name:
                return jsonify({"error": "algorithm parameter required"}), 400
            ap = Path(app.config["AUDIO_PATH"])
            for sweep_dir in [ap.parent / "sweep",
                              ap.parent / ap.stem / "sweep",
                              ap.parent / "analysis" / "sweep"]:
                algo_file = sweep_dir / f"sweep_{algo_name}.json"
                if algo_file.exists():
                    with open(algo_file, "r", encoding="utf-8") as fh:
                        return jsonify(json.load(fh))
            return jsonify({"error": f"No data for algorithm {algo_name}"}), 404

        @app.route("/phonemize", methods=["POST"])
        def phonemize():
            body = request.get_json(force=True)
            word = body.get("word", "").strip()
            start_ms = body.get("start_ms", 0)
            end_ms = body.get("end_ms", 100)
            if not word:
                return jsonify({"error": "No word provided"}), 400
            try:
                from src.analyzer.phonemes import word_to_papagayo, distribute_phoneme_timing
                import nltk
                nltk.download("cmudict", quiet=True)
                from nltk.corpus import cmudict as _cmudict
                cmu_dict = _cmudict.dict()
                papagayo = word_to_papagayo(word.upper(), cmu_dict)
                marks = distribute_phoneme_timing(papagayo, start_ms, end_ms)
                return jsonify({
                    "phonemes": [{"label": m.label, "start_ms": m.start_ms, "end_ms": m.end_ms} for m in marks],
                    "papagayo": papagayo,
                })
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

        @app.route("/waveform")
        def waveform():
            stem = request.args.get("stem", "")
            audio_src = Path(app.config["AUDIO_PATH"])
            if stem:
                for stem_dir in [
                    audio_src.parent / "stems",
                    audio_src.parent / audio_src.stem / "stems",
                    audio_src.parent / ".stems",
                ]:
                    candidate = stem_dir / f"{stem}.mp3"
                    if candidate.exists():
                        audio_src = candidate
                        break

            samples_per_pixel = int(request.args.get("spp", 512))
            try:
                import librosa
                import numpy as np
                y, sr = librosa.load(str(audio_src), sr=22050, mono=True)
                n_chunks = len(y) // samples_per_pixel
                if n_chunks == 0:
                    return jsonify({"samples": [], "sample_rate": sr, "samples_per_pixel": samples_per_pixel})
                trimmed = y[:n_chunks * samples_per_pixel]
                chunks = trimmed.reshape(n_chunks, samples_per_pixel)
                peaks = np.abs(chunks).max(axis=1)
                peak_max = peaks.max()
                if peak_max > 0:
                    peaks = peaks / peak_max
                return jsonify({
                    "samples": [round(float(v), 3) for v in peaks],
                    "sample_rate": sr,
                    "samples_per_pixel": samples_per_pixel,
                    "duration_s": len(y) / sr,
                })
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

        @app.route("/save-words", methods=["POST"])
        def save_words():
            body = request.get_json(force=True)
            new_word_marks = body.get("word_marks", [])
            new_phoneme_marks = body.get("phoneme_marks")
            if not new_word_marks:
                return jsonify({"error": "No word marks provided"}), 400
            try:
                with open(app.config["ANALYSIS_PATH"], "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                pr = data.get("phoneme_result")
                if pr:
                    if "word_track" in pr:
                        pr["word_track"]["marks"] = new_word_marks
                    if new_phoneme_marks is not None and "phoneme_track" in pr:
                        pr["phoneme_track"]["marks"] = new_phoneme_marks
                    if "lyrics_block" in pr:
                        pr["lyrics_block"]["text"] = " ".join(
                            m.get("label", "") for m in new_word_marks
                        )
                with open(app.config["ANALYSIS_PATH"], "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2, ensure_ascii=False)
                return jsonify({"ok": True, "count": len(new_word_marks)})
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

    # ── Grouper editor routes ─────────────────────────────────────────────────
    # These routes are always available regardless of analysis_path mode.

    # Per-layout in-memory edit state: md5 -> GroupingEdits
    _grouper_edits: dict[str, object] = {}

    @app.route("/grouper")
    def grouper_index():
        return send_from_directory(app.static_folder, "grouper.html")

    @app.route("/grouper/browse")
    def grouper_browse():
        """Browse directories and list XML files for the layout file picker."""
        dir_path = request.args.get("dir", "")
        if not dir_path:
            # Default starting points: home dir, common xLights locations
            home = Path.home()
            roots: list[dict] = []
            candidates = [
                home,
                home / "Documents",
                home / "xLights",
                home / "Documents" / "xLights",
                Path("/"),
            ]
            for c in candidates:
                if c.is_dir():
                    roots.append({"name": c.name or str(c), "path": str(c)})
            return jsonify({"roots": roots})

        target = Path(dir_path)
        if not target.is_dir():
            return jsonify({"error": f"Not a directory: {dir_path}"}), 400

        dirs: list[dict] = []
        files: list[dict] = []
        try:
            for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    dirs.append({"name": entry.name, "path": str(entry)})
                elif entry.is_file() and entry.suffix.lower() == ".xml":
                    files.append({"name": entry.name, "path": str(entry)})
        except PermissionError:
            return jsonify({"error": f"Permission denied: {dir_path}"}), 403

        parent = str(target.parent) if target.parent != target else None
        return jsonify({
            "current": str(target),
            "parent": parent,
            "dirs": dirs,
            "files": files,
        })

    @app.route("/grouper/layout")
    def grouper_layout():
        from src.grouper.classifier import classify_props, normalize_coords
        from src.grouper.editor import (
            GroupingEdits,
            apply_edits,
            layout_md5,
            load_baseline,
            load_edits,
            new_edits,
            _TIER_LABELS,
            _TIER_PREFIXES,
        )

        layout_path_str = request.args.get("path", "")
        if not layout_path_str:
            return jsonify({"error": "Missing 'path' query parameter"}), 400

        layout_path = Path(layout_path_str)
        if not layout_path.exists():
            return jsonify({"error": f"Layout file not found: {layout_path_str}"}), 400

        try:
            baseline, all_prop_names = load_baseline(layout_path)
        except Exception as exc:
            return jsonify({"error": f"Failed to parse layout: {exc}"}), 500

        md5 = layout_md5(layout_path)

        # Load or create edits for this layout.
        # Always update layout_path to the current container path — saved edits may
        # contain a stale host path (e.g. /Users/rob/xLights/...) from a previous session.
        if md5 not in _grouper_edits:
            saved = load_edits(layout_path, all_prop_names)
            edits_obj = saved if saved is not None else new_edits(layout_path)
            edits_obj.layout_path = str(layout_path)
            _grouper_edits[md5] = edits_obj

        edits = _grouper_edits[md5]
        has_saved_edits = any([edits.moves, edits.added_groups, edits.removed_groups, edits.renamed_groups])
        merged = apply_edits(baseline, edits if has_saved_edits else None, all_prop_names)

        # Fetch prop metadata for the UI
        from src.grouper.layout import parse_layout
        layout = parse_layout(layout_path)
        normalize_coords(layout.props)
        classify_props(layout.props)
        prop_map = {p.name: p for p in layout.props}

        props_json = [
            {
                "name": p.name,
                "display_as": p.display_as,
                "pixel_count": p.pixel_count,
                "norm_x": round(p.norm_x, 3),
                "norm_y": round(p.norm_y, 3),
            }
            for p in layout.props
        ]

        # Build per-tier structure
        groups_by_tier: dict[int, list] = {t: [] for t in range(1, 9)}
        for grp in merged.groups:
            groups_by_tier.setdefault(grp.tier, []).append(grp)

        # Build ungrouped: props not in any group for each tier
        tiers_json = []
        for tier_num in range(1, 9):
            tier_groups = groups_by_tier.get(tier_num, [])
            assigned = set()
            for g in tier_groups:
                assigned.update(g.members)
            ungrouped = [n for n in all_prop_names if n not in assigned]
            tiers_json.append({
                "tier": tier_num,
                "label": _TIER_LABELS.get(tier_num, f"Tier {tier_num}"),
                "prefix": _TIER_PREFIXES.get(tier_num, ""),
                "groups": [
                    {"name": g.name, "members": list(g.members), "is_user_created": False}
                    for g in sorted(tier_groups, key=lambda g: g.name)
                ],
                "ungrouped": ungrouped,
            })

        return jsonify({
            "layout_md5": md5,
            "layout_path": str(layout_path),
            "props": props_json,
            "tiers": tiers_json,
            "has_edits": has_saved_edits,
            "edited_props": list(merged.edited_props),
        })

    @app.route("/grouper/move", methods=["POST"])
    def grouper_move():
        from src.grouper.editor import PropMove, apply_edits, load_baseline, new_edits
        from src.grouper.editor import _TIER_LABELS, _TIER_PREFIXES

        body = request.get_json(force=True) or {}
        md5 = body.get("layout_md5", "")
        moves_data = body.get("moves", [])

        if md5 not in _grouper_edits:
            return jsonify({"error": "Layout not loaded. Call GET /grouper/layout first."}), 400

        edits = _grouper_edits[md5]

        # Validate and add moves
        for m in moves_data:
            prop_name = m.get("prop_name", "")
            tier = m.get("tier")
            from_group = m.get("from_group")
            to_group = m.get("to_group")

            if not prop_name or tier is None:
                return jsonify({"error": "Each move requires prop_name and tier"}), 400

            # Check not already in target group (will be filtered by apply_edits too)
            edits.moves.append(PropMove(
                prop_name=prop_name,
                tier=tier,
                from_group=from_group,
                to_group=to_group,
            ))

        # Re-apply edits and return updated tier
        tier_nums = list({m.get("tier") for m in moves_data})
        if len(tier_nums) != 1:
            return jsonify({"error": "All moves in one request must be for the same tier"}), 400
        tier_num = tier_nums[0]

        # Get the prop names for this layout
        layout_path = Path(edits.layout_path)
        _, all_prop_names = load_baseline(layout_path)
        from src.grouper.grouper import generate_groups
        from src.grouper.classifier import classify_props, normalize_coords
        from src.grouper.layout import parse_layout
        layout_obj = parse_layout(layout_path)
        normalize_coords(layout_obj.props)
        classify_props(layout_obj.props)
        baseline = generate_groups(layout_obj.props)

        merged = apply_edits(baseline, edits, all_prop_names)

        # Extract updated tier data
        tier_groups = [g for g in merged.groups if g.tier == tier_num]
        assigned = set()
        for g in tier_groups:
            assigned.update(g.members)
        ungrouped = [n for n in all_prop_names if n not in assigned]

        return jsonify({
            "success": True,
            "tier": tier_num,
            "groups": [
                {"name": g.name, "members": list(g.members)}
                for g in sorted(tier_groups, key=lambda g: g.name)
            ],
            "ungrouped": ungrouped,
            "edited_props": list(merged.edited_props),
        })

    @app.route("/grouper/group/create", methods=["POST"])
    def grouper_group_create():
        from src.grouper.editor import add_group_to_edits

        body = request.get_json(force=True) or {}
        md5 = body.get("layout_md5", "")
        tier = body.get("tier")
        name = body.get("name", "")

        if md5 not in _grouper_edits:
            return jsonify({"error": "Layout not loaded"}), 400

        edits = _grouper_edits[md5]
        try:
            add_group_to_edits(edits, name, tier)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        return jsonify({
            "success": True,
            "group": {"name": name, "tier": tier, "members": [], "is_user_created": True},
        })

    @app.route("/grouper/group/delete", methods=["POST"])
    def grouper_group_delete():
        from src.grouper.editor import remove_group_from_edits, apply_edits, load_baseline

        body = request.get_json(force=True) or {}
        md5 = body.get("layout_md5", "")
        group_name = body.get("group_name", "")

        if md5 not in _grouper_edits:
            return jsonify({"error": "Layout not loaded"}), 400

        edits = _grouper_edits[md5]

        # Find current members before deleting (from in-memory merged state)
        layout_path = Path(edits.layout_path)
        from src.grouper.classifier import classify_props, normalize_coords
        from src.grouper.layout import parse_layout
        layout_obj = parse_layout(layout_path)
        normalize_coords(layout_obj.props)
        classify_props(layout_obj.props)
        from src.grouper.grouper import generate_groups
        baseline = generate_groups(layout_obj.props)
        all_prop_names = [p.name for p in layout_obj.props]
        merged = apply_edits(baseline, edits, all_prop_names)

        displaced = []
        for g in merged.groups:
            if g.name == group_name:
                displaced = list(g.members)
                tier = g.tier
                break
        else:
            tier = None

        remove_group_from_edits(edits, group_name)

        return jsonify({
            "success": True,
            "displaced_props": displaced,
            "tier": tier,
            "ungrouped": displaced,
        })

    @app.route("/grouper/group/rename", methods=["POST"])
    def grouper_group_rename():
        from src.grouper.editor import rename_group_in_edits

        body = request.get_json(force=True) or {}
        md5 = body.get("layout_md5", "")
        old_name = body.get("old_name", "")
        new_name = body.get("new_name", "")

        if md5 not in _grouper_edits:
            return jsonify({"error": "Layout not loaded"}), 400

        edits = _grouper_edits[md5]
        try:
            rename_group_in_edits(edits, old_name, new_name)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        # Find members in merged state
        layout_path = Path(edits.layout_path)
        from src.grouper.classifier import classify_props, normalize_coords
        from src.grouper.layout import parse_layout
        from src.grouper.grouper import generate_groups
        from src.grouper.editor import apply_edits
        layout_obj = parse_layout(layout_path)
        normalize_coords(layout_obj.props)
        classify_props(layout_obj.props)
        baseline = generate_groups(layout_obj.props)
        all_prop_names = [p.name for p in layout_obj.props]
        merged = apply_edits(baseline, edits, all_prop_names)
        grp = next((g for g in merged.groups if g.name == new_name), None)

        return jsonify({
            "success": True,
            "group": {
                "name": new_name,
                "tier": grp.tier if grp else None,
                "members": list(grp.members) if grp else [],
            },
        })

    @app.route("/grouper/save", methods=["POST"])
    def grouper_save():
        from src.grouper.editor import save_edits

        body = request.get_json(force=True) or {}
        md5 = body.get("layout_md5", "")

        if md5 not in _grouper_edits:
            return jsonify({"error": "Layout not loaded"}), 400

        edits = _grouper_edits[md5]
        layout_path = Path(edits.layout_path)
        try:
            save_edits(edits, layout_path)
        except Exception as exc:
            return jsonify({"error": f"Save failed: {exc}"}), 500

        from src.settings import save_settings
        save_settings({"layout_path": str(layout_path)})

        from src.grouper.editor import edits_path
        return jsonify({"success": True, "edits_path": str(edits_path(layout_path))})

    @app.route("/grouper/reset", methods=["POST"])
    def grouper_reset():
        from src.grouper.editor import reset_edits, new_edits

        body = request.get_json(force=True) or {}
        md5 = body.get("layout_md5", "")

        if md5 not in _grouper_edits:
            return jsonify({"error": "Layout not loaded"}), 400

        edits = _grouper_edits[md5]
        layout_path = Path(edits.layout_path)
        reset_edits(layout_path)
        _grouper_edits[md5] = new_edits(layout_path)

        return jsonify({"success": True, "message": "All edits discarded. Showing baseline grouping."})

    @app.route("/grouper/export", methods=["POST"])
    def grouper_export():
        from src.grouper.editor import (
            apply_edits, export_grouping, load_baseline
        )
        from src.grouper.classifier import classify_props, normalize_coords
        from src.grouper.layout import parse_layout
        from src.grouper.grouper import generate_groups

        body = request.get_json(force=True) or {}
        md5 = body.get("layout_md5", "")

        if md5 not in _grouper_edits:
            return jsonify({"error": "Layout not loaded"}), 400

        edits = _grouper_edits[md5]
        layout_path = Path(edits.layout_path)

        try:
            layout_obj = parse_layout(layout_path)
            normalize_coords(layout_obj.props)
            classify_props(layout_obj.props)
            baseline = generate_groups(layout_obj.props)
            all_prop_names = [p.name for p in layout_obj.props]
            has_edits = any([edits.moves, edits.added_groups, edits.removed_groups, edits.renamed_groups])
            merged = apply_edits(baseline, edits if has_edits else None, all_prop_names)
            out_path = export_grouping(merged, layout_path)
        except Exception as exc:
            return jsonify({"error": f"Export failed: {exc}"}), 500

        return jsonify({
            "success": True,
            "export_path": str(out_path),
            "group_count": len(merged.groups),
            "has_edits": has_edits,
            "edited_prop_count": len(merged.edited_props),
        })

    # ── Generation preview ─────────────────────────────────────────────────

    @app.route("/generation-preview")
    def generation_preview_page():
        return send_from_directory(app.static_folder, "generation-preview.html")

    @app.route("/api/generation-preview/<hash_id>")
    def generation_preview_api(hash_id: str):
        """Return a preview of what generation would produce for a song."""
        from src.library import Library

        lib = Library()
        entry = lib.find_by_hash(hash_id)
        if entry is None:
            return jsonify({"error": "Song not found"}), 404

        analysis_path = entry.analysis_path
        if not analysis_path or not Path(analysis_path).exists():
            return jsonify({"error": "Analysis not found"}), 404

        try:
            data = json.loads(Path(analysis_path).read_text(encoding="utf-8"))
        except Exception as exc:
            return jsonify({"error": f"Cannot read analysis: {exc}"}), 500

        hierarchy = data.get("hierarchy", data)
        raw_sections = hierarchy.get("sections", [])

        sections = []
        for sec in raw_sections:
            label = sec.get("label", "unknown")
            start = sec.get("time_ms", 0)
            end = sec.get("end_ms", start)
            duration_s = (end - start) / 1000.0
            sections.append({
                "label": label,
                "start_ms": start,
                "end_ms": end,
                "duration_s": round(duration_s, 1),
            })

        preview = {
            "title": entry.title or Path(entry.source_file).stem,
            "duration_ms": data.get("duration_ms", hierarchy.get("duration_ms", 0)),
            "section_count": len(sections),
            "sections": sections,
            "stems_available": data.get("stems_available", hierarchy.get("stems_available", [])),
            "track_count": len(data.get("timing_tracks", [])),
            "has_story": bool(hierarchy.get("song_story")),
        }

        return jsonify(preview)

    # ── Rotation report endpoint ───────────────────────────────────────────

    @app.route("/rotation-report")
    def rotation_report_api():
        """Return rotation plan data from a .plan.json file.

        Query params:
          plan_path — path to the .plan.json file (required)
          section   — filter to section label (optional)
          group     — filter to group name (optional)
        """
        plan_path = request.args.get("plan_path")
        if not plan_path:
            return jsonify({"error": "plan_path query parameter required"}), 400

        plan_file = Path(plan_path)
        if not plan_file.exists():
            return jsonify({"error": f"Plan file not found: {plan_path}"}), 404

        try:
            data = json.loads(plan_file.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            return jsonify({"error": f"Failed to read plan file: {exc}"}), 400

        rp = data.get("rotation_plan")
        if not rp:
            return jsonify({"error": "No rotation_plan found in file"}), 404

        entries = rp.get("entries", [])

        section_filter = request.args.get("section")
        group_filter = request.args.get("group")
        if section_filter:
            entries = [e for e in entries if e["section_label"] == section_filter]
        if group_filter:
            entries = [e for e in entries if e["group_name"] == group_filter]

        return jsonify({"rotation_plan": {**rp, "entries": entries}})

    return app
