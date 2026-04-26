#!/usr/bin/env bash
# Build the xlights-render Docker image.
#
# - Downloads the official xLights AppImage (linux/amd64) if missing
# - Extracts the appended squashfs to ./xlights/ (gitignored)
# - Builds the image with --platform linux/amd64 (Rosetta on Apple Silicon)
#
# Usage: ./build.sh [release-tag]   (defaults to 2026.06)
set -euo pipefail

RELEASE="${1:-2026.06}"
ASSET_URL="https://github.com/xLightsSequencer/xLights/releases/download/${RELEASE}/xLights-${RELEASE}-x86_64.AppImage"

cd "$(dirname "$0")"

if [ ! -f "xLights.AppImage" ]; then
    echo "[build] downloading xLights ${RELEASE} AppImage..."
    curl -fL --progress-bar -o xLights.AppImage "$ASSET_URL"
fi

if [ ! -d "xlights" ]; then
    echo "[build] extracting squashfs from AppImage..."
    OFFSET=$(python3 -c "
import struct
with open('xLights.AppImage', 'rb') as f:
    data = f.read(64)
e_shoff = struct.unpack_from('<Q', data, 0x28)[0]
e_shentsize = struct.unpack_from('<H', data, 0x3a)[0]
e_shnum = struct.unpack_from('<H', data, 0x3c)[0]
print(e_shoff + e_shentsize * e_shnum)
")
    dd if=xLights.AppImage of=xlights.squashfs bs=1 skip="$OFFSET" status=none
    if ! command -v unsquashfs >/dev/null; then
        echo "[build] need unsquashfs — install with 'brew install squashfs'" >&2
        exit 1
    fi
    unsquashfs -d xlights xlights.squashfs >/dev/null
    rm xlights.squashfs
fi

echo "[build] docker build (linux/amd64)..."
docker build --platform linux/amd64 -t xlights-render .
echo "[build] image ready: xlights-render"
echo
echo "  Render a sequence:"
echo "    docker run --rm --platform linux/amd64 \\"
echo "      -v <show-dir>:/work xlights-render \\"
echo "      /work \"/work/<sequence>.xsq\""
