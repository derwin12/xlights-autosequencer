#!/usr/bin/env bash
# Restart the xlight-review server running inside a devcontainer.
# The server does not hot-reload backend Python changes, so this must be run
# after every commit before testing through http://localhost:5000.
#
# Works from two places:
#   - The Windows host (Git Bash etc.): uses `docker exec` against the
#     devcontainer.
#   - A shell already inside the devcontainer (e.g. VS Code's "Open in
#     terminal" on the container): runs the commands directly, since
#     there's no `docker` CLI (or container to exec into) in there.
set -euo pipefail

# "xlight-dev" is this project's own dev container name (not something
# VS Code's Dev Containers extension guarantees for anyone else -- it
# auto-generates its own name per workspace, so a fresh clone's container
# will be called something else entirely). Override with
# XLIGHT_DEVCONTAINER_NAME=<name> if yours differs; find it with
# `docker ps` (look for the image built from .devcontainer/Dockerfile).
CONTAINER="${XLIGHT_DEVCONTAINER_NAME:-xlight-dev}"
PORT=5000

if command -v docker &>/dev/null; then
  if ! docker inspect "$CONTAINER" &>/dev/null; then
    echo "Error: no container named '$CONTAINER' found."
    echo "Run 'docker ps' to find your devcontainer's actual name, then either:"
    echo "  export XLIGHT_DEVCONTAINER_NAME=<your-container-name>"
    echo "and re-run this script, or pass it inline:"
    echo "  XLIGHT_DEVCONTAINER_NAME=<your-container-name> $0"
    exit 1
  fi

  echo "Stopping any running xlight-review process in $CONTAINER..."
  docker exec "$CONTAINER" pkill -f xlight-review || true

  echo "Starting xlight-review..."
  # `docker exec -d` output goes nowhere on its own -- it's not captured by
  # `docker logs` (that only shows the container's PID 1 stdout), so without
  # an explicit redirect the server's logs are simply unavailable. Route to
  # a file so `docker exec xlight-dev tail -f /tmp/xlight-review.log` works.
  MSYS_NO_PATHCONV=1 docker exec -d "$CONTAINER" sh -c \
    "/usr/bin/python3 /home/node/.local/bin/xlight-review --dev --host 0.0.0.0 --port $PORT >/tmp/xlight-review.log 2>&1"
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
  echo "  docker exec $CONTAINER cat /tmp/xlight-review.log"
else
  echo "  ps aux | grep xlight-review"
  echo "  cat /tmp/xlight-review.log"
fi
exit 1
