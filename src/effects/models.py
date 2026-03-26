"""Data models for the xLights effect library."""
from __future__ import annotations

from dataclasses import dataclass, field

# All 56 known xLights effects (from EffectManager.h enum RGB_EFFECTS_e)
ALL_XLIGHTS_EFFECTS: list[str] = [
    "Off", "On", "Adjust",
    "Color Wash", "Fill", "Shimmer", "Strobe", "Twinkle",
    "Bars", "Butterfly", "Circles", "Curtain", "Fan", "Galaxy",
    "Garlands", "Kaleidoscope", "Lines", "Marquee", "Pinwheel",
    "Plasma", "Ripple", "Shape", "Shockwave", "Spirals",
    "Spirograph", "Wave",
    "Candle", "Fire", "Fireworks", "Life", "Lightning", "Liquid",
    "Meteors", "Snowflakes", "Snow Storm", "Tree",
    "Single Strand", "Morph", "Warp",
    "Tendril", "Sketch",
    "Music", "Piano", "Guitar", "VU Meter",
    "Text", "Pictures", "Video", "Shader", "Glediator",
    "Faces", "State", "Duplicate",
    "DMX", "Servo", "Moving Head",
]

PROP_TYPES: list[str] = ["matrix", "outline", "arch", "vertical", "tree", "radial"]
SUITABILITY_RATINGS: list[str] = ["ideal", "good", "possible", "not_recommended"]
VALID_WIDGET_TYPES: list[str] = ["slider", "checkbox", "choice", "textctrl", "filepicker"]
VALID_VALUE_TYPES: list[str] = ["int", "float", "bool", "choice", "string"]
VALID_ANALYSIS_LEVELS: list[str] = ["L0", "L1", "L2", "L3", "L4", "L5", "L6"]
VALID_MAPPING_TYPES: list[str] = ["direct", "inverted", "threshold_trigger"]
VALID_CATEGORIES: list[str] = [
    "color_wash", "pattern", "nature", "movement",
    "audio_reactive", "media", "utility",
]
VALID_LAYER_ROLES: list[str] = ["standalone", "modifier", "either"]
VALID_DURATION_TYPES: list[str] = ["section", "bar", "beat", "trigger"]
VALID_CURVE_SHAPES: list[str] = ["linear", "logarithmic", "exponential", "step"]


@dataclass
class EffectParameter:
    name: str
    storage_name: str
    widget_type: str
    value_type: str
    default: int | float | bool | str
    description: str
    min: int | float | None = None
    max: int | float | None = None
    choices: list[str] | None = None
    supports_value_curve: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> EffectParameter:
        return cls(
            name=data["name"],
            storage_name=data["storage_name"],
            widget_type=data["widget_type"],
            value_type=data["value_type"],
            default=data["default"],
            description=data["description"],
            min=data.get("min"),
            max=data.get("max"),
            choices=data.get("choices"),
            supports_value_curve=data.get("supports_value_curve", False),
        )


@dataclass
class AnalysisMapping:
    parameter: str
    analysis_level: str
    analysis_field: str
    mapping_type: str
    description: str
    # Mapping mechanics — how to convert analysis values to parameter values
    input_min: float = 0.0      # analysis field range low end
    input_max: float = 100.0    # analysis field range high end
    output_min: float | None = None  # parameter range low end (None = use param min)
    output_max: float | None = None  # parameter range high end (None = use param max)
    curve_shape: str = "linear"  # linear, logarithmic, exponential, step
    # For threshold_trigger: the threshold value in analysis-field units
    threshold: float | None = None

    @classmethod
    def from_dict(cls, data: dict) -> AnalysisMapping:
        return cls(
            parameter=data["parameter"],
            analysis_level=data["analysis_level"],
            analysis_field=data["analysis_field"],
            mapping_type=data["mapping_type"],
            description=data["description"],
            input_min=data.get("input_min", 0.0),
            input_max=data.get("input_max", 100.0),
            output_min=data.get("output_min"),
            output_max=data.get("output_max"),
            curve_shape=data.get("curve_shape", "linear"),
            threshold=data.get("threshold"),
        )


@dataclass
class EffectDefinition:
    name: str
    xlights_id: str
    category: str
    description: str
    intent: str
    parameters: list[EffectParameter]
    prop_suitability: dict[str, str]
    analysis_mappings: list[AnalysisMapping] = field(default_factory=list)
    layer_role: str = "standalone"  # standalone, modifier, or either
    duration_type: str = "section"  # section, bar, beat, or trigger

    @classmethod
    def from_dict(cls, data: dict) -> EffectDefinition:
        return cls(
            name=data["name"],
            xlights_id=data.get("xlights_id", ""),
            category=data["category"],
            description=data["description"],
            intent=data["intent"],
            parameters=[EffectParameter.from_dict(p) for p in data["parameters"]],
            prop_suitability=data["prop_suitability"],
            analysis_mappings=[
                AnalysisMapping.from_dict(m)
                for m in data.get("analysis_mappings", [])
            ],
            layer_role=data.get("layer_role", "standalone"),
            duration_type=data.get("duration_type", "section"),
        )


@dataclass
class CoverageResult:
    cataloged: list[str]
    uncatalogued: list[str]
    total_xlights: int
