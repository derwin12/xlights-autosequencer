#!/usr/bin/env bash
# Entrypoint for the standalone `docker compose up` path (docker-compose.yml
# at the repo root). Installs the app into the container's system Python
# (verified against a real long-running working container, 2026-07-18: vamp,
# madmom, whisperx, torch, and this project all coexist fine in ONE
# environment — the separate .venv-vamp the README describes for a native
# install is not actually needed inside the container), builds the frontend
# if it hasn't been built yet, then starts the server.
#
# Runs on every `docker compose up` — pip/npm are no-ops on a cache hit, so
# after the first run this is fast. All system-level dependencies (ffmpeg,
# the compiled Vamp plugin .so files, Node, xLights AppImage) are already
# baked into the image by .devcontainer/Dockerfile; this script only
# handles the Python/JS package layer, which can't be baked into the image
# because it depends on the live-mounted /workspace source.
set -euo pipefail
cd /workspace

# `pip install --user` puts console scripts (xlight-review) in ~/.local/bin,
# which is NOT on PATH by default in a non-login shell inside this image.
export PATH="$HOME/.local/bin:$PATH"

# Debian's python3.11 is PEP 668 "externally managed" — pip refuses to
# install even with --user unless this is set. Safe here for the same
# reason the Dockerfile's own pip steps pass --break-system-packages:
# this container's system Python IS the app environment by design.
export PIP_BREAK_SYSTEM_PACKAGES=1

echo "[1/5] Installing the Python package (editable) + optional extras..."
pip install --user -e ".[all]" --quiet
# madmom is deliberately excluded from the "all" extra (pyproject.toml notes
# it needs numpy<2 -- true for a bare venv, but not inside this image, where
# numpy is already pinned compatibly by the other extras' resolution).
pip install --user madmom --quiet

echo "[2/5] Installing torch (CPU wheel — needed for stem separation + phonemes)..."
python3 -c "import torch" 2>/dev/null || \
  pip install --user torch torchaudio --index-url https://download.pytorch.org/whl/cpu --quiet

echo "[3/5] Downloading nltk data (phoneme + lyric POS tagging)..."
python3 -c "import nltk; nltk.download('cmudict', quiet=True); nltk.download('averaged_perceptron_tagger_eng', quiet=True)" || true

echo "[4/5] Building the review UI frontend (skipped if already built)..."
if [ ! -d src/review/frontend/dist ]; then
  (cd src/review/frontend && npm install && npm run build)
else
  echo "  dist/ already present — run 'npm run build' manually inside src/review/frontend/ after pulling frontend changes."
fi

# .venv-vamp is a compatibility shim: some code paths check for a sidecar
# interpreter at this path specifically (see src/analyzer/*.py). Everything
# is actually installed in the one system Python here, so this is just a
# symlink, not a real separate venv (matches the Dockerfile's own convention).
mkdir -p /home/node/.venv-vamp/bin
ln -sf "$(command -v python3)" /home/node/.venv-vamp/bin/python

echo "[5/5] Starting xlight-review at http://localhost:5000 ..."
exec xlight-review --dev --host 0.0.0.0 --port 5000
