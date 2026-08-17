"""conform — NON-DESTRUCTIVE conformance of an existing project to the lab_tracker layout.

The hard guarantee (enforced in code, not just documented): conforming someone's existing project
NEVER edits a file's contents and NEVER deletes their work. It only

  1. AUDITS  — inventories every artifact and proposes keep/move/leave/skip + a destination, so a
               human can see what is actually necessary to keep and where it should go; and
  2. MOVES   — relocates ONLY the artifacts a reviewed plan marks `move`, refusing to overwrite
               anything, preferring `git mv` (tracked + trivially reversible) and otherwise COPYING
               (additive — the original is left untouched), always recording a reversible manifest.

Reorganize, don't rewrite. Audit, don't destroy. When unsure, copy-and-keep rather than move-and-risk.

Phases (nothing in the source is touched until you run `apply` on a plan you have reviewed):

    python conform.py plan  <project>                 # DRY RUN → conform_plan.json + audit.md
    python conform.py apply <project> [--git-mv|--copy]# execute ONLY reviewed `move` rows
    python conform.py undo  <project>                 # reverse the last apply from the manifest

The tool never assigns H{NNN} science structure — it stages research artifacts into `_unsorted/`
buckets and leaves the intelligent grouping to the human/agent (who use the same safe moves).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PLAN_NAME = "conform_plan.json"
MANIFEST_NAME = "conform_manifest.json"
AUDIT_NAME = "notes/00_conformance_audit.md"

# code that may hardcode relative data paths — relocating it silently breaks those paths
_CODE_SUFFIX = {".py", ".r", ".sh", ".sbatch", ".pl", ".rb", ".jl", ".ipynb", ".sql", ".m", ".do"}
_BIG_COPY = 1 * 1024**3        # warn once the untracked-copy total crosses ~1 GB

# Never MOVE these — they are not research artifacts. We do not delete them either; we simply
# leave them where they are (SKIP) or keep them in place as project infrastructure (LEAVE).
_SKIP_DIRS = {"__pycache__", ".ipynb_checkpoints", ".venv", "venv", "node_modules",
              ".mypy_cache", ".pytest_cache", ".git", "dist", "build"}
_SKIP_SUFFIX = {".pyc", ".pyo", ".DS_Store"}
_SKIP_NAMES = {".DS_Store"}
_LEAVE_NAMES = {".gitignore", ".gitattributes", "license", "license.md", "license.txt",
                "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "makefile",
                "dockerfile", ".env", ".env.example", "conform_plan.json", "conform_manifest.json"}

# lab_tracker standard dirs (created if missing; artifacts staged into _unsorted/ for human ID-ing)
_DATA_SUFFIX = {".csv", ".tsv", ".parquet", ".feather", ".h5", ".hdf5", ".npy", ".npz",
                ".json", ".jsonl", ".xlsx", ".dta", ".sav", ".fasta", ".vcf", ".bed"}
_FIG_SUFFIX = {".png", ".pdf", ".svg", ".jpg", ".jpeg", ".tiff", ".eps"}
_DOC_SUFFIX = {".md", ".rst", ".txt", ".docx", ".tex"}


# --------------------------------------------------------------------------- #
# Inventory + classification (advisory — the human edits the plan)             #
# --------------------------------------------------------------------------- #
def _rel(p: Path, root: Path) -> str:
    return str(p.relative_to(root))


def classify(path: Path, root: Path) -> dict:
    """Propose an action for one file. Actions: move | leave | skip | review.
    Only `move` ever relocates; leave/skip/review never touch the file."""
    rel = _rel(path, root)
    parts = path.relative_to(root).parts
    name = path.name.lower()
    suf = path.suffix.lower()

    if any(seg in _SKIP_DIRS for seg in parts) or suf in _SKIP_SUFFIX or name in _SKIP_NAMES:
        return {"path": rel, "action": "skip", "dest": None,
                "reason": "generated/cache/vcs artifact — not needed; left in place, not deleted"}
    if name in _LEAVE_NAMES or name == "readme.md" or ".lab-standard" in name:
        return {"path": rel, "action": "leave", "dest": None,
                "reason": "project infrastructure / scaffold merge-aid — kept in place"}

    # already in a standard location? leave it.
    top = parts[0] if parts else ""
    if top in {"hypotheses", "experiments", "reports", "notebooks", "notes", "data", "src",
               "campaigns", "literature", "logs"}:
        return {"path": rel, "action": "leave", "dest": None,
                "reason": f"already under standard dir `{top}/`"}

    raw_ctx = any("raw" in seg.lower() for seg in parts[:-1])
    if suf == ".ipynb":
        dest = f"notebooks/{path.name}"
    elif suf == ".py":
        dest = f"experiments/_unsorted/{rel}"          # agent assigns H{NNN} later
    elif suf in _DATA_SUFFIX:
        dest = f"data/{'raw' if raw_ctx else 'processed'}/_unsorted/{path.name}"
    elif suf in _FIG_SUFFIX:
        dest = f"reports/figures/_unsorted/{path.name}"
    elif suf in _DOC_SUFFIX:
        dest = f"reports/_unsorted/{path.name}"
    else:
        return {"path": rel, "action": "review", "dest": None,
                "reason": f"unrecognized artifact ({suf or 'no ext'}) — human decides keep/move"}

    note = "research artifact → staged; assign H{NNN}/keep decision on review"
    if raw_ctx:
        note += "; RAW data — mark read-only, never modify (CLAUDE.md)"
    return {"path": rel, "action": "move", "dest": dest, "reason": note}


def inventory(root: Path) -> list:
    rows = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rows.append(classify(p, root))
    return rows


# --------------------------------------------------------------------------- #
# Plan (DRY RUN — touches nothing in the source)                               #
# --------------------------------------------------------------------------- #
def _human_bytes(n: int) -> str:
    x = float(n)
    for u in ("B", "K", "M", "G", "T"):
        if x < 1024 or u == "T":
            return f"{x:.0f}{u}" if u == "B" else f"{x:.1f}{u}"
        x /= 1024
    return f"{x:.1f}T"


def _hardcodes_parent_path(p: Path) -> bool:
    """True if a code file references a parent-relative path (`../…`) — relocating breaks it."""
    try:
        return bool(re.search(r"\.\./", p.read_text(encoding="utf-8", errors="ignore")))
    except Exception:
        return False


def _enrich_and_flag(root: Path, rows: list) -> dict:
    """Annotate each `move` row with method (git-mv vs COPY) + byte size, and DOWNGRADE code that
    hardcodes `../` paths to `review` (relocating would silently break it and conform can't edit
    files to fix it). Returns a summary so the audit can warn about the real copy hazard up front."""
    git = _is_git_repo(root)
    copy_bytes = will_copy = will_gitmv = relpath_flagged = 0
    for r in rows:
        if r.get("action") != "move":
            continue
        src = root / r["path"]
        if src.suffix.lower() in _CODE_SUFFIX and _hardcodes_parent_path(src):
            r["action"], r["dest"] = "review", None
            r["reason"] = ("hardcodes `../` path(s) — relocating would break it and conform can't "
                           "edit files to fix it; review (leave in place, or fix paths first)")
            relpath_flagged += 1
            continue
        try:
            size = src.stat().st_size
        except OSError:
            size = 0
        tracked = git and _is_tracked(root, r["path"])
        r["method"], r["bytes"] = ("git-mv" if tracked else "copy"), size
        if tracked:
            will_gitmv += 1
        else:
            will_copy += 1
            copy_bytes += size
    return {"will_gitmv": will_gitmv, "will_copy": will_copy, "copy_bytes": copy_bytes,
            "relpath_flagged": relpath_flagged, "big_copy": copy_bytes >= _BIG_COPY}


def plan(root: Path) -> dict:
    rows = inventory(root)
    summary = _enrich_and_flag(root, rows)      # may downgrade move→review; annotates method/bytes
    counts: dict = {}
    for r in rows:
        counts[r["action"]] = counts.get(r["action"], 0) + 1
    plan_obj = {"project": str(root), "generated_by": "conform.py plan",
                "guarantee": "no source file is edited or deleted; only `move` rows relocate, "
                             "refusing overwrite, recorded reversibly",
                "counts": counts, "summary": summary, "artifacts": rows}
    (root / PLAN_NAME).write_text(json.dumps(plan_obj, indent=2), encoding="utf-8")
    _write_audit(root, plan_obj)
    return plan_obj


def _write_audit(root: Path, plan_obj: dict) -> None:
    c = plan_obj["counts"]
    lines = [
        "# Conformance audit (proposed — nothing has been moved)", "",
        f"Project: `{plan_obj['project']}`", "",
        "**Guarantee:** conform.py never edits or deletes your files. Only rows marked `move` "
        "below will relocate, and only after you review this plan and run `conform.py apply`. "
        "Moves prefer `git mv` (reversible) or else COPY (your original stays). Run "
        "`conform.py undo` to reverse.", "",
        f"- move: {c.get('move', 0)}  ·  leave: {c.get('leave', 0)}  ·  "
        f"skip: {c.get('skip', 0)}  ·  review: {c.get('review', 0)}", "",
    ]
    s = plan_obj.get("summary", {})
    copy_h = _human_bytes(s.get("copy_bytes", 0))
    warn = "  ⚠️ **large — this duplicates data on disk**" if s.get("big_copy") else ""
    lines += [
        f"**Move method:** {s.get('will_gitmv', 0)} tracked file(s) `git mv` (reversible); "
        f"**{s.get('will_copy', 0)} untracked file(s) will COPY (~{copy_h} duplicated){warn}**. "
        "Untracked files can't be `git mv`'d, so `apply` copies them — your original stays, but the "
        "bytes are written twice. If that's a lot, downgrade those rows to `leave` and index them by "
        "path instead.", "",
        f"**Relative-path safety:** {s.get('relpath_flagged', 0)} code file(s) hardcoding `../` "
        "paths were auto-downgraded to `review` — relocating them would break those paths (conform "
        "can't edit files to fix them).", "",
        "Edit `conform_plan.json` to correct any destination or change an action to `leave`/`skip` "
        "before applying. `review` rows are NOT moved until you set them to `move` with a dest.", "",
        "| artifact | action | method | size | → destination | why |",
        "|---|---|---|--:|---|---|",
    ]
    for r in plan_obj["artifacts"]:
        method = r.get("method") or ("—" if r["action"] != "move" else "?")
        size = _human_bytes(r["bytes"]) if r.get("bytes") is not None and r["action"] == "move" else "—"
        lines.append(f"| `{r['path']}` | {r['action']} | {method} | {size} | "
                     f"{('`'+r['dest']+'`') if r['dest'] else '—'} | {r['reason']} |")
    p = root / AUDIT_NAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# Safe relocation primitives — the enforced guardrails                         #
# --------------------------------------------------------------------------- #
class ConformError(RuntimeError):
    pass


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_git_repo(root: Path) -> bool:
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
                           capture_output=True, text=True)
        return r.returncode == 0 and r.stdout.strip() == "true"
    except Exception:
        return False


def _is_tracked(root: Path, rel: str) -> bool:
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", rel],
                           capture_output=True, text=True)
        return r.returncode == 0
    except Exception:
        return False


def safe_relocate(root: Path, src_rel: str, dst_rel: str, *, prefer_git: bool) -> dict:
    """Relocate ONE artifact under `root`, enforcing every safety invariant.

    - refuses if the source is missing or the destination already exists (NO overwrite);
    - `git mv` for tracked files (true move, reversible); otherwise COPY (original kept);
    - copies are byte-verified (sha256) so content is never altered;
    - never deletes a source file itself (git mv is git's own tracked relocation).
    Returns a manifest entry describing exactly what happened (for undo).
    """
    src = (root / src_rel).resolve()
    dst = (root / dst_rel).resolve()
    if not str(src).startswith(str(root.resolve())) or not str(dst).startswith(str(root.resolve())):
        raise ConformError(f"refusing path outside project: {src_rel} -> {dst_rel}")
    if not src.is_file():
        raise ConformError(f"source missing: {src_rel}")
    if dst.exists():
        raise ConformError(f"destination exists — refusing to overwrite: {dst_rel}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    before = _sha(src)

    if prefer_git and _is_git_repo(root) and _is_tracked(root, src_rel):
        r = subprocess.run(["git", "-C", str(root), "mv", src_rel, dst_rel],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise ConformError(f"git mv failed for {src_rel}: {r.stderr.strip()}")
        if _sha(dst) != before:
            raise ConformError(f"content changed during git mv (should be impossible): {src_rel}")
        return {"src": src_rel, "dst": dst_rel, "method": "git-mv", "sha256": before}

    # COPY strategy — additive, the original is left exactly as it was.
    shutil.copy2(src, dst)
    if _sha(dst) != before:
        # botched copy: remove the bad copy we just made (never the original) and abort.
        try:
            dst.unlink()
        except OSError:
            pass
        raise ConformError(f"copy verification failed for {src_rel} — aborted, original untouched")
    return {"src": src_rel, "dst": dst_rel, "method": "copy", "sha256": before}


# --------------------------------------------------------------------------- #
# Apply (executes ONLY reviewed `move` rows)                                    #
# --------------------------------------------------------------------------- #
def apply(root: Path, *, force_method: str | None = None) -> dict:
    plan_path = root / PLAN_NAME
    if not plan_path.exists():
        raise ConformError(f"no {PLAN_NAME} — run `conform.py plan {root}` and review it first")
    plan_obj = json.loads(plan_path.read_text(encoding="utf-8"))
    prefer_git = (force_method != "copy")
    if force_method == "git-mv" and not _is_git_repo(root):
        raise ConformError("--git-mv requested but the project is not a git repo")

    moved, skipped, manifest = [], [], []
    for r in plan_obj.get("artifacts", []):
        if r.get("action") != "move" or not r.get("dest"):
            continue
        try:
            entry = safe_relocate(root, r["path"], r["dest"], prefer_git=prefer_git)
            manifest.append(entry)
            moved.append(entry)
        except ConformError as err:
            skipped.append({"path": r["path"], "reason": str(err)})

    (root / MANIFEST_NAME).write_text(
        json.dumps({"project": str(root), "moved": manifest, "skipped": skipped}, indent=2),
        encoding="utf-8")
    try:                                    # breadcrumb so a skipped register_project is surfaced
        import projects
        projects.record_conformed(root)
    except Exception:
        pass
    return {"moved": moved, "skipped": skipped}


# --------------------------------------------------------------------------- #
# Undo (reverse the last apply from the manifest)                              #
# --------------------------------------------------------------------------- #
def undo(root: Path) -> dict:
    man_path = root / MANIFEST_NAME
    if not man_path.exists():
        raise ConformError(f"no {MANIFEST_NAME} to undo")
    man = json.loads(man_path.read_text(encoding="utf-8"))
    restored, problems = [], []
    for e in man.get("moved", []):
        src, dst, method = e["src"], e["dst"], e.get("method")
        sp, dp = (root / src), (root / dst)
        if method == "git-mv":
            if sp.exists():
                problems.append({"dst": dst, "reason": "original path already occupied"})
                continue
            r = subprocess.run(["git", "-C", str(root), "mv", dst, src],
                               capture_output=True, text=True)
            (restored if r.returncode == 0 else problems).append(
                {"dst": dst} if r.returncode == 0 else {"dst": dst, "reason": r.stderr.strip()})
        else:  # copy — we only remove the COPY we made, and only if it still matches (never originals)
            if dp.exists() and dp.is_file() and _sha(dp) == e.get("sha256"):
                dp.unlink()
                restored.append({"dst": dst})
            else:
                problems.append({"dst": dst, "reason": "copy missing or modified — left as-is"})
    return {"restored": restored, "problems": problems}


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("plan", help="DRY RUN: inventory + propose keep/move/skip (touches nothing)")
    pp.add_argument("project")
    ap_ = sub.add_parser("apply", help="execute ONLY reviewed `move` rows (non-destructive)")
    ap_.add_argument("project")
    g = ap_.add_mutually_exclusive_group()
    g.add_argument("--git-mv", dest="method", action="store_const", const="git-mv",
                   help="force git mv (tracked files only)")
    g.add_argument("--copy", dest="method", action="store_const", const="copy",
                   help="force copy (additive; originals kept)")
    up = sub.add_parser("undo", help="reverse the last apply from the manifest")
    up.add_argument("project")
    args = ap.parse_args(argv)

    root = Path(args.project).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2

    if args.cmd == "plan":
        obj = plan(root)
        c = obj["counts"]
        print(f"Planned (nothing moved). move={c.get('move',0)} leave={c.get('leave',0)} "
              f"skip={c.get('skip',0)} review={c.get('review',0)}")
        print(f"Review {root/AUDIT_NAME} and {root/PLAN_NAME}, then: conform.py apply {root}")
        return 0
    if args.cmd == "apply":
        try:
            res = apply(root, force_method=getattr(args, "method", None))
        except ConformError as err:
            print(f"error: {err}", file=sys.stderr)
            return 1
        print(f"Moved {len(res['moved'])} artifact(s); skipped {len(res['skipped'])}. "
              f"Reversible via: conform.py undo {root}")
        print(f"NEXT (or the work stays invisible to the lab): register it into shared WIP →\n"
              f"  register_project(\"{root}\")   # MCP tool, in a Claude session")
        for s in res["skipped"]:
            print(f"  skipped {s['path']}: {s['reason']}")
        return 0
    if args.cmd == "undo":
        try:
            res = undo(root)
        except ConformError as err:
            print(f"error: {err}", file=sys.stderr)
            return 1
        print(f"Restored {len(res['restored'])}; {len(res['problems'])} problem(s).")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
