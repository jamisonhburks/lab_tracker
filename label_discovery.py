"""label_discovery — induce NEW activity labels from PROVISIONAL token spend.

Dimension-1 (activity) attribution is not always confident: an unknown tool or specialist skill
can't be mapped to a known token_meter.ACTIVITY, so it is flagged PROVISIONAL with a semantic
`hint` (the tool/skill name) instead of being dumped into `uncategorized`. This module clusters
those hints — across ONE person's runs, and across USERS when their ledgers are pooled — to
surface groups of semantically-similar work the taxonomy simply has no name for yet. Each cluster
is a CANDIDATE new activity label to review; adopt the good ones into token_meter.TOOL_ACTIVITY.

Clustering is dependency-light (token-overlap single-linkage), matching the concept-form matching
used elsewhere in the repo (memory.py, coverage.py) — no embeddings, auditable by eye. The
cross-user signal matters: a cluster that recurs for several distinct sources is a stronger
candidate than one person's one-off.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import is_dataclass, asdict

# Only STRUCTURAL words are stripped. Domain verbs (run/read/query/fetch/…) are KEPT: provisional
# hints are UNKNOWN tool/skill names, so those verbs carry the signal that clusters similar work,
# and the known query_*/read_* tools are already mapped (they never reach discovery).
_STOP = {"the", "a", "an", "of", "to", "and", "for", "with", "or", "in", "on"}


def _tokens(s: str) -> list:
    return [t for t in re.findall(r"[a-z0-9]+", (s or "").lower())
            if t not in _STOP and len(t) > 1]


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def _as_dicts(events) -> list:
    out = []
    for e in events or []:
        out.append(asdict(e) if is_dataclass(e) else dict(e))
    return out


def discover(events, min_support: int = 2, threshold: float = 0.34) -> list:
    """Cluster provisional hints into candidate activity labels.

    events: spend rows (dicts or SpendEvent). Only provisional ones are used.
    min_support: drop clusters seen in fewer than this many events.
    Returns candidate clusters, biggest token-spend first:
      {suggested_label, hints, events, tokens, sources, exemplar}
    """
    rows = [e for e in _as_dicts(events) if e.get("provisional")]
    if not rows:
        return []

    # aggregate per distinct hint
    agg: dict[str, dict] = {}
    for r in rows:
        h = (r.get("hint") or "").strip()
        if not h:
            continue
        a = agg.setdefault(h, {"hint": h, "events": 0, "tokens": 0, "sources": set(),
                               "toks": set(_tokens(h))})
        a["events"] += 1
        a["tokens"] += int(r.get("in_tok", 0)) + int(r.get("out_tok", 0))
        a["sources"].add(r.get("user") or r.get("run_id") or "local")
    hints = list(agg.values())

    # single-linkage clustering by token-overlap on the hints
    parent = {h["hint"]: h["hint"] for h in hints}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    for i in range(len(hints)):
        for j in range(i + 1, len(hints)):
            if _jaccard(hints[i]["toks"], hints[j]["toks"]) >= threshold:
                union(hints[i]["hint"], hints[j]["hint"])

    groups: dict[str, list] = {}
    for h in hints:
        groups.setdefault(find(h["hint"]), []).append(h)

    out = []
    for members in groups.values():
        events_n = sum(m["events"] for m in members)
        if events_n < min_support:
            continue
        tokens = sum(m["tokens"] for m in members)
        sources = set().union(*(m["sources"] for m in members))
        tok_freq = Counter()
        for m in members:
            tok_freq.update(m["toks"])
        # suggested label: the most distinctive shared token(s)
        top = [t for t, _ in tok_freq.most_common(2)]
        suggested = "_".join(top) if top else "unnamed"
        exemplar = max(members, key=lambda m: m["tokens"])["hint"]
        out.append({
            "suggested_label": suggested,
            "hints": sorted(m["hint"] for m in members),
            "events": events_n,
            "tokens": tokens,
            "sources": len(sources),           # distinct runs/users — cross-source recurrence
            "exemplar": exemplar,
        })
    return sorted(out, key=lambda c: (-c["tokens"], -c["events"]))
