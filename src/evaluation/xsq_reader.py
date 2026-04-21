"""Parser for xLights .xsq and .xsqz sequence files."""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from src.evaluation.models import Placement, SequenceSummary

# ZIP magic bytes — first two bytes of every ZIP/xsqz file
_ZIP_MAGIC = b"PK"

# Ordered token → prop-type mappings (order matters: longer/more specific first)
_PROP_TYPE_TOKENS: list[tuple[str, str]] = [
    ("snowflake", "snowflake"),
    ("outline", "outline"),
    ("candy", "candy"),
    ("matrix", "matrix"),
    ("arch", "arch"),
    ("tree", "tree"),
    ("star", "star"),
    ("deer", "deer"),
    ("house", "house"),
    ("mega", "mega"),
]

# Regex to extract effect name from EffectDB settings strings (fallback for old format)
_EFFECT_NAME_RE = re.compile(r"E_NOTEBOOK_(\w[\w ]*?)=")

# Regex to find active palette slot indices: C_CHECKBOX_PaletteN=1
_PALETTE_CHECKBOX_RE = re.compile(r"C_CHECKBOX_Palette(\d+)=1")
# Regex to find palette colors: C_BUTTON_PaletteN=#RRGGBB
_PALETTE_COLOR_RE = re.compile(r"C_BUTTON_Palette(\d+)=(#[0-9A-Fa-f]{6})")


def _parse_palette_text(text: str) -> tuple[str, ...]:
    """Parse a ColorPalette text string into active hex color strings.

    Format: comma-separated key=value pairs where:
      C_BUTTON_PaletteN=#RRGGBB  — defines the color in slot N
      C_CHECKBOX_PaletteN=1      — marks slot N as active/enabled

    Returns only the colors for active (checked) slots, in slot order.
    """
    # Find which slot numbers are active
    active_slots = {int(m.group(1)) for m in _PALETTE_CHECKBOX_RE.finditer(text)}
    if not active_slots:
        # No checkboxes at all — return all defined colors (old fixture format)
        colors = {}
        for m in _PALETTE_COLOR_RE.finditer(text):
            colors[int(m.group(1))] = m.group(2).upper()
        return tuple(colors[k] for k in sorted(colors))

    # Collect colors for active slots only
    colors: dict[int, str] = {}
    for m in _PALETTE_COLOR_RE.finditer(text):
        slot = int(m.group(1))
        if slot in active_slots:
            colors[slot] = m.group(2).upper()

    return tuple(colors[k] for k in sorted(colors))


def _infer_prop_type(model_name: str) -> str:
    lower = model_name.lower()
    for token, prop_type in _PROP_TYPE_TOKENS:
        if token in lower:
            return prop_type
    return "Unknown"


def _parse_xml(xml_bytes: bytes, song_id: str, source_label: str) -> SequenceSummary:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError(f"Malformed XSQ XML: {exc}") from exc

    # --- duration ---
    head = root.find("head")
    duration_ms = 0
    if head is not None:
        dur_el = head.find("sequenceDuration")
        if dur_el is not None and dur_el.text:
            # sequenceDuration is stored in seconds (float); convert to ms
            duration_ms = round(float(dur_el.text) * 1000)

    # --- palette lookup ---
    # ColorPalette elements have no child elements; colors are in text content as:
    #   C_BUTTON_Palette1=#RRGGBB,...,C_CHECKBOX_Palette3=1,...
    # Only slots with C_CHECKBOX_PaletteN=1 are "active" (lit) colors.
    palettes: list[tuple[str, ...]] = []
    color_palettes_el = root.find("ColorPalettes")
    if color_palettes_el is not None:
        for cp in color_palettes_el.findall("ColorPalette"):
            palettes.append(_parse_palette_text(cp.text or ""))

    # --- placements ---
    # Effect type is the `name` attribute on each placement <Effect> element.
    # The EffectDB `ref` index is used for settings lookup but the name is
    # already on the placement itself — no EffectDB traversal needed for type.
    placements: list[Placement] = []
    model_names_seen: list[str] = []

    element_effects_el = root.find("ElementEffects")
    if element_effects_el is not None:
        for element_el in element_effects_el.findall("Element"):
            if element_el.get("type") != "model":
                continue
            model_name = element_el.get("name", "")
            if model_name not in model_names_seen:
                model_names_seen.append(model_name)

            for layer_index, layer_el in enumerate(element_el.findall("EffectLayer")):
                for eff_el in layer_el.findall("Effect"):
                    start_ms = int(eff_el.get("startTime", "0"))
                    end_ms = int(eff_el.get("endTime", "0"))
                    palette_idx = int(eff_el.get("palette", "-1") or "-1")

                    # Effect name is directly on the placement element
                    effect_type = eff_el.get("name", "Unknown") or "Unknown"

                    palette_colors: tuple[str, ...] = (
                        palettes[palette_idx]
                        if 0 <= palette_idx < len(palettes)
                        else ()
                    )

                    if start_ms < end_ms:
                        placements.append(
                            Placement(
                                start_ms=start_ms,
                                end_ms=end_ms,
                                effect_type=effect_type,
                                model_name=model_name,
                                palette_colors=palette_colors,
                                layer_index=layer_index,
                            )
                        )

    model_names = tuple(model_names_seen)
    inferred_prop_types = {name: _infer_prop_type(name) for name in model_names}

    return SequenceSummary(
        song_id=song_id,
        source_label=source_label,
        duration_ms=duration_ms,
        placements=tuple(placements),
        model_names=model_names,
        inferred_prop_types=inferred_prop_types,
    )


def parse_bytes(
    data: bytes,
    filename: str = "sequence.xsq",
    song_id: str = "",
    source_label: str = "ours",
) -> SequenceSummary:
    """Parse .xsq bytes or .xsqz (zip) bytes into a SequenceSummary."""
    if data[:2] == _ZIP_MAGIC:
        # It's a zip archive — find the inner .xsq member
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xsq_name = next(
                (name for name in zf.namelist() if name.endswith(".xsq")),
                None,
            )
            if xsq_name is None:
                raise ValueError(f"No .xsq member found inside {filename!r}")
            xml_bytes = zf.read(xsq_name)
    else:
        xml_bytes = data

    return _parse_xml(xml_bytes, song_id=song_id, source_label=source_label)


def parse(
    path: Path | str,
    song_id: str = "",
    source_label: str = "ours",
) -> SequenceSummary:
    """Parse a .xsq or .xsqz file from disk into a SequenceSummary."""
    path = Path(path)
    data = path.read_bytes()
    return parse_bytes(data, filename=path.name, song_id=song_id, source_label=source_label)
