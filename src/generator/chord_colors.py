"""Chord-to-color mapping and harmonic tension analysis.

Maps chordino chord labels to colors via the circle of fifths (12 roots = 12 hues)
and classifies harmonic tension to drive brightness/intensity in sequences.
"""
from __future__ import annotations

import colorsys
import re
from typing import Optional

from src.analyzer.result import TimingMark


# ── Circle of fifths ─────────────────────────────────────────────────────────
# Each position maps to index * 30 degrees of hue (0-360).
CIRCLE_OF_FIFTHS = ["C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F"]

# Enharmonic equivalents → canonical name used in the circle
_ENHARMONIC: dict[str, str] = {
    "Gb": "F#", "C#": "Db", "G#": "Ab", "D#": "Eb", "A#": "Bb",
    "Cb": "B", "Fb": "E", "B#": "C", "E#": "F",
}

# Quality keywords found in chordino labels, ordered longest-first for matching
_QUALITY_PATTERNS: list[tuple[str, str]] = [
    ("maj7", "major7"),
    ("min7b5", "diminished"),  # half-diminished ≈ diminished tension
    ("m7b5", "diminished"),
    ("dim7", "diminished"),
    ("dim", "diminished"),
    ("aug", "augmented"),
    ("sus4", "suspended"),
    ("sus2", "suspended"),
    ("m7", "minor7"),
    ("min7", "minor7"),
    ("m6", "minor"),
    ("min6", "minor"),
    ("min", "minor"),
    ("m", "minor"),       # must come after m7, m6, maj7, min*
    ("7", "dominant7"),   # must come after maj7, m7, dim7
    ("6", "major"),
    ("9", "dominant7"),   # 9th chords have dominant function
    ("11", "dominant7"),
    ("13", "dominant7"),
]


# ── Chord parsing ────────────────────────────────────────────────────────────

_ROOT_RE = re.compile(r"^([A-G][#b]?)")


def parse_chord_label(label: str) -> tuple[str, str]:
    """Parse a chordino label into (root, quality).

    Examples:
        "G"      -> ("G", "major")
        "Em"     -> ("E", "minor")
        "D7"     -> ("D", "dominant7")
        "Bdim"   -> ("B", "diminished")
        "F#m7b5" -> ("F#", "diminished")
        "N"      -> ("N", "none")

    Returns ("N", "none") for unrecognized labels.
    """
    if not label or label == "N":
        return ("N", "none")

    # Handle slash chords: use root before the slash
    base = label.split("/")[0]

    m = _ROOT_RE.match(base)
    if not m:
        return ("N", "none")

    root = m.group(1)
    remainder = base[len(root):]

    # Canonicalize root
    root = _ENHARMONIC.get(root, root)

    # Determine quality from remainder
    quality = "major"  # default
    for pattern, qual in _QUALITY_PATTERNS:
        if remainder == pattern or remainder.startswith(pattern):
            quality = qual
            break

    return (root, quality)


# ── Color mapping ────────────────────────────────────────────────────────────

def chord_to_hue(root: str) -> int:
    """Map a chord root to a hue angle (0-359) via circle-of-fifths position."""
    if root in CIRCLE_OF_FIFTHS:
        return CIRCLE_OF_FIFTHS.index(root) * 30
    # Try enharmonic
    canonical = _ENHARMONIC.get(root, root)
    if canonical in CIRCLE_OF_FIFTHS:
        return CIRCLE_OF_FIFTHS.index(canonical) * 30
    return 0


def _hsv_to_hex(h: float, s: float, v: float) -> str:
    """Convert HSV (h=0-360, s=0-100, v=0-100) to #RRGGBB hex string."""
    r, g, b = colorsys.hsv_to_rgb(h / 360.0, s / 100.0, v / 100.0)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def _hex_to_hsv(hex_color: str) -> tuple[float, float, float]:
    """Convert #RRGGBB hex to HSV (h=0-360, s=0-100, v=0-100)."""
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0, s * 100.0, v * 100.0


def chord_to_color(label: str) -> str:
    """Map a chordino label to a hex color.

    Major chords:  full saturation (S=90, V=100)
    Minor chords:  warm-shifted hue (+15deg), reduced saturation (S=70, V=85)
    Dominant 7ths: slight orange push (+5deg), high saturation (S=95, V=100)
    Diminished:    desaturated and dark (S=50, V=60) — tense/murky
    Augmented:     cool-shifted (-10deg), high saturation (S=85, V=95)
    Suspended:     pastel (S=55, V=95)
    No chord (N):  neutral gray
    """
    root, quality = parse_chord_label(label)
    if root == "N":
        return "#404040"

    hue = chord_to_hue(root)

    if quality == "major" or quality == "major7":
        return _hsv_to_hex(hue, 90, 100)
    elif quality == "minor" or quality == "minor7":
        return _hsv_to_hex((hue + 15) % 360, 70, 85)
    elif quality == "dominant7":
        return _hsv_to_hex((hue + 5) % 360, 95, 100)
    elif quality == "diminished":
        return _hsv_to_hex(hue, 50, 60)
    elif quality == "augmented":
        return _hsv_to_hex((hue - 10) % 360, 85, 95)
    elif quality == "suspended":
        return _hsv_to_hex(hue, 55, 95)
    else:
        return _hsv_to_hex(hue, 90, 100)


def generate_chord_palette(
    chord_marks: list[TimingMark],
    start_ms: int,
    end_ms: int,
) -> list[str]:
    """Generate a color palette from chords active in a time window.

    Returns 1-8 unique colors from the chords present, ordered by first
    appearance. Deduplicates identical colors.
    """
    seen: set[str] = set()
    palette: list[str] = []

    for m in chord_marks:
        if m.time_ms < start_ms:
            continue
        if m.time_ms >= end_ms:
            break
        color = chord_to_color(m.label or "N")
        if color not in seen:
            seen.add(color)
            palette.append(color)
        if len(palette) >= 8:
            break

    return palette if palette else []


def chord_at_time(chord_marks: list[TimingMark], time_ms: int) -> Optional[str]:
    """Return the chord label active at a given time (binary search)."""
    if not chord_marks:
        return None
    lo, hi = 0, len(chord_marks) - 1
    result = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if chord_marks[mid].time_ms <= time_ms:
            result = chord_marks[mid].label
            lo = mid + 1
        else:
            hi = mid - 1
    return result


# ── Harmonic tension ─────────────────────────────────────────────────────────

# Tension values: 0 = complete rest, 100 = maximum dissonance
_TENSION_BY_QUALITY: dict[str, int] = {
    "none":       10,   # N (silence/no chord)
    "major":      30,   # stable, resolved
    "major7":     35,   # slightly more color than plain major
    "minor":      40,   # darker but stable
    "minor7":     50,   # jazz tension, moderate
    "suspended":  55,   # unresolved but not dissonant
    "dominant7":  65,   # creates expectation of resolution
    "augmented":  75,   # unstable, ambiguous
    "diminished": 80,   # high dissonance
}


def classify_tension(label: str) -> int:
    """Return a tension score (0-100) for a chord label."""
    _, quality = parse_chord_label(label)
    return _TENSION_BY_QUALITY.get(quality, 40)


def detect_resolution(prev_label: str, curr_label: str) -> bool:
    """Detect if curr_label resolves prev_label (dominant → tonic movement).

    Common resolutions: V7→I, e.g. G7→C, D7→G, A7→D, E7→A, B7→E, etc.
    The tonic is one position earlier in the circle of fifths from the dominant root.
    """
    prev_root, prev_quality = parse_chord_label(prev_label)
    curr_root, curr_quality = parse_chord_label(curr_label)

    if prev_quality != "dominant7" or prev_root == "N" or curr_root == "N":
        return False

    # The dominant's root should be one step forward in the circle of fifths
    # relative to the tonic. So if prev_root is at position i, tonic is at i-1.
    if prev_root not in CIRCLE_OF_FIFTHS or curr_root not in CIRCLE_OF_FIFTHS:
        return False

    dominant_idx = CIRCLE_OF_FIFTHS.index(prev_root)
    expected_tonic_idx = (dominant_idx - 1) % 12
    tonic_idx = CIRCLE_OF_FIFTHS.index(curr_root)

    return tonic_idx == expected_tonic_idx


def build_tension_curve(
    chord_marks: list[TimingMark],
    duration_ms: int,
) -> list[tuple[int, int]]:
    """Build a time→tension curve from chord marks.

    Returns list of (time_ms, tension) pairs — one per chord change,
    with resolution dips inserted where V7→I movement is detected.
    """
    if not chord_marks:
        return [(0, 10), (duration_ms, 10)]

    curve: list[tuple[int, int]] = []

    for i, mark in enumerate(chord_marks):
        label = mark.label or "N"
        tension = classify_tension(label)

        # Check for resolution from previous chord
        if i > 0:
            prev_label = chord_marks[i - 1].label or "N"
            if detect_resolution(prev_label, label):
                # Brief tension release at the resolution point
                tension = 15

        curve.append((mark.time_ms, tension))

    # Extend to song end if needed
    if curve and curve[-1][0] < duration_ms:
        curve.append((duration_ms, curve[-1][1]))

    return curve


def tension_at_time(curve: list[tuple[int, int]], time_ms: int) -> int:
    """Look up tension at a given time from a tension curve (step function)."""
    if not curve:
        return 30
    result = curve[0][1]
    for t, tension in curve:
        if t > time_ms:
            break
        result = tension
    return result


# ── Palette brightness modulation ────────────────────────────────────────────

def adjust_palette_brightness(palette: list[str], tension: int) -> list[str]:
    """Scale palette brightness based on harmonic tension.

    Tension 10 (rest)     → V scaled to 55%
    Tension 30 (baseline) → V unchanged
    Tension 80 (peak)     → V boosted to 100%

    Linear interpolation between anchor points.
    """
    if not palette:
        return palette

    # Map tension (10-80) to a brightness multiplier (0.55-1.15)
    # Clamp tension to 10-80 range for mapping
    t = max(10, min(80, tension))
    # 10→0.55, 30→1.0, 80→1.15
    if t <= 30:
        # 10→0.55, 30→1.0 — linear
        multiplier = 0.55 + (t - 10) / 20.0 * 0.45
    else:
        # 30→1.0, 80→1.15 — linear
        multiplier = 1.0 + (t - 30) / 50.0 * 0.15

    result: list[str] = []
    for hex_color in palette:
        try:
            h, s, v = _hex_to_hsv(hex_color)
            v = min(100.0, v * multiplier)
            result.append(_hsv_to_hex(h, s, v))
        except (ValueError, IndexError):
            result.append(hex_color)

    return result


def blend_palettes(
    theme_palette: list[str],
    chord_palette: list[str],
    chord_weight: float = 0.4,
) -> list[str]:
    """Blend theme palette with chord-derived palette.

    The theme palette defines the "character" (warm fire colors, cool blues).
    The chord palette shifts the hue. The result keeps the theme's saturation
    and value but rotates hue toward the chord colors.

    chord_weight: 0.0 = pure theme, 1.0 = pure chord colors.
    """
    if not chord_palette:
        return theme_palette
    if not theme_palette:
        return chord_palette

    result: list[str] = []
    for i, theme_hex in enumerate(theme_palette):
        chord_hex = chord_palette[i % len(chord_palette)]
        try:
            th, ts, tv = _hex_to_hsv(theme_hex)
            ch, _, _ = _hex_to_hsv(chord_hex)

            # Circular hue interpolation (shortest arc)
            diff = ch - th
            if diff > 180:
                diff -= 360
            elif diff < -180:
                diff += 360
            blended_h = (th + diff * chord_weight) % 360

            result.append(_hsv_to_hex(blended_h, ts, tv))
        except (ValueError, IndexError):
            result.append(theme_hex)

    return result
