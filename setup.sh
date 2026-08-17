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

Done. Solo test (the default — no token, no shared node):
  1) open this folder in VS Code (or Reload Window if it's already open)
  2) approve the "lab" MCP server when Claude Code prompts
  3) in the Claude Code chat, say:  onboard me

Joining a shared lab instead? (see QUICKSTART.md)
  cp examples/mcp.shared.json .mcp.json      # two servers: lab-shared + my-personal
  export LAB_SUBSTRATE_TOKEN=<token>         # from the lab admin; add to ~/.bashrc
EOF
