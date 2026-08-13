"""scaling — content accounting per hypothesis/experiment.

Profiles how much CONTENT each experiment generates on disk — the hypothesis spec,
experiment code, metrics, figures, run log, evaluation report, provenance card, and
tool ledger — plus its scientific-op count, so the scaling of the
generate → test → interpret loop is visible at a glance.

    python scaling.py            # all experiments — comparison table
    python scaling.py H001       # one experiment — detailed breakdown

Note: this measures ON-DISK artifacts (deterministic). The other scaling axis — the
Claude subagent tokens the pipeline consumes (planner/implementer/runner/evaluator) —
is orchestration telemetry, not on disk; the local Qwen generation half is token-free.
Text-token estimates here are bytes/4, a rough proxy for artifact volume only.
"""

import glob
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
_TEXT = lambda f: not f.endswith((".png", ".pdf"))

# label -> how to find that group's files for an experiment id
GROUPS = {
    "spec":       lambda e: glob.glob(str(ROOT / "hypotheses" / f"{e}*.y*ml")),
    "code":       lambda e: [ROOT / "experiments" / e / "run.py", ROOT / "experiments" / e / "config.yaml"],
    "metrics":    lambda e: glob.glob(str(ROOT / "experiments" / e / "results" / "*.csv")),
    "figures":    lambda e: glob.glob(str(ROOT / "experiments" / e / "results" / "figures" / "*")),
    "log":        lambda e: glob.glob(str(ROOT / "experiments" / e / "logs" / "*.log")),
    "report":     lambda e: [ROOT / "reports" / f"{e}_evaluation.md"],
    "provenance": lambda e: [ROOT / "experiments" / e / "provenance.md"],
    "ledger":     lambda e: [ROOT / "experiments" / e / "tool_ledger.json"],
}


def measure(exp: str) -> tuple:
    """Return (per_group {label: (bytes, lines)}, totals (bytes, lines), n_scientific_ops)."""
    per, tb, tl = {}, 0, 0
    for label, finder in GROUPS.items():
        b = l = 0
        for f in finder(exp):
            f = str(f)
            if os.path.exists(f):
                b += os.path.getsize(f)
                if _TEXT(f):
                    l += sum(1 for _ in open(f, errors="ignore"))
        per[label] = (b, l)
        tb += b
        tl += l
    ledger = ROOT / "experiments" / exp / "tool_ledger.json"
    n_ops = len(json.loads(ledger.read_text())["actual"]) if ledger.exists() else 0
    return per, (tb, tl), n_ops


def _experiments() -> list:
    return sorted(Path(p).name for p in glob.glob(str(ROOT / "experiments" / "H*"))
                  if (Path(p) / "run.py").exists())


def detail(exp: str) -> None:
    per, (tb, tl), n_ops = measure(exp)
    print(f"=== {exp} — content accounting ===")
    print(f"{'group':14} {'KB':>9} {'lines':>8}")
    for label, (b, l) in per.items():
        print(f"{label:14} {b/1024:9.1f} {l:8}")
    print(f"{'TOTAL':14} {tb/1024:9.1f} {tl:8}   (~{tb//4/1000:.0f}k text-tokens, "
          f"{n_ops} scientific ops)")


def table() -> None:
    exps = _experiments()
    if not exps:
        print("No experiments found under experiments/.")
        return
    print(f"{'exp':6} {'KB':>8} {'lines':>7} {'~ktok':>6} {'sci-ops':>7}  biggest-group")
    for e in exps:
        per, (tb, tl), n_ops = measure(e)
        biggest = max(per.items(), key=lambda kv: kv[1][0])[0]
        print(f"{e:6} {tb/1024:8.1f} {tl:7} {tb//4/1000:6.0f} {n_ops:7}  {biggest}")
    print("\n(on-disk artifacts only; Claude pipeline tokens tracked separately, "
          "local generation is token-free — see ADR-0023.)")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        detail(sys.argv[1])
    else:
        table()
