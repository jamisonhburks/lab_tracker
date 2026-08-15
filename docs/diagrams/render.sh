#!/usr/bin/env bash
# Render every extracted .mmd diagram to SVG (vector — best for slides) using mermaid-cli.
# Requires Node; uses npx to fetch @mermaid-js/mermaid-cli on demand (no global install).
# Regenerate the .mmd files first with:  python export.py
# Usage:  ./render.sh          (SVG)      |    FMT=png ./render.sh   (PNG)
set -euo pipefail
cd "$(dirname "$0")"
FMT="${FMT:-svg}"
MMDC=(npx -y @mermaid-js/mermaid-cli@latest)
for f in [0-9][0-9]-*.mmd; do
  out="${f%.mmd}.${FMT}"
  echo "rendering $f -> $out"
  if [ "$FMT" = "png" ]; then
    "${MMDC[@]}" -i "$f" -o "$out" -b white -s 3          # white bg, 3x scale — crisp for projection
  else
    "${MMDC[@]}" -i "$f" -o "$out" -b transparent          # vector — scales losslessly
  fi
done
echo "done: $(ls -1 [0-9][0-9]-*.${FMT} | wc -l | tr -d ' ') diagram(s)"
