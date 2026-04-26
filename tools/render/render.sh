#!/usr/bin/env bash
# Render an .xsq sequence under Xvfb and return when the .fseq is produced.
# Usage: render.sh <show-dir> <sequence.xsq>
set -uo pipefail

SHOW_DIR="${1:?show dir required}"
XSQ="${2:?xsq required}"

echo "[render] show=$SHOW_DIR  xsq=$XSQ"
echo "[render] starting Xvfb on :99"
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!
sleep 1
export DISPLAY=:99

echo "[render] launching xLights -r"
/opt/xlights/xlights/AppRun -r -s "$SHOW_DIR" -m "$SHOW_DIR" "$XSQ" &
XLIGHTS_PID=$!

# xLights -r writes the fseq and exits. Wait up to 5min for completion.
for i in $(seq 1 300); do
    if ! kill -0 "$XLIGHTS_PID" 2>/dev/null; then
        echo "[render] xLights exited"
        break
    fi
    sleep 1
done

if kill -0 "$XLIGHTS_PID" 2>/dev/null; then
    echo "[render] killing xLights after timeout"
    kill -9 "$XLIGHTS_PID" 2>/dev/null || true
fi
kill "$XVFB_PID" 2>/dev/null || true
wait 2>/dev/null

TARGET="${XSQ%.xsq}.fseq"
if [ -f "$TARGET" ]; then
    SIZE=$(stat -c "%s" "$TARGET" 2>/dev/null || stat -f "%z" "$TARGET")
    echo "[render] FSEQ output: $TARGET ($SIZE bytes)"
    exit 0
fi
echo "[render] no FSEQ produced"
exit 1
