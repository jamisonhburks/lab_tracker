"""token_audit — roll up token spend by ACTIVITY × OUTCOME to see where research tokens go
and how much is wasted. Reads the durable spend ledgers written by token_meter.flush()
(memory/token_ledgers/*.jsonl); each line is one LLM call tagged with activity, outcome, layer,
backend, model, token counts, and $ (local generation is counted at $0 — cost-free, ADR-0060).

Usage:
  python token_audit.py                  # audit all recorded runs
  python token_audit.py --run <run_id>   # one run
  python token_audit.py --paid           # only paid (Claude / other frontier) tokens
  python token_audit.py --discover       # candidate NEW activity labels from provisional spend
"""
import argparse
import json

import label_discovery
import token_meter
from token_meter import SpendEvent, SpendMeter

LEDGER_DIR = token_meter.LEDGER_DIR


def load_events(run: str | None = None, paid_only: bool = False) -> list:
    events = []
    if not LEDGER_DIR.exists():
        return events
    for p in sorted(LEDGER_DIR.glob("*.jsonl")):
        for line in p.open(encoding="utf-8"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if run and d.get("run_id") != run:
                continue
            if paid_only and not (float(d.get("usd", 0)) > 0):
                continue
            events.append(d)
    return events


def to_meter(events: list) -> SpendMeter:
    m = SpendMeter()
    for d in events:
        m.add(SpendEvent(
            activity=d.get("activity", "uncategorized"), outcome=d.get("outcome", "unknown"),
            backend=d.get("backend", ""), model=d.get("model", ""),
            in_tok=int(d.get("in_tok", 0)), out_tok=int(d.get("out_tok", 0)),
            usd=float(d.get("usd", 0.0)), layer=d.get("layer", "orchestrator"),
            provisional=bool(d.get("provisional", False)), hint=d.get("hint", ""),
            run_id=d.get("run_id", ""), ts=d.get("ts", "")))
    return m


def _bar(frac: float, width: int = 12) -> str:
    n = int(round(frac * width))
    return "█" * n + "·" * (width - n)


def report(events: list, discover: bool = False) -> str:
    if not events:
        return ("No spend recorded yet. Token capture is automatic once an entry point runs "
                f"(agent / specialist); ledgers land in {LEDGER_DIR}.")
    m = to_meter(events)
    t = m.totals()
    out = ["# Token audit", ""]
    out.append(f"{t['calls']} calls · {t['tok']:,} tokens (in {t['in_tok']:,} / out {t['out_tok']:,}) "
               f"· ${t['usd']:.2f} paid · waste {round(100 * t['waste_frac'])}%")
    out.append("")

    # by activity
    out.append("## By activity")
    out.append("| activity | tokens | share | $ paid | waste% |")
    out.append("|---|--:|:--|--:|--:|")
    ba = m.by_activity()
    for act, a in sorted(ba.items(), key=lambda kv: -kv[1]["tok"]):
        share = a["tok"] / t["tok"] if t["tok"] else 0
        wf = a["waste_tok"] / a["tok"] if a["tok"] else 0
        out.append(f"| {act} | {a['tok']:,} | {_bar(share)} {round(100*share)}% | "
                   f"${a['usd']:.2f} | {round(100*wf)}% |")
    out.append("")

    # layer split (where the PAID money goes)
    layers: dict = {}
    for e in m.events:
        L = layers.setdefault(e.layer, {"tok": 0, "usd": 0.0})
        L["tok"] += e.total_tok
        L["usd"] += e.usd
    out.append("## By layer")
    out.append("| layer | tokens | $ paid |")
    out.append("|---|--:|--:|")
    for L, v in sorted(layers.items(), key=lambda kv: -kv[1]["usd"]):
        out.append(f"| {L} | {v['tok']:,} | ${v['usd']:.2f} |")
    out.append("")

    # waste detail: activity × waste-outcome
    waste_rows = [(k, v) for k, v in m.by_activity_outcome().items()
                  if k[1] in token_meter.WASTE_OUTCOMES and v["tok"]]
    if waste_rows:
        out.append("## Waste detail (activity × outcome)")
        out.append("| activity | outcome | tokens | $ |")
        out.append("|---|---|--:|--:|")
        for (act, oc), v in sorted(waste_rows, key=lambda kv: -kv[1]["tok"]):
            out.append(f"| {act} | {oc} | {v['tok']:,} | ${v['usd']:.2f} |")
        out.append("")

    # provisional → candidate new labels
    prov = [e for e in events if e.get("provisional")]
    if prov:
        ptok = sum(int(e.get("in_tok", 0)) + int(e.get("out_tok", 0)) for e in prov)
        out.append(f"## Provisional (unlabelled) — {len(prov)} calls, {ptok:,} tokens")
        if discover:
            cands = label_discovery.discover(events, min_support=1)
            if cands:
                out.append("")
                out.append("Candidate NEW activity labels (cluster provisional hints; review & adopt):")
                out.append("| suggested | events | tokens | sources | member hints |")
                out.append("|---|--:|--:|--:|---|")
                for c in cands:
                    out.append(f"| `{c['suggested_label']}` | {c['events']} | {c['tokens']:,} | "
                               f"{c['sources']} | {', '.join(c['hints'][:6])} |")
            else:
                out.append("(no recurring clusters yet — need more provisional samples)")
        else:
            out.append("Run with --discover to cluster these into candidate new labels.")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None, help="filter to one run_id")
    ap.add_argument("--paid", action="store_true", help="only paid (frontier) tokens")
    ap.add_argument("--discover", action="store_true", help="induce candidate new labels")
    args = ap.parse_args()
    events = load_events(run=args.run, paid_only=args.paid)
    print(report(events, discover=args.discover))


if __name__ == "__main__":
    main()
