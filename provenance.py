"""provenance — assemble a per-experiment "how it was formed / how it was tested" card.

Deterministic (no LLM): reads an experiment's own artifacts — the hypothesis spec, the
tool ledgers (formation + the scientific-op trace), the config, the metrics, and the
evaluation verdict — and stitches them into one auditable view at
`experiments/{id}/provenance.md`. This ties the whole generate→test→interpret arc
together in a single place.

    python provenance.py H001
"""

import glob
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def _load_yaml(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _find_hypothesis(exp_id: str) -> Path | None:
    hits = sorted(glob.glob(str(ROOT / "hypotheses" / f"{exp_id}*.y*ml")))
    return Path(hits[0]) if hits else None


def _sci_trace(exp_id: str) -> list | None:
    """The experiment's actual scientific tool calls, in order (from its tool ledger)."""
    p = ROOT / "experiments" / exp_id / "tool_ledger.json"
    if not p.exists():
        return None
    return [(a["tool"], a.get("args", {})) for a in json.loads(p.read_text())["actual"]]


def _formation_trace(hyp: dict) -> tuple | None:
    """Best-effort link to the orchestrator run that FORMED this hypothesis: match a
    run ledger whose task shares terms with the hypothesis title/question."""
    terms = set(re.findall(r"[a-z0-9]+", (hyp.get("title", "") + " " +
                hyp.get("question", "")).lower())) - {"the", "and", "of", "a", "in", "to"}
    best, best_ov = None, 0
    for f in glob.glob(str(ROOT / "memory" / "tool_ledgers" / "run-*.json")):
        d = json.loads(Path(f).read_text())
        ov = len(terms & set(re.findall(r"[a-z0-9]+", d.get("task", "").lower())))
        if ov > best_ov:
            best, best_ov = d, ov
    if best and best_ov >= 2:
        return best["run_id"], [a["tool"] for a in best["actual"]]
    return None


def _verdict(exp_id: str) -> str | None:
    p = ROOT / "reports" / f"{exp_id}_evaluation.md"
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8")
    m = re.search(r"(?im)^.*one-line verdict[:*\s]*(.+)$", text)
    if m:
        return m.group(1).strip(" *")
    m = re.search(r"(?is)##\s*Summary\s*\n+(.+?)(?:\n##|\Z)", text)
    if m:
        return " ".join(m.group(1).split())[:600]
    return None


def _metrics_summary(exp_id: str) -> str:
    files = sorted(glob.glob(str(ROOT / "experiments" / exp_id / "results" / "*.csv")))
    if not files:
        return "(no metrics files)"
    out = []
    for f in files:
        n = sum(1 for _ in open(f, encoding="utf-8")) - 1
        out.append(f"{Path(f).name} ({max(n, 0)} rows)")
    return ", ".join(out)


def _design(exp_id: str) -> str:
    p = ROOT / "experiments" / exp_id / "config.yaml"
    if not p.exists():
        return "(no config)"
    cfg = _load_yaml(p)
    bits = []
    for k in ("gene_panel", "panel_genes"):
        if k in cfg:
            bits.append(f"{len(cfg[k])}-gene panel")
            break
    for role in ("primary", "replication"):
        if isinstance(cfg.get(role), dict) and cfg[role].get("geo_id"):
            bits.append(f"{role}={cfg[role]['geo_id']}")
    if cfg.get("seeds"):
        bits.append(f"seeds={cfg['seeds']}")
    return "; ".join(bits) or "(see config.yaml)"


def _fmt_trace(trace: list) -> list:
    """Collapse consecutive identical tools into `tool ×N` for readability."""
    lines, i = [], 0
    for tool, args in trace:
        detail = args.get("method") or args.get("dataset") or args.get("variant") \
            or args.get("geo_id") or args.get("artifact") or ""
        lines.append(f"{tool}" + (f" ({detail})" if detail else ""))
    return lines


def build(exp_id: str) -> Path:
    hyp_path = _find_hypothesis(exp_id)
    hyp = _load_yaml(hyp_path) if hyp_path else {}
    sci = _sci_trace(exp_id)
    form = _formation_trace(hyp)
    verdict = _verdict(exp_id)

    L = [f"# Provenance — {exp_id}: {hyp.get('title', '(no title)')}", "",
         "*Assembled by `provenance.py` from the experiment's own artifacts "
         "(deterministic, no LLM). One view of how the hypothesis was formed and tested.*", ""]

    L += ["## Hypothesis (how it was framed)",
          f"- **Question:** {hyp.get('question', '—')}",
          f"- **H₀:** {hyp.get('null_hypothesis', '—')}",
          f"- **H₁:** {hyp.get('alternative_hypothesis', '—')}",
          f"- **Success metric:** {hyp.get('success_metric', '—')}",
          f"- **Status:** {hyp.get('status', '—')} · created {hyp.get('created', '—')}", ""]

    L += ["## Formation — how the hypothesis was formed",
          f"- **Method:** {hyp.get('method', '—')}"]
    data = hyp.get("data", {})
    if isinstance(data, dict) and data.get("source"):
        L.append(f"- **Data source:** {data['source']}")
    if hyp.get("pre_registration"):
        L.append(f"- **Pre-registered decisions:** {', '.join(hyp['pre_registration'].keys())}")
    if form:
        L.append(f"- **Formation tool trace** (orchestrator run {form[0]}): "
                 + " → ".join(form[1]))
    else:
        L.append("- **Formation tool trace:** not linked (hypothesis predates the tool "
                 "ledger, or was formalized directly); reasoning captured in the spec above.")
    L.append("")

    L += ["## Testing — how it was tested", f"- **Design:** {_design(exp_id)}"]
    if sci:
        L.append(f"- **Scientific tool calls (in order, {len(sci)}):**")
        L += [f"  {i}. {line}" for i, line in enumerate(_fmt_trace(sci), 1)]
    else:
        L.append("- **Scientific tool calls:** no `experiments/%s/tool_ledger.json` "
                 "(experiment predates instrumentation; re-run to capture)." % exp_id)
    L.append("- **Statistical standards:** Bonferroni + BH-FDR, effect sizes, "
             f"≥{hyp.get('min_runs', '?')} runs/robustness checks, reproducibility log.")
    L.append("")

    L += ["## Result",
          f"- **Metrics:** {_metrics_summary(exp_id)}",
          f"- **Verdict:** {verdict or '(no evaluation report found)'}", ""]

    L += ["## Audit trail",
          f"- spec: `{hyp_path.relative_to(ROOT) if hyp_path else 'hypotheses/(missing)'}`",
          f"- config: `experiments/{exp_id}/config.yaml`",
          f"- tool ledger (scientific ops): `experiments/{exp_id}/tool_ledger.json`",
          f"- metrics: `experiments/{exp_id}/results/`",
          f"- evaluation: `reports/{exp_id}_evaluation.md`",
          f"- run log: `experiments/{exp_id}/logs/run.log`"]

    out = ROOT / "experiments" / exp_id / "provenance.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python provenance.py <experiment_id>")
        sys.exit(1)
    path = build(sys.argv[1])
    print(f"Provenance card written to {path}")
    print(path.read_text(encoding="utf-8"))
