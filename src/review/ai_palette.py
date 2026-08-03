"""Local-Ollama palette suggestion for the custom theme editor.

See openspec/changes/theme-ai-palette-suggest for the design rationale and
the manual testing this technique was validated against (2026-08-02):
Ollama's structured-output JSON Schema `format` (not the `format: "json"`
string, which produced inconsistent wrapper shapes and occasional garbage)
gave 10/10 clean, valid 4-color hex arrays across 2 runs x 5 songs.

This module never raises -- suggest_palette() returns None on any failure
(connection refused, timeout, malformed response, wrong shape) so the
caller falls back to the existing manual palette entry with a clear error
message, never a broken dialog.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_PALETTE_SIZE = 4

_PALETTE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "string",
        "pattern": "^#[0-9A-Fa-f]{6}$",
    },
    "minItems": _PALETTE_SIZE,
    "maxItems": _PALETTE_SIZE,
}


def _build_prompt(title: str, artist: str, genre: str, occasion: str) -> str:
    return (
        "You are a color designer for a holiday/Christmas outdoor LED light "
        "show synced to music.\n"
        "Given a song, propose a 4-color palette (hex codes) that captures "
        "the song's mood, energy, and genre/artist identity for the light "
        "display. Avoid plain primary colors like #FF0000, #00FF00, "
        "#0000FF, #FFFF00 unless the song truly calls for them.\n\n"
        f'Song: "{title}"\n'
        f"Artist: {artist}\n"
        f"Genre: {genre}\n"
        f"Occasion: {occasion}\n\n"
        "Respond with ONLY a JSON array of exactly 4 uppercase hex color "
        'strings, e.g. ["#RRGGBB","#RRGGBB","#RRGGBB","#RRGGBB"]. No '
        "explanation, no markdown, no extra text."
    )


def suggest_palette(
    title: str,
    artist: str,
    genre: str,
    occasion: str,
    ollama_host: str,
    ollama_model: str,
    timeout_s: float = 10.0,
) -> list[str] | None:
    """Ask a local Ollama model for a 4-color palette. Never raises."""
    payload = {
        "model": ollama_model,
        "prompt": _build_prompt(title, artist, genre, occasion),
        "format": _PALETTE_SCHEMA,
        "stream": False,
    }
    request_obj = urllib.request.Request(
        f"{ollama_host.rstrip('/')}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None

    raw_response = body.get("response")
    if not isinstance(raw_response, str):
        return None
    try:
        colors = json.loads(raw_response)
    except json.JSONDecodeError:
        return None

    if not isinstance(colors, list) or len(colors) != _PALETTE_SIZE:
        return None
    if not all(isinstance(c, str) and _HEX_COLOR_RE.match(c) for c in colors):
        return None
    return [c.upper() for c in colors]
