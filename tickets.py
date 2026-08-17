"""tickets — a lightweight alpha issue tracker on the SHARED (admin) substrate.

During alpha, when a member's session hits a bug or rough edge it files a ticket; the ticket lands
in the shared tracker the admin triages. Append-only, attributed to the reporter (via the shared
substrate's `_caller()`), and status-tracked in place — the same shape as the lab's other shared
JSONL stores, so the shared node's cron `git commit` snapshots it for audit (docs/deployment.md §5).

Store: memory/tickets.jsonl. LLM-free; every operation is safe under concurrent members (store_lock).

    python tickets.py list [open|ack|closed]     # admin: see the queue
    python tickets.py ack   <id>                  # admin: acknowledge
    python tickets.py close <id> [resolution]     # admin: close with a note
    python tickets.py file  "<title>"             # (mostly filed via the MCP tool)
    python tickets.py stats
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import store_lock

ROOT = Path(__file__).parent
TICKETS = ROOT / "memory" / "tickets.jsonl"

SEVERITIES = ("low", "medium", "high", "blocker")
STATUSES = ("open", "ack", "closed")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load() -> list:
    if not TICKETS.exists():
        return []
    return [json.loads(l) for l in TICKETS.open(encoding="utf-8") if l.strip()]


def _save(rows: list) -> None:
    TICKETS.parent.mkdir(parents=True, exist_ok=True)
    TICKETS.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def file_ticket(title: str, body: str = "", severity: str = "medium", area: str = "",
                context: str = "", reporter: str = "") -> str:
    """Record a new ticket; returns its id (T-NNNN). Id assigned under a lock (concurrency-safe)."""
    sev = severity if severity in SEVERITIES else "medium"
    reporter = reporter or "unknown"
    with store_lock.critical(TICKETS):
        rows = _load()
        n = max((int(re.sub(r"\D", "", r.get("id", "")) or 0) for r in rows), default=0) + 1
        tid = f"T-{n:04d}"
        rows.append({
            "id": tid, "ts": _now(), "reporter": reporter, "severity": sev,
            "area": area.strip(), "title": title.strip(), "body": body.strip(),
            "context": context.strip(), "status": "open", "resolution": "", "updated": _now(),
            "history": [{"ts": _now(), "by": reporter, "action": "filed"}]})
        _save(rows)
    return tid


def _short(args) -> str:
    try:
        s = json.dumps(args, default=str)
    except Exception:
        s = str(args)
    return s[:200]


def auto_file(exc: BaseException, tool: str = "", args=None, area: str = "mcp",
              reporter: str = "", context: str = "") -> str:
    """Auto-file a ticket for an UNHANDLED tool error. Deduplicated by (tool, error-signature) while
    a matching ticket is still open — a recurrence bumps `occurrences` instead of spamming new
    tickets. NEVER raises (telemetry must not compound the failure it's reporting)."""
    try:
        reporter = reporter or os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "auto"
        etype = type(exc).__name__
        first = (str(exc) or "").splitlines()[0] if str(exc) else ""
        sig = f"{tool}|{etype}|{first[:120]}"
        with store_lock.critical(TICKETS):
            rows = _load()
            dup = next((r for r in rows if r.get("status") != "closed" and r.get("signature") == sig), None)
            if dup is not None:
                dup["occurrences"] = int(dup.get("occurrences", 1)) + 1
                dup["updated"] = _now()
                dup.setdefault("history", []).append(
                    {"ts": _now(), "by": reporter, "action": "recurred"})
                _save(rows)
                return f"(known issue {dup['id']} — recurred x{dup['occurrences']}; not re-filed)"
            n = max((int(re.sub(r"\D", "", r.get("id", "")) or 0) for r in rows), default=0) + 1
            tid = f"T-{n:04d}"
            rows.append({
                "id": tid, "ts": _now(), "reporter": reporter, "severity": "high", "area": area,
                "title": f"[auto] {tool or 'tool'} raised {etype}: {first[:80]}".strip(),
                "body": f"tool={tool} args={_short(args)}\n{context}".strip(),
                "context": f"{etype}: {str(exc)[:300]}", "status": "open", "resolution": "",
                "signature": sig, "occurrences": 1, "auto": True, "updated": _now(),
                "history": [{"ts": _now(), "by": reporter, "action": "auto-filed"}]})
            _save(rows)
        return f"filed {tid}"
    except Exception:
        return "(auto-ticket failed)"


def update_ticket(ticket_id: str, status: str = None, note: str = "", by: str = "",
                  title: str = "", severity: str = "", area: str = "") -> dict | None:
    """Triage/edit a ticket: set status (ack|closed), append a note, and/or CORRECT its title,
    severity, or area (so a mis-filed ticket can be fixed in place — not just annotated). Returns
    the ticket, or None if unknown."""
    status = status if status in STATUSES else None
    with store_lock.critical(TICKETS):
        rows = _load()
        t = next((r for r in rows if r.get("id") == ticket_id), None)
        if t is None:
            return None
        edited = []
        if status:
            t["status"] = status
            if status == "closed" and note:
                t["resolution"] = note
        if title.strip():
            t["title"] = title.strip(); edited.append("title")
        if severity.strip() in SEVERITIES:
            t["severity"] = severity.strip(); edited.append("severity")
        if area.strip():
            t["area"] = area.strip(); edited.append("area")
        t["updated"] = _now()
        action = status or ("edited:" + ",".join(edited) if edited else "note")
        t.setdefault("history", []).append({"ts": _now(), "by": by or "admin",
                                            "action": action, "note": note})
        _save(rows)
        return t


def list_tickets(status: str = "", area: str = "", reporter: str = "") -> list:
    """Tickets, filtered; ordered open→ack→closed, then blocker→low, then oldest first."""
    rows = _load()
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if area:
        rows = [r for r in rows if area.lower() in r.get("area", "").lower()]
    if reporter:
        rows = [r for r in rows if reporter.lower() in r.get("reporter", "").lower()]
    st = {s: i for i, s in enumerate(STATUSES)}
    sev = {s: i for i, s in enumerate(reversed(SEVERITIES))}   # blocker first
    return sorted(rows, key=lambda r: (st.get(r.get("status"), 9),
                                       sev.get(r.get("severity"), 9), r.get("ts", "")))


def stats() -> dict:
    rows = _load()
    by_status = {}
    for r in rows:
        by_status[r.get("status", "open")] = by_status.get(r.get("status", "open"), 0) + 1
    return {"total": len(rows), "by_status": by_status,
            "open": sum(1 for r in rows if r.get("status") != "closed")}


def render(status: str = "") -> str:
    rows = list_tickets(status=status)
    if not rows:
        return "No tickets." + (f" (status={status})" if status else "")
    head = f"{len(rows)} ticket(s)" + (f" [{status}]" if status else "") + ":"
    lines = [head]
    for r in rows:
        area = f" · {r['area']}" if r.get("area") else ""
        occ = f" (x{r['occurrences']})" if int(r.get("occurrences", 1)) > 1 else ""
        lines.append(f"  {r['id']}  [{r.get('status')}/{r.get('severity')}] {r.get('title')}{occ}"
                     f"  — {r.get('reporter')}{area}")
    return "\n".join(lines)


def _main(argv) -> int:
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        print(render(status=argv[1] if len(argv) > 1 else ""))
    elif cmd == "file":
        print("filed", file_ticket(title=argv[1] if len(argv) > 1 else "untitled"))
    elif cmd == "ack" and len(argv) > 1:
        print("acked" if update_ticket(argv[1], status="ack") else "not found", argv[1])
    elif cmd == "close" and len(argv) > 1:
        ok = update_ticket(argv[1], status="closed", note=" ".join(argv[2:]))
        print("closed" if ok else "not found", argv[1])
    elif cmd == "stats":
        print(json.dumps(stats(), indent=2))
    else:
        print("usage: tickets.py [list [open|ack|closed] | file <title> | ack <id> | "
              "close <id> [note] | stats]")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
