#!/usr/bin/env bash
# render_song_for_review.sh — generate + render a song's .xsq under a named suffix.
#
# Used by the tier-layering-policy iteration loop. Run once on `main` to
# capture a baseline, then again on the feature branch to capture a
# treatment. The suffix becomes part of the output filename so both
# pairs can sit alongside each other in the show dir.
#
# Usage:
#   scripts/render_song_for_review.sh <song.mp3> <suffix>
#
# Outputs:
#   $SHOW_DIR/<slug>__<suffix>.xsq
#   $SHOW_DIR/<slug>__<suffix>.fseq
#   $SHOW_DIR/<slug>.mp3        (copied once if absent — referenced by both .xsq)
#
# Env overrides:
#   SHOW_DIR  — default /home/node/xlights
#   LAYOUT    — default $SHOW_DIR/xlights_rgbeffects.xml
set -euo pipefail

if [ $# -ne 2 ]; then
    echo "Usage: $0 <song.mp3> <suffix>" >&2
    echo "  suffix is typically 'baseline' or 'treatment'" >&2
    exit 2
fi

SONG="$1"
SUFFIX="$2"
SHOW_DIR="${SHOW_DIR:-/home/node/xlights}"
LAYOUT="${LAYOUT:-$SHOW_DIR/xlights_rgbeffects.xml}"
SLUG=$(basename "$SONG" .mp3)
OUTDIR="microscope-out-${SLUG}-${SUFFIX}"

if [ ! -f "$SONG" ]; then
    echo "Song not found: $SONG" >&2
    exit 2
fi
if [ ! -f "$LAYOUT" ]; then
    echo "Layout not found: $LAYOUT  (set LAYOUT= to override)" >&2
    exit 2
fi

echo "[1/3] generate via microscope run..."
python3 -c "from src.cli.evaluate import main; main()" \
    microscope run "$SONG" \
    --layout "$LAYOUT" \
    --output-dir "$OUTDIR" 2>&1 | tail -3

SRC_XSQ="$OUTDIR/microscope/$SLUG/$SLUG.xsq"
SRC_MP3="$OUTDIR/microscope/$SLUG/$SLUG.mp3"
DST_XSQ="$SHOW_DIR/${SLUG}__${SUFFIX}.xsq"

if [ ! -f "$SRC_XSQ" ]; then
    echo "Generation did not produce $SRC_XSQ" >&2
    exit 1
fi

echo "[2/3] stage in show dir..."
cp "$SRC_XSQ" "$DST_XSQ"
if [ -f "$SRC_MP3" ] && [ ! -f "$SHOW_DIR/${SLUG}.mp3" ]; then
    cp "$SRC_MP3" "$SHOW_DIR/${SLUG}.mp3"
fi

echo "[3/3] render on host xLights..."
xlights-render.sh "$DST_XSQ"

DST_FSEQ="${DST_XSQ%.xsq}.fseq"
echo
echo "Done:"
echo "  $DST_XSQ"
[ -f "$DST_FSEQ" ] && echo "  $DST_FSEQ" || echo "  (no .fseq — render may have failed)"
