#!/usr/bin/env python3
"""Library-wide fidelity score — mean multi-source agreement across all stories.

Scans a directory of songs (each with a `*_story.json` next to the MP3),
collects every section's `agreement_score`, and reports:

  - Per-song mean and distribution of agreement scores
  - Library-wide mean and percentiles
  - Sections with score 0 (no independent corroboration — worth reviewing)

Intended use: run before and after pipeline changes. A change that lifts
the library-wide mean without adding regressions is a genuine improvement;
a change that lowers it is quietly degrading quality.

Usage:
    python scripts/library_fidelity.py /path/to/songs_dir
    python scripts/library_fidelity.py /path/to/songs_dir --json /tmp/fidelity.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


def load_stories(songs_dir: Path) -> list[tuple[str, dict]]:
    """Find every `*_story.json` under *songs_dir* and return [(name, story)]."""
    out: list[tuple[str, dict]] = []
    for story_path in sorted(songs_dir.rglob("*_story.json")):
        if "stems" in story_path.parts:
            continue
        try:
            story = json.loads(story_path.read_text())
        except Exception as exc:
            print(f"  skipping {story_path} ({exc})", file=sys.stderr)
            continue
        song_name = story_path.stem.removesuffix("_story")
        out.append((song_name, story))
    return out


def summarize_song(name: str, story: dict) -> dict:
    sections = story.get("sections") or []
    scores = [int(s.get("agreement_score", 0)) for s in sections]
    src = story.get("global", {}).get("section_source", "?")
    n_zero = sum(1 for s in scores if s == 0)
    n_strong = sum(1 for s in scores if s >= 3)
    zero_roles = [sections[i].get("role") for i, s in enumerate(scores) if s == 0]
    return {
        "name": name,
        "source": src,
        "n_sections": len(scores),
        "mean_score": statistics.mean(scores) if scores else 0.0,
        "median_score": statistics.median(scores) if scores else 0.0,
        "n_zero": n_zero,
        "n_strong": n_strong,
        "zero_roles": zero_roles,
    }


def print_report(per_song: list[dict]) -> None:
    if not per_song:
        print("No stories found.")
        return

    all_scores: list[int] = []
    all_zero_sections = 0
    all_sections = 0
    for ps, s in zip(per_song, per_song):
        # dummy to silence lint — we compute from per_song below
        break

    # Recompute globals from raw data
    for row in per_song:
        all_sections += row["n_sections"]
        all_zero_sections += row["n_zero"]

    print(f"{'song':<50} {'source':<10} {'n':<3} {'mean':<6} {'zeros':<6} {'strong':<7} {'zero_roles'}")
    print("-" * 120)
    for row in sorted(per_song, key=lambda r: -r["mean_score"]):
        zr = ",".join(row["zero_roles"][:4]) if row["zero_roles"] else ""
        if len(row["zero_roles"]) > 4:
            zr += f",…(+{len(row['zero_roles']) - 4})"
        print(
            f"{row['name']:<50} {row['source']:<10} "
            f"{row['n_sections']:<3} {row['mean_score']:<6.2f} "
            f"{row['n_zero']:<6} {row['n_strong']:<7} {zr}"
        )

    # Aggregate
    print()
    print(f"Library totals:")
    print(f"  Songs: {len(per_song)}")
    print(f"  Sections: {all_sections}")
    if all_sections:
        print(f"  Sections with score 0: {all_zero_sections} ({100*all_zero_sections/all_sections:.1f}%)")
    means = [r["mean_score"] for r in per_song]
    if means:
        print(f"  Per-song mean score — library mean:   {statistics.mean(means):.3f}")
        print(f"  Per-song mean score — library median: {statistics.median(means):.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("songs_dir", type=Path)
    ap.add_argument("--json", type=Path, default=None,
                    help="Also write machine-readable summary to this path")
    args = ap.parse_args()

    if not args.songs_dir.is_dir():
        print(f"Not a directory: {args.songs_dir}", file=sys.stderr)
        sys.exit(1)

    stories = load_stories(args.songs_dir)
    if not stories:
        print(f"No *_story.json files found under {args.songs_dir}")
        sys.exit(0)

    per_song = [summarize_song(name, story) for name, story in stories]
    print_report(per_song)

    if args.json:
        args.json.write_text(json.dumps(per_song, indent=2))
        print(f"\nJSON summary → {args.json}")


if __name__ == "__main__":
    main()
