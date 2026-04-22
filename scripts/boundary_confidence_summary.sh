#!/usr/bin/env bash
# Run boundary_confidence_map.py on every song that has a cached hierarchy
# and collect the HTML outputs + summary stats.
#
# Usage:
#   scripts/boundary_confidence_summary.sh           # all analyzed songs
#   scripts/boundary_confidence_summary.sh --no-genius
#
# Outputs:
#   /tmp/bcm/<stem>.html   — per-song timeline
#   /tmp/bcm/<stem>.txt    — per-song text report
#   /tmp/bcm/index.html    — landing page linking to all per-song reports

set -u

OUT_DIR="${OUT_DIR:-/tmp/bcm}"
PY="${PY:-/workspace/.venv-vamp/bin/python}"
SCRIPT="/workspace/scripts/boundary_confidence_map.py"
EXTRA_ARGS="${*:-}"

mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR"/*.html "$OUT_DIR"/*.txt 2>/dev/null

songs=()
for hier in /workspace/songs/*/*/*_hierarchy.json; do
    folder="$(dirname "$(dirname "$hier")")"
    songs+=("$folder")
done

if [[ ${#songs[@]} -eq 0 ]]; then
    echo "No analyzed songs found."
    exit 1
fi

echo "Running boundary confidence map on ${#songs[@]} songs..."
echo

index_rows=""
for folder in "${songs[@]}"; do
    stem="$(basename "$folder")"
    html="$OUT_DIR/$stem.html"
    txt="$OUT_DIR/$stem.txt"
    echo "  → $stem"
    "$PY" "$SCRIPT" "$folder" --html "$html" $EXTRA_ARGS > "$txt" 2>&1
    consensus="$(grep -oE 'High-confidence consensus boundaries.*: [0-9]+' "$txt" | head -1 | grep -oE '[0-9]+$')"
    consensus="${consensus:-?}"
    genius_count="$(grep -oE '^  genius +[0-9]+' "$txt" | awk '{print $2}')"
    genius_count="${genius_count:-0}"
    if grep -q "Genius match rejected" "$txt"; then
        genius_status="rejected"
    elif grep -q "No Genius match" "$txt"; then
        genius_status="no match"
    elif grep -q "Genius matched" "$txt"; then
        genius_status="used ($genius_count)"
    else
        genius_status="—"
    fi
    index_rows+="<tr><td><a href=\"$stem.html\">$stem</a></td><td><a href=\"$stem.txt\">text</a></td><td>$consensus</td><td>$genius_status</td></tr>"
done

cat > "$OUT_DIR/index.html" <<EOF
<!DOCTYPE html><html><head><meta charset="utf-8"><title>Boundary Confidence — all songs</title>
<style>body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:24px}
table{border-collapse:collapse}th,td{padding:6px 12px;border-bottom:1px solid #e2e8f0;text-align:left}
th{background:#f1f5f9}a{color:#2563eb;text-decoration:none}a:hover{text-decoration:underline}</style>
</head><body><h1>Boundary Confidence — all songs</h1>
<p>Per-song timelines and text reports.  The "consensus" column is how many
boundaries had ≥3 sources agreeing.</p>
<table><tr><th>Song</th><th>Report</th><th>Consensus ≥3</th><th>Genius</th></tr>
$index_rows
</table></body></html>
EOF

echo
echo "Done. Open $OUT_DIR/index.html"
