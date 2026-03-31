"""Data classes for the Song Story module.

All entities are plain dataclasses serializable to/from dict. These are the
canonical Python representations of the song story JSON schema (v1.0.0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Sub-entities ──────────────────────────────────────────────────────────────

@dataclass
class BandEnergy:
    """Energy in a single frequency band within a section."""
    mean: float          # Average energy in this band
    relative: float      # Energy relative to overall section energy (0-1)

    def to_dict(self) -> dict:
        return {"mean": round(self.mean, 4), "relative": round(self.relative, 4)}

    @classmethod
    def from_dict(cls, d: dict) -> "BandEnergy":
        return cls(mean=d["mean"], relative=d["relative"])


@dataclass
class LeaderTransition:
    """A moment where the dominant stem changes within a section."""
    time: float          # Timestamp in seconds
    from_stem: str       # Previous dominant stem
    to_stem: str         # New dominant stem

    def to_dict(self) -> dict:
        return {"time": self.time, "from_stem": self.from_stem, "to_stem": self.to_stem}

    @classmethod
    def from_dict(cls, d: dict) -> "LeaderTransition":
        return cls(time=d["time"], from_stem=d["from_stem"], to_stem=d["to_stem"])


@dataclass
class SoloRegion:
    """A solo region where one stem dominates."""
    stem: str            # Which stem is soloing
    start: float         # Solo start time in seconds
    end: float           # Solo end time in seconds
    prominence: float    # 0-1, how dominant the stem was during the solo

    def to_dict(self) -> dict:
        return {
            "stem": self.stem,
            "start": self.start,
            "end": self.end,
            "prominence": round(self.prominence, 4),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SoloRegion":
        return cls(stem=d["stem"], start=d["start"], end=d["end"], prominence=d["prominence"])


@dataclass
class DrumPattern:
    """Kick/snare/hihat onset summary for a section."""
    kick_count: int          # Number of kick drum onsets
    snare_count: int         # Number of snare onsets
    hihat_count: int         # Number of hihat onsets
    total_density: float     # Total drum onsets per second
    dominant_element: str    # "kick", "snare", or "hihat"
    style: str               # "driving", "fills", "riding", "sparse", "balanced"

    def to_dict(self) -> dict:
        return {
            "kick_count": self.kick_count,
            "snare_count": self.snare_count,
            "hihat_count": self.hihat_count,
            "total_density": round(self.total_density, 4),
            "dominant_element": self.dominant_element,
            "style": self.style,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DrumPattern":
        return cls(
            kick_count=d["kick_count"],
            snare_count=d["snare_count"],
            hihat_count=d["hihat_count"],
            total_density=d["total_density"],
            dominant_element=d["dominant_element"],
            style=d["style"],
        )


@dataclass
class HandoffEvent:
    """A melodic stem handoff event (one stem passes melodic role to another)."""
    time: float          # Handoff midpoint in seconds
    from_stem: str       # Stem that drops out
    to_stem: str         # Stem that enters
    confidence: float    # 0-1, 1.0 = seamless, 0.0 = large gap

    def to_dict(self) -> dict:
        return {
            "time": self.time,
            "from_stem": self.from_stem,
            "to_stem": self.to_stem,
            "confidence": round(self.confidence, 4),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HandoffEvent":
        return cls(
            time=d["time"],
            from_stem=d["from_stem"],
            to_stem=d["to_stem"],
            confidence=d["confidence"],
        )


@dataclass
class ChordChange:
    """A chord change event within a section."""
    time: float      # Timestamp in seconds
    chord: str       # Chord label (e.g., "Cmaj7", "Am", "F#dim")

    def to_dict(self) -> dict:
        return {"time": self.time, "chord": self.chord}

    @classmethod
    def from_dict(cls, d: dict) -> "ChordChange":
        return cls(time=d["time"], chord=d["chord"])


# ── Section sub-entities ───────────────────────────────────────────────────────

@dataclass
class SectionCharacter:
    """Energy, texture, and spectral properties of a section."""
    energy_level: str                              # "low", "medium", "high"
    energy_score: int                              # 0-100 normalized energy
    energy_peak: int                               # 0-100 peak energy within section
    energy_variance: float                         # Energy variance (dynamic vs sustained)
    energy_trajectory: str                         # "rising", "falling", "stable", "oscillating"
    texture: str                                   # "harmonic", "percussive", "balanced"
    hp_ratio: float                                # Harmonic/percussive ratio
    onset_density: float                           # Full-mix onsets per second
    spectral_brightness: str                       # "dark", "neutral", "bright"
    spectral_centroid_hz: int                      # Average spectral centroid in Hz
    spectral_flatness: float                       # 0-1 (0=tonal, 1=noisy)
    local_tempo_bpm: float                         # Local tempo from beats within section
    dominant_note: str                             # Most energetic pitch class (e.g., "F#")
    frequency_bands: dict[str, BandEnergy] = field(default_factory=dict)
    # Bands: sub_bass, bass, low_mid, mid, upper_mid, presence, brilliance

    def to_dict(self) -> dict:
        return {
            "energy_level": self.energy_level,
            "energy_score": self.energy_score,
            "energy_peak": self.energy_peak,
            "energy_variance": round(self.energy_variance, 4),
            "energy_trajectory": self.energy_trajectory,
            "texture": self.texture,
            "hp_ratio": round(self.hp_ratio, 4),
            "onset_density": round(self.onset_density, 4),
            "spectral_brightness": self.spectral_brightness,
            "spectral_centroid_hz": self.spectral_centroid_hz,
            "spectral_flatness": round(self.spectral_flatness, 4),
            "local_tempo_bpm": round(self.local_tempo_bpm, 2),
            "dominant_note": self.dominant_note,
            "frequency_bands": {k: v.to_dict() for k, v in self.frequency_bands.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SectionCharacter":
        return cls(
            energy_level=d["energy_level"],
            energy_score=d["energy_score"],
            energy_peak=d["energy_peak"],
            energy_variance=d["energy_variance"],
            energy_trajectory=d["energy_trajectory"],
            texture=d["texture"],
            hp_ratio=d["hp_ratio"],
            onset_density=d["onset_density"],
            spectral_brightness=d["spectral_brightness"],
            spectral_centroid_hz=d["spectral_centroid_hz"],
            spectral_flatness=d["spectral_flatness"],
            local_tempo_bpm=d["local_tempo_bpm"],
            dominant_note=d["dominant_note"],
            frequency_bands={k: BandEnergy.from_dict(v) for k, v in d.get("frequency_bands", {}).items()},
        )


@dataclass
class SectionStems:
    """Per-stem activity data for a section."""
    vocals_active: bool
    dominant_stem: str
    active_stems: list[str] = field(default_factory=list)
    stem_levels: dict[str, float] = field(default_factory=dict)      # 0-1 per stem
    onset_counts: dict[str, int] = field(default_factory=dict)       # per stem
    leader_stem: str = ""
    leader_transitions: list[LeaderTransition] = field(default_factory=list)
    solos: list[SoloRegion] = field(default_factory=list)
    drum_pattern: Optional[DrumPattern] = None
    tightness: Optional[str] = None                                   # "unison", "independent", "mixed"
    handoffs: list[HandoffEvent] = field(default_factory=list)
    chords: list[ChordChange] = field(default_factory=list)
    other_stem_class: Optional[str] = None                           # "spatial", "timing", "ambiguous"

    def to_dict(self) -> dict:
        return {
            "vocals_active": self.vocals_active,
            "dominant_stem": self.dominant_stem,
            "active_stems": self.active_stems,
            "stem_levels": {k: round(v, 4) for k, v in self.stem_levels.items()},
            "onset_counts": self.onset_counts,
            "leader_stem": self.leader_stem,
            "leader_transitions": [t.to_dict() for t in self.leader_transitions],
            "solos": [s.to_dict() for s in self.solos],
            "drum_pattern": self.drum_pattern.to_dict() if self.drum_pattern else None,
            "tightness": self.tightness,
            "handoffs": [h.to_dict() for h in self.handoffs],
            "chords": [c.to_dict() for c in self.chords],
            "other_stem_class": self.other_stem_class,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SectionStems":
        return cls(
            vocals_active=d["vocals_active"],
            dominant_stem=d["dominant_stem"],
            active_stems=d.get("active_stems", []),
            stem_levels=d.get("stem_levels", {}),
            onset_counts=d.get("onset_counts", {}),
            leader_stem=d.get("leader_stem", ""),
            leader_transitions=[LeaderTransition.from_dict(t) for t in d.get("leader_transitions", [])],
            solos=[SoloRegion.from_dict(s) for s in d.get("solos", [])],
            drum_pattern=DrumPattern.from_dict(d["drum_pattern"]) if d.get("drum_pattern") else None,
            tightness=d.get("tightness"),
            handoffs=[HandoffEvent.from_dict(h) for h in d.get("handoffs", [])],
            chords=[ChordChange.from_dict(c) for c in d.get("chords", [])],
            other_stem_class=d.get("other_stem_class"),
        )


@dataclass
class SectionLighting:
    """Recommended lighting parameters for a section."""
    active_tiers: list[int] = field(default_factory=list)        # Which tiers (1-8)
    brightness_ceiling: float = 1.0                               # 0-1 max brightness
    theme_layer_mode: str = "base_only"                           # base_only, base_mid, full, variant
    use_secondary_theme: bool = False
    transition_in: str = "hard_cut"                               # hard_cut, quick_fade, crossfade, snap_on, quick_build
    moment_count: int = 0
    moment_pattern: str = "isolated"                              # isolated, plateau, cascade, scattered
    beat_effect_density: float = 0.5                              # 0-1

    def to_dict(self) -> dict:
        return {
            "active_tiers": self.active_tiers,
            "brightness_ceiling": round(self.brightness_ceiling, 4),
            "theme_layer_mode": self.theme_layer_mode,
            "use_secondary_theme": self.use_secondary_theme,
            "transition_in": self.transition_in,
            "moment_count": self.moment_count,
            "moment_pattern": self.moment_pattern,
            "beat_effect_density": round(self.beat_effect_density, 4),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SectionLighting":
        return cls(
            active_tiers=d.get("active_tiers", []),
            brightness_ceiling=d.get("brightness_ceiling", 1.0),
            theme_layer_mode=d.get("theme_layer_mode", "base_only"),
            use_secondary_theme=d.get("use_secondary_theme", False),
            transition_in=d.get("transition_in", "hard_cut"),
            moment_count=d.get("moment_count", 0),
            moment_pattern=d.get("moment_pattern", "isolated"),
            beat_effect_density=d.get("beat_effect_density", 0.5),
        )


@dataclass
class SectionOverrides:
    """User review overrides for a section. All fields null = use auto-classified values."""
    role: Optional[str] = None
    energy_level: Optional[str] = None
    mood: Optional[str] = None                    # "ethereal", "structural", "aggressive", "dark"
    theme: Optional[str] = None                   # One of 21 built-in themes or custom
    focus_stem: Optional[str] = None              # "drums", "bass", "vocals", "guitar", "piano", "other"
    intensity: Optional[float] = None             # 0.0-2.0 multiplier
    notes: Optional[str] = None
    is_highlight: bool = False

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "energy_level": self.energy_level,
            "mood": self.mood,
            "theme": self.theme,
            "focus_stem": self.focus_stem,
            "intensity": self.intensity,
            "notes": self.notes,
            "is_highlight": self.is_highlight,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SectionOverrides":
        return cls(
            role=d.get("role"),
            energy_level=d.get("energy_level"),
            mood=d.get("mood"),
            theme=d.get("theme"),
            focus_stem=d.get("focus_stem"),
            intensity=d.get("intensity"),
            notes=d.get("notes"),
            is_highlight=d.get("is_highlight", False),
        )


# ── Top-level entities ─────────────────────────────────────────────────────────

@dataclass
class SongIdentity:
    """Audio file identity and metadata."""
    title: str
    artist: str
    file: str
    source_hash: str
    duration_seconds: float
    duration_formatted: str    # "MM:SS.mmm"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "artist": self.artist,
            "file": self.file,
            "source_hash": self.source_hash,
            "duration_seconds": round(self.duration_seconds, 3),
            "duration_formatted": self.duration_formatted,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SongIdentity":
        return cls(
            title=d["title"],
            artist=d["artist"],
            file=d["file"],
            source_hash=d["source_hash"],
            duration_seconds=d["duration_seconds"],
            duration_formatted=d["duration_formatted"],
        )


@dataclass
class GlobalProperties:
    """Song-wide musical properties."""
    tempo_bpm: float
    tempo_stability: str          # "steady", "variable", "free"
    key: str                      # e.g., "C major"
    key_confidence: float         # 0-1
    energy_arc: str               # ramp, arch, flat, valley, sawtooth, bookend
    vocal_coverage: float         # 0-1 fraction with active vocals
    harmonic_percussive_ratio: float
    onset_density_avg: float      # onsets per second, song-wide
    stems_available: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tempo_bpm": round(self.tempo_bpm, 2),
            "tempo_stability": self.tempo_stability,
            "key": self.key,
            "key_confidence": round(self.key_confidence, 4),
            "energy_arc": self.energy_arc,
            "vocal_coverage": round(self.vocal_coverage, 4),
            "harmonic_percussive_ratio": round(self.harmonic_percussive_ratio, 4),
            "onset_density_avg": round(self.onset_density_avg, 4),
            "stems_available": self.stems_available,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GlobalProperties":
        return cls(
            tempo_bpm=d["tempo_bpm"],
            tempo_stability=d["tempo_stability"],
            key=d["key"],
            key_confidence=d["key_confidence"],
            energy_arc=d["energy_arc"],
            vocal_coverage=d["vocal_coverage"],
            harmonic_percussive_ratio=d["harmonic_percussive_ratio"],
            onset_density_avg=d["onset_density_avg"],
            stems_available=d.get("stems_available", []),
        )


@dataclass
class Preferences:
    """Song-wide creative direction set by user during review."""
    mood: Optional[str] = None          # "ethereal", "structural", "aggressive", "dark"
    theme: Optional[str] = None         # Force one theme for whole song
    focus_stem: Optional[str] = None    # "drums", "bass", "vocals", "guitar", "piano", "other"
    intensity: float = 1.0              # 0.0-2.0 scaler (default 1.0)
    occasion: str = "general"           # "general", "christmas", "halloween"
    genre: Optional[str] = None         # Genre hint; null = auto from ID3

    def to_dict(self) -> dict:
        return {
            "mood": self.mood,
            "theme": self.theme,
            "focus_stem": self.focus_stem,
            "intensity": round(self.intensity, 4),
            "occasion": self.occasion,
            "genre": self.genre,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Preferences":
        return cls(
            mood=d.get("mood"),
            theme=d.get("theme"),
            focus_stem=d.get("focus_stem"),
            intensity=d.get("intensity", 1.0),
            occasion=d.get("occasion", "general"),
            genre=d.get("genre"),
        )


@dataclass
class Section:
    """A song section with classified role, timing, and enriched profile."""
    id: str                        # Stable ID, e.g., "s01"
    role: str                      # intro, verse, pre_chorus, chorus, post_chorus, bridge,
                                   # instrumental_break, climax, ambient_bridge, outro, interlude
    role_confidence: float         # 0-1 classifier confidence
    start: float                   # Start time in seconds
    end: float                     # End time in seconds
    start_fmt: str                 # "MM:SS.mmm"
    end_fmt: str                   # "MM:SS.mmm"
    duration: float                # Duration in seconds
    character: SectionCharacter
    stems: SectionStems
    lighting: SectionLighting
    overrides: SectionOverrides = field(default_factory=SectionOverrides)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "role_confidence": round(self.role_confidence, 4),
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "start_fmt": self.start_fmt,
            "end_fmt": self.end_fmt,
            "duration": round(self.duration, 3),
            "character": self.character.to_dict(),
            "stems": self.stems.to_dict(),
            "lighting": self.lighting.to_dict(),
            "overrides": self.overrides.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Section":
        return cls(
            id=d["id"],
            role=d["role"],
            role_confidence=d["role_confidence"],
            start=d["start"],
            end=d["end"],
            start_fmt=d["start_fmt"],
            end_fmt=d["end_fmt"],
            duration=d["duration"],
            character=SectionCharacter.from_dict(d["character"]),
            stems=SectionStems.from_dict(d["stems"]),
            lighting=SectionLighting.from_dict(d["lighting"]),
            overrides=SectionOverrides.from_dict(d.get("overrides", {})),
        )


@dataclass
class Moment:
    """A ranked dramatic moment in the song."""
    id: str                  # Stable ID, e.g., "m001"
    time: float              # Timestamp in seconds
    time_fmt: str            # "MM:SS.mmm"
    section_id: str          # Which section this belongs to
    type: str                # energy_surge, energy_drop, percussive_impact, brightness_spike,
                             # tempo_change, silence, vocal_entry, vocal_exit, texture_shift, handoff
    stem: str                # Source stem or "full_mix"
    intensity: float         # Raw intensity value
    description: str         # Human-readable description
    pattern: str             # isolated, plateau, cascade, double_tap, scattered
    rank: int                # Importance rank (1 = most important)
    dismissed: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "time": round(self.time, 3),
            "time_fmt": self.time_fmt,
            "section_id": self.section_id,
            "type": self.type,
            "stem": self.stem,
            "intensity": round(self.intensity, 4),
            "description": self.description,
            "pattern": self.pattern,
            "rank": self.rank,
            "dismissed": self.dismissed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Moment":
        return cls(
            id=d["id"],
            time=d["time"],
            time_fmt=d["time_fmt"],
            section_id=d["section_id"],
            type=d["type"],
            stem=d["stem"],
            intensity=d["intensity"],
            description=d["description"],
            pattern=d["pattern"],
            rank=d["rank"],
            dismissed=d.get("dismissed", False),
        )


@dataclass
class StemCurves:
    """Continuous per-stem data sampled at 2Hz for value curve binding."""
    sample_rate_hz: int = 2
    drums: dict = field(default_factory=lambda: {"rms": []})
    bass: dict = field(default_factory=lambda: {"rms": []})
    vocals: dict = field(default_factory=lambda: {"rms": []})
    guitar: dict = field(default_factory=lambda: {"rms": []})
    piano: dict = field(default_factory=lambda: {"rms": []})
    other: dict = field(default_factory=lambda: {"rms": []})
    full_mix: dict = field(default_factory=lambda: {
        "rms": [], "spectral_centroid_hz": [], "harmonic_rms": [], "percussive_rms": []
    })

    def to_dict(self) -> dict:
        return {
            "sample_rate_hz": self.sample_rate_hz,
            "drums": self.drums,
            "bass": self.bass,
            "vocals": self.vocals,
            "guitar": self.guitar,
            "piano": self.piano,
            "other": self.other,
            "full_mix": self.full_mix,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StemCurves":
        return cls(
            sample_rate_hz=d.get("sample_rate_hz", 2),
            drums=d.get("drums", {"rms": []}),
            bass=d.get("bass", {"rms": []}),
            vocals=d.get("vocals", {"rms": []}),
            guitar=d.get("guitar", {"rms": []}),
            piano=d.get("piano", {"rms": []}),
            other=d.get("other", {"rms": []}),
            full_mix=d.get("full_mix", {"rms": [], "spectral_centroid_hz": [], "harmonic_rms": [], "percussive_rms": []}),
        )


@dataclass
class ReviewState:
    """Review progress state."""
    status: str = "draft"             # "draft" or "reviewed"
    reviewed_at: Optional[str] = None # ISO timestamp
    reviewer_notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reviewed_at": self.reviewed_at,
            "reviewer_notes": self.reviewer_notes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewState":
        return cls(
            status=d.get("status", "draft"),
            reviewed_at=d.get("reviewed_at"),
            reviewer_notes=d.get("reviewer_notes"),
        )


@dataclass
class SongStory:
    """Top-level container for the complete song interpretation."""
    schema_version: str
    song: SongIdentity
    global_props: GlobalProperties    # serialized as "global" (reserved word in Python)
    preferences: Preferences
    sections: list[Section] = field(default_factory=list)
    moments: list[Moment] = field(default_factory=list)
    stems: StemCurves = field(default_factory=StemCurves)
    review: ReviewState = field(default_factory=ReviewState)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "song": self.song.to_dict(),
            "global": self.global_props.to_dict(),
            "preferences": self.preferences.to_dict(),
            "sections": [s.to_dict() for s in self.sections],
            "moments": [m.to_dict() for m in self.moments],
            "stems": self.stems.to_dict(),
            "review": self.review.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SongStory":
        return cls(
            schema_version=d["schema_version"],
            song=SongIdentity.from_dict(d["song"]),
            global_props=GlobalProperties.from_dict(d["global"]),
            preferences=Preferences.from_dict(d.get("preferences", {})),
            sections=[Section.from_dict(s) for s in d.get("sections", [])],
            moments=[Moment.from_dict(m) for m in d.get("moments", [])],
            stems=StemCurves.from_dict(d.get("stems", {})),
            review=ReviewState.from_dict(d.get("review", {})),
        )
