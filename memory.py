"""Episodic memory: an append-only log of past agent runs, with recall.

Episodic = "what happened when". Each completed run becomes one JSONL line.
Findings are stored as claim->sources pairs so provenance is bound directly to
each claim, not pooled in a separate bag that can drift out of sync.

Deliberately dependency-free: recall is plain keyword overlap. When we add
SEMANTIC memory we'll swap the scorer for embedding similarity — the interface
(record_run / recall_past_runs) stays the same.
"""

import json
import re
from datetime import datetime
from pathlib import Path

STORE = Path(__file__).parent / "memory" / "episodic.jsonl"

HALF_LIFE_DAYS = 30.0   # a run's relevance halves every 30 days (recency decay)


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _load() -> list:
    if not STORE.exists():
        return []
    with STORE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def record_run(question: str, tool_calls: list, findings: list) -> dict:
    """Append one run. `findings` is a list of {"claim": str, "sources": [str]}."""
    STORE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": f"run-{len(_load()) + 1}",
        "ts": datetime.now().isoformat(timespec="seconds"),
        "question": question,
        "tools_called": tool_calls,
        "findings": findings,  # each claim carries its own provenance
    }
    with STORE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def recall_past_runs(query: str, max_results: int = 3, min_overlap: int = 1) -> str:
    """Recall past runs by keyword overlap, decayed by recency.

    final = keyword_overlap * 0.5 ** (age_days / HALF_LIFE_DAYS)

    So a slightly-less-relevant recent run can outrank a stale exact match.
    `min_overlap` is the threshold: runs sharing fewer tokens are dropped.
    """
    runs = _load()
    if not runs:
        return "No past runs recorded yet."

    q = _tokens(query)
    now = datetime.now()

    def overlap(r):
        claim_text = " ".join(f["claim"] for f in r.get("findings", []))
        return len(q & _tokens(f"{r['question']} {claim_text}"))

    def recency(r):
        age_days = (now - datetime.fromisoformat(r["ts"])).total_seconds() / 86400
        return 0.5 ** (age_days / HALF_LIFE_DAYS)

    scored = []
    for r in runs:
        ov = overlap(r)
        if ov < min_overlap:            # threshold: not enough shared terms
            continue
        scored.append((ov * recency(r), ov, r))

    if not scored:
        return "No past runs matched that query."
    scored.sort(key=lambda t: t[0], reverse=True)

    blocks = []
    for final, ov, r in scored[:max_results]:
        header = f"[{r['id']} @ {r['ts']}  overlap={ov} score={final:.2f}]"
        lines = [header, f"Q: {r['question']}", "Findings:"]
        for f in r.get("findings", []):
            srcs = ", ".join(f["sources"]) or "no source"
            lines.append(f"  - {f['claim']}  [{srcs}]")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
