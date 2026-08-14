# ADR-0034: `scaffold.py` — automate the mechanical half of onboarding

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
ADR-0033 added the `lab-standard/` playbook: agent-followable rules for scaffolding a new
project or conforming an existing one. Running the glaucoma-genetics demo through those flows
by hand showed that a large, *deterministic* slice of the work — create the standard dir tree,
copy `templates/project-CLAUDE.md` + `project-README.md`, fill `{{PROJECT_TITLE}}` /
`{{SUBSTRATE_PATH}}` / modality, drop a `.gitignore` and a charter stub — is pure boilerplate.
Having the agent hand-create ~a dozen files each time is slow, error-prone (a mis-typed
substrate path or a skipped dir silently breaks the promotion tooling that keys off exact
names), and wastes the model on work a script does perfectly.

## Decision
Add **`scaffold.py`** (repo root, stdlib-only, no dependencies) with two subcommands that
execute the mechanical steps of the playbook — and *only* those:

- **`new "<title>" [--slug --dest --modality --git-init --force]`** — build the standard tree,
  write `CLAUDE.md` + `README.md` (placeholders filled; status set to `scaffolding`), a
  `.gitignore`, and `notes/00_charter.md` — a **stub that lists the substrate checks for the
  next session to run**, not results. Default `--dest` is a sibling `../<slug>` (matching
  `new-project.md`); the substrate path in `CLAUDE.md` is computed with `os.path.relpath`.
- **`conform <path> [--title --force]`** — **non-destructive**: create only missing standard
  dirs, drop `CLAUDE.md` / `README.md` / `notes/00_conformance_audit.md` only if absent, and
  never move or overwrite existing files (the audit-then-move thinking stays with the agent).

Idempotent by default (existing files are kept and reported, `--force` to overwrite).

## Rationale & evidence
- **The mechanical/thinking split is the whole design.** `scaffold.py` does copy-and-fill;
  it deliberately does **not** ground claims, check novelty, or write hypotheses. The charter
  and audit files it emits are *checklists that hand control back to the agent* — so the
  script speeds up boilerplate without ever pretending to do science.
- **Names are load-bearing.** `list_active_work` and the `provenance://` / `report://`
  resources key off exact dir/file names (ADR-0033 / `project-structure.md`). A script that
  always produces the canonical layout removes a silent failure mode of hand-scaffolding.
- **Non-destructive `conform` matches the playbook's "librarian, not experimenter" rule** —
  it stages structure around existing work without touching it, verified against a project
  containing a stray file (left untouched) and pre-existing dirs (skipped).
- **Verified**: `new` fills title/modality/relative-substrate-path and sets status
  `scaffolding`; re-running keeps all files (idempotent); `conform` adds only missing pieces
  and leaves stray/existing files in place; `scaffold.py` parses clean; zero new dependencies.

## Consequences
- The `new-project.md` / `conform-project.md` flows now open with a one-command step, with
  the manual checklist retained as the fallback and as the description of what the script does.
- Onboarding a project is seconds of boilerplate + the agent's judgement, not a dozen manual
  file writes. The glaucoma-genetics project is the reference output shape.
- Future nicety (not done): a `--dry-run` and a `check` subcommand that lints an existing
  project against `project-structure.md` (missing gates, un-named artifacts, absent provenance).
