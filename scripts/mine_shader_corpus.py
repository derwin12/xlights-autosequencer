#!/usr/bin/env python3
"""Mine a show folder's .xsq sequences for Shader-effect (.fs file) usage.

Read-only against the scanned show folder — nothing is ever written back to
it. Unlike scripts/mine_prop_corpus.py, this miner writes ONLY aggregated,
corpus-wide statistics: no per-song data.json/summary.md, no song titles, no
media filenames, no source file paths. The whole point of this pass is to
find out which of xLights' ~300 bundled shaders are worth cataloging as
variants next — the identity of which specific show/song used which shader
is not needed for that and must not be persisted.

Scans only the top-level directory (no subfolders, no Backup/ snapshots, no
.xsqz/.zip packages) for *.xsq files, and for each one:

  - Parses EffectDB + ElementEffects for every effect placement whose base
    effect is "Shader".
  - Resolves each placement's E_0FILEPICKERCTRL_IFS (the "Shaders/<name>.fs"
    file actually loaded) plus a few other common shader parameters
    (E_SLIDER_Shader_Speed, E_TEXTCTRL_Shader_Zoom, T_CHOICE_LayerMethod,
    active palette color count).
  - Tallies usage per shader file across the whole corpus: placement count,
    distinct-song count (a count only, not which songs), duration/speed/zoom
    distributions, and how often it appears with a mask-style blend (a signal
    for "needs a colored base layer" per the requires_color_mask tag already
    used in src/variants/builtins/Shader.json).

Writes one aggregated report: docs/shader_corpus/INDEX.md.

Usage:
    python scripts/mine_shader_corpus.py "E:\\2023\\ShowFolder3D"
"""

from __future__ import annotations

import argparse
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_ZIP_MAGIC = b"PK"
_SHADER_EFFECT_NAME = "Shader"
_SHADER_FILE_KEY = "E_0FILEPICKERCTRL_IFS"
_SHADER_SPEED_KEY = "E_SLIDER_Shader_Speed"
_SHADER_ZOOM_KEY = "E_TEXTCTRL_Shader_Zoom"
_LAYER_METHOD_KEY = "T_CHOICE_LayerMethod"

_PALETTE_CHECKBOX_RE = re.compile(r"C_CHECKBOX_Palette(\d+)=1")
_PALETTE_COLOR_RE = re.compile(r"C_BUTTON_Palette(\d+)=(#[0-9A-Fa-f]{6})")

_DURATION_BUCKET_ORDER = [
    "<0.25s", "0.25-0.5s", "0.5-1s", "1-2s", "2-4s", "4-8s",
    "8-16s", "16-30s", "30-60s", "60s+",
]


@dataclass
class ShaderPlacement:
    shader_file: str
    duration_ms: int
    speed: float | None
    zoom: float | None
    layer_method: str
    palette_color_count: int


@dataclass
class ShaderStats:
    placement_count: int = 0
    song_indices: set[int] = field(default_factory=set)
    durations_s: list[float] = field(default_factory=list)
    speeds: list[float] = field(default_factory=list)
    zooms: list[float] = field(default_factory=list)
    masked_count: int = 0
    mono_color_count: int = 0
    multi_color_count: int = 0


def _parse_palette_text(text: str) -> tuple[str, ...]:
    active_slots = {int(m.group(1)) for m in _PALETTE_CHECKBOX_RE.finditer(text)}
    colors: dict[int, str] = {}
    for m in _PALETTE_COLOR_RE.finditer(text):
        slot = int(m.group(1))
        if not active_slots or slot in active_slots:
            colors[slot] = m.group(2).upper()
    return tuple(colors[k] for k in sorted(colors))


def _parse_effect_db_settings(text: str) -> dict[str, str]:
    settings: dict[str, str] = {}
    for part in text.split(","):
        if "=" in part:
            key, _, value = part.partition("=")
            settings[key] = value
    return settings


def load_xsq_root(xsq_path: Path) -> ET.Element:
    data = xsq_path.read_bytes()
    if data[:2] == _ZIP_MAGIC:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xsq_name = next((n for n in zf.namelist() if n.endswith(".xsq")), None)
            if xsq_name is None:
                raise ValueError(f"No .xsq member found inside {xsq_path.name!r}")
            data = zf.read(xsq_name)
    return ET.fromstring(data)


def _shader_basename(path_value: str) -> str:
    """'Shaders/Plasma Emitter.fs' -> 'Plasma Emitter.fs'; tolerate backslashes
    and bare filenames from machine-specific absolute paths."""
    normalized = path_value.replace("\\", "/")
    return normalized.rsplit("/", 1)[-1] if normalized else "(unset)"


def mine_shader_placements(xsq_path: Path) -> list[ShaderPlacement]:
    root = load_xsq_root(xsq_path)

    palettes: list[tuple[str, ...]] = []
    cp_el = root.find("ColorPalettes")
    if cp_el is not None:
        for cp in cp_el.findall("ColorPalette"):
            palettes.append(_parse_palette_text(cp.text or ""))

    effect_db_settings: list[dict[str, str]] = []
    edb_el = root.find("EffectDB")
    if edb_el is not None:
        for e in edb_el.findall("Effect"):
            effect_db_settings.append(_parse_effect_db_settings(e.text or ""))

    placements: list[ShaderPlacement] = []
    ee = root.find("ElementEffects")
    if ee is None:
        return placements

    for elem_el in ee.findall("Element"):
        if elem_el.get("type") != "model":
            continue
        for layer_el in elem_el.findall("EffectLayer"):
            for eff_el in layer_el.findall("Effect"):
                if eff_el.get("name") != _SHADER_EFFECT_NAME:
                    continue
                start_ms = int(eff_el.get("startTime", "0"))
                end_ms = int(eff_el.get("endTime", "0"))
                if end_ms <= start_ms:
                    continue
                ref_idx = int(eff_el.get("ref", "-1") or "-1")
                settings = effect_db_settings[ref_idx] if 0 <= ref_idx < len(effect_db_settings) else {}
                pal_idx = int(eff_el.get("palette", "-1") or "-1")
                colors = palettes[pal_idx] if 0 <= pal_idx < len(palettes) else ()

                shader_file = _shader_basename(settings.get(_SHADER_FILE_KEY, ""))
                speed = _to_float(settings.get(_SHADER_SPEED_KEY))
                zoom = _to_float(settings.get(_SHADER_ZOOM_KEY))
                layer_method = settings.get(_LAYER_METHOD_KEY, "")

                placements.append(ShaderPlacement(
                    shader_file=shader_file,
                    duration_ms=end_ms - start_ms,
                    speed=speed,
                    zoom=zoom,
                    layer_method=layer_method,
                    palette_color_count=len(colors),
                ))

    return placements


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def bucket_duration(dur_s: float) -> str:
    if dur_s < 0.25:
        return "<0.25s"
    if dur_s < 0.5:
        return "0.25-0.5s"
    if dur_s < 1.0:
        return "0.5-1s"
    if dur_s < 2.0:
        return "1-2s"
    if dur_s < 4.0:
        return "2-4s"
    if dur_s < 8.0:
        return "4-8s"
    if dur_s < 16.0:
        return "8-16s"
    if dur_s < 30.0:
        return "16-30s"
    if dur_s < 60.0:
        return "30-60s"
    return "60s+"


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def write_index_md(
    out_path: Path,
    stats_by_shader: dict[str, ShaderStats],
    songs_scanned: int,
    songs_with_shaders: int,
    songs_unreadable: int,
) -> None:
    total_placements = sum(s.placement_count for s in stats_by_shader.values())

    lines = ["# Shader (.fs) corpus — index", ""]
    lines.append(
        "Aggregated only — no song titles, filenames, or per-sequence data are stored here or "
        "anywhere else this script writes, by design."
    )
    lines.append("")
    lines.append(f"- Sequences scanned: {songs_scanned}")
    lines.append(f"- Sequences with at least one Shader placement: {songs_with_shaders}")
    lines.append(f"- Sequences skipped (unreadable/malformed): {songs_unreadable}")
    lines.append(f"- Total Shader placements: {total_placements}")
    lines.append(f"- Distinct shader files in use: {len(stats_by_shader)}")
    lines.append("")

    lines.append("## Shader files by placement count")
    lines.append("")
    lines.append("| Shader file | Placements | % of all Shader placements | Songs using it | Mask-blended | Mono-color | Multi-color | Median speed | Median zoom | Median duration |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for shader_file, stats in sorted(
        stats_by_shader.items(), key=lambda kv: kv[1].placement_count, reverse=True
    ):
        pct = stats.placement_count / max(total_placements, 1) * 100
        median_speed = _median(stats.speeds)
        median_zoom = _median(stats.zooms)
        median_dur = _median(stats.durations_s)
        lines.append(
            f"| {shader_file} | {stats.placement_count} | {pct:.1f}% | {len(stats.song_indices)} | "
            f"{stats.masked_count} | {stats.mono_color_count} | {stats.multi_color_count} | "
            f"{median_speed if median_speed is not None else '—'} | "
            f"{median_zoom if median_zoom is not None else '—'} | "
            f"{f'{median_dur:.1f}s' if median_dur is not None else '—'} |"
        )
    lines.append("")

    lines.append("## Duration distribution across all Shader placements")
    all_durations = [d for s in stats_by_shader.values() for d in s.durations_s]
    duration_buckets = Counter(bucket_duration(d) for d in all_durations)
    for b in _DURATION_BUCKET_ORDER:
        count = duration_buckets.get(b, 0)
        if count:
            lines.append(f"- {b}: {count}")
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("show_folder", type=Path, help="Show folder containing .xsq sequences (top level only)")
    parser.add_argument("--out", type=Path, default=Path("docs/shader_corpus/INDEX.md"))
    args = parser.parse_args()

    show_folder: Path = args.show_folder
    if not show_folder.exists():
        raise SystemExit(f"Show folder not found: {show_folder}")

    xsq_paths = sorted(show_folder.glob("*.xsq"))
    print(f"Found {len(xsq_paths)} top-level .xsq file(s)")

    stats_by_shader: dict[str, ShaderStats] = defaultdict(ShaderStats)
    songs_with_shaders = 0
    songs_unreadable = 0

    for song_index, xsq_path in enumerate(xsq_paths):
        try:
            placements = mine_shader_placements(xsq_path)
        except (ET.ParseError, ValueError, zipfile.BadZipFile) as exc:
            print(f"  SKIP (unreadable): {exc}")
            songs_unreadable += 1
            continue

        if not placements:
            continue
        songs_with_shaders += 1

        for p in placements:
            stats = stats_by_shader[p.shader_file]
            stats.placement_count += 1
            stats.song_indices.add(song_index)
            stats.durations_s.append(p.duration_ms / 1000.0)
            if p.speed is not None:
                stats.speeds.append(p.speed)
            if p.zoom is not None:
                stats.zooms.append(p.zoom)
            if p.layer_method.strip():
                stats.masked_count += 1
            if p.palette_color_count <= 1:
                stats.mono_color_count += 1
            else:
                stats.multi_color_count += 1

    write_index_md(
        args.out, stats_by_shader,
        songs_scanned=len(xsq_paths), songs_with_shaders=songs_with_shaders,
        songs_unreadable=songs_unreadable,
    )
    print(
        f"\n{songs_with_shaders}/{len(xsq_paths)} sequence(s) used at least one Shader placement "
        f"({sum(s.placement_count for s in stats_by_shader.values())} total placements, "
        f"{len(stats_by_shader)} distinct shader files) -> {args.out}"
    )


if __name__ == "__main__":
    main()
