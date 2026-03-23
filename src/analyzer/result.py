"""T008: Core data classes for the analysis pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.analyzer.phonemes import PhonemeResult


@dataclass
class TimingMark:
    """A single timing event within a track."""

    time_ms: int
    confidence: Optional[float]

    def __post_init__(self) -> None:
        self.time_ms = int(self.time_ms)


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
        return {
            "name": self.name,
            "algorithm_name": self.algorithm_name,
            "element_type": self.element_type,
            "mark_count": self.mark_count,
            "avg_interval_ms": self.avg_interval_ms,
            "quality_score": round(self.quality_score, 4),
            "stem_source": self.stem_source,
            "marks": [
                {"time_ms": m.time_ms, "confidence": m.confidence}
                for m in self.marks
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TimingTrack":
        marks = [
            TimingMark(time_ms=m["time_ms"], confidence=m.get("confidence"))
            for m in d.get("marks", [])
        ]
        return cls(
            name=d["name"],
            algorithm_name=d["algorithm_name"],
            element_type=d["element_type"],
            marks=marks,
            quality_score=d.get("quality_score", 0.0),
            stem_source=d.get("stem_source", "full_mix"),
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
    source_hash: Optional[str] = None

    def to_dict(self) -> dict:
        from src.analyzer.phonemes import PhonemeResult as _PR
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
            "phoneme_result": self.phoneme_result.to_dict() if self.phoneme_result else None,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AnalysisResult":
        from src.analyzer.phonemes import PhonemeResult as _PR
        pr_data = d.get("phoneme_result")
        phoneme_result = _PR.from_dict(pr_data) if pr_data else None
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
            source_hash=d.get("source_hash"),
        )
