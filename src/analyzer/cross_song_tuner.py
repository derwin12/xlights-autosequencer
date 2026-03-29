"""Cross-song parameter tuning framework.

Runs parameter sweeps across multiple songs in prioritized batches,
aggregates results, and produces optimal default values for each parameter.

Batch strategy (most impactful first):
  Batch 1 — Onset Detection:  sensitivity, threshold, silence
  Batch 2 — Beat/Tempo:       inputtempo, constraintempo, minioi
  Batch 3 — Pitch/Melody:     threshdistr, outputunvoiced, attack
  Batch 4 — Envelope/Perc:    release, perc_threshold, perc_sensitivity
"""
from __future__ import annotations

import copy
import json
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from src.analyzer.stem_affinity import AFFINITY_TABLE


# ── Parameter batch definitions ──────────────────────────────────────────────

@dataclass
class ParamSpec:
    """Describes one tunable parameter and its sweep range."""

    name: str
    algorithms: list[str]
    min_val: float
    max_val: float
    default_val: float
    steps: int = 7
    is_quantized: bool = False
    quantize_step: float = 0.0
    description: str = ""

    def sweep_values(self) -> list[float]:
        """Generate evenly-spaced sweep values across the range."""
        if self.is_quantized and self.quantize_step > 0:
            vals = []
            v = self.min_val
            while v <= self.max_val + 1e-9:
                vals.append(round(v, 6))
                v += self.quantize_step
            # If too many, subsample evenly
            if len(vals) > self.steps:
                indices = np.linspace(0, len(vals) - 1, self.steps, dtype=int)
                vals = [vals[i] for i in indices]
            return vals
        if self.steps <= 1:
            return [round((self.min_val + self.max_val) / 2, 6)]
        return [
            round(self.min_val + (self.max_val - self.min_val) * i / (self.steps - 1), 6)
            for i in range(self.steps)
        ]


@dataclass
class ParamBatch:
    """A group of parameters to tune together."""

    batch_id: int
    name: str
    description: str
    params: list[ParamSpec]


# ── Built-in batch definitions ───────────────────────────────────────────────

TUNING_BATCHES: list[ParamBatch] = [
    ParamBatch(
        batch_id=1,
        name="Onset Detection",
        description=(
            "Controls how sensitively onset detectors fire. "
            "These parameters affect 6 algorithms across QM and Aubio onset detectors — "
            "the most widely-used timing track producers."
        ),
        params=[
            ParamSpec(
                name="sensitivity",
                algorithms=["qm_onsets_complex", "qm_onsets_hfc", "qm_onsets_phase"],
                min_val=0.0, max_val=100.0, default_val=50.0, steps=7,
                description="QM onset detector sensitivity (0=least, 100=most sensitive)",
            ),
            ParamSpec(
                name="threshold",
                algorithms=["aubio_onset"],
                min_val=0.0, max_val=1.0, default_val=0.3, steps=7,
                description="Aubio onset detection threshold (lower=more onsets)",
            ),
            ParamSpec(
                name="silence",
                algorithms=["aubio_onset"],
                min_val=-90.0, max_val=-20.0, default_val=-70.0, steps=7,
                description="Aubio silence gate in dB (below this = silence)",
            ),
        ],
    ),
    ParamBatch(
        batch_id=2,
        name="Beat & Tempo",
        description=(
            "Controls tempo estimation hints and inter-onset spacing. "
            "Affects QM beat/bar trackers and Aubio onset minimum interval."
        ),
        params=[
            ParamSpec(
                name="inputtempo",
                algorithms=["qm_beats", "qm_bars"],
                min_val=60.0, max_val=180.0, default_val=120.0, steps=7,
                description="Tempo hint in BPM for QM beat/bar trackers",
            ),
            ParamSpec(
                name="constraintempo",
                algorithms=["qm_beats", "qm_bars"],
                min_val=0.0, max_val=1.0, default_val=0.0, steps=3,
                is_quantized=True, quantize_step=1.0,
                description="Whether to constrain to inputtempo (0=no, 1=yes)",
            ),
            ParamSpec(
                name="minioi",
                algorithms=["aubio_onset"],
                min_val=0.0, max_val=0.1, default_val=0.02, steps=6,
                description="Minimum inter-onset interval in seconds",
            ),
        ],
    ),
    ParamBatch(
        batch_id=3,
        name="Pitch & Melody",
        description=(
            "Controls pitch detection behavior for pYIN and amplitude envelope. "
            "Affects vocal/melodic timing track quality."
        ),
        params=[
            ParamSpec(
                name="threshdistr",
                algorithms=["pyin_notes", "pyin_pitch_changes"],
                min_val=0.0, max_val=7.0, default_val=2.0, steps=8,
                is_quantized=True, quantize_step=1.0,
                description="pYIN threshold distribution (0-7, each is a different distribution)",
            ),
            ParamSpec(
                name="outputunvoiced",
                algorithms=["pyin_notes", "pyin_pitch_changes"],
                min_val=0.0, max_val=2.0, default_val=0.0, steps=3,
                is_quantized=True, quantize_step=1.0,
                description="pYIN unvoiced output mode (0=none, 1=negative, 2=random)",
            ),
            ParamSpec(
                name="attack",
                algorithms=["amplitude_follower"],
                min_val=0.001, max_val=0.5, default_val=0.01, steps=7,
                description="Amplitude follower attack time in seconds",
            ),
        ],
    ),
    ParamBatch(
        batch_id=4,
        name="Envelope & Percussion",
        description=(
            "Fine-tunes amplitude envelope tracking and percussion onset detection. "
            "Lower priority as these affect fewer tracks."
        ),
        params=[
            ParamSpec(
                name="release",
                algorithms=["amplitude_follower"],
                min_val=0.001, max_val=0.5, default_val=0.01, steps=7,
                description="Amplitude follower release time in seconds",
            ),
            ParamSpec(
                name="threshold",
                algorithms=["percussion_onsets"],
                min_val=0.0, max_val=1.0, default_val=0.5, steps=7,
                description="Percussion onset detection threshold",
            ),
            ParamSpec(
                name="sensitivity",
                algorithms=["percussion_onsets"],
                min_val=0.0, max_val=100.0, default_val=50.0, steps=7,
                description="Percussion onset sensitivity",
            ),
        ],
    ),
]


def get_batch(batch_id: int) -> ParamBatch:
    """Return a specific batch by ID (1-based)."""
    for b in TUNING_BATCHES:
        if b.batch_id == batch_id:
            return b
    raise ValueError(f"No batch with id={batch_id}. Valid: 1-{len(TUNING_BATCHES)}")


# ── Per-song sweep result ────────────────────────────────────────────────────

@dataclass
class ParamResult:
    """Result of testing one parameter value on one algorithm for one song."""

    song: str
    algorithm: str
    param_name: str
    param_value: float
    stem: str
    quality_score: float
    mark_count: int
    avg_interval_ms: int
    duration_ms: int = 0


@dataclass
class SongBatchResult:
    """All parameter sweep results for one song in one batch."""

    song_path: str
    song_name: str
    batch_id: int
    results: list[ParamResult] = field(default_factory=list)
    duration_s: float = 0.0


# ── Cross-song aggregation ───────────────────────────────────────────────────

@dataclass
class ParamRecommendation:
    """Recommended optimal value for a single parameter across songs."""

    param_name: str
    algorithms: list[str]
    optimal_value: float
    default_value: float
    mean_score_at_optimal: float
    mean_score_at_default: float
    improvement_pct: float
    per_song_optimal: dict[str, float] = field(default_factory=dict)
    agreement_score: float = 0.0  # 0-1, how much songs agree on the value
    notes: str = ""


@dataclass
class BatchReport:
    """Aggregated tuning report for one batch across all songs."""

    batch_id: int
    batch_name: str
    songs: list[str]
    recommendations: list[ParamRecommendation]
    song_results: list[SongBatchResult]
    generated_at: str = ""
    locked_params: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "batch_name": self.batch_name,
            "songs": self.songs,
            "generated_at": self.generated_at,
            "locked_params": self.locked_params,
            "recommendations": [
                {
                    "param_name": r.param_name,
                    "algorithms": r.algorithms,
                    "optimal_value": r.optimal_value,
                    "default_value": r.default_value,
                    "mean_score_at_optimal": round(r.mean_score_at_optimal, 4),
                    "mean_score_at_default": round(r.mean_score_at_default, 4),
                    "improvement_pct": round(r.improvement_pct, 2),
                    "per_song_optimal": {
                        k: round(v, 4) for k, v in r.per_song_optimal.items()
                    },
                    "agreement_score": round(r.agreement_score, 4),
                    "notes": r.notes,
                }
                for r in self.recommendations
            ],
            "song_details": [
                {
                    "song": sr.song_name,
                    "duration_s": round(sr.duration_s, 1),
                    "result_count": len(sr.results),
                }
                for sr in self.song_results
            ],
        }

    def write(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def read(cls, path: str | Path) -> "BatchReport":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        recs = [
            ParamRecommendation(
                param_name=r["param_name"],
                algorithms=r["algorithms"],
                optimal_value=r["optimal_value"],
                default_value=r["default_value"],
                mean_score_at_optimal=r["mean_score_at_optimal"],
                mean_score_at_default=r["mean_score_at_default"],
                improvement_pct=r["improvement_pct"],
                per_song_optimal=r.get("per_song_optimal", {}),
                agreement_score=r.get("agreement_score", 0.0),
                notes=r.get("notes", ""),
            )
            for r in data["recommendations"]
        ]
        return cls(
            batch_id=data["batch_id"],
            batch_name=data["batch_name"],
            songs=data["songs"],
            recommendations=recs,
            song_results=[],
            generated_at=data.get("generated_at", ""),
            locked_params=data.get("locked_params", {}),
        )


@dataclass
class TuningSession:
    """Full tuning session tracking all batches and their locked-in values."""

    session_id: str
    songs: list[str]
    batch_reports: list[BatchReport] = field(default_factory=list)
    locked_params: dict[str, float] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "songs": self.songs,
            "locked_params": {k: round(v, 6) for k, v in self.locked_params.items()},
            "batch_reports": [br.to_dict() for br in self.batch_reports],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def write(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def read(cls, path: str | Path) -> "TuningSession":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        reports = [BatchReport.read.__func__(BatchReport, None)
                   if False else None for _ in []]  # placeholder
        session = cls(
            session_id=data["session_id"],
            songs=data["songs"],
            locked_params=data.get("locked_params", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
        # Re-hydrate batch reports from inline data
        for br_data in data.get("batch_reports", []):
            recs = [
                ParamRecommendation(
                    param_name=r["param_name"],
                    algorithms=r["algorithms"],
                    optimal_value=r["optimal_value"],
                    default_value=r["default_value"],
                    mean_score_at_optimal=r["mean_score_at_optimal"],
                    mean_score_at_default=r["mean_score_at_default"],
                    improvement_pct=r["improvement_pct"],
                    per_song_optimal=r.get("per_song_optimal", {}),
                    agreement_score=r.get("agreement_score", 0.0),
                    notes=r.get("notes", ""),
                )
                for r in br_data.get("recommendations", [])
            ]
            session.batch_reports.append(BatchReport(
                batch_id=br_data["batch_id"],
                batch_name=br_data["batch_name"],
                songs=br_data["songs"],
                recommendations=recs,
                song_results=[],
                generated_at=br_data.get("generated_at", ""),
                locked_params=br_data.get("locked_params", {}),
            ))
        return session


# ── Core tuning engine ───────────────────────────────────────────────────────

class CrossSongTuner:
    """Runs parameter sweeps across multiple songs and aggregates results.

    Usage::

        tuner = CrossSongTuner(["song1.mp3", "song2.mp3", "song3.mp3"])
        # Run batch 1 (onset detection params)
        report = tuner.run_batch(1)
        # Lock in optimal values from batch 1
        tuner.lock_recommendations(report)
        # Run batch 2 with batch 1 values locked
        report2 = tuner.run_batch(2)
    """

    def __init__(
        self,
        song_paths: list[str],
        output_dir: str | Path | None = None,
        sample_duration_s: float = 30.0,
        sample_start_s: float = 30.0,
    ) -> None:
        self._songs = [str(Path(p).resolve()) for p in song_paths]
        self._output_dir = Path(output_dir) if output_dir else Path.cwd() / "tuning_results"
        self._sample_duration_s = sample_duration_s
        self._sample_start_s = sample_start_s
        self._locked_params: dict[str, float] = {}
        self._session = TuningSession(
            session_id=datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
            songs=[Path(s).stem for s in self._songs],
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @property
    def locked_params(self) -> dict[str, float]:
        return dict(self._locked_params)

    @property
    def session(self) -> TuningSession:
        return self._session

    def lock_recommendations(self, report: BatchReport) -> dict[str, float]:
        """Lock in the optimal values from a batch report for subsequent batches."""
        newly_locked: dict[str, float] = {}
        for rec in report.recommendations:
            if rec.improvement_pct > 0 or rec.agreement_score >= 0.5:
                self._locked_params[rec.param_name] = rec.optimal_value
                newly_locked[rec.param_name] = rec.optimal_value
        self._session.locked_params = dict(self._locked_params)
        return newly_locked

    def run_batch(
        self,
        batch_id: int,
        progress_callback=None,
    ) -> BatchReport:
        """Run a parameter batch across all songs and aggregate results."""
        batch = get_batch(batch_id)
        song_results: list[SongBatchResult] = []

        total_songs = len(self._songs)
        for song_idx, song_path in enumerate(self._songs):
            song_name = Path(song_path).stem
            if progress_callback:
                progress_callback(
                    "song_start", song_idx + 1, total_songs, song_name, batch.name
                )

            t0 = time.perf_counter()
            result = self._sweep_song(song_path, batch, progress_callback)
            result.duration_s = time.perf_counter() - t0
            song_results.append(result)

            if progress_callback:
                progress_callback(
                    "song_done", song_idx + 1, total_songs, song_name,
                    f"{len(result.results)} results in {result.duration_s:.1f}s"
                )

        # Aggregate across songs
        recommendations = self._aggregate(batch, song_results)

        report = BatchReport(
            batch_id=batch.batch_id,
            batch_name=batch.name,
            songs=[Path(s).stem for s in self._songs],
            recommendations=recommendations,
            song_results=song_results,
            generated_at=datetime.now(timezone.utc).isoformat(),
            locked_params=dict(self._locked_params),
        )

        # Save report
        report_path = self._output_dir / f"batch_{batch_id}_{batch.name.lower().replace(' ', '_')}.json"
        report.write(report_path)

        # Update session
        # Remove any existing report for this batch
        self._session.batch_reports = [
            br for br in self._session.batch_reports if br.batch_id != batch_id
        ]
        self._session.batch_reports.append(report)
        self._session.updated_at = datetime.now(timezone.utc).isoformat()
        self._session.write(self._output_dir / "tuning_session.json")

        return report

    def _sweep_song(
        self,
        song_path: str,
        batch: ParamBatch,
        progress_callback=None,
    ) -> SongBatchResult:
        """Run all parameter permutations for one song in one batch."""
        import librosa

        song_name = Path(song_path).stem
        result = SongBatchResult(
            song_path=song_path,
            song_name=song_name,
            batch_id=batch.batch_id,
        )

        # Load audio segment
        y, sr = librosa.load(song_path, sr=None, mono=True)
        start_sample = int(self._sample_start_s * sr)
        end_sample = start_sample + int(self._sample_duration_s * sr)
        if end_sample > len(y):
            end_sample = len(y)
            start_sample = max(0, end_sample - int(self._sample_duration_s * sr))
        y_segment = y[start_sample:end_sample]

        # Load stems if available
        stem_cache = self._load_stems(song_path, sr, start_sample, end_sample)
        stem_cache["full_mix"] = y_segment

        # Get algorithm instances
        algo_map = self._get_algorithm_map()

        # For each param in the batch, sweep across its algorithms
        for param_spec in batch.params:
            sweep_values = param_spec.sweep_values()

            for algo_name in param_spec.algorithms:
                algo_template = algo_map.get(algo_name)
                if algo_template is None:
                    continue

                # Determine stem
                entry = AFFINITY_TABLE.get(algo_name, {})
                preferred_stems = entry.get("stems", ["full_mix"])
                stem = "full_mix"
                for s in preferred_stems:
                    if s in stem_cache:
                        stem = s
                        break

                audio = stem_cache.get(stem, y_segment)

                for val in sweep_values:
                    algo = copy.copy(algo_template)

                    # Apply locked params + current sweep value
                    params = dict(self._locked_params)
                    params[param_spec.name] = val
                    algo.parameters = dict(getattr(algo, 'parameters', {}))
                    algo.parameters.update(params)

                    t0 = time.perf_counter()
                    try:
                        track = algo.run(audio, sr)
                    except Exception:
                        track = None
                    elapsed = int((time.perf_counter() - t0) * 1000)

                    if track is not None and len(track.marks) > 0:
                        from src.analyzer.scorer import score_track
                        qs = score_track(track)
                    else:
                        qs = 0.0

                    result.results.append(ParamResult(
                        song=song_name,
                        algorithm=algo_name,
                        param_name=param_spec.name,
                        param_value=val,
                        stem=stem,
                        quality_score=qs,
                        mark_count=len(track.marks) if track else 0,
                        avg_interval_ms=track.avg_interval_ms if track else 0,
                        duration_ms=elapsed,
                    ))

        return result

    def _aggregate(
        self,
        batch: ParamBatch,
        song_results: list[SongBatchResult],
    ) -> list[ParamRecommendation]:
        """Aggregate per-song results into cross-song recommendations."""
        recommendations: list[ParamRecommendation] = []

        for param_spec in batch.params:
            # Collect all results for this parameter grouped by song
            by_song: dict[str, list[ParamResult]] = {}
            for sr in song_results:
                for r in sr.results:
                    if r.param_name == param_spec.name:
                        by_song.setdefault(r.song, []).append(r)

            if not by_song:
                continue

            # For each song, find the value that maximizes mean quality across algorithms
            per_song_best_value: dict[str, float] = {}
            per_song_best_score: dict[str, float] = {}
            per_song_default_score: dict[str, float] = {}

            for song, results in by_song.items():
                # Group by param_value, average score across algorithms
                by_value: dict[float, list[float]] = {}
                for r in results:
                    by_value.setdefault(r.param_value, []).append(r.quality_score)

                best_val = param_spec.default_val
                best_mean = 0.0
                default_mean = 0.0

                for val, scores in by_value.items():
                    mean = statistics.mean(scores)
                    if mean > best_mean:
                        best_mean = mean
                        best_val = val
                    # Find the closest value to default
                    if abs(val - param_spec.default_val) < 1e-6:
                        default_mean = mean

                per_song_best_value[song] = best_val
                per_song_best_score[song] = best_mean
                per_song_default_score[song] = default_mean

            # Cross-song optimal: weighted vote (each song votes for its best value)
            # Use the value that appears most often, tie-break by mean score
            value_votes: dict[float, list[float]] = {}
            for song, val in per_song_best_value.items():
                score = per_song_best_score[song]
                value_votes.setdefault(val, []).append(score)

            # Pick the value with highest average score weighted by vote count
            optimal_value = param_spec.default_val
            best_composite = -1.0
            for val, scores in value_votes.items():
                # composite = vote_fraction * mean_score
                composite = (len(scores) / len(by_song)) * statistics.mean(scores)
                if composite > best_composite:
                    best_composite = composite
                    optimal_value = val

            # Agreement: fraction of songs that picked the same optimal
            songs_agreeing = sum(
                1 for v in per_song_best_value.values()
                if abs(v - optimal_value) < 1e-6
            )
            agreement = songs_agreeing / len(per_song_best_value) if per_song_best_value else 0.0

            mean_at_optimal = statistics.mean(per_song_best_score.values()) if per_song_best_score else 0.0
            mean_at_default = statistics.mean(per_song_default_score.values()) if per_song_default_score else 0.0

            improvement = (
                ((mean_at_optimal - mean_at_default) / mean_at_default * 100)
                if mean_at_default > 0 else 0.0
            )

            # Generate notes
            notes_parts = []
            if agreement >= 0.8:
                notes_parts.append(f"Strong consensus ({songs_agreeing}/{len(per_song_best_value)} songs agree)")
            elif agreement >= 0.5:
                notes_parts.append(f"Moderate consensus ({songs_agreeing}/{len(per_song_best_value)} songs)")
            else:
                notes_parts.append(f"Low consensus — songs disagree on optimal value")
                # Show the spread
                unique_vals = sorted(set(per_song_best_value.values()))
                notes_parts.append(f"Range: {unique_vals}")

            if improvement > 5:
                notes_parts.append(f"Significant improvement over default ({improvement:.1f}%)")
            elif improvement > 0:
                notes_parts.append(f"Marginal improvement ({improvement:.1f}%)")
            else:
                notes_parts.append("Default value is already optimal or near-optimal")

            recommendations.append(ParamRecommendation(
                param_name=param_spec.name,
                algorithms=param_spec.algorithms,
                optimal_value=optimal_value,
                default_value=param_spec.default_val,
                mean_score_at_optimal=mean_at_optimal,
                mean_score_at_default=mean_at_default,
                improvement_pct=improvement,
                per_song_optimal=per_song_best_value,
                agreement_score=agreement,
                notes=". ".join(notes_parts),
            ))

        return recommendations

    def _load_stems(
        self,
        song_path: str,
        sr: int,
        start_sample: int,
        end_sample: int,
    ) -> dict[str, np.ndarray]:
        """Load available stem audio for a song."""
        import librosa

        cache: dict[str, np.ndarray] = {}
        audio_p = Path(song_path)

        for candidate_dir in [
            audio_p.parent / "stems",
            audio_p.parent / audio_p.stem / "stems",
            audio_p.parent / ".stems",
        ]:
            if not candidate_dir.exists():
                continue
            for stem_file in candidate_dir.iterdir():
                if stem_file.suffix in (".mp3", ".wav") and stem_file.stem in (
                    "drums", "bass", "vocals", "guitar", "piano", "other"
                ):
                    try:
                        stem_y, _ = librosa.load(str(stem_file), sr=sr, mono=True)
                        cache[stem_file.stem] = stem_y[start_sample:end_sample]
                    except Exception:
                        pass
            break  # Use first found stems directory

        return cache

    @staticmethod
    def _get_algorithm_map() -> dict:
        """Get all available algorithm instances."""
        try:
            from src.analyzer.runner import default_algorithms
            return {a.name: a for a in default_algorithms()}
        except ImportError:
            return {}


# ── Optimal defaults generation ──────────────────────────────────────────────

@dataclass
class OptimalDefaults:
    """The final output: a set of optimal default parameter values."""

    params: dict[str, float]
    metadata: dict[str, dict]  # param_name -> {improvement, agreement, notes}
    songs_tested: list[str]
    generated_at: str

    def to_dict(self) -> dict:
        return {
            "optimal_defaults": {k: round(v, 6) for k, v in self.params.items()},
            "metadata": self.metadata,
            "songs_tested": self.songs_tested,
            "generated_at": self.generated_at,
        }

    def write(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def from_session(cls, session: TuningSession) -> "OptimalDefaults":
        """Extract optimal defaults from a completed tuning session."""
        params: dict[str, float] = {}
        metadata: dict[str, dict] = {}

        for report in session.batch_reports:
            for rec in report.recommendations:
                params[rec.param_name] = rec.optimal_value
                metadata[rec.param_name] = {
                    "algorithms": rec.algorithms,
                    "improvement_pct": round(rec.improvement_pct, 2),
                    "agreement_score": round(rec.agreement_score, 4),
                    "default_value": rec.default_value,
                    "notes": rec.notes,
                }

        return cls(
            params=params,
            metadata=metadata,
            songs_tested=session.songs,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def apply_to_affinity_table(self) -> dict[str, dict]:
        """Generate an updated AFFINITY_TABLE snippet with optimal defaults.

        Does not modify the actual table — returns a dict of algorithm -> params
        that can be applied or reviewed.
        """
        updates: dict[str, dict] = {}

        for param_name, value in self.params.items():
            # Find which algorithms use this parameter
            for algo_name, entry in AFFINITY_TABLE.items():
                if param_name in entry.get("params", []):
                    updates.setdefault(algo_name, {})[param_name] = value

        return updates
