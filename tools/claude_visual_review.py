"""Run Claude (vision) over UI screenshots and post a sticky PR review comment.

Designed to be invoked from .github/workflows/screenshots-on-pr.yml after
the capture step. Gracefully no-ops when ``ANTHROPIC_API_KEY`` is missing
so the workflow stays green for forks and contributors without secrets.

Usage::

    python tools/claude_visual_review.py \\
        --pr 142 \\
        --repo bobbyfriday/xlight-autosequencer \\
        --sha abc1234 \\
        --screenshots-dir tests/golden/ui/screenshots/

Reads ``ANTHROPIC_API_KEY`` and ``GH_TOKEN`` from the environment. Posts
(or updates) a single comment marked ``<!-- claude-visual-review-bot -->``
so subsequent runs replace it instead of accumulating.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

# Per-run safety bounds. Visual review is best as a quick scan, not an
# exhaustive audit — costs money + time and the signal degrades on huge
# batches anyway.
MAX_IMAGES = 20
PER_IMAGE_BYTES_LIMIT = 5 * 1024 * 1024  # Anthropic API limit per image
MODEL = "claude-opus-4-7"

REVIEW_PROMPT = """You are reviewing UI screenshots from a pull request to an internal
audio-analysis web app. The user wants a quick visual sanity check, not an
exhaustive audit.

Look for:
- Layout breakage (cut-off text, overlapping elements, missing content).
- Contrast or readability issues.
- Inconsistent spacing or alignment vs. neighbouring screens.
- Anything that looks broken, half-rendered, or mid-load.

Do NOT:
- Comment on aesthetics that aren't broken (colour choice, font weight).
- Speculate about behaviour you can't see in the static image.
- Produce a long report — keep it tight.

Respond in markdown:
- One short summary line (one sentence).
- A bullet list of concrete issues with the screenshot filename, OR
  "No visual regressions spotted." if nothing stands out.

Reviewing PR #{pr} (commit {sha}). Screenshots follow."""


def _iter_screenshots(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() in (".jpg", ".jpeg", ".png") and p.is_file():
            if p.stat().st_size > PER_IMAGE_BYTES_LIMIT:
                continue
            yield p


def _encode_image(path: Path) -> dict:
    media = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media,
            "data": base64.standard_b64encode(path.read_bytes()).decode("ascii"),
        },
    }


def _post_comment(repo: str, pr: int, body: str, marker: str) -> None:
    """Find a sticky comment by marker and update it; otherwise create one."""
    existing = subprocess.run(
        ["gh", "api", f"repos/{repo}/issues/{pr}/comments",
         "--jq", f'.[] | select(.body | startswith("{marker}")) | .id'],
        check=True, capture_output=True, text=True,
    ).stdout.strip().splitlines()
    body_payload = json.dumps({"body": body})
    if existing:
        comment_id = existing[0]
        proc = subprocess.run(
            ["gh", "api", "-X", "PATCH",
             f"repos/{repo}/issues/comments/{comment_id}",
             "--input", "-"],
            input=body_payload, text=True, capture_output=True,
        )
    else:
        proc = subprocess.run(
            ["gh", "api", "-X", "POST",
             f"repos/{repo}/issues/{pr}/comments",
             "--input", "-"],
            input=body_payload, text=True, capture_output=True,
        )
    if proc.returncode != 0:
        sys.stderr.write(f"gh api failed: {proc.stderr}\n")
        sys.exit(1)


def _call_anthropic(prompt: str, images: list[dict], api_key: str) -> str:
    """Single multimodal call. urllib instead of `anthropic` to avoid an
    extra runtime dependency in CI."""
    import urllib.request

    body = {
        "model": MODEL,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}, *images],
            }
        ],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    parts = data.get("content", [])
    return "\n".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--screenshots-dir", required=True)
    args = ap.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ANTHROPIC_API_KEY not set — skipping visual review.")
        return 0

    root = Path(args.screenshots_dir)
    paths = list(_iter_screenshots(root))[:MAX_IMAGES]
    if not paths:
        print("No screenshots to review.")
        return 0

    print(f"Reviewing {len(paths)} screenshots…")
    images = []
    for p in paths:
        rel = p.relative_to(root)
        images.append({"type": "text", "text": f"\n**{rel}**\n"})
        images.append(_encode_image(p))

    review = _call_anthropic(
        REVIEW_PROMPT.format(pr=args.pr, sha=args.sha[:8]),
        images,
        api_key,
    )

    body = (
        f"<!-- claude-visual-review-bot -->\n"
        f"## 🤖 Claude visual review\n\n"
        f"{review}\n\n"
        f"_Reviewed {len(paths)} screenshot(s) at commit `{args.sha[:8]}` "
        f"with `{MODEL}`._"
    )
    _post_comment(args.repo, args.pr, body, "<!-- claude-visual-review-bot -->")
    print("Posted Claude visual review comment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
