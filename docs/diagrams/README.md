# Diagrams — standalone exports for slides

Every Mermaid diagram in [`../architecture-overview.md`](../architecture-overview.md), extracted to
a standalone file so you can drop it straight into a deck.

- **`NN-*.mmd`** — the Mermaid source (edit-friendly; paste into [mermaid.live](https://mermaid.live)
  or any Mermaid-aware tool).
- **`NN-*.svg`** — rendered vector (scales cleanly in Keynote / PowerPoint / Google Slides).
- **`MANIFEST.txt`** — the ordered list, matching the section order in the overview.

Numbering follows the document: `01` = the parent diagram, `11` = the before/after slide.

## Regenerate

```bash
# 1) re-extract .mmd from the overview (after editing architecture-overview.md)
python export.py

# 2) render every .mmd to SVG (vector; best for slides).  FMT=png ./render.sh for PNG.
./render.sh
```

`render.sh` uses `npx @mermaid-js/mermaid-cli` — no global install needed, just Node. Only the
`.mmd` files are the source of truth; the `.svg` files are build artifacts committed for convenience
(so reviewers without Node can preview them).
