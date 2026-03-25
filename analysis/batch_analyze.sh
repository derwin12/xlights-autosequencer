#!/usr/bin/env bash
# Batch-analyze a directory of MP3s using only the algorithms needed
# to validate the musical-analysis-design doc.
#
# Usage: ./analysis/batch_analyze.sh /path/to/mp3s
#
# Algorithms run (4 of 36 — fast pass):
#   bbc_energy    — energy impacts, gaps, dynamic range
#   qm_bars       — beat/bar detection frequency
#   segmentino    — repeat labels, section structure
#   aubio_onset   — onset density

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"

SONGS_DIR="${1:?Usage: $0 /path/to/mp3s}"
ALGORITHMS="bbc_energy,qm_bars,segmentino,aubio_onset"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: venv python not found at $VENV_PYTHON" >&2
    exit 1
fi

echo "=== Batch Analysis ==="
echo "Songs dir:  $SONGS_DIR"
echo "Algorithms: $ALGORITHMS"
echo "Python:     $VENV_PYTHON"
echo ""

count=0
failed=0
total=$(find "$SONGS_DIR" -maxdepth 1 -name '*.mp3' | wc -l | tr -d ' ')

for mp3 in "$SONGS_DIR"/*.mp3; do
    [ -f "$mp3" ] || continue
    count=$((count + 1))
    name=$(basename "$mp3" .mp3)

    # CLI writes to <mp3_parent>/<song_name>/<song_name>_analysis.json
    expected_json="$SONGS_DIR/$name/${name}_analysis.json"

    echo "[$count/$total] $name"

    if [ -f "$expected_json" ]; then
        echo "  -> cached, skipping (delete $expected_json to re-run)"
        continue
    fi

    if "$VENV_PYTHON" -c "from src.cli import cli; cli()" -- analyze "$mp3" \
        --algorithms "$ALGORITHMS" \
        --no-madmom \
        --no-cache \
        2>&1 | sed 's/^/  /'; then
        # Verify output was created
        if [ -f "$expected_json" ]; then
            echo "  -> OK"
        else
            echo "  -> WARNING: output not found at $expected_json"
        fi
    else
        echo "  -> FAILED"
        failed=$((failed + 1))
    fi

    echo ""
done

echo "=== Done: $count songs analyzed ($failed failed) ==="
echo ""
echo "Next: $VENV_PYTHON analysis/batch_report.py $SONGS_DIR"
