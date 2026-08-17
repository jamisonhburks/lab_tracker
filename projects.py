"""projects — registry of EXTERNAL projects conformed into the lab.

A conformed project's hypotheses/experiments/campaigns live in the project's own directory (e.g. on
Lustre), NOT inside the substrate repo. Without a registry, the shared substrate's `list_active_work`
only globs its own root, so a member can finish conformance and end with work no colleague — or even
their own `list_active_work` — can see. Registering a project records its path so the shared views
aggregate across it. Store: memory/projects.jsonl (shared-JSONL shape; cron-snapshot friendly).
"""
import glob
import json
from datetime import datetime
from pathlib import Path

import store_lock

ROOT = Path(__file__).parent
REGISTRY = ROOT / "memory" / "projects.jsonl"


def _load() -> list:
    if not REGISTRY.exists():
        return []
    rows, seen = [], set()
    for line in reversed(REGISTRY.open(encoding="utf-8").read().splitlines()):   # last write wins
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("path") and r["path"] not in seen:
            seen.add(r["path"])
            rows.append(r)
    return list(reversed(rows))


def register_project(path: str, name: str = "", by: str = "") -> dict:
    """Register a conformed project (must exist and have a hypotheses/ dir). Idempotent by path."""
    p = Path(path).expanduser()
    try:
        p = p.resolve()
    except Exception:
        pass
    if not p.is_dir():
        return {"ok": False, "msg": f"not a directory: {path}"}
    if not (p / "hypotheses").is_dir():
        return {"ok": False, "msg": f"{p.name} has no hypotheses/ — conform it first "
                                    f"(python conform.py plan {path}), then register."}
    if any(r["path"] == str(p) for r in _load()):
        return {"ok": True, "msg": f"{p.name} is already registered.", "path": str(p)}
    entry = {"name": (name or "").strip() or p.name, "path": str(p),
             "registered_by": by or "unknown", "ts": datetime.now().isoformat(timespec="seconds")}
    store_lock.append_jsonl(REGISTRY, entry)
    return {"ok": True, "path": str(p),
            "msg": f"registered '{entry['name']}' — its hypotheses now show up in list_active_work."}


def list_projects() -> list:
    return _load()


def project_roots() -> list:
    """(name, Path) for each registered project dir that still exists."""
    return [(r.get("name") or Path(r["path"]).name, Path(r["path"]))
            for r in _load() if Path(r["path"]).is_dir()]


def roots(base_root) -> list:
    """The substrate root (label 'lab') + every registered project root, for aggregated views."""
    return [("lab", Path(base_root))] + project_roots()
