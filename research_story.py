"""research_story — an HONEST narrative of a project's arc.

NOT a highlight reel. For each step it interweaves what you accomplished with what's SHAKY —
caveats drawn from the validity gates, grounding/novelty, power, corroboration, and the
evaluator's OWN words — and concrete ways to SOLIDIFY the finding. A story is only as strong as
its least-corroborated link, and this says so. Read-only composition of hypotheses/, reports/,
experiments/*/validity.json, campaigns/, and the contribution log.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
HYP = ROOT / "hypotheses"
REPORTS = ROOT / "reports"
EXP = ROOT / "experiments"
CAMPAIGNS = ROOT / "campaigns"


def _hyps():
    out = []
    if not HYP.exists():
        return out
    try:
        import yaml
    except Exception:
        return out
    for f in sorted(HYP.glob("*.y*ml")):
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            d.setdefault("id", f.stem.split("_")[0])
            out.append(d)
        except Exception:
            pass
    return sorted(out, key=lambda d: str(d.get("id", "")))


def _validity(hid):
    f = EXP / hid / "validity.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _report(hid):
    f = REPORTS / f"{hid}_evaluation.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _verdict_line(report):
    """The evaluator's verdict, in their words (first substantive line under a Verdict heading)."""
    lines = [l.strip() for l in report.splitlines()]
    for i, l in enumerate(lines):
        if l.lower().lstrip("# ").startswith("verdict") or ("verdict" in l.lower() and l.startswith("#")):
            for nxt in lines[i + 1:i + 6]:
                if nxt and not nxt.startswith("#") and not nxt.startswith("|"):
                    return nxt[:200]
    return ""


# --- caveats (honest) + how to solidify, from real signals --------------------
def _validity_caveats(gates):
    out = []
    for g in gates:
        if g.get("passed", True):
            continue
        if g.get("severity") == "halt":
            out.append((f"a HALT gate ({g['name']}) tripped — the result would be INVALID, not "
                        f"negative: {g.get('detail', '')}", "fix the cohort/pipeline issue, then re-run"))
        else:
            out.append((f"a data-quality FLAG ({g['name']}: {g.get('detail', '')}) — read the "
                        "result with that caveat", f"resolve {g['name']} (re-check scale/units/labels)"))
    return out


def _struct_caveats(h):
    out = []
    prov = h.get("provenance", {}) if isinstance(h.get("provenance"), dict) else {}
    g, nov = str(prov.get("kg_grounding", "")).lower(), str(prov.get("novelty", "")).lower()
    if "weakly" in g:
        out.append(("only long / low-trust KG paths support the link",
                    "seek stronger mechanistic grounding or more independent evidence"))
    if "novel_unverified" in g or "off_graph" in g:
        out.append(("uncorroborated in the trusted KG (novel ≠ true)",
                    "verify the mechanism directly before over-claiming"))
    if "bridge_published" in nov or "established" in nov:
        out.append(("the core link is already published — this is validation, not discovery",
                    "pivot to an unexamined facet, or frame it honestly as replication"))
    try:
        if int(h.get("min_runs", 3)) < 3:
            out.append(("fewer than 3 runs pre-registered",
                        "reproduce across ≥3 runs / independent cohorts"))
    except Exception:
        pass
    data = h.get("data", {}) if isinstance(h.get("data"), dict) else {}
    if "synthetic" in (str(data.get("source", "")) + " " + str(data.get("type", ""))).lower():
        out.append(("results are on SYNTHETIC data — the pipeline is validated, the biological "
                    "claim is not", "confirm on real data before claiming the effect"))
    return out


def _report_caveats(report):
    out, seen = [], set()
    lines = [l.strip() for l in report.splitlines() if l.strip() and not l.startswith(("#", "|"))]
    rules = [("underpowered", "run a power analysis and size the cohort for the target effect"),
             ("binding limitation", "address the binding limitation (power) directly"),
             ("did not replicate", "seek independent replication in a second cohort"),
             ("not replicate", "seek independent replication in a second cohort"),
             ("promising_but_poorly_tested", "power the test before treating the null as a refutation"),
             ("no central gene", "widen the panel or use a more powered assay (e.g. single-nucleus)"),
             ("no gene reaches", "widen the panel or use a more powered assay")]
    for kw, solid in rules:
        if solid in seen:
            continue
        line = next((l for l in lines if kw in l.lower()), None)
        if line:
            out.append((f"the evaluator flags: “{line[:130]}”", solid))
            seen.add(solid)
    return out[:3]


def _wins(h, gates, report):
    out = []
    if str(h.get("status", "")).lower() == "complete":
        out.append("carried it through to an evaluated verdict")
    if any(not g.get("passed", True) and g.get("severity") == "flag" for g in gates):
        out.append("a validity gate caught a real anomaly (rigor — the honest catch)")
    low = report.lower()
    if "null" in low:
        out.append("recorded an honest null — that saves the lab a repeat run")
    if "replicat" in low:
        out.append("built in a replication arm")
    return out


def story(campaign: str = "") -> str:
    hyps = _hyps()
    title = "Research story — an honest arc"
    if campaign:
        cf = CAMPAIGNS / (campaign if campaign.endswith(".json") else f"{campaign}.json")
        try:
            c = json.loads(cf.read_text(encoding="utf-8"))
            order = [n["experiment_id"] for n in c.get("nodes", [])]
            hyps = sorted([h for h in hyps if h.get("id") in order],
                          key=lambda h: order.index(h.get("id")))
            title = f"Research story — {c.get('name', campaign)}"
        except Exception:
            pass
    if not hyps:
        return "No hypotheses to narrate yet — start one (hypothesis-workflow) and the story writes itself."

    out = [f"# {title}\n"]
    tally = {}
    for h in hyps:
        hid = h.get("id")
        gates, report = _validity(hid), _report(hid)
        wins = _wins(h, gates, report)
        caveats = _validity_caveats(gates) + _struct_caveats(h) + _report_caveats(report)
        tally[hid] = len(caveats)
        out.append(f"## {hid} — {h.get('title', '')}")
        out.append(f"*{h.get('status', '?')}.* {str(h.get('question', ''))[:200]}")
        if wins:
            out.append(f"**Went well:** {'; '.join(dict.fromkeys(wins))}.")
        v = _verdict_line(report)
        if v:
            out.append(f"**Verdict:** {v}")
        if caveats:
            out.append("**But — where it's shaky:**")
            out += [f"  - ⚠ {c}" for c, _ in caveats[:4]]
            out.append("**To solidify:**")
            out += [f"  - → {s}" for s in dict.fromkeys(s for _, s in caveats[:4])]
        else:
            out.append("  - No gate/grounding caveats flagged — still, confirm INDEPENDENT "
                       "corroboration before narrating it as settled.")
        out.append("")

    out.append("---\n## The honest bottom line")
    if tally:
        weak = max(tally, key=tally.get)
        cavs = _validity_caveats(_validity(weak)) + _struct_caveats(next(h for h in hyps if h.get("id") == weak)) + _report_caveats(_report(weak))
        if cavs:
            out.append(f"The arc's **weakest link is {weak}** ({tally[weak]} caveat(s)). The single "
                       f"highest-value move to solidify the story: **{cavs[0][1]}**.")
    out.append("Progress is real — but a story is only as strong as its least-corroborated link. "
               "Solidify the shaky steps before you present the arc as settled.")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    print(story(sys.argv[1] if len(sys.argv) > 1 else ""))
