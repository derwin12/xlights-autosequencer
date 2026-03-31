"""Flask review server for xlight-analyze review UI."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_file, send_from_directory, stream_with_context
from werkzeug.utils import secure_filename


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

    def __init__(self, mp3_path: str) -> None:
        self.mp3_path = mp3_path
        self.status: str = "running"  # "running" | "done" | "error"
        self.events: list[dict] = []
        self.total: int = 6  # orchestrator has ~6 stages
        self.result_path: str | None = None
        self.error_message: str | None = None
        self.lock = threading.Lock()

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


_current_job: AnalysisJob | None = None
_job_lock = threading.Lock()


def _run_analysis(app: Flask, job: AnalysisJob) -> None:
    """Background thread: run orchestrator pipeline and update job state."""
    with app.app_context():
        try:
            from src.analyzer.orchestrator import run_orchestrator, _hierarchy_json_path

            stage_idx = 0

            def _progress(msg: str) -> None:
                nonlocal stage_idx
                stage_idx += 1
                job.record_progress(stage_idx, 6, msg)

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
                lib_entry = LibraryEntry(
                    source_hash=result.source_hash,
                    source_file=str(mp3.resolve()),
                    filename=mp3.name,
                    analysis_path=str(Path(out_path).resolve()),
                    duration_ms=result.duration_ms,
                    estimated_tempo_bpm=result.estimated_bpm,
                    track_count=len(result.beats.marks) if result.beats else 0,
                    stem_separation=bool(result.stems_available),
                    analyzed_at=int(time.time() * 1000),
                )
                Library().upsert(lib_entry)
            except Exception:
                pass

            with job.lock:
                job.result_path = out_path
                job.status = "done"

        except Exception as exc:
            with job.lock:
                job.status = "error"
                job.error_message = str(exc)


def _progress_generator(job: AnalysisJob):
    """SSE generator: yields progress events from a running or completed job."""
    idx = 0
    while True:
        # Drain any new events
        events = job.events  # list ref; safe to read length (append-only)
        while idx < len(events):
            yield f"data: {json.dumps(events[idx])}\n\n"
            idx += 1

        status = job.status
        if status != "running":
            # All events emitted — send terminal event
            if status == "done":
                yield f"data: {json.dumps({'done': True, 'result_path': job.result_path})}\n\n"
            else:
                yield f"data: {json.dumps({'error': job.error_message or 'Analysis failed'})}\n\n"
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

    - analysis_path=None, audio_path=None  → upload/library mode
    - Both provided                         → review mode (shows timeline)
    - scan_dir provided                     → library mode scanning that directory
    """
    app = Flask(__name__, static_folder=str(Path(__file__).parent / "static"), static_url_path="")
    app.config["ANALYSIS_PATH"] = analysis_path
    app.config["AUDIO_PATH"] = audio_path
    app.config["SCAN_DIR"] = scan_dir

    # ── Register the story review blueprint ───────────────────────────────────
    from src.review.story_routes import story_bp  # noqa: PLC0415
    app.register_blueprint(story_bp, url_prefix="/story")

    # ── Story review SPA route (always available) ─────────────────────────────
    @app.route("/story-review")
    def story_review_spa():
        return send_from_directory(app.static_folder, "story-review.html")

    if analysis_path is None:
        # ── Upload mode ───────────────────────────────────────────────────────

        @app.route("/")
        def upload_index():
            # Once analysis is done, serve the review timeline UI
            job = _current_job
            if job is not None and job.status == "done":
                return send_from_directory(app.static_folder, "index.html")
            return send_from_directory(app.static_folder, "library.html")

        @app.route("/library-view")
        def library_view():
            return send_from_directory(app.static_folder, "library.html")

        @app.route("/phonemes-view")
        def phonemes_view():
            return send_from_directory(app.static_folder, "phonemes.html")

        @app.route("/library")
        def library_index():
            from src.library import Library
            lib = Library()
            entries = lib.all_entries()

            def _has_phonemes(analysis_path: str) -> bool:
                try:
                    with open(analysis_path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    return data.get("phoneme_result") is not None
                except Exception:
                    return False

            result = {
                "version": "1.0",
                "entries": [
                    {
                        **e.__dict__,
                        "source_file_exists": Path(e.source_file).exists(),
                        "has_phonemes": _has_phonemes(e.analysis_path),
                    }
                    for e in entries
                ],
            }
            return jsonify(result)

        @app.route("/phonemes")
        def phonemes():
            hash_param = request.args.get("hash")
            if hash_param:
                from src.library import Library
                entry = Library().find_by_hash(hash_param)
                if entry is None:
                    return jsonify({"error": f"No analysis found for hash {hash_param}"}), 404
                analysis_path = entry.analysis_path
                mp3_path = entry.source_file
            else:
                job = _current_job
                if job is None or job.result_path is None:
                    return jsonify({"error": "No analysis available"}), 404
                analysis_path = job.result_path
                mp3_path = job.mp3_path

            try:
                with open(analysis_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                return jsonify({"error": f"Cannot read analysis: {exc}"}), 500

            phoneme_result = data.get("phoneme_result")
            if phoneme_result is None:
                return jsonify({"error": "No phoneme data in this analysis"}), 404

            vocals_path = Path(mp3_path).parent / "stems" / "vocals.mp3"
            return jsonify({
                **phoneme_result,
                "duration_ms": data.get("duration_ms", 0),
                "filename": data.get("filename", ""),
                "has_vocals_audio": vocals_path.exists(),
            })

        @app.route("/vocal-audio")
        def vocal_audio():
            job = _current_job
            if job is None:
                return jsonify({"error": "No active job"}), 404
            vocals_path = Path(job.mp3_path).parent / "stems" / "vocals.mp3"
            if not vocals_path.exists():
                return jsonify({"error": "No vocals stem available"}), 404
            resp = send_file(str(vocals_path), mimetype="audio/mpeg", conditional=True)
            resp.headers["Accept-Ranges"] = "bytes"
            return resp

        @app.route("/stem-audio")
        def stem_audio_upload():
            stem_name = request.args.get("stem", "")
            job = _current_job
            if not stem_name or job is None:
                return jsonify({"error": "No stem or job"}), 400
            stem_file = Path(job.mp3_path).parent / "stems" / f"{stem_name}.mp3"
            if not stem_file.exists():
                return jsonify({"error": f"Stem {stem_name} not found"}), 404
            resp = send_file(str(stem_file), mimetype="audio/mpeg", conditional=True)
            resp.headers["Accept-Ranges"] = "bytes"
            return resp

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
            # Construct a minimal completed job pointing at the library entry.
            job = AnalysisJob.__new__(AnalysisJob)
            job.mp3_path = entry.source_file
            job.include_vamp = True
            job.include_madmom = True
            job.status = "done"
            job.result_path = entry.analysis_path
            job.events = []
            job.total = 0
            job.error_message = None
            job.lock = threading.Lock()
            with _job_lock:
                _current_job = job
            return jsonify({"ok": True}), 200

        @app.route("/hierarchy-library")
        def hierarchy_library():
            scan_dir = app.config.get("SCAN_DIR")
            if not scan_dir or not Path(scan_dir).is_dir():
                return jsonify({"entries": [], "scan_dir": scan_dir})
            entries = []
            for json_path in sorted(Path(scan_dir).rglob("*_hierarchy.json")):
                summary = _hierarchy_summary_for_server(json_path)
                if summary:
                    entries.append(summary)
            entries.sort(key=lambda e: e.get("overall") or 0, reverse=True)
            return jsonify({"entries": entries, "scan_dir": str(scan_dir)})

        @app.route("/open-hierarchy", methods=["POST"])
        def open_hierarchy():
            global _current_job
            body = request.get_json(force=True) or {}
            json_path = body.get("json_path", "")
            if not json_path or not Path(json_path).exists():
                return jsonify({"error": "json_path not found"}), 400
            try:
                with open(json_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500
            mp3_path = data.get("source_file", "")
            if not mp3_path or not Path(mp3_path).exists():
                return jsonify({"error": f"source_file not found: {mp3_path}"}), 404
            job = AnalysisJob.__new__(AnalysisJob)
            job.mp3_path = mp3_path
            job.status = "done"
            job.result_path = json_path
            job.events = []
            job.total = 0
            job.error_message = None
            job.lock = threading.Lock()
            with _job_lock:
                _current_job = job
            return jsonify({"ok": True})

        @app.route("/upload", methods=["POST"])
        def upload():
            global _current_job

            # Concurrency guard
            with _job_lock:
                if _current_job is not None and _current_job.status == "running":
                    return jsonify({"error": "Analysis already running. Please wait."}), 409

            # Validate file
            if "mp3" not in request.files:
                return jsonify({"error": "No file provided"}), 400
            f = request.files["mp3"]
            if not f.filename or not f.filename.lower().endswith(".mp3"):
                return jsonify({"error": "Only .mp3 files are accepted"}), 400

            # Save to ./songs/<stem>/<filename>
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

            job = AnalysisJob(mp3_path=save_path)

            with _job_lock:
                _current_job = job

            t = threading.Thread(target=_run_analysis, args=(app, job), daemon=True)
            t.start()

            return jsonify({
                "status": "started",
                "filename": filename,
                "total": 6,
            }), 202

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
                "error": job.error_message,
            })

        @app.route("/analysis")
        def analysis_upload():
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
            job = _current_job
            if job is None or job.result_path is None:
                return jsonify({"error": "No analysis available"}), 404
            with open(job.result_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return jsonify(_adapt_hierarchy_for_ui(data))

        @app.route("/audio")
        def audio_upload():
            job = _current_job
            if job is None:
                return jsonify({"error": "No audio available"}), 404
            resp = send_file(job.mp3_path, mimetype="audio/mpeg", conditional=True)
            resp.headers["Accept-Ranges"] = "bytes"
            return resp

        @app.route("/export", methods=["POST"])
        def export_upload():
            job = _current_job
            if job is None or job.result_path is None:
                return jsonify({"error": "No analysis available"}), 404

            body = request.get_json(force=True) or {}
            selected_names = body.get("selected_track_names", [])
            overwrite = body.get("overwrite", False)

            if not selected_names:
                return jsonify({"error": "No tracks selected"}), 400

            with open(job.result_path, "r", encoding="utf-8") as fh:
                source = json.load(fh)

            name_set = set(selected_names)
            all_tracks = source.get("timing_tracks", []) + source.get("sweep_tracks", [])
            selected_tracks = [t for t in all_tracks if t.get("name") in name_set]

            src_path = Path(job.result_path)
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

    else:
        # ── Review mode (existing behaviour) ─────────────────────────────────

        @app.route("/")
        def index():
            return send_from_directory(app.static_folder, "index.html")

        @app.route("/analysis")
        def analysis():
            with open(app.config["ANALYSIS_PATH"], "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return jsonify(_adapt_hierarchy_for_ui(data))

        @app.route("/audio")
        def audio():
            resp = send_file(
                app.config["AUDIO_PATH"],
                mimetype="audio/mpeg",
                conditional=True,
            )
            resp.headers["Accept-Ranges"] = "bytes"
            return resp

        @app.route("/stem-audio")
        def stem_audio():
            stem_name = request.args.get("stem", "")
            audio_path = Path(app.config["AUDIO_PATH"])
            if not stem_name:
                return jsonify({"error": "No stem specified"}), 400
            # Check all possible stem locations
            stem_file = None
            for stem_dir in [
                audio_path.parent / "stems",
                audio_path.parent / audio_path.stem / "stems",
                audio_path.parent / ".stems",
            ]:
                candidate = stem_dir / f"{stem_name}.mp3"
                if candidate.exists():
                    stem_file = candidate
                    break
            if stem_file is None:
                return jsonify({"error": f"Stem {stem_name} not found"}), 404
            resp = send_file(str(stem_file), mimetype="audio/mpeg", conditional=True)
            resp.headers["Accept-Ranges"] = "bytes"
            return resp

        @app.route("/vocal-audio")
        def vocal_audio():
            audio_path = Path(app.config["AUDIO_PATH"])
            for stem_dir in [audio_path.parent / "stems",
                             audio_path.parent / audio_path.stem / "stems",
                             audio_path.parent / ".stems"]:
                vocals = stem_dir / "vocals.mp3"
                if vocals.exists():
                    resp = send_file(str(vocals), mimetype="audio/mpeg", conditional=True)
                    resp.headers["Accept-Ranges"] = "bytes"
                    return resp
            return jsonify({"error": "Vocals stem not found"}), 404

        @app.route("/phonemes-view")
        def phonemes_view():
            return send_from_directory(app.static_folder, "phonemes.html")

        @app.route("/sweep-view")
        def sweep_view():
            return send_from_directory(app.static_folder, "sweep.html")

        @app.route("/sweep-report")
        def sweep_report():
            """Return the sweep report JSON for the current song."""
            audio_path = Path(app.config["AUDIO_PATH"])
            # Check song folder convention: <stem>/sweep/ or <parent>/sweep/
            for sweep_dir in [audio_path.parent / "sweep",
                              audio_path.parent / audio_path.stem / "sweep",
                              audio_path.parent / "analysis" / "sweep"]:
                report_path = sweep_dir / "sweep_report.json"
                if report_path.exists():
                    with open(report_path, "r", encoding="utf-8") as fh:
                        return jsonify(json.load(fh))
            return jsonify({"error": "No sweep results found. Run sweep-matrix first."}), 404

        @app.route("/sweep-winners")
        def sweep_winners():
            """Return full-song winner marks for the UI."""
            audio_path = Path(app.config["AUDIO_PATH"])
            for sweep_dir in [audio_path.parent / "sweep",
                              audio_path.parent / audio_path.stem / "sweep",
                              audio_path.parent / "analysis" / "sweep"]:
                winners_path = sweep_dir / "winners" / "winners.json"
                if winners_path.exists():
                    with open(winners_path, "r", encoding="utf-8") as fh:
                        return jsonify(json.load(fh))
            return jsonify({"error": "No winners found. Run sweep-matrix and export winners first."}), 404

        @app.route("/sweep-algo-detail")
        def sweep_algo_detail():
            """Return full per-algorithm sweep data (including timing marks)."""
            algo_name = request.args.get("algorithm", "")
            if not algo_name:
                return jsonify({"error": "algorithm parameter required"}), 400
            audio_path = Path(app.config["AUDIO_PATH"])
            for sweep_dir in [audio_path.parent / "sweep",
                              audio_path.parent / audio_path.stem / "sweep",
                              audio_path.parent / "analysis" / "sweep"]:
                algo_file = sweep_dir / f"sweep_{algo_name}.json"
                if algo_file.exists():
                    with open(algo_file, "r", encoding="utf-8") as fh:
                        return jsonify(json.load(fh))
            return jsonify({"error": f"No data for algorithm {algo_name}"}), 404

        @app.route("/phonemes")
        def phonemes():
            with open(app.config["ANALYSIS_PATH"], "r", encoding="utf-8") as fh:
                data = json.load(fh)
            pr = data.get("phoneme_result")
            if not pr:
                return jsonify({"error": "No phoneme data in this analysis"}), 404
            audio_path = Path(app.config["AUDIO_PATH"])
            has_vocals = any(
                (audio_path.parent / d / "vocals.mp3").exists()
                for d in ["stems", ".stems",
                          f"{audio_path.stem}/stems"]
            )
            pr["duration_ms"] = data.get("duration_ms", 0)
            pr["filename"] = data.get("filename", "")
            pr["has_vocals_audio"] = has_vocals
            # Detect MP3 encoder padding so the UI can compensate
            try:
                import subprocess
                probe = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-print_format", "json",
                     "-show_format", str(audio_path)],
                    capture_output=True, text=True,
                )
                import json as _json
                fmt = _json.loads(probe.stdout).get("format", {})
                pr["audio_offset_ms"] = round(float(fmt.get("start_time", 0)) * 1000)
            except Exception:
                pr["audio_offset_ms"] = 0
            return jsonify(pr)

        @app.route("/phonemize", methods=["POST"])
        def phonemize():
            """Generate Papagayo phonemes for a word using cmudict."""
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
            """Return downsampled waveform amplitude data as JSON."""
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
                # Downsample: compute max amplitude per chunk
                n_chunks = len(y) // samples_per_pixel
                if n_chunks == 0:
                    return jsonify({"samples": [], "sample_rate": sr, "samples_per_pixel": samples_per_pixel})
                trimmed = y[:n_chunks * samples_per_pixel]
                chunks = trimmed.reshape(n_chunks, samples_per_pixel)
                peaks = np.abs(chunks).max(axis=1)
                # Normalize to 0-1
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
            """Persist edited word and phoneme timing back to the analysis JSON."""
            body = request.get_json(force=True)
            new_word_marks = body.get("word_marks", [])
            new_phoneme_marks = body.get("phoneme_marks")  # optional

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
                    # Update lyrics block text
                    if "lyrics_block" in pr:
                        pr["lyrics_block"]["text"] = " ".join(
                            m.get("label", "") for m in new_word_marks
                        )
                with open(app.config["ANALYSIS_PATH"], "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2, ensure_ascii=False)
                return jsonify({"ok": True, "count": len(new_word_marks)})
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

        @app.route("/export", methods=["POST"])
        def export():
            body = request.get_json(force=True) or {}
            selected_names = body.get("selected_track_names", [])
            overwrite = body.get("overwrite", False)

            if not selected_names:
                return jsonify({"error": "No tracks selected"}), 400

            with open(app.config["ANALYSIS_PATH"], "r", encoding="utf-8") as fh:
                source = json.load(fh)

            name_set = set(selected_names)
            all_tracks = source.get("timing_tracks", []) + source.get("sweep_tracks", [])
            selected_tracks = [t for t in all_tracks if t.get("name") in name_set]

            src_path = Path(app.config["ANALYSIS_PATH"])
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

    # ── Grouper editor routes ─────────────────────────────────────────────────
    # These routes are always available regardless of analysis_path mode.

    # Per-layout in-memory edit state: md5 -> GroupingEdits
    _grouper_edits: dict[str, object] = {}

    @app.route("/grouper")
    def grouper_index():
        return send_from_directory(app.static_folder, "grouper.html")

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

        # Load or create edits for this layout
        if md5 not in _grouper_edits:
            saved = load_edits(layout_path, all_prop_names)
            _grouper_edits[md5] = saved if saved is not None else new_edits(layout_path)

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

    return app
