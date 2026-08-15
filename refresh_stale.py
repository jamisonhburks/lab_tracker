#!/usr/bin/env python3
"""refresh_stale — scheduled maintenance: re-distil topics whose cache has gone stale.

The deep-search cache ages (ADR-0047): a topic searched long ago is flagged STALE. This job
re-runs the local agent's `curate_literature` on each stale topic so the primary KG stays current
WITHOUT waiting for someone to ask again. It is AUTONOMOUS and therefore uses the local model
(curate_literature distils) — run it where the model is available (the local agent host, or set
LLM_BACKEND=anthropic). Each refresh writes fresh evidence + a new cache entry (via mark_searched),
which resets the topic's staleness.

    python refresh_stale.py               # refresh every stale topic
    python refresh_stale.py --max 5       # cap how many to refresh this run
    python refresh_stale.py --older-than 90
    python refresh_stale.py --dry-run     # just list what's stale

Cron (weekly, on the cluster) — see docs/deployment.md:
    0 3 * * 0  cd /srv/lab/toy-research-agent && /srv/lab/venv/bin/python refresh_stale.py --max 20
"""
import argparse

import deep_search


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh stale deep-search topics.")
    ap.add_argument("--older-than", type=int, default=deep_search.STALE_AFTER_DAYS,
                    help=f"staleness threshold in days (default {deep_search.STALE_AFTER_DAYS})")
    ap.add_argument("--max", type=int, default=0, help="cap topics refreshed this run (0 = all)")
    ap.add_argument("--dry-run", action="store_true", help="list stale topics, refresh nothing")
    args = ap.parse_args()

    stale = deep_search.stale_topics(args.older_than)
    if not stale:
        print(f"No topics older than {args.older_than}d. Cache is fresh.")
        return 0
    if args.max:
        stale = stale[:args.max]
    print(f"{len(stale)} stale topic(s) (>{args.older_than}d):")
    for s in stale:
        print(f"  {s['age_days']}d  {s['topic']!r}  (last by {s['contributor']} on {s['ts'][:10]})")
    if args.dry_run:
        return 0

    import agent                                   # local model distils (autonomous)
    print("\nRefreshing (curate_literature re-distils each into the primary KG)…")
    for s in stale:
        try:
            print(f"\n▸ {s['topic']!r}")
            print("  " + agent.curate_literature(s["topic"]).replace("\n", "\n  "))
        except Exception as err:
            print(f"  [failed: {err}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
