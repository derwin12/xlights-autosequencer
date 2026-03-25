#!/usr/bin/env python3
"""
Extract audio clips around harmonic split points for listening review.

For each split point, extracts a clip from 5s before to 5s after and saves
as a WAV file. Also generates an HTML player page for easy review.

Usage: python analysis/split_clips.py /path/to/song.mp3 [seconds_before] [seconds_after]
       python analysis/split_clips.py /path/to/mp3s          # all songs, picks 3 splits each
"""
from __future__ import annotations

import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import vamp


def get_segmentino_sections(y: np.ndarray, sr: int) -> list[dict]:
    out = vamp.collect(y, sr, "segmentino:segmentino")
    sections = []
    for item in out.get("list", []):
        sections.append({
            "start_s": float(item["timestamp"]),
            "duration_s": float(item.get("duration", 0)),
            "label": item.get("label", "?"),
        })
    return sections


def get_harmonic_splits(y: np.ndarray, sr: int, sections: list[dict],
                        min_section_s: float = 15.0) -> list[dict]:
    """Find harmonic change peaks that fall inside long Segmentino sections."""
    out = vamp.collect(y, sr, "nnls-chroma:chordino", output="harmonicchange")
    if "vector" not in out:
        return []

    _, vals = out["vector"]
    vals = np.array(vals, dtype=np.float64)
    duration_s = len(y) / sr
    frame_s = duration_s / len(vals)

    threshold = np.percentile(vals, 99)
    min_dist_frames = int(8.0 / frame_s)

    # Find peaks
    above = np.where(vals > threshold)[0]
    peaks = []
    last = -min_dist_frames
    for idx in above:
        if idx - last >= min_dist_frames:
            peaks.append((idx * frame_s, float(vals[idx])))
            last = idx

    # Find splits inside long sections
    splits = []
    for sec in sections:
        if sec["duration_s"] < min_section_s:
            continue
        sec_start = sec["start_s"]
        sec_end = sec_start + sec["duration_s"]
        margin = 2.0

        for peak_s, peak_val in peaks:
            if sec_start + margin < peak_s < sec_end - margin:
                splits.append({
                    "time_s": peak_s,
                    "value": peak_val,
                    "section_label": sec["label"],
                    "section_start_s": sec_start,
                    "section_end_s": sec_end,
                    "section_duration_s": sec["duration_s"],
                })

    return splits


def extract_clip(y: np.ndarray, sr: int, center_s: float,
                 before_s: float = 5.0, after_s: float = 5.0) -> np.ndarray:
    """Extract a clip centered on a time point."""
    start_sample = max(0, int((center_s - before_s) * sr))
    end_sample = min(len(y), int((center_s + after_s) * sr))
    return y[start_sample:end_sample]


def process_song(mp3_path: str, out_dir: Path, before_s: float, after_s: float,
                 max_splits: int | None = None) -> list[dict]:
    """Process one song: find splits, extract clips, return metadata."""
    y, sr = librosa.load(mp3_path, mono=True)
    song_name = Path(mp3_path).stem

    sections = get_segmentino_sections(y, sr)
    splits = get_harmonic_splits(y, sr, sections)

    if max_splits and len(splits) > max_splits:
        # Pick the highest-value splits
        splits.sort(key=lambda s: s["value"], reverse=True)
        splits = splits[:max_splits]
        splits.sort(key=lambda s: s["time_s"])

    clips = []
    for i, split in enumerate(splits):
        clip = extract_clip(y, sr, split["time_s"], before_s, after_s)

        clip_name = f"{song_name}_split{i+1}_{split['time_s']:.0f}s.wav"
        clip_path = out_dir / clip_name
        sf.write(str(clip_path), clip, sr)

        clips.append({
            "song": song_name,
            "clip_file": clip_name,
            "split_time_s": round(split["time_s"], 1),
            "harmonic_value": round(split["value"], 4),
            "section_label": split["section_label"],
            "section_range": f"{split['section_start_s']:.0f}s-{split['section_end_s']:.0f}s",
            "section_duration_s": round(split["section_duration_s"], 1),
            "clip_range": f"{max(0, split['time_s']-before_s):.1f}s-{split['time_s']+after_s:.1f}s",
            "before_s": before_s,
            "after_s": after_s,
        })

    return clips


def write_html(clips: list[dict], out_dir: Path) -> Path:
    """Generate an HTML page with audio players for each clip."""
    html_path = out_dir / "split_review.html"

    rows = ""
    for i, clip in enumerate(clips):
        rows += f"""
        <tr id="row-{i}" data-song="{clip['song']}" data-split-time="{clip['split_time_s']}"
            data-section-label="{clip['section_label']}" data-harmonic-value="{clip['harmonic_value']}">
            <td><strong>{clip['song'][:30]}</strong></td>
            <td>{clip['split_time_s']}s</td>
            <td>{clip['section_label']} ({clip['section_range']}, {clip['section_duration_s']}s)</td>
            <td>{clip['harmonic_value']}</td>
            <td>
                <audio controls preload="none" style="width:280px">
                    <source src="{clip['clip_file']}" type="audio/wav">
                </audio>
            </td>
            <td>
                <button class="vote-btn yes" data-value="yes" onclick="vote({i},'yes')">Yes</button>
                <button class="vote-btn no" data-value="no" onclick="vote({i},'no')">No</button>
                <button class="vote-btn maybe" data-value="maybe" onclick="vote({i},'maybe')">Maybe</button>
            </td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Split Point Review</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; margin: 20px; background: #1a1a2e; color: #e0e0e0; }}
        h1 {{ color: #00d4ff; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th {{ background: #16213e; color: #00d4ff; padding: 10px; text-align: left; }}
        td {{ padding: 8px 10px; border-bottom: 1px solid #333; vertical-align: middle; }}
        tr:hover {{ background: #16213e; }}
        tr.voted-yes {{ background: #0a3d0a; }}
        tr.voted-no {{ background: #3d0a0a; }}
        tr.voted-maybe {{ background: #3d3d0a; }}
        .info {{ color: #888; margin-bottom: 20px; }}
        audio {{ vertical-align: middle; }}
        .vote-btn {{
            padding: 6px 14px; margin: 2px; border: none; border-radius: 4px;
            cursor: pointer; font-size: 14px; font-weight: bold;
        }}
        .vote-btn.yes {{ background: #2d7a2d; color: white; }}
        .vote-btn.no {{ background: #7a2d2d; color: white; }}
        .vote-btn.maybe {{ background: #7a7a2d; color: white; }}
        .vote-btn.selected {{ outline: 2px solid white; }}
        #export-bar {{
            position: sticky; top: 0; background: #0f3460; padding: 12px 20px;
            z-index: 10; display: flex; align-items: center; gap: 20px;
            border-bottom: 2px solid #00d4ff;
        }}
        #export-bar button {{
            padding: 8px 20px; background: #00d4ff; color: #1a1a2e; border: none;
            border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 14px;
        }}
        #stats {{ color: #aaa; }}
    </style>
</head>
<body>
    <h1>Split Point Review</h1>
    <p class="info">
        Each clip is {clips[0]['before_s']:.0f}s before and {clips[0]['after_s']:.0f}s after the proposed split point.
        Listen for a musical change at the midpoint of each clip. Vote Yes/No/Maybe for each.
    </p>
    <div id="export-bar">
        <button onclick="exportFeedback()">Export Feedback JSON</button>
        <span id="stats">0 / {len(clips)} reviewed</span>
    </div>
    <table>
        <tr>
            <th>Song</th>
            <th>Split At</th>
            <th>Section</th>
            <th>H.Value</th>
            <th>Listen</th>
            <th>Vote</th>
        </tr>
        {rows}
    </table>
    <script>
        const votes = {{}};
        let totalClips = {len(clips)};

        function vote(idx, value) {{
            votes[idx] = value;
            // Update row styling
            const row = document.getElementById('row-' + idx);
            row.className = 'voted-' + value;
            // Update button styling
            row.querySelectorAll('.vote-btn').forEach(btn => {{
                btn.classList.toggle('selected', btn.dataset.value === value);
            }});
            updateStats();
        }}

        function updateStats() {{
            const n = Object.keys(votes).length;
            const yes = Object.values(votes).filter(v => v === 'yes').length;
            const no = Object.values(votes).filter(v => v === 'no').length;
            const maybe = Object.values(votes).filter(v => v === 'maybe').length;
            document.getElementById('stats').textContent =
                n + ' / ' + totalClips + ' reviewed  |  ' + yes + ' yes, ' + no + ' no, ' + maybe + ' maybe';
        }}

        function exportFeedback() {{
            const clips = document.querySelectorAll('tr[id^="row-"]');
            const feedback = [];
            clips.forEach((row, i) => {{
                feedback.push({{
                    song: row.dataset.song,
                    split_time_s: parseFloat(row.dataset.splitTime),
                    section_label: row.dataset.sectionLabel,
                    harmonic_value: parseFloat(row.dataset.harmonicValue),
                    vote: votes[i] || 'unreviewed'
                }});
            }});
            const blob = new Blob([JSON.stringify(feedback, null, 2)], {{type: 'application/json'}});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'split_feedback.json';
            a.click();
        }}
    </script>
</body>
</html>"""

    html_path.write_text(html)
    return html_path


def main():
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/Users/rob/mp3")
    before_s = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    after_s = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0

    out_dir = Path("analysis/split_clips")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_clips = []

    if target.is_file():
        # Single song — extract all splits
        print(f"Processing {target.name}...")
        clips = process_song(str(target), out_dir, before_s, after_s)
        all_clips.extend(clips)
        print(f"  {len(clips)} split clips extracted")
    else:
        # Directory — pick top 3 splits per song
        mp3s = sorted(target.glob("*.mp3"))
        print(f"Processing {len(mp3s)} songs (top 3 splits each)...")
        for mp3 in mp3s:
            name = mp3.stem[:40]
            try:
                clips = process_song(str(mp3), out_dir, before_s, after_s, max_splits=3)
                all_clips.extend(clips)
                print(f"  {name}: {len(clips)} clips")
            except Exception as exc:
                print(f"  {name}: ERROR - {exc}")

    if all_clips:
        html_path = write_html(all_clips, out_dir)
        print(f"\n{len(all_clips)} clips extracted to: {out_dir}/")
        print(f"Review page: {html_path}")
        print(f"\nOpen in browser:")
        print(f"  open {html_path}")
    else:
        print("No splits found.")


if __name__ == "__main__":
    main()
