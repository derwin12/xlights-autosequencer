"""Song structure analysis using All-in-One (allin1)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StructureSegment:
    """A single labeled section of a song (intro, verse, chorus, etc.)."""

    label: str       # e.g. "intro", "verse", "chorus", "bridge", "outro"
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        self.start_ms = int(self.start_ms)
        self.end_ms = int(self.end_ms)

    def to_dict(self) -> dict:
        return {"label": self.label, "start_ms": self.start_ms, "end_ms": self.end_ms}

    @classmethod
    def from_dict(cls, d: dict) -> "StructureSegment":
        return cls(label=d["label"], start_ms=d["start_ms"], end_ms=d["end_ms"])


@dataclass
class SongStructure:
    """Complete structural segmentation result for one audio file."""

    segments: list[StructureSegment] = field(default_factory=list)
    source: str = "allin1"

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "segments": [s.to_dict() for s in self.segments],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SongStructure":
        return cls(
            segments=[StructureSegment.from_dict(s) for s in d.get("segments", [])],
            source=d.get("source", "allin1"),
        )


class StructureAnalyzer:
    """
    Detect song structure (intro/verse/chorus/bridge/outro) using All-in-One.

    All-in-One is a transformer-based model trained on pop/rock music that
    returns semantic segment labels with timestamps.

    Requires: pip install allin1
    First run downloads the model (~200 MB) to ~/.cache/allin1/.
    """

    def analyze(self, audio_path: str) -> SongStructure:
        """
        Analyze song structure from an audio file.

        Raises RuntimeError if allin1 is not installed.
        Returns a SongStructure with an empty segments list if no structure detected.
        """
        try:
            import allin1
        except ImportError:
            raise RuntimeError(
                "allin1 is required for structure analysis. "
                "Install it with: pip install allin1"
            )

        result = allin1.analyze(audio_path)

        segments = [
            StructureSegment(
                label=seg.label,
                start_ms=int(round(seg.start * 1000)),
                end_ms=int(round(seg.end * 1000)),
            )
            for seg in result.segments
        ]

        return SongStructure(segments=segments, source="allin1")
