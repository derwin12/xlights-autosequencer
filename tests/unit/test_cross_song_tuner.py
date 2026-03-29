"""Tests for the cross-song parameter tuning framework."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.analyzer.cross_song_tuner import (
    BatchReport,
    CrossSongTuner,
    OptimalDefaults,
    ParamBatch,
    ParamRecommendation,
    ParamResult,
    ParamSpec,
    SongBatchResult,
    TUNING_BATCHES,
    TuningSession,
    get_batch,
)


# ── ParamSpec tests ──────────────────────────────────────────────────────────

class TestParamSpec:
    def test_sweep_values_continuous(self):
        spec = ParamSpec(
            name="sensitivity",
            algorithms=["qm_onsets_complex"],
            min_val=0.0,
            max_val=100.0,
            default_val=50.0,
            steps=5,
        )
        vals = spec.sweep_values()
        assert len(vals) == 5
        assert vals[0] == 0.0
        assert vals[-1] == 100.0
        assert vals[2] == 50.0  # midpoint

    def test_sweep_values_quantized(self):
        spec = ParamSpec(
            name="threshdistr",
            algorithms=["pyin_notes"],
            min_val=0.0,
            max_val=7.0,
            default_val=2.0,
            steps=8,
            is_quantized=True,
            quantize_step=1.0,
        )
        vals = spec.sweep_values()
        assert vals == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]

    def test_sweep_values_quantized_subsampled(self):
        """When quantized range has more steps than requested, subsample."""
        spec = ParamSpec(
            name="threshdistr",
            algorithms=["pyin_notes"],
            min_val=0.0,
            max_val=7.0,
            default_val=2.0,
            steps=4,
            is_quantized=True,
            quantize_step=1.0,
        )
        vals = spec.sweep_values()
        assert len(vals) == 4
        assert vals[0] == 0.0
        assert vals[-1] == 7.0

    def test_sweep_values_single_step(self):
        spec = ParamSpec(
            name="x",
            algorithms=["algo"],
            min_val=0.0,
            max_val=1.0,
            default_val=0.5,
            steps=1,
        )
        # steps=1 returns midpoint
        vals = spec.sweep_values()
        assert len(vals) == 1
        assert vals[0] == 0.5


# ── Batch definitions tests ─────────────────────────────────────────────────

class TestBatchDefinitions:
    def test_four_batches_defined(self):
        assert len(TUNING_BATCHES) == 4

    def test_batch_ids_sequential(self):
        ids = [b.batch_id for b in TUNING_BATCHES]
        assert ids == [1, 2, 3, 4]

    def test_each_batch_has_three_params(self):
        for batch in TUNING_BATCHES:
            assert len(batch.params) == 3, (
                f"Batch {batch.batch_id} ({batch.name}) has {len(batch.params)} params, expected 3"
            )

    def test_get_batch_valid(self):
        b = get_batch(1)
        assert b.name == "Onset Detection"

    def test_get_batch_invalid(self):
        with pytest.raises(ValueError, match="No batch"):
            get_batch(99)

    def test_batch1_is_onset_detection(self):
        b = get_batch(1)
        param_names = [p.name for p in b.params]
        assert "sensitivity" in param_names
        assert "threshold" in param_names
        assert "silence" in param_names

    def test_batch2_is_beat_tempo(self):
        b = get_batch(2)
        param_names = [p.name for p in b.params]
        assert "inputtempo" in param_names
        assert "constraintempo" in param_names
        assert "minioi" in param_names


# ── Aggregation tests ────────────────────────────────────────────────────────

class TestAggregation:
    def _make_tuner(self):
        """Create a tuner with mocked internals for aggregation testing."""
        tuner = CrossSongTuner.__new__(CrossSongTuner)
        tuner._songs = ["/fake/song1.mp3", "/fake/song2.mp3"]
        tuner._locked_params = {}
        tuner._output_dir = Path("/tmp/test_tuning")
        return tuner

    def test_aggregate_unanimous(self):
        """When all songs agree on the same optimal value."""
        tuner = self._make_tuner()
        batch = ParamBatch(
            batch_id=1,
            name="Test",
            description="",
            params=[ParamSpec(
                name="sensitivity",
                algorithms=["qm_onsets_complex"],
                min_val=0.0, max_val=100.0, default_val=50.0, steps=3,
            )],
        )

        song_results = [
            SongBatchResult(
                song_path="/fake/song1.mp3", song_name="song1", batch_id=1,
                results=[
                    ParamResult("song1", "qm_onsets_complex", "sensitivity", 0.0, "drums", 0.3, 50, 500),
                    ParamResult("song1", "qm_onsets_complex", "sensitivity", 50.0, "drums", 0.8, 100, 400),
                    ParamResult("song1", "qm_onsets_complex", "sensitivity", 100.0, "drums", 0.5, 200, 300),
                ],
            ),
            SongBatchResult(
                song_path="/fake/song2.mp3", song_name="song2", batch_id=1,
                results=[
                    ParamResult("song2", "qm_onsets_complex", "sensitivity", 0.0, "drums", 0.2, 40, 500),
                    ParamResult("song2", "qm_onsets_complex", "sensitivity", 50.0, "drums", 0.9, 120, 380),
                    ParamResult("song2", "qm_onsets_complex", "sensitivity", 100.0, "drums", 0.4, 180, 310),
                ],
            ),
        ]

        recs = tuner._aggregate(batch, song_results)
        assert len(recs) == 1
        rec = recs[0]
        assert rec.param_name == "sensitivity"
        assert rec.optimal_value == 50.0  # both songs agree
        assert rec.agreement_score == 1.0
        # When optimal == default, scores should be equal
        assert rec.mean_score_at_optimal == rec.mean_score_at_default

    def test_aggregate_disagreement(self):
        """When songs disagree on optimal value, picks highest composite."""
        tuner = self._make_tuner()
        batch = ParamBatch(
            batch_id=1,
            name="Test",
            description="",
            params=[ParamSpec(
                name="threshold",
                algorithms=["aubio_onset"],
                min_val=0.0, max_val=1.0, default_val=0.3, steps=3,
            )],
        )

        song_results = [
            SongBatchResult(
                song_path="/fake/song1.mp3", song_name="song1", batch_id=1,
                results=[
                    ParamResult("song1", "aubio_onset", "threshold", 0.0, "drums", 0.6, 100, 400),
                    ParamResult("song1", "aubio_onset", "threshold", 0.5, "drums", 0.4, 80, 500),
                    ParamResult("song1", "aubio_onset", "threshold", 1.0, "drums", 0.2, 40, 600),
                ],
            ),
            SongBatchResult(
                song_path="/fake/song2.mp3", song_name="song2", batch_id=1,
                results=[
                    ParamResult("song2", "aubio_onset", "threshold", 0.0, "drums", 0.3, 60, 450),
                    ParamResult("song2", "aubio_onset", "threshold", 0.5, "drums", 0.7, 120, 380),
                    ParamResult("song2", "aubio_onset", "threshold", 1.0, "drums", 0.5, 90, 420),
                ],
            ),
        ]

        recs = tuner._aggregate(batch, song_results)
        assert len(recs) == 1
        rec = recs[0]
        assert rec.agreement_score < 1.0  # songs disagree


# ── Serialization tests ─────────────────────────────────────────────────────

class TestSerialization:
    def test_batch_report_roundtrip(self, tmp_path):
        report = BatchReport(
            batch_id=1,
            batch_name="Onset Detection",
            songs=["song1", "song2"],
            recommendations=[
                ParamRecommendation(
                    param_name="sensitivity",
                    algorithms=["qm_onsets_complex"],
                    optimal_value=65.0,
                    default_value=50.0,
                    mean_score_at_optimal=0.85,
                    mean_score_at_default=0.70,
                    improvement_pct=21.4,
                    per_song_optimal={"song1": 65.0, "song2": 65.0},
                    agreement_score=1.0,
                    notes="Strong consensus",
                ),
            ],
            song_results=[],
            generated_at="2026-03-29T00:00:00",
            locked_params={},
        )

        path = tmp_path / "report.json"
        report.write(path)

        loaded = BatchReport.read(path)
        assert loaded.batch_id == 1
        assert loaded.batch_name == "Onset Detection"
        assert len(loaded.recommendations) == 1
        assert loaded.recommendations[0].optimal_value == 65.0
        assert loaded.recommendations[0].agreement_score == 1.0

    def test_tuning_session_roundtrip(self, tmp_path):
        session = TuningSession(
            session_id="test_001",
            songs=["song1", "song2"],
            locked_params={"sensitivity": 65.0},
            created_at="2026-03-29T00:00:00",
            updated_at="2026-03-29T01:00:00",
        )
        session.batch_reports.append(BatchReport(
            batch_id=1,
            batch_name="Onset Detection",
            songs=["song1", "song2"],
            recommendations=[
                ParamRecommendation(
                    param_name="sensitivity",
                    algorithms=["qm_onsets_complex"],
                    optimal_value=65.0,
                    default_value=50.0,
                    mean_score_at_optimal=0.85,
                    mean_score_at_default=0.70,
                    improvement_pct=21.4,
                    agreement_score=1.0,
                ),
            ],
            song_results=[],
            generated_at="2026-03-29T00:00:00",
        ))

        path = tmp_path / "session.json"
        session.write(path)

        loaded = TuningSession.read(path)
        assert loaded.session_id == "test_001"
        assert loaded.locked_params == {"sensitivity": 65.0}
        assert len(loaded.batch_reports) == 1
        assert loaded.batch_reports[0].recommendations[0].optimal_value == 65.0

    def test_optimal_defaults_roundtrip(self, tmp_path):
        defaults = OptimalDefaults(
            params={"sensitivity": 65.0, "threshold": 0.25},
            metadata={
                "sensitivity": {
                    "algorithms": ["qm_onsets_complex"],
                    "improvement_pct": 21.4,
                    "agreement_score": 1.0,
                    "default_value": 50.0,
                    "notes": "Strong consensus",
                },
                "threshold": {
                    "algorithms": ["aubio_onset"],
                    "improvement_pct": 5.0,
                    "agreement_score": 0.66,
                    "default_value": 0.3,
                    "notes": "Moderate consensus",
                },
            },
            songs_tested=["song1", "song2", "song3"],
            generated_at="2026-03-29T00:00:00",
        )

        path = tmp_path / "defaults.json"
        defaults.write(path)

        data = json.loads(path.read_text())
        assert data["optimal_defaults"]["sensitivity"] == 65.0
        assert data["optimal_defaults"]["threshold"] == 0.25
        assert len(data["songs_tested"]) == 3


# ── OptimalDefaults.apply_to_affinity_table tests ────────────────────────────

class TestApplyToAffinityTable:
    def test_maps_params_to_algorithms(self):
        defaults = OptimalDefaults(
            params={"sensitivity": 65.0},
            metadata={},
            songs_tested=[],
            generated_at="",
        )
        updates = defaults.apply_to_affinity_table()
        # sensitivity should map to qm_onsets_complex, qm_onsets_hfc, qm_onsets_phase
        assert "qm_onsets_complex" in updates
        assert "qm_onsets_hfc" in updates
        assert "qm_onsets_phase" in updates
        assert updates["qm_onsets_complex"]["sensitivity"] == 65.0

    def test_inputtempo_maps_to_beat_trackers(self):
        defaults = OptimalDefaults(
            params={"inputtempo": 128.0},
            metadata={},
            songs_tested=[],
            generated_at="",
        )
        updates = defaults.apply_to_affinity_table()
        assert "qm_beats" in updates
        assert "qm_bars" in updates
        assert updates["qm_beats"]["inputtempo"] == 128.0


# ── Lock recommendations tests ──────────────────────────────────────────────

class TestLockRecommendations:
    def test_locks_improving_params(self):
        tuner = CrossSongTuner.__new__(CrossSongTuner)
        tuner._locked_params = {}
        tuner._session = TuningSession(
            session_id="test", songs=[], locked_params={},
        )

        report = BatchReport(
            batch_id=1,
            batch_name="Test",
            songs=[],
            recommendations=[
                ParamRecommendation(
                    param_name="sensitivity",
                    algorithms=["qm_onsets_complex"],
                    optimal_value=65.0,
                    default_value=50.0,
                    mean_score_at_optimal=0.85,
                    mean_score_at_default=0.70,
                    improvement_pct=21.4,
                    agreement_score=0.8,
                ),
                ParamRecommendation(
                    param_name="threshold",
                    algorithms=["aubio_onset"],
                    optimal_value=0.3,
                    default_value=0.3,
                    mean_score_at_optimal=0.7,
                    mean_score_at_default=0.7,
                    improvement_pct=0.0,
                    agreement_score=0.3,  # low agreement AND no improvement
                ),
            ],
            song_results=[],
        )

        locked = tuner.lock_recommendations(report)
        assert "sensitivity" in locked
        assert locked["sensitivity"] == 65.0
        # threshold has 0% improvement and low agreement, should not be locked
        assert "threshold" not in locked


# ── OptimalDefaults.from_session tests ───────────────────────────────────────

class TestFromSession:
    def test_extracts_all_params(self):
        session = TuningSession(
            session_id="test",
            songs=["s1", "s2"],
        )
        session.batch_reports = [
            BatchReport(
                batch_id=1,
                batch_name="B1",
                songs=["s1", "s2"],
                recommendations=[
                    ParamRecommendation(
                        param_name="sensitivity",
                        algorithms=["qm_onsets_complex"],
                        optimal_value=65.0,
                        default_value=50.0,
                        mean_score_at_optimal=0.85,
                        mean_score_at_default=0.70,
                        improvement_pct=21.4,
                        agreement_score=1.0,
                    ),
                ],
                song_results=[],
            ),
            BatchReport(
                batch_id=2,
                batch_name="B2",
                songs=["s1", "s2"],
                recommendations=[
                    ParamRecommendation(
                        param_name="inputtempo",
                        algorithms=["qm_beats"],
                        optimal_value=128.0,
                        default_value=120.0,
                        mean_score_at_optimal=0.9,
                        mean_score_at_default=0.8,
                        improvement_pct=12.5,
                        agreement_score=0.5,
                    ),
                ],
                song_results=[],
            ),
        ]

        defaults = OptimalDefaults.from_session(session)
        assert defaults.params["sensitivity"] == 65.0
        assert defaults.params["inputtempo"] == 128.0
        assert len(defaults.songs_tested) == 2
