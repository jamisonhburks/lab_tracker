"""pending — owner-scoped "unfinished business across the tiers".

Closes the conform → shared-WIP → consensus loop by telling YOU what's still pending, with the exact
next command:
  1. conformed but NOT in shared WIP  → register_project(path)
  2. tracked but NOT yet evaluated     → evaluate it (write the evaluation report)
  3. evaluated but NOT yet contributed → contribute_finding(...) when it's defensible

"Yours" = hypotheses in projects you registered (registered_by == you) + the substrate root. LLM-free
and best-effort. Folded into warm_start's "Waiting on you" and exposed as the `my_work` MCP tool.
"""
import glob
import os
from pathlib import Path

import projects

ROOT = Path(__file__).parent


def _who(member=None) -> str:
    return member or os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "you"


def _hyps(root: Path) -> list:
    out = []
    for f in sorted(glob.glob(str(Path(root) / "hypotheses" / "*.y*ml"))):
        try:
            import yaml
            d = yaml.safe_load(open(f, encoding="utf-8")) or {}
        except Exception:
            d = {}
        hid = d.get("id", Path(f).stem)
        out.append({"id": hid, "title": str(d.get("title", ""))[:70],
                    "status": d.get("status", "?"),
                    "evaluated": (Path(root) / "reports" / f"{hid}_evaluation.md").exists()})
    return out


def unfinished(member=None) -> dict:
    who = _who(member)
    mine = [(r["name"], Path(r["path"])) for r in projects.list_projects()
            if r.get("registered_by") == who and Path(r["path"]).is_dir()]
    roots = list(mine) + ([("lab", ROOT)] if _hyps(ROOT) else [])
    unevaluated, unpromoted = [], []
    for label, root in roots:
        for h in _hyps(root):
            (unevaluated if not h["evaluated"] else unpromoted).append({"project": label, **h})
    unregistered = projects.pending_registrations()
    return {"member": who, "projects": [n for n, _ in mine],
            "unregistered": unregistered, "unevaluated": unevaluated, "unpromoted": unpromoted}


def summary(member=None) -> dict:
    u = unfinished(member)
    return {"unregistered": len(u["unregistered"]), "unevaluated": len(u["unevaluated"]),
            "unpromoted": len(u["unpromoted"])}


def summary_line(member=None) -> str:
    s = summary(member)
    bits = []
    if s["unregistered"]:
        bits.append(f"{s['unregistered']} conformed project(s) not yet in WIP (register_project)")
    if s["unevaluated"]:
        bits.append(f"{s['unevaluated']} hypothesis(es) not yet evaluated")
    if s["unpromoted"]:
        bits.append(f"{s['unpromoted']} evaluated, not yet contributed to consensus")
    return "; ".join(bits)


def render(member=None) -> str:
    u = unfinished(member)
    L = [f"Your unfinished work — {u['member']}:"]
    if u["unregistered"]:
        L.append("• Conformed but NOT in shared WIP (colleagues can't see it) — register it:")
        for e in u["unregistered"]:
            L.append(f"    - {e['path']}  →  register_project(\"{e['path']}\")")
    if u["unevaluated"]:
        L.append("• Tracked but NOT yet evaluated:")
        for h in u["unevaluated"][:12]:
            L.append(f"    - {h['id']} [{h['status']}] ({h['project']}) — evaluate it "
                     f"(write reports/{h['id']}_evaluation.md)")
    if u["unpromoted"]:
        L.append("• Evaluated — contribute to consensus when the result is defensible:")
        for h in u["unpromoted"][:12]:
            L.append(f"    - {h['id']} ({h['project']}) — contribute_finding(...)  ({h['title']})")
    if len(L) == 1:
        L.append("  nothing pending — everything's registered and evaluated; promotion is your call.")
    return "\n".join(L)
