#!/usr/bin/env bash
# Parallel batch analysis for multiple MP3s.
#
# Runs `xlight-analyze analyze` + `xlight-analyze story` for every MP3 under
# songs/ that doesn't already have a cached hierarchy.json. Runs up to
# $WORKERS songs concurrently (default 2).
#
# Logs per-song stdout/stderr to /tmp/batch_analyze/<song>.log
# Prints one-line status per song as they complete.
#
# Usage:
#   scripts/batch_analyze_parallel.sh          # 2 workers, all missing
#   WORKERS=3 scripts/batch_analyze_parallel.sh # override worker count

set -u

WORKERS="${WORKERS:-2}"
XLIGHT="${XLIGHT:-/workspace/.venv-vamp/bin/xlight-analyze}"
SONGS_DIR="${SONGS_DIR:-/workspace/songs}"
LOG_DIR="/tmp/batch_analyze"

mkdir -p "$LOG_DIR"

# Find MP3s that don't have a cached hierarchy.json
queue=()
for mp3 in "$SONGS_DIR"/*/*.mp3; do
    folder="$(dirname "$mp3")"
    stem="$(basename "$mp3" .mp3)"
    hier="$folder/$stem/${stem}_hierarchy.json"
    if [[ ! -f "$hier" ]]; then
        queue+=("$mp3")
    fi
done

if [[ ${#queue[@]} -eq 0 ]]; then
    echo "All songs already have cached hierarchy.json — nothing to do."
    exit 0
fi

echo "Queue: ${#queue[@]} songs, $WORKERS concurrent workers"
echo "Logs:  $LOG_DIR/<stem>.log"
echo

run_one() {
    local mp3="$1"
    local stem
    stem="$(basename "$mp3" .mp3)"
    local log="$LOG_DIR/${stem}.log"
    local start
    start=$(date +%s)

    {
        echo "=== analyze $mp3 ==="
        "$XLIGHT" analyze "$mp3" 2>&1
        echo
        echo "=== story $mp3 ==="
        "$XLIGHT" story "$mp3" 2>&1
    } > "$log" 2>&1
    local rc=$?

    local elapsed=$(( $(date +%s) - start ))
    if [[ $rc -eq 0 ]]; then
        printf "  OK   %4ds  %s\n" "$elapsed" "$stem"
    else
        printf "  FAIL %4ds  %s  (see %s)\n" "$elapsed" "$stem" "$log"
    fi
    return $rc
}

export -f run_one
export XLIGHT LOG_DIR

printf '%s\n' "${queue[@]}" | xargs -P "$WORKERS" -I{} bash -c 'run_one "$@"' _ {}

echo
echo "Done."
