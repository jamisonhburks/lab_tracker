#!/usr/bin/env bash
# run_shared.sh — start the SHARED substrate service for a trusted internal alpha (one command).
#
# This is the minimal, no-TLS version: one HTTP node that every collaborator's Claude connects to,
# so they share ONE brain and their tickets/work land centrally. Run it on a node your collaborators
# can reach, from a clone on SHARED filesystem (so register_project paths resolve for everyone).
#
#   ./run_shared.sh                      # binds 0.0.0.0:8765, SUBSTRATE_SCOPE=shared
#   MCP_PORT=9000 KG_BACKEND=hetionet ./run_shared.sh
#
# ⚠ No TLS and no auth: attribution trusts each client's X-Substrate-Contributor header. Fine for a
#   trusted internal alpha on a private network; move to the reverse-proxy setup (ADMIN.md §A /
#   docs/deployment.md) before it's a real multi-writer lab.
set -euo pipefail
cd "$(dirname "$0")"

if [ -n "${SUBSTRATE_PYTHON:-}" ] && command -v "$SUBSTRATE_PYTHON" >/dev/null 2>&1; then
  PY="$SUBSTRATE_PYTHON"
elif [ -x ".venv/bin/python" ]; then
  PY="$(pwd)/.venv/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PY="$VIRTUAL_ENV/bin/python"
else
  PY="$(command -v python3 || command -v python)"
fi

export MCP_TRANSPORT=http
export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT="${MCP_PORT:-8765}"
export SUBSTRATE_SCOPE=shared
export KG_BACKEND="${KG_BACKEND:-demo}"          # demo is tiny/fast; hetionet|combined for real KG queries

echo "Shared substrate → http://${MCP_HOST}:${MCP_PORT}/mcp   (scope=shared, KG=${KG_BACKEND})"
echo "Hand collaborators examples/mcp.shared-dev.json with this URL + their name. Ctrl-C to stop."
exec "$PY" mcp_server.py
