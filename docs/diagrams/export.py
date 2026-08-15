"""export — extract every Mermaid diagram from the architecture overview into standalone .mmd files.

Reproducible: re-run after editing docs/architecture-overview.md to refresh docs/diagrams/*.mmd.
Each block is named by its nearest preceding heading, numbered in document order. Render to SVG/PNG
with render.sh (mermaid-cli) — see docs/diagrams/README.md.
"""
import re
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE.parent / "architecture-overview.md"


def _slug(text: str) -> str:
    text = re.sub(r"^#+\s*", "", text).strip().lower()
    text = re.sub(r"^\d+(\.\d+)?\s*[·.]?\s*", "", text)        # drop leading "2.1 · "
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "diagram"


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    heading, blocks, buf, in_block = "diagram", [], [], False
    for ln in lines:
        if not in_block and ln.startswith("#"):
            heading = _slug(ln)
        if ln.strip().startswith("```mermaid"):
            in_block, buf = True, []
            continue
        if in_block and ln.strip() == "```":
            blocks.append((heading, "\n".join(buf)))
            in_block = False
            continue
        if in_block:
            buf.append(ln)

    manifest = []
    for i, (name, body) in enumerate(blocks, 1):
        fname = f"{i:02d}-{name}.mmd"
        (HERE / fname).write_text(body + "\n", encoding="utf-8")
        manifest.append(fname)
    (HERE / "MANIFEST.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    print(f"exported {len(blocks)} diagram(s) → {HERE}/")
    for m in manifest:
        print("  " + m)


if __name__ == "__main__":
    main()
