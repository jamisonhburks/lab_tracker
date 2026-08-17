#!/usr/bin/env bash
# setup.sh — one-time deps for a lab member using Claude in VS Code.
# No Ollama, no API keys: Claude Code is the model; this only installs the substrate + MCP server
# your personal stdio server (.mcp.json → my-personal) runs from. Idempotent.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "error: '$PY' not found. Set PYTHON=<your python3> and re-run (module load / conda first)." >&2
  exit 1
fi

echo "→ creating .venv with $($PY --version 2>&1) ..."
"$PY" -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
echo "→ installing requirements + fastmcp ..."
./.venv/bin/pip install --quiet -r requirements.txt

echo "→ sanity check (personal MCP server imports) ..."
if ./.venv/bin/python -c "import fastmcp" 2>/dev/null; then
  echo "  fastmcp OK"
else
  echo "  warning: fastmcp not importable — the personal server won't start." >&2
fi

cat <<'EOF'

Done. Next:
  1) export LAB_SUBSTRATE_TOKEN=<your token>     # from the lab admin; add to ~/.bashrc
  2) open this folder in VS Code:  code .
  3) in the Claude Code chat, say:  onboard me

If Claude Code prompts to approve MCP servers (lab-shared, my-personal), approve both.
EOF
