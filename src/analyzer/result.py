"""Core data classes for the analysis pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.analyzer.phonemes import PhonemeResult
    from src.analyzer.structure import SongStructure


@dataclass
class CriterionResult:
    """A single criterion's measurement and score for one track."""

    name: str
    label: str
    measured_value: float
    target_min: float
    target_max: float
    weight: float
    score: float
    contribution: float

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "measured_value": round(self.measured_value, 4),
            "target_min": round(self.target_min, 4),
            "target_max": round(self.target_max, 4),
            "weight": round(self.weight, 4),
            "score": round(self.score, 4),
            "contribution": round(self.contribution, 4),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CriterionResult":
        return cls(
            name=d["name"],
            label=d["label"],
            measured_value=d["measured_value"],
            target_min=d["target_min"],
            target_max=d["target_max"],
            weight=d["weight"],
            score=d["score"],
            contribution=d["contribution"],
        )


@dataclass
class ScoreBreakdown:
    """The complete scoring result for a single track."""

    track_name: str
    algorithm_name: str
    category: str
    overall_score: float
    criteria: list[CriterionResult]
    passed_thresholds: bool = True
    threshold_failures: list[str] = field(default_factory=list)
    skipped_as_duplicate: bool = False
    duplicate_of: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "track_name": self.track_name,
            "algorithm_name": self.algorithm_name,
            "category": self.category,
            "overall_score": round(self.overall_score, 4),
            "criteria": [c.to_dict() for c in self.criteria],
            "passed_thresholds": self.passed_thresholds,
            "threshold_failures": self.threshold_failures,
            "skipped_as_duplicate": self.skipped_as_duplicate,
            "duplicate_of": self.duplicate_of,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ScoreBreakdown":
        return cls(
            track_name=d["track_name"],
            algorithm_name=d["algorithm_name"],
            category=d["category"],
            overall_score=d["overall_score"],
            criteria=[CriterionResult.from_dict(c) for c in d.get("criteria", [])],
            passed_thresholds=d.get("passed_thresholds", True),
            threshold_failures=d.get("threshold_failures", []),
            skipped_as_duplicate=d.get("skipped_as_duplicate", False),
            duplicate_of=d.get("duplicate_of"),
        )


@dataclass
class TimingMark:
    """A single timing event within a track."""

    time_ms: int
    confidence: Optional[float]
    label: Optional[str] = None
    duration_ms: Optional[int] = None

    def __post_init__(self) -> None:
        self.time_ms = int(self.time_ms)
        if self.duration_ms is not None:
            self.duration_ms = int(self.duration_ms)


@dataclass
class AnalysisAlgorithm:
    """Describes one algorithm configuration used in a run."""

    name: str
    element_type: str
    library: str
    plugin_key: Optional[str]
    parameters: dict

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "element_type": self.element_type,
            "library": self.library,
            "plugin_key": self.plugin_key,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AnalysisAlgorithm":
        return cls(
            name=d["name"],
            element_type=d["element_type"],
            library=d["library"],
            plugin_key=d.get("plugin_key"),
            parameters=d.get("parameters", {}),
        )


@dataclass
class TimingTrack:
    """A named sequence of timing marks produced by one algorithm."""

    name: str
    algorithm_name: str
    element_type: str
    marks: list[TimingMark]
    quality_score: float
    stem_source: str = "full_mix"
    score_breakdown: Optional["ScoreBreakdown"] = None

    def __post_init__(self) -> None:
        # Marks are always sorted ascending by time_ms.
        self.marks = sorted(self.marks, key=lambda m: m.time_ms)

    @property
    def mark_count(self) -> int:
        return len(self.marks)

    @property
    def avg_interval_ms(self) -> int:
        if len(self.marks) < 2:
            return 0
        intervals = [
            self.marks[i + 1].time_ms - self.marks[i].time_ms
            for i in range(len(self.marks) - 1)
        ]
        return round(sum(intervals) / len(intervals))

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "algorithm_name": self.algorithm_name,
            "element_type": self.element_type,
            "mark_count": self.mark_count,
            "avg_interval_ms": self.avg_interval_ms,
            "quality_score": round(self.quality_score, 4),
            "stem_source": self.stem_source,
            "marks": [
                {k: v for k, v in {
                    "time_ms": m.time_ms,
                    "confidence": m.confidence,
                    "label": m.label,
                    "duration_ms": m.duration_ms,
                }.items() if v is not None}
                for m in self.marks
            ],
        }
        if self.score_breakdown is not None:
            d["score_breakdown"] = self.score_breakdown.to_dict()
        # Serialize value_curve if attached (e.g. bbc_energy algorithms)
        vc = getattr(self, "value_curve", None)
        if vc is not None and hasattr(vc, "to_dict"):
            d["value_curve"] = vc.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TimingTrack":
        marks = [
            TimingMark(
                time_ms=m["time_ms"],
                confidence=m.get("confidence"),
                label=m.get("label"),
                duration_ms=m.get("duration_ms"),
            )
            for m in d.get("marks", [])
        ]
        bd_data = d.get("score_breakdown")
        breakdown = ScoreBreakdown.from_dict(bd_data) if bd_data else None
        track = cls(
            name=d["name"],
            algorithm_name=d["algorithm_name"],
            element_type=d["element_type"],
            marks=marks,
            quality_score=d.get("quality_score", 0.0),
            stem_source=d.get("stem_source", "full_mix"),
            score_breakdown=breakdown,
        )
        # Restore value_curve if serialized (ValueCurve defined later in this module)
        vc_data = d.get("value_curve")
        if vc_data is not None:
            _vc_cls = globals().get("ValueCurve")
            if _vc_cls is not None:
                track.value_curve = _vc_cls.from_dict(vc_data)
        return track


# ── Interaction analysis result types ─────────────────────────────────────────

@dataclass
class LeaderTransition:
    """A single point where the dominant stem changes."""

    time_ms: int
    from_stem: str
    to_stem: str

    def __post_init__(self) -> None:
        self.time_ms = int(self.time_ms)

    def to_dict(self) -> dict:
        return {"time_ms": self.time_ms, "from_stem": self.from_stem, "to_stem": self.to_stem}

    @classmethod
    def from_dict(cls, d: dict) -> "LeaderTransition":
        return cls(time_ms=d["time_ms"], from_stem=d["from_stem"], to_stem=d["to_stem"])


@dataclass
class LeaderTrack:
    """Frame-by-frame record of which stem holds dominant energy."""

    fps: int
    frames: list[str]                        # one stem name per frame
    transitions: list[LeaderTransition] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return int(len(self.frames) * 1000 / self.fps)

    def to_dict(self) -> dict:
        return {
            "fps": self.fps,
            "frames": self.frames,
            "transitions": [t.to_dict() for t in self.transitions],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LeaderTrack":
        return cls(
            fps=d["fps"],
            frames=d["frames"],
            transitions=[LeaderTransition.from_dict(t) for t in d.get("transitions", [])],
        )


@dataclass
class TightnessWindow:
    """Per-window kick-bass rhythmic tightness measurement."""

    start_ms: int
    end_ms: int
    score: float           # 0.0–1.0
    label: str             # "unison" | "independent" | "mixed"

    def __post_init__(self) -> None:
        self.start_ms = int(self.start_ms)
        self.end_ms = int(self.end_ms)

    def to_dict(self) -> dict:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "score": round(self.score, 4),
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TightnessWindow":
        return cls(
            start_ms=d["start_ms"],
            end_ms=d["end_ms"],
            score=d["score"],
            label=d["label"],
        )


@dataclass
class TightnessResult:
    """Collection of per-window kick-bass rhythmic tightness scores."""

    windows: list[TightnessWindow] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"windows": [w.to_dict() for w in self.windows]}

    @classmethod
    def from_dict(cls, d: dict) -> "TightnessResult":
        return cls(windows=[TightnessWindow.from_dict(w) for w in d.get("windows", [])])


@dataclass
class SidechainedCurve:
    """Vocal/melodic feature curve modified by drum onset positions."""

    source_stem: str
    feature: str
    fps: int
    values: list[int]         # 0–100 per frame, brightness dimension
    boost_values: list[int]   # 0–100 per frame, secondary dimension (e.g. saturation)

    def to_dict(self) -> dict:
        return {
            "source_stem": self.source_stem,
            "feature": self.feature,
            "fps": self.fps,
            "values": self.values,
            "boost_values": self.boost_values,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SidechainedCurve":
        return cls(
            source_stem=d["source_stem"],
            feature=d["feature"],
            fps=d["fps"],
            values=d["values"],
            boost_values=d.get("boost_values", []),
        )


@dataclass
class HandoffEvent:
    """Detected melodic handoff between two stems."""

    time_ms: int
    from_stem: str
    to_stem: str
    confidence: float   # 0.0–1.0

    def __post_init__(self) -> None:
        self.time_ms = int(self.time_ms)

    def to_dict(self) -> dict:
        return {
            "time_ms": self.time_ms,
            "from_stem": self.from_stem,
            "to_stem": self.to_stem,
            "confidence": round(self.confidence, 4),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HandoffEvent":
        return cls(
            time_ms=d["time_ms"],
            from_stem=d["from_stem"],
            to_stem=d["to_stem"],
            confidence=d["confidence"],
        )


@dataclass
class InteractionResult:
    """Container for all cross-stem interaction analysis outputs."""

    leader_track: LeaderTrack
    tightness: Optional[TightnessResult] = None
    sidechained_curves: list[SidechainedCurve] = field(default_factory=list)
    handoffs: list[HandoffEvent] = field(default_factory=list)
    other_stem_class: Optional[str] = None   # "spatial" | "timing" | "ambiguous" | None

    def to_dict(self) -> dict:
        return {
            "leader_track": self.leader_track.to_dict(),
            "tightness": self.tightness.to_dict() if self.tightness else None,
            "sidechained_curves": [c.to_dict() for c in self.sidechained_curves],
            "handoffs": [h.to_dict() for h in self.handoffs],
            "other_stem_class": self.other_stem_class,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "InteractionResult":
        tightness_data = d.get("tightness")
        return cls(
            leader_track=LeaderTrack.from_dict(d["leader_track"]),
            tightness=TightnessResult.from_dict(tightness_data) if tightness_data else None,
            sidechained_curves=[SidechainedCurve.from_dict(c) for c in d.get("sidechained_curves", [])],
            handoffs=[HandoffEvent.from_dict(h) for h in d.get("handoffs", [])],
            other_stem_class=d.get("other_stem_class"),
        )


# ── ValueCurve ─────────────────────────────────────────────────────────────────

@dataclass
class ValueCurve:
    """Continuous time-series of normalized energy values (0-100 per frame).

    Replaces the fake TimingMark lists previously used by bbc_energy et al.
    """

    name: str
    stem_source: str
    fps: int
    values: list[int]

    @property
    def duration_ms(self) -> int:
        if self.fps <= 0:
            return 0
        return int(len(self.values) * 1000 / self.fps)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "stem_source": self.stem_source,
            "fps": self.fps,
            "values": self.values,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ValueCurve":
        return cls(
            name=d["name"],
            stem_source=d["stem_source"],
            fps=d["fps"],
            values=d["values"],
        )


# ── HierarchyResult ────────────────────────────────────────────────────────────

@dataclass
class HierarchyResult:
    """Structured output of the hierarchy orchestrator (schema_version 2.0.0).

    Replaces AnalysisResult as the primary output for the new zero-flag pipeline.
    One field per hierarchy level (L0–L6) plus metadata.
    """

    schema_version: str                          # "2.0.0"
    source_file: str
    source_hash: str                             # MD5 of file content (cache key)
    duration_ms: int
    estimated_bpm: float

    # L0: Special Moments
    energy_impacts: list[TimingMark] = field(default_factory=list)
    energy_drops: list[TimingMark] = field(default_factory=list)
    gaps: list[TimingMark] = field(default_factory=list)

    # L1: Structure
    sections: list[TimingMark] = field(default_factory=list)

    # L2: Bars (single best track)
    bars: Optional["TimingTrack"] = None

    # L3: Beats (single best track) — marks carry label="1"|"2"|"3"|"4" (beat position in bar)
    beats: Optional["TimingTrack"] = None

    # L2.5: Half-bars — beats at positions 1 and 3 within each bar (2-beat grid)
    half_bars: Optional["TimingTrack"] = None

    # L3.5: Eighth notes — subdivided between beats (2× beat density)
    eighth_notes: Optional["TimingTrack"] = None

    # L4: Events (stem_name → onset track)
    events: dict[str, "TimingTrack"] = field(default_factory=dict)

    # Solos: stem_name → list of solo regions (TimingMark with duration_ms set)
    solos: dict[str, list["TimingMark"]] = field(default_factory=dict)

    # L5: Energy curves (stem_name → ValueCurve)
    energy_curves: dict[str, ValueCurve] = field(default_factory=dict)
    spectral_flux: Optional[ValueCurve] = None

    # L6: Harmony
    chords: Optional["TimingTrack"] = None
    key_changes: Optional["TimingTrack"] = None

    # Interactions
    interactions: Optional["InteractionResult"] = None

    # Metadata
    stems_available: list[str] = field(default_factory=list)
    capabilities: dict[str, bool] = field(default_factory=dict)
    algorithms_run: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validation: dict = field(default_factory=dict)

    def _mark_to_dict(self, m: TimingMark) -> dict:
        return {k: v for k, v in {
            "time_ms": m.time_ms,
            "confidence": m.confidence,
            "label": m.label,
            "duration_ms": m.duration_ms,
        }.items() if v is not None}

    def _mark_from_dict(self, d: dict) -> TimingMark:
        return TimingMark(
            time_ms=d["time_ms"],
            confidence=d.get("confidence"),
            label=d.get("label"),
            duration_ms=d.get("duration_ms"),
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "duration_ms": self.duration_ms,
            "estimated_bpm": self.estimated_bpm,
            "energy_impacts": [self._mark_to_dict(m) for m in self.energy_impacts],
            "energy_drops": [self._mark_to_dict(m) for m in self.energy_drops],
            "gaps": [self._mark_to_dict(m) for m in self.gaps],
            "sections": [self._mark_to_dict(m) for m in self.sections],
            "bars": self.bars.to_dict() if self.bars else None,
            "beats": self.beats.to_dict() if self.beats else None,
            "half_bars": self.half_bars.to_dict() if self.half_bars else None,
            "eighth_notes": self.eighth_notes.to_dict() if self.eighth_notes else None,
            "events": {k: v.to_dict() for k, v in self.events.items()},
            "solos": {k: [self._mark_to_dict(m) for m in v] for k, v in self.solos.items()},
            "energy_curves": {k: v.to_dict() for k, v in self.energy_curves.items()},
            "spectral_flux": self.spectral_flux.to_dict() if self.spectral_flux else None,
            "chords": self.chords.to_dict() if self.chords else None,
            "key_changes": self.key_changes.to_dict() if self.key_changes else None,
            "interactions": self.interactions.to_dict() if self.interactions else None,
            "stems_available": self.stems_available,
            "capabilities": self.capabilities,
            "algorithms_run": self.algorithms_run,
            "warnings": self.warnings,
            "validation": self.validation,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HierarchyResult":
        obj = cls(
            schema_version=d["schema_version"],
            source_file=d["source_file"],
            source_hash=d["source_hash"],
            duration_ms=d["duration_ms"],
            estimated_bpm=d["estimated_bpm"],
        )
        obj.energy_impacts = [
            TimingMark(time_ms=m["time_ms"], confidence=m.get("confidence"),
                       label=m.get("label"), duration_ms=m.get("duration_ms"))
            for m in d.get("energy_impacts", [])
        ]
        obj.energy_drops = [
            TimingMark(time_ms=m["time_ms"], confidence=m.get("confidence"),
                       label=m.get("label"), duration_ms=m.get("duration_ms"))
            for m in d.get("energy_drops", [])
        ]
        obj.gaps = [
            TimingMark(time_ms=m["time_ms"], confidence=m.get("confidence"),
                       label=m.get("label"), duration_ms=m.get("duration_ms"))
            for m in d.get("gaps", [])
        ]
        obj.sections = [
            TimingMark(time_ms=m["time_ms"], confidence=m.get("confidence"),
                       label=m.get("label"), duration_ms=m.get("duration_ms"))
            for m in d.get("sections", [])
        ]
        bars_data = d.get("bars")
        obj.bars = TimingTrack.from_dict(bars_data) if bars_data else None
        beats_data = d.get("beats")
        obj.beats = TimingTrack.from_dict(beats_data) if beats_data else None
        hb_data = d.get("half_bars")
        obj.half_bars = TimingTrack.from_dict(hb_data) if hb_data else None
        en_data = d.get("eighth_notes")
        obj.eighth_notes = TimingTrack.from_dict(en_data) if en_data else None
        obj.events = {k: TimingTrack.from_dict(v) for k, v in d.get("events", {}).items()}
        obj.solos = {
            k: [TimingMark(time_ms=m["time_ms"], confidence=m.get("confidence"),
                           label=m.get("label"), duration_ms=m.get("duration_ms"))
                for m in v]
            for k, v in d.get("solos", {}).items()
        }
        obj.energy_curves = {k: ValueCurve.from_dict(v) for k, v in d.get("energy_curves", {}).items()}
        sf_data = d.get("spectral_flux")
        obj.spectral_flux = ValueCurve.from_dict(sf_data) if sf_data else None
        chords_data = d.get("chords")
        obj.chords = TimingTrack.from_dict(chords_data) if chords_data else None
        key_data = d.get("key_changes")
        obj.key_changes = TimingTrack.from_dict(key_data) if key_data else None
        ir_data = d.get("interactions")
        obj.interactions = InteractionResult.from_dict(ir_data) if ir_data else None
        obj.stems_available = d.get("stems_available", [])
        obj.capabilities = d.get("capabilities", {})
        obj.algorithms_run = d.get("algorithms_run", [])
        obj.warnings = d.get("warnings", [])
        obj.validation = d.get("validation", {})
        return obj


# ── Stem selection ─────────────────────────────────────────────────────────────

@dataclass
class StemSelection:
    """User-confirmed stem selection after interactive review."""

    stems: dict[str, str]         # stem name → "keep" | "skip"
    overrides: list[str] = field(default_factory=list)   # stems where user overrode verdict
    fallback_to_mix: bool = False  # True when all stems ended up skipped

    @property
    def kept_stems(self) -> list[str]:
        return [name for name, verdict in self.stems.items() if verdict == "keep"]

    def to_dict(self) -> dict:
        return {
            "stems": self.stems,
            "overrides": self.overrides,
            "fallback_to_mix": self.fallback_to_mix,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StemSelection":
        return cls(
            stems=d["stems"],
            overrides=d.get("overrides", []),
            fallback_to_mix=d.get("fallback_to_mix", False),
        )


# ── Conditioned curve ──────────────────────────────────────────────────────────

@dataclass
class ConditionedCurve:
    """A feature curve after downsampling, smoothing, and 0-100 normalization."""

    name: str
    stem: str
    feature: str
    fps: int
    values: list[int]   # integers 0–100, one per frame
    is_flat: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "stem": self.stem,
            "feature": self.feature,
            "fps": self.fps,
            "values": self.values,
            "is_flat": self.is_flat,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConditionedCurve":
        return cls(
            name=d["name"],
            stem=d["stem"],
            feature=d["feature"],
            fps=d["fps"],
            values=d["values"],
            is_flat=d.get("is_flat", False),
        )


# ── Export manifest types ──────────────────────────────────────────────────────

@dataclass
class ValueCurveExport:
    """Metadata for one exported .xvc file."""

    file_path: str
    curve_name: str
    curve_type: str        # "macro" | "segment"
    start_ms: int
    end_ms: int
    point_count: int
    segment_label: Optional[str] = None

    def __post_init__(self) -> None:
        self.start_ms = int(self.start_ms)
        self.end_ms = int(self.end_ms)

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "curve_name": self.curve_name,
            "curve_type": self.curve_type,
            "segment_label": self.segment_label,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "point_count": self.point_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ValueCurveExport":
        return cls(
            file_path=d["file_path"],
            curve_name=d["curve_name"],
            curve_type=d["curve_type"],
            start_ms=d["start_ms"],
            end_ms=d["end_ms"],
            point_count=d["point_count"],
            segment_label=d.get("segment_label"),
        )


@dataclass
class TimingTrackExport:
    """Metadata for one exported .xtiming file."""

    file_path: str
    track_name: str
    source_stem: str
    element_type: str   # beat | onset | segment | handoff | leader_change
    mark_count: int

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "track_name": self.track_name,
            "source_stem": self.source_stem,
            "element_type": self.element_type,
            "mark_count": self.mark_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TimingTrackExport":
        return cls(
            file_path=d["file_path"],
            track_name=d["track_name"],
            source_stem=d["source_stem"],
            element_type=d["element_type"],
            mark_count=d["mark_count"],
        )


@dataclass
class ExportManifest:
    """Summary of all files exported for one song."""

    song_file: str
    export_dir: str
    exported_at: str
    stems_used: list[str]
    timing_tracks: list[TimingTrackExport] = field(default_factory=list)
    value_curves: list[ValueCurveExport] = field(default_factory=list)
    interactions_detected: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "song_file": self.song_file,
            "export_dir": self.export_dir,
            "exported_at": self.exported_at,
            "stems_used": self.stems_used,
            "timing_tracks": [t.to_dict() for t in self.timing_tracks],
            "value_curves": [v.to_dict() for v in self.value_curves],
            "interactions_detected": self.interactions_detected,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ExportManifest":
        return cls(
            song_file=d["song_file"],
            export_dir=d["export_dir"],
            exported_at=d["exported_at"],
            stems_used=d["stems_used"],
            timing_tracks=[TimingTrackExport.from_dict(t) for t in d.get("timing_tracks", [])],
            value_curves=[ValueCurveExport.from_dict(v) for v in d.get("value_curves", [])],
            interactions_detected=d.get("interactions_detected", {}),
            warnings=d.get("warnings", []),
        )


@dataclass
class AnalysisResult:
    """Complete output of a single analysis run."""

    schema_version: str
    source_file: str
    filename: str
    duration_ms: int
    sample_rate: int
    estimated_tempo_bpm: float
    run_timestamp: str
    algorithms: list[AnalysisAlgorithm]
    timing_tracks: list[TimingTrack]
    stem_separation: bool = False
    stem_cache: Optional[str] = None
    phoneme_result: Optional["PhonemeResult"] = None
    song_structure: Optional["SongStructure"] = None
    source_hash: Optional[str] = None
    interaction_result: Optional[InteractionResult] = None
    sweep_tracks: list[dict] = field(default_factory=list)
    pipeline_stats: Optional[dict] = None  # T038: wall_clock_ms, cpu_ms, parallelism_ratio, step_timings

    def to_dict(self) -> dict:
        d: dict = {
            "schema_version": self.schema_version,
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "filename": self.filename,
            "duration_ms": self.duration_ms,
            "sample_rate": self.sample_rate,
            "estimated_tempo_bpm": self.estimated_tempo_bpm,
            "run_timestamp": self.run_timestamp,
            "stem_separation": self.stem_separation,
            "stem_cache": self.stem_cache,
            "algorithms": [a.to_dict() for a in self.algorithms],
            "timing_tracks": [t.to_dict() for t in self.timing_tracks],
            "sweep_tracks": self.sweep_tracks,
            "phoneme_result": self.phoneme_result.to_dict() if self.phoneme_result else None,
            "song_structure": self.song_structure.to_dict() if self.song_structure else None,
            "interaction_result": self.interaction_result.to_dict() if self.interaction_result else None,
            "pipeline_stats": self.pipeline_stats,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AnalysisResult":
        from src.analyzer.phonemes import PhonemeResult as _PR
        from src.analyzer.structure import SongStructure as _SS
        pr_data = d.get("phoneme_result")
        ss_data = d.get("song_structure")
        ir_data = d.get("interaction_result")
        phoneme_result = _PR.from_dict(pr_data) if pr_data else None
        song_structure = _SS.from_dict(ss_data) if ss_data else None
        interaction_result = InteractionResult.from_dict(ir_data) if ir_data else None
        return cls(
            schema_version=d["schema_version"],
            source_file=d["source_file"],
            filename=d["filename"],
            duration_ms=d["duration_ms"],
            sample_rate=d["sample_rate"],
            estimated_tempo_bpm=d["estimated_tempo_bpm"],
            run_timestamp=d["run_timestamp"],
            algorithms=[AnalysisAlgorithm.from_dict(a) for a in d.get("algorithms", [])],
            timing_tracks=[TimingTrack.from_dict(t) for t in d.get("timing_tracks", [])],
            stem_separation=d.get("stem_separation", False),
            stem_cache=d.get("stem_cache", None),
            phoneme_result=phoneme_result,
            song_structure=song_structure,
            source_hash=d.get("source_hash"),
            interaction_result=interaction_result,
            sweep_tracks=d.get("sweep_tracks", []),
            pipeline_stats=d.get("pipeline_stats"),
        )
