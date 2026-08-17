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
PENDING = ROOT / "memory" / "conformed_pending.jsonl"   # conformed but not yet register_project'd


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
        return {"ok": False, "msg": f"can't see '{path}' from the substrate. A shared node only "
                "reaches projects on shared filesystem mounted at the same path — put the project on "
                "shared FS (e.g. the cluster's Lustre), or register from a substrate that can read it."}
    if not (p / "hypotheses").is_dir():
        return {"ok": False, "msg": f"{p.name} has no hypotheses/ — conform it first "
                                    f"(python conform.py plan {path}), then register."}
    if any(r["path"] == str(p) for r in _load()):
        return {"ok": True, "msg": f"{p.name} is already registered.", "path": str(p)}
    # heads-up on H{NNN} id collisions with already-tracked work (they're disambiguated by project
    # tag in list_active_work, but the bare ids overlap — the alpha's T-0002).
    existing = _hypothesis_ids(ROOT)
    for _n, r in project_roots():
        existing |= _hypothesis_ids(r)
    collisions = sorted(_hypothesis_ids(p) & existing)
    entry = {"name": (name or "").strip() or p.name, "path": str(p),
             "registered_by": by or "unknown", "ts": datetime.now().isoformat(timespec="seconds")}
    store_lock.append_jsonl(REGISTRY, entry)
    msg = f"registered '{entry['name']}' — its hypotheses now show up in list_active_work."
    if collisions:
        msg += (f" ⚠ shares id(s) {', '.join(collisions)} with existing work; they're distinguished "
                f"by project tag in list_active_work, but the bare ids collide.")
    return {"ok": True, "path": str(p), "collisions": collisions, "msg": msg}


def _hypothesis_ids(root) -> set:
    """The H{NNN} ids declared under a root's hypotheses/ (best-effort)."""
    ids = set()
    for f in glob.glob(str(Path(root) / "hypotheses" / "*.y*ml")):
        try:
            import yaml
            d = yaml.safe_load(open(f, encoding="utf-8")) or {}
            ids.add(str(d.get("id") or Path(f).stem))
        except Exception:
            ids.add(Path(f).stem)
    return ids


def record_conformed(path: str, by: str = "") -> None:
    """Breadcrumb: a project was conformed. `pending_registrations` surfaces it until the project is
    registered, so a skipped register_project doesn't leave the work silently invisible."""
    try:
        p = Path(path).expanduser().resolve()
    except Exception:
        p = Path(path)
    store_lock.append_jsonl(PENDING, {"path": str(p), "by": by or "unknown",
                                      "ts": datetime.now().isoformat(timespec="seconds")})


def pending_registrations() -> list:
    """Conformed projects NOT yet registered (breadcrumbs minus anything already in the registry)."""
    if not PENDING.exists():
        return []
    registered = {r["path"] for r in _load()}
    out, seen = [], set()
    for line in PENDING.open(encoding="utf-8"):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        p = e.get("path")
        if not p or p in seen or p in registered or not Path(p).is_dir():
            continue
        seen.add(p)
        out.append(e)
    return out


def list_projects() -> list:
    return _load()


def project_roots() -> list:
    """(name, Path) for each registered project dir that still exists."""
    return [(r.get("name") or Path(r["path"]).name, Path(r["path"]))
            for r in _load() if Path(r["path"]).is_dir()]


def roots(base_root) -> list:
    """The substrate root (label 'lab') + every registered project root, for aggregated views."""
    return [("lab", Path(base_root))] + project_roots()
