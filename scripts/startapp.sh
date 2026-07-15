#!/usr/bin/env bash
# Restart the xlight-review server running inside the xlight-dev devcontainer.
# The server does not hot-reload backend Python changes, so this must be run
# after every commit before testing through http://localhost:5000.
#
# Works from two places:
#   - The Windows host (Git Bash etc.): uses `docker exec` against the
#     xlight-dev container.
#   - A shell already inside the xlight-dev container (e.g. VS Code's
#     "Open in terminal" on the container): runs the commands directly,
#     since there's no `docker` CLI (or container to exec into) in there.
set -euo pipefail

CONTAINER="xlight-dev"
PORT=5000

if command -v docker &>/dev/null; then
  echo "Stopping any running xlight-review process in $CONTAINER..."
  docker exec "$CONTAINER" pkill -f xlight-review || true

  echo "Starting xlight-review..."
  MSYS_NO_PATHCONV=1 docker exec -d "$CONTAINER" /usr/bin/python3 /home/node/.local/bin/xlight-review --dev --host 0.0.0.0 --port "$PORT"
else
  echo "docker CLI not found — assuming this shell is already inside $CONTAINER."
  echo "Stopping any running xlight-review process..."
  pkill -f xlight-review || true

  echo "Starting xlight-review..."
  nohup /usr/bin/python3 /home/node/.local/bin/xlight-review --dev --host 0.0.0.0 --port "$PORT" >/tmp/xlight-review.log 2>&1 &
  disown
fi

echo -n "Waiting for server to come up"
for _ in $(seq 1 15); do
  if curl -s -o /dev/null "http://localhost:$PORT/"; then
    echo ""
    echo "xlight-review is up at http://localhost:$PORT/"
    exit 0
  fi
  echo -n "."
  sleep 1
done

echo ""
echo "Warning: server did not respond within 15s. Check with:"
if command -v docker &>/dev/null; then
  echo "  docker exec $CONTAINER ps aux | grep xlight-review"
else
  echo "  ps aux | grep xlight-review"
  echo "  cat /tmp/xlight-review.log"
fi
exit 1
