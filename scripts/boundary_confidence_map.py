#!/usr/bin/env python3
"""Boundary confidence map — diagnostic tool for section boundary detection.

Reads <song>_hierarchy.json and <song>_story.json from a song folder,
extracts section-boundary candidates from every available source, and
reports where sources agree and disagree.

Optionally fetches Genius section boundaries and aligns them with WhisperX
(requires GENIUS_API_TOKEN in env).

Usage:
    python scripts/boundary_confidence_map.py <song_folder>
    python scripts/boundary_confidence_map.py <song_folder> --html <out.html>
    python scripts/boundary_confidence_map.py <song_folder> --no-genius

Examples:
    python scripts/boundary_confidence_map.py songs/02_-_Candy_Cane_Lane
    python scripts/boundary_confidence_map.py songs/mad_russian_christmas --html /tmp/bcm.html
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Load .env if present (for GENIUS_API_TOKEN)
_env_path = Path(__file__).resolve().parents[1] / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line.startswith("export "):
            _line = _line[7:]
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            _v = _v.strip().strip('"').strip("'")
            os.environ.setdefault(_k, _v)

# Shared helpers live in src.analyzer.boundary_cluster — import them so this
# script and the main pipeline (src/story/builder.py) stay in sync.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.analyzer.boundary_cluster import (  # noqa: E402
    AgreementCluster,
    Boundary,
    cluster_boundaries,
    extract_chord_density_spikes,
    extract_energy_events,
    extract_key_changes,
    extract_qm_segmenter,
    extract_segmentino,
    extract_stem_entry_events,
)


# ── Script-specific source extractor (story.json) ────────────────────────────
# All hierarchy.json extractors live in src.analyzer.boundary_cluster.


def extract_story_sections(story: dict) -> list[Boundary]:
    """Boundaries from the final classifier output (story.sections)."""
    out: list[Boundary] = []
    source_tag = (story.get("global") or {}).get("section_source") or "heuristic"
    for s in story.get("sections", []):
        if "start" in s:
            t = int(round(float(s["start"]) * 1000))
        elif "start_ms" in s:
            t = int(s["start_ms"])
        else:
            continue
        out.append(Boundary(
            time_ms=t,
            source=f"story ({source_tag})",
            label=s.get("role"),
            extra={"id": s.get("id"), "confidence": s.get("role_confidence")},
        ))
    return out


def fetch_genius_boundaries(
    mp3_path: Path, hier: dict
) -> tuple[list[Boundary], list[str]]:
    """
    Fetch Genius sections and anchor them to vocal-onset clusters.

    Returns (boundaries, notes). Notes include warnings/errors to surface in
    the report. Boundaries list is empty if fetch fails.

    Anchoring strategy (WhisperX-free):
      1. Parse Genius sections into an ordered list.
      2. Find vocal-entry events (>= 3s silence before) in the vocals stem.
      3. Assign each *non-instrumental* Genius section to the nearest
         proportional vocal-entry candidate.
      4. Instrumental sections ([Intro], [Break], [Outro]) are placed
         proportionally between their neighbors.

    This is *approximate* — not a replacement for WhisperX. Its purpose
    here is to give the diagnostic a "Genius says a section starts around
    here" signal that can be compared with segmentino/QM/heuristic outputs.
    """
    notes: list[str] = []
    token = os.environ.get("GENIUS_API_TOKEN", "")
    if not token:
        return [], ["GENIUS_API_TOKEN not set — skipping Genius fetch."]

    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from src.analyzer.genius_segments import (
            is_instrumental_section,
            parse_sections,
            read_id3_tags,
            sanitize_title,
            strip_boilerplate,
        )
    except ImportError as exc:
        return [], [f"Could not import genius_segments: {exc}"]

    try:
        artist, title = read_id3_tags(str(mp3_path))
    except ValueError:
        title = mp3_path.stem.replace("_", " ").replace("-", " ").strip()
        title = re.sub(r"^\d+\s*[-.]?\s*", "", title).strip()
        artist = ""
        notes.append(f"No ID3 tags — guessing title from filename: '{title}'")

    search_title = sanitize_title(title)
    try:
        import lyricsgenius
        genius = lyricsgenius.Genius(
            token, remove_section_headers=False, timeout=30, retries=3,
        )
        genius.verbose = False  # suppress "Searching for…" prints
        song = genius.search_song(search_title, artist)
    except Exception as exc:
        return [], [f"Genius API error: {exc}"]

    if song is None:
        return [], [f"No Genius match for '{search_title}' / '{artist}'."]

    notes.append(f"Genius matched: '{song.title}' by {song.artist}")
    raw_lyrics = song.lyrics or ""
    clean = strip_boilerplate(raw_lyrics)
    sections = parse_sections(clean)
    if not sections:
        return [], [*notes, "Genius match had no parseable sections."]

    # ── Quality gate ──────────────────────────────────────────────────────────
    # Adapted from src/story/builder.py:_genius_quality_ok(). Runs before
    # alignment so we reject a clearly-wrong match before showing it in the
    # report. Uses proportional estimates for timing-based checks so bad
    # matches (like false-positive Russian rap on TSO instrumentals) are
    # flagged instead of pulluting the diagnostic.

    def _title_match_ok(asked: str, got: str) -> bool:
        """Cheap token-overlap check on sanitized titles."""
        def tokens(s: str) -> set[str]:
            return {t for t in re.sub(r"[^a-z0-9 ]", " ", s.lower()).split() if len(t) >= 2}
        a, g = tokens(asked), tokens(got)
        if not a:
            return True
        overlap = len(a & g) / len(a)
        return overlap > 0.5

    dur_s = (hier.get("duration_ms", 0) or 0) / 1000.0
    n = len(sections)

    # Normalize Genius labels to our canonical role set (matches builder logic).
    def _normalize(label: str) -> str:
        l = label.lower().split(":")[0].split("(")[0].strip()
        for key, role in (
            ("intro", "intro"), ("outro", "outro"), ("verse", "verse"),
            ("chorus", "chorus"), ("hook", "chorus"), ("refrain", "chorus"),
            ("pre-chorus", "pre_chorus"), ("pre chorus", "pre_chorus"),
            ("post-chorus", "post_chorus"), ("post chorus", "post_chorus"),
            ("bridge", "bridge"), ("interlude", "interlude"),
            ("instrumental", "instrumental"), ("solo", "instrumental"),
            ("break", "instrumental"),
        ):
            if l == key or l.startswith(key):
                return role
        return l

    roles = {_normalize(s.label) for s in sections}
    quality_issues: list[str] = []

    if not _title_match_ok(search_title, song.title):
        quality_issues.append(
            f"title mismatch — asked '{search_title}', got '{song.title}'"
        )
    if dur_s > 60 and n < 3:
        quality_issues.append(f"only {n} sections for a {dur_s:.0f}s song")
    if len(roles) < 2:
        quality_issues.append(f"only {len(roles)} distinct role(s): {roles}")

    if quality_issues:
        notes.append(
            "Genius match rejected by quality gate: "
            + "; ".join(quality_issues)
        )
        return [], notes

    # Build vocal-entry candidates from cached onset data
    duration_ms = int(hier.get("duration_ms", 0))
    vocal_track = (hier.get("events") or {}).get("vocals") or {}
    vocal_marks = vocal_track.get("marks") or []
    vocal_times = [int(m["time_ms"]) for m in vocal_marks]

    vocal_entries: list[int] = []
    min_silence_ms = 3000
    if vocal_times:
        prev = vocal_times[0]
        if prev >= min_silence_ms:
            vocal_entries.append(prev)
        for t in vocal_times[1:]:
            if t - prev >= min_silence_ms:
                vocal_entries.append(t)
            prev = t

    # Separate vocal vs instrumental sections while preserving order
    n = len(sections)
    out: list[Boundary] = []

    # First pass: estimate a time for every section proportionally
    estimated_times: list[int] = [
        int(duration_ms * (i / max(n, 1))) for i in range(n)
    ]

    # Second pass: snap vocal sections to the nearest vocal-entry candidate
    # (consuming each candidate at most once, preserving left-to-right order)
    available = list(vocal_entries)
    for i, section in enumerate(sections):
        if is_instrumental_section(section.label):
            continue
        estimate = estimated_times[i]
        if not available:
            continue
        # Pick nearest candidate that still preserves monotonicity vs. any
        # already-assigned neighbour (previous out boundary time).
        prev_time = out[-1].time_ms if out else 0
        candidates_ahead = [c for c in available if c >= prev_time]
        pool = candidates_ahead or available
        best = min(pool, key=lambda c: abs(c - estimate))
        available.remove(best)
        estimated_times[i] = best

    # Emit boundaries in order
    for i, section in enumerate(sections):
        t = estimated_times[i]
        occ_tag = f" #{section.occurrence_index + 1}" if section.occurrence_index > 0 else ""
        out.append(Boundary(
            time_ms=t,
            source="genius",
            label=f"{section.label}{occ_tag}",
            extra={"instrumental": is_instrumental_section(section.label)},
        ))

    if not vocal_entries:
        notes.append(
            "No vocals-stem entries found — Genius sections are placed "
            "proportionally without alignment."
        )
    else:
        notes.append(
            f"Genius sections anchored to {len(vocal_entries)} vocal-entry "
            "candidates from the vocals stem (approximate alignment)."
        )
    return out, notes


# ── Agreement analysis ────────────────────────────────────────────────────────
# AgreementCluster and cluster_boundaries() live in src.analyzer.boundary_cluster.


def nearest_downbeat_offset_ms(time_ms: int, downbeats: list[int]) -> Optional[int]:
    """Signed offset in ms from `time_ms` to its nearest downbeat (time - downbeat)."""
    if not downbeats:
        return None
    best = min(downbeats, key=lambda d: abs(d - time_ms))
    return time_ms - best


# ── Reporting ─────────────────────────────────────────────────────────────────

def fmt_ms(ms: int) -> str:
    sign = "-" if ms < 0 else ""
    ms = abs(ms)
    m = ms // 60_000
    s = (ms % 60_000) / 1000
    return f"{sign}{m:02d}:{s:06.3f}"


def print_text_report(
    song_stem: str,
    duration_ms: int,
    bar_interval_ms: int,
    sources: dict[str, list[Boundary]],
    clusters: list[AgreementCluster],
    downbeats: list[int],
    notes: list[str],
    tolerance_ms: int,
) -> None:
    print(f"═══════════════════════════════════════════════════════════════════")
    print(f" Boundary Confidence Map — {song_stem}")
    print(f"═══════════════════════════════════════════════════════════════════")
    print(f"  Duration       : {fmt_ms(duration_ms)}")
    print(f"  Median bar     : {bar_interval_ms} ms")
    print(f"  Cluster tol.   : ±{tolerance_ms} ms (≈ 1 bar)")
    print(f"  Downbeats      : {len(downbeats)}")
    print()

    # Notes (e.g. Genius fetch status)
    if notes:
        print("Notes:")
        for n in notes:
            print(f"  • {n}")
        print()

    # Per-source summary
    print("Source summary:")
    print(f"  {'source':<26} {'count':>6}  example boundaries")
    print(f"  {'-'*26} {'-'*6}  {'-'*50}")
    for src in sorted(sources.keys()):
        bs = sources[src]
        examples = ", ".join(fmt_ms(b.time_ms) for b in bs[:3])
        if len(bs) > 3:
            examples += f", … (+{len(bs)-3} more)"
        print(f"  {src:<26} {len(bs):>6}  {examples}")
    print()

    # Cluster report — grouped boundaries with agreement score
    print("Agreement clusters (boundaries grouped within tolerance):")
    print(f"  {'time':<10} {'score':>5}  {'db_off':>7}  sources & labels")
    print(f"  {'-'*10} {'-'*5}  {'-'*7}  {'-'*60}")
    for c in clusters:
        db_off = nearest_downbeat_offset_ms(c.centre_ms, downbeats)
        db_str = f"{db_off:+5d}ms" if db_off is not None else "    -"
        # One entry per source with its label
        entries = []
        seen = set()
        for m in c.members:
            src = m.source.split(":")[0]
            key = (src, m.source)
            if key in seen:
                continue
            seen.add(key)
            tag = m.source if ":" in m.source else src
            if m.label:
                entries.append(f"{tag}={m.label}")
            else:
                entries.append(tag)
        marker = "⚑" if c.score >= 3 else " "
        print(f"  {fmt_ms(c.centre_ms):<10} {c.score:>4}{marker}  {db_str:>7}  {', '.join(entries)}")
    print()

    # High-confidence consensus list
    high = [c for c in clusters if c.score >= 3]
    print(f"High-confidence consensus boundaries (≥3 sources): {len(high)}")
    for c in high:
        db_off = nearest_downbeat_offset_ms(c.centre_ms, downbeats)
        print(f"  {fmt_ms(c.centre_ms)}  ({c.score} sources)  downbeat offset {db_off:+d}ms")
    print()


def render_html(
    song_stem: str,
    duration_ms: int,
    sources: dict[str, list[Boundary]],
    clusters: list[AgreementCluster],
    downbeats: list[int],
    out_path: Path,
) -> None:
    """Render a self-contained HTML timeline with one row per source."""
    order = [
        "story", "genius", "segmentino", "qm_segmenter",
        "chord_density_spike", "key_change",
        "energy_impact", "energy_drop",
        "stem_entry",
    ]
    # Group sources by prefix (stem_entry:drums → stem_entry)
    grouped: dict[str, list[Boundary]] = {}
    for src_name, bs in sources.items():
        key = src_name.split(":")[0] if src_name.startswith("stem_entry") else src_name
        # story key may be "story (heuristic)" — preserve full label as key
        if src_name.startswith("story"):
            key = src_name
        grouped.setdefault(key, []).extend(bs)

    def order_key(k: str) -> int:
        for i, prefix in enumerate(order):
            if k.startswith(prefix):
                return i
        return len(order)

    ordered_keys = sorted(grouped.keys(), key=order_key)

    colors = {
        "story": "#2563eb",
        "genius": "#db2777",
        "segmentino": "#059669",
        "qm_segmenter": "#7c3aed",
        "chord_density_spike": "#d97706",
        "key_change": "#0891b2",
        "energy_impact": "#dc2626",
        "energy_drop": "#64748b",
        "stem_entry": "#ea580c",
    }

    def color_for(k: str) -> str:
        for prefix, c in colors.items():
            if k.startswith(prefix):
                return c
        return "#334155"

    w = 1400
    row_h = 28
    margin = 80
    track_w = w - margin - 40

    def x(t_ms: int) -> float:
        if duration_ms <= 0:
            return margin
        return margin + (t_ms / duration_ms) * track_w

    rows_html = []
    for i, key in enumerate(ordered_keys):
        y = i * row_h
        col = color_for(key)
        ticks = []
        for b in grouped[key]:
            cx = x(b.time_ms)
            title = f"{fmt_ms(b.time_ms)}  {b.source}"
            if b.label:
                title += f"  [{b.label}]"
            ticks.append(
                f'<line x1="{cx:.1f}" y1="{y+4}" x2="{cx:.1f}" y2="{y+row_h-4}" '
                f'stroke="{col}" stroke-width="2"><title>{title}</title></line>'
            )
        label_txt = f"{key} ({len(grouped[key])})"
        rows_html.append(
            f'<text x="{margin-8:.1f}" y="{y+row_h/2+4:.1f}" text-anchor="end" '
            f'font-size="12" fill="#1e293b">{label_txt}</text>'
            + "".join(ticks)
        )

    # Consensus band along the top
    consensus_y = len(ordered_keys) * row_h + 10
    consensus_ticks = []
    for c in clusters:
        if c.score >= 3:
            cx = x(c.centre_ms)
            consensus_ticks.append(
                f'<line x1="{cx:.1f}" y1="{consensus_y}" x2="{cx:.1f}" '
                f'y2="{consensus_y+20}" stroke="#111827" stroke-width="3">'
                f'<title>{fmt_ms(c.centre_ms)} ({c.score} sources)</title></line>'
            )

    # Time axis
    axis_y = consensus_y + 40
    minute_ticks = []
    for m in range(0, duration_ms // 60_000 + 1):
        t_ms = m * 60_000
        if t_ms > duration_ms:
            break
        cx = x(t_ms)
        minute_ticks.append(
            f'<line x1="{cx:.1f}" y1="{axis_y}" x2="{cx:.1f}" y2="{axis_y+6}" stroke="#475569"/>'
            f'<text x="{cx:.1f}" y="{axis_y+20}" text-anchor="middle" font-size="11" '
            f'fill="#475569">{m:02d}:00</text>'
        )

    svg_height = axis_y + 40
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Boundary Confidence Map — {song_stem}</title>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; color: #0f172a; }}
    h1 {{ font-size: 18px; margin: 0 0 4px 0; }}
    .meta {{ color: #64748b; font-size: 13px; margin-bottom: 16px; }}
    svg {{ background: #f8fafc; border: 1px solid #e2e8f0; display: block; }}
    .legend {{ margin-top: 12px; font-size: 12px; }}
    .legend span {{ display: inline-block; margin-right: 16px; }}
    .sw {{ display: inline-block; width: 14px; height: 14px; vertical-align: middle;
           margin-right: 4px; border-radius: 2px; }}
</style></head><body>
<h1>Boundary Confidence Map — {song_stem}</h1>
<div class="meta">Duration: {fmt_ms(duration_ms)}  ·  Sources: {len(ordered_keys)}  ·  High-confidence consensus: {sum(1 for c in clusters if c.score >= 3)}</div>
<svg width="{w}" height="{svg_height}" xmlns="http://www.w3.org/2000/svg">
{chr(10).join(rows_html)}
<text x="{margin-8}" y="{consensus_y+15}" text-anchor="end" font-size="12" fill="#0f172a" font-weight="bold">consensus ≥3</text>
{chr(10).join(consensus_ticks)}
<line x1="{margin}" y1="{axis_y}" x2="{w-40}" y2="{axis_y}" stroke="#475569"/>
{chr(10).join(minute_ticks)}
</svg>
<div class="legend">
{''.join(f'<span><span class="sw" style="background:{color_for(k)}"></span>{k}</span>' for k in ordered_keys)}
</div>
</body></html>"""
    out_path.write_text(html, encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def find_hierarchy_and_story(song_folder: Path) -> tuple[Path, Optional[Path], Path]:
    """Return (hierarchy_path, story_path_or_None, mp3_path)."""
    mp3s = [p for p in song_folder.glob("*.mp3") if "stems" not in p.parts]
    if not mp3s:
        raise FileNotFoundError(f"No MP3 in {song_folder}")
    mp3 = mp3s[0]
    stem = mp3.stem
    # Nested folder layout: <folder>/<stem>/<stem>_hierarchy.json
    hier = song_folder / stem / f"{stem}_hierarchy.json"
    if not hier.exists():
        # Flat layout fallback
        hier = song_folder / f"{stem}_hierarchy.json"
    if not hier.exists():
        raise FileNotFoundError(f"No hierarchy.json for {stem}")

    story = song_folder / f"{stem}_story.json"
    if not story.exists():
        story = song_folder / stem / f"{stem}_story.json"
    return hier, (story if story.exists() else None), mp3


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("song_folder", help="Song folder, e.g. songs/02_-_Candy_Cane_Lane")
    ap.add_argument("--html", help="Write an HTML timeline to this path")
    ap.add_argument("--no-genius", action="store_true", help="Skip Genius fetch")
    ap.add_argument("--tolerance-bars", type=float, default=1.0,
                    help="Cluster tolerance in bars (default 1.0)")
    args = ap.parse_args()

    folder = Path(args.song_folder).resolve()
    if not folder.is_dir():
        print(f"ERROR: {folder} is not a directory", file=sys.stderr)
        sys.exit(1)

    hier_path, story_path, mp3_path = find_hierarchy_and_story(folder)
    hier = json.loads(hier_path.read_text())
    story = json.loads(story_path.read_text()) if story_path else {}

    duration_ms = int(hier.get("duration_ms", 0))
    bars_track = hier.get("bars") or {}
    bar_marks = bars_track.get("marks") or []
    downbeats = [int(m["time_ms"]) for m in bar_marks]
    bar_interval_ms = int(bars_track.get("avg_interval_ms") or 2000)
    tolerance_ms = int(bar_interval_ms * args.tolerance_bars)

    # Collect boundaries
    by_source: dict[str, list[Boundary]] = {}
    def add(bs: list[Boundary]) -> None:
        for b in bs:
            by_source.setdefault(b.source, []).append(b)

    add(extract_segmentino(hier))
    add(extract_qm_segmenter(hier))
    add(extract_story_sections(story))
    add(extract_key_changes(hier))
    add(extract_energy_events(hier))
    add(extract_chord_density_spikes(hier, bar_interval_ms))
    add(extract_stem_entry_events(hier))

    notes: list[str] = []
    if not args.no_genius:
        genius_bs, g_notes = fetch_genius_boundaries(mp3_path, hier)
        notes.extend(g_notes)
        add(genius_bs)

    # Cluster + report
    all_boundaries: list[Boundary] = [b for bs in by_source.values() for b in bs]
    clusters = cluster_boundaries(all_boundaries, tolerance_ms)

    print_text_report(
        song_stem=mp3_path.stem,
        duration_ms=duration_ms,
        bar_interval_ms=bar_interval_ms,
        sources=by_source,
        clusters=clusters,
        downbeats=downbeats,
        notes=notes,
        tolerance_ms=tolerance_ms,
    )

    if args.html:
        out = Path(args.html).resolve()
        render_html(
            song_stem=mp3_path.stem,
            duration_ms=duration_ms,
            sources=by_source,
            clusters=clusters,
            downbeats=downbeats,
            out_path=out,
        )
        print(f"HTML timeline written to {out}")


if __name__ == "__main__":
    main()
