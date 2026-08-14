#!/usr/bin/env python3
"""scaffold — automate the MECHANICAL parts of the lab-standard onboarding flows.

The `lab-standard/` playbook has an agent read rules and hand-create a project's dir tree +
template files (see `lab-standard/new-project.md` / `conform-project.md`). That copy-and-fill
work is deterministic, so it lives here — leaving the THINKING (substrate grounding, novelty
checks, actual hypotheses) to the agent, which is the whole point of the split.

    python scaffold.py new "Glaucoma Genetics in UK Biobank" \
        --slug glaucoma-genetics --modality genomic [--dest ../glaucoma-genetics] [--git-init]

    python scaffold.py conform ../some-existing-project [--title "..."]

`new`     builds the standard tree, drops CLAUDE.md + README.md (placeholders filled) + a
          .gitignore + a charter stub that tells the next session which substrate checks to run.
`conform` is NON-DESTRUCTIVE: creates only missing standard dirs, drops CLAUDE.md/README/
          audit-stub only if absent, and never touches existing files.

Stdlib only; no dependencies. Idempotent: existing files are never overwritten (use --force).
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATES = ROOT / "lab-standard" / "templates"
STD_DIRS = [
    "data/raw", "data/processed", "data/external",
    "hypotheses", "experiments", "reports", "campaigns",
    "notes", "literature", "src",
]
GITIGNORE = """# de-identified data never enters version control
data/raw/
data/processed/
__pycache__/
*.pyc
.DS_Store
"""


def _fill(template_name: str, repl: dict) -> str:
    text = (TEMPLATES / template_name).read_text(encoding="utf-8")
    for k, v in repl.items():
        text = text.replace(k, v)
    return text


def _write(path: Path, content: str, force: bool, made: list, skipped: list) -> None:
    if path.exists() and not force:
        skipped.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    made.append(path)


def _charter_stub(title: str) -> str:
    return f"""# Charter — {title}  (local semantic · private)

*Tier 1 (local semantic). Private thinking, un-gated. Scaffolded by `scaffold.py`; the
substrate grounding below is a CHECKLIST for the next session to actually run — not results.*

## The question and the strategy

{{{{State the scientific question and why it matters. What data/modality? Exploratory or
targeted? If targeted, go straight to `hypothesis-workflow.md` and write H001.}}}}

## Substrate grounding — RUN THESE before committing to a direction
(see `lab-standard/using-the-substrate.md`; record findings here)

- [ ] `list_active_work()` — is the lab already doing this? Don't duplicate.
- [ ] `query_curated_findings(object="<disease/target>")` — already concluded?
- [ ] `ground_claim(subject, object)` / `find_paths(...)` — mechanistic path in the KG?
- [ ] `calibrate_link(...)` — stronger than degree-matched random, or a hub artifact?
- [ ] `check_novelty(...)` — published (rediscovery) or a new juxtaposition? Be honest.

## Surviving candidate directions → hypotheses

| Dir | Test | Novelty verdict | → |
|-----|------|-----------------|---|
|  1  |      |                 | H001 |
"""


def cmd_new(args) -> int:
    title = args.title
    slug = args.slug or _slugify(title)
    dest = Path(args.dest).resolve() if args.dest else (ROOT.parent / slug).resolve()
    substrate_rel = os.path.relpath(ROOT, dest)
    modality = args.modality or "tabular | ehr-events | ehr-tabular | waveform | genomic | ml-methods | mixed"

    made, skipped = [], []
    for d in STD_DIRS:
        (dest / d).mkdir(parents=True, exist_ok=True)

    claude = _fill("project-CLAUDE.md", {
        "{{PROJECT_TITLE}}": title,
        "{{SUBSTRATE_PATH}}": substrate_rel,
    })
    readme = _fill("project-README.md", {
        "{{PROJECT_TITLE}}": title,
        "{{tabular | ehr-events | ehr-tabular | waveform | genomic | ml-methods | mixed}}": modality,
        "`scaffolding | active | paused | complete`": "`scaffolding`",
    })
    _write(dest / "CLAUDE.md", claude, args.force, made, skipped)
    _write(dest / "README.md", readme, args.force, made, skipped)
    _write(dest / ".gitignore", GITIGNORE, args.force, made, skipped)
    _write(dest / "notes" / "00_charter.md", _charter_stub(title), args.force, made, skipped)

    if args.git_init and not (dest / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=dest, check=False)

    _report(dest, made, skipped)
    print(f"\nNext: open {os.path.relpath(dest)}/notes/00_charter.md and run the substrate "
          f"checks, then follow {substrate_rel}/lab-standard/hypothesis-workflow.md.")
    return 0


def cmd_conform(args) -> int:
    dest = Path(args.path).resolve()
    if not dest.exists():
        print(f"error: {dest} does not exist (conform operates on an EXISTING project).",
              file=sys.stderr)
        return 2
    title = args.title or dest.name
    substrate_rel = os.path.relpath(ROOT, dest)

    made, skipped = [], []
    for d in STD_DIRS:                       # create only missing standard dirs
        p = dest / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            made.append(p)

    claude = _fill("project-CLAUDE.md",
                   {"{{PROJECT_TITLE}}": title, "{{SUBSTRATE_PATH}}": substrate_rel})
    _write(dest / "CLAUDE.md", claude, args.force, made, skipped)
    if not (dest / "README.md").exists() or args.force:
        readme = _fill("project-README.md", {"{{PROJECT_TITLE}}": title})
        _write(dest / "README.md", readme, args.force, made, skipped)
    audit = (f"# Conformance audit — {title}  (local semantic)\n\n"
             "Map every EXISTING artifact → its standard destination + new name + tier, and\n"
             "show this to a human BEFORE moving anything. Follow "
             f"{substrate_rel}/lab-standard/conform-project.md.\n\n"
             "| original path | → destination (H{NNN}) | tier | status | notes |\n"
             "|---|---|---|---|---|\n|  |  |  |  |  |\n")
    _write(dest / "notes" / "00_conformance_audit.md", audit, args.force, made, skipped)

    _report(dest, made, skipped)
    print(f"\nNon-destructive. Nothing existing was moved. Next: fill "
          f"{os.path.relpath(dest)}/notes/00_conformance_audit.md, then execute "
          f"{substrate_rel}/lab-standard/conform-project.md.")
    return 0


def _slugify(title: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in title)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def _report(dest: Path, made: list, skipped: list) -> None:
    print(f"scaffold → {dest}")
    for p in made:
        tag = "dir " if p.is_dir() else "file"
        print(f"  + {tag} {p.relative_to(dest)}")
    for p in skipped:
        print(f"  · kept {p.relative_to(dest)} (exists; --force to overwrite)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Scaffold a lab-standard project.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", help="scaffold a brand-new project")
    n.add_argument("title", help='e.g. "Glaucoma Genetics in UK Biobank"')
    n.add_argument("--slug", help="dir name (default: slugified title)")
    n.add_argument("--dest", help="destination path (default: ../<slug>, sibling of substrate)")
    n.add_argument("--modality", help="tabular | ehr-events | ehr-tabular | waveform | genomic | ml-methods | mixed")
    n.add_argument("--git-init", action="store_true", help="git init the new project")
    n.add_argument("--force", action="store_true", help="overwrite existing files")
    n.set_defaults(func=cmd_new)

    c = sub.add_parser("conform", help="add standard scaffolding to an EXISTING project (non-destructive)")
    c.add_argument("path", help="path to the existing project")
    c.add_argument("--title", help="project title (default: dir name)")
    c.add_argument("--force", action="store_true", help="overwrite existing CLAUDE.md/README")
    c.set_defaults(func=cmd_conform)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
