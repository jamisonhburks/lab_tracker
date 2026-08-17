#!/usr/bin/env bash
# Launch the PERSONAL substrate MCP server with the best available Python interpreter, so the
# .mcp.json `my-personal` entry works regardless of how a member manages Python (venv / conda /
# modules). Resolution order:
#   SUBSTRATE_PYTHON (explicit override) → repo .venv → active $VIRTUAL_ENV → python3 → python
set -euo pipefail
cd "$(dirname "$0")"

if [ -n "${SUBSTRATE_PYTHON:-}" ] && command -v "$SUBSTRATE_PYTHON" >/dev/null 2>&1; then
  PY="$SUBSTRATE_PYTHON"
elif [ -x ".venv/bin/python" ]; then
  PY="$(pwd)/.venv/bin/python"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PY="$VIRTUAL_ENV/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  PY="python"
fi

export SUBSTRATE_SCOPE="${SUBSTRATE_SCOPE:-personal}"
exec "$PY" mcp_server.py
