#!/bin/bash
# Validate xLights sequences (check sequence).
#   amd64: runs xLights locally via Xvfb
#   arm64: SSHs to macOS host and runs the native xLights.app
#
# Usage: xlights-check.sh [-s /path/to/show] sequence1.xsq [sequence2.xsq ...]
# If -s is omitted, defaults to the mounted show directory.
set -euo pipefail

SHOW_DIR="/home/node/xlights"

while getopts "s:" opt; do
  case $opt in
    s) SHOW_DIR="$OPTARG" ;;
    *) echo "Usage: xlights-check.sh [-s show_dir] sequence.xsq [...]" >&2; exit 1 ;;
  esac
done
shift $((OPTIND - 1))

if [ $# -eq 0 ]; then
  echo "Error: no sequence files specified" >&2
  echo "Usage: xlights-check.sh [-s show_dir] sequence.xsq [...]" >&2
  exit 1
fi

ARCH=$(dpkg --print-architecture)

if [ "$ARCH" = "amd64" ]; then
  # ── Local check via Xvfb ──
  if [ ! -d "$SHOW_DIR" ]; then
    echo "Error: show directory not found: $SHOW_DIR" >&2
    exit 1
  fi
  export LIBGL_ALWAYS_SOFTWARE=1
  export MESA_GL_VERSION_OVERRIDE=3.3
  exec xvfb-run -a -s "-screen 0 1280x1024x24 +extension GLX" \
    xLights --checksequence --show="$SHOW_DIR" "$@"
else
  # ── Remote check via SSH to macOS host ──
  HOST_USER="${XLIGHTS_HOST_USER:?Set XLIGHTS_HOST_USER to your macOS username}"
  HOST_SHOW="${XLIGHTS_HOST_SHOW_DIR:-$HOME/xlights}"
  SSH_KEY=""
  for key in /home/node/.ssh-host/id_ed25519 /home/node/.ssh-host/id_rsa; do
    if [ -f "$key" ]; then SSH_KEY="$key"; break; fi
  done
  if [ -z "$SSH_KEY" ]; then
    echo "Error: no SSH key found in ~/.ssh-host/ (need id_ed25519 or id_rsa)" >&2
    echo "Ensure macOS Remote Login is enabled and your SSH key exists at ~/.ssh/" >&2
    exit 1
  fi

  # Translate container paths → host paths
  HOST_ARGS=()
  for seq in "$@"; do
    if [[ "$seq" == /home/node/xlights/* ]]; then
      HOST_ARGS+=("${HOST_SHOW}${seq#/home/node/xlights}")
    else
      HOST_ARGS+=("$seq")
    fi
  done

  echo "Checking sequences on macOS host via SSH (${HOST_USER}@host.docker.internal)..."
  ssh -i "$SSH_KEY" "${HOST_USER}@host.docker.internal" \
    /Applications/xLights.app/Contents/MacOS/xLights \
    --checksequence --show="$HOST_SHOW" "${HOST_ARGS[@]}"
fi
