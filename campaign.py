"""campaign — a program: a lineage (DAG) of atomic experiments.

Experiments stay immutable (ADR-0020/0024); result-driven adaptivity lives HERE, not
inside a running experiment. A campaign records which experiment led to which
(parent -> child, with the reason it was spawned), auto-syncs each node's verdict from
its evaluation report, and a planner proposes the NEXT atomic experiment from the last
verdict + the evaluator's own recommendations + the campaign context.

So "update the longer experiment plan" = APPEND a new atomic experiment to the program,
never mutate a running one — which keeps every experiment reproducible and each
plan-change auditable (the DAG records why H002 followed H001, etc.).

    python campaign.py show  <name>    # render the lineage
    python campaign.py plan  <name>    # propose the next atomic experiment
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
CAMP_DIR = ROOT / "campaigns"


def _report_text(exp_id: str) -> str:
    p = ROOT / "reports" / f"{exp_id}_evaluation.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _verdict(exp_id: str) -> str:
    text = _report_text(exp_id)
    m = re.search(r"(?im)^.*one-line verdict[:*\s]*(.+)$", text)
    if m:
        return m.group(1).strip(" *")
    m = re.search(r"(?is)##\s*Summary\s*\n+(.+?)(?:\n##|\Z)", text)
    return " ".join(m.group(1).split())[:400] if m else "(no verdict yet)"


def _recommendations(exp_id: str) -> str:
    """Pull the evaluator's 'Recommended next steps' section (feeds the planner)."""
    text = _report_text(exp_id)
    m = re.search(r"(?is)#+\s*[\d.]*\s*recommend[^\n]*\n+(.+?)(?:\n#+\s|\Z)", text)
    return m.group(1).strip() if m else ""


class Campaign:
    def __init__(self, name: str, question: str = "", created: str = "", nodes=None):
        self.name = name
        self.question = question
        self.created = created or datetime.now().isoformat(timespec="seconds")
        self.nodes = nodes or []

    @classmethod
    def load(cls, name: str) -> "Campaign":
        d = json.loads((CAMP_DIR / f"{name}.json").read_text(encoding="utf-8"))
        return cls(d["name"], d.get("question", ""), d.get("created", ""), d.get("nodes", []))

    def save(self) -> Path:
        CAMP_DIR.mkdir(parents=True, exist_ok=True)
        p = CAMP_DIR / f"{self.name}.json"
        p.write_text(json.dumps({"name": self.name, "question": self.question,
                                 "created": self.created, "nodes": self.nodes}, indent=2),
                     encoding="utf-8")
        return p

    def add(self, exp_id: str, hypothesis_id: str, parent: str = None,
            because: str = "", status: str = "complete") -> dict:
        node = {"experiment_id": exp_id, "hypothesis_id": hypothesis_id,
                "parent": parent, "spawned_because": because, "status": status,
                "verdict": _verdict(exp_id) if status == "complete" else None,
                "added": datetime.now().isoformat(timespec="seconds")}
        self.nodes.append(node)
        return node

    def latest_complete(self) -> dict:
        done = [n for n in self.nodes if n["status"] == "complete"]
        return done[-1] if done else None

    def abandon(self, exp_id: str, why: str = "") -> bool:
        """Mark a branch abandoned — tried and given up (abandoned-branch detection). Any tokens a
        later replan spends BECAUSE this line died are attributed to it as dead_end (see next_step)."""
        hit = False
        for n in self.nodes:
            if n["experiment_id"] == exp_id:
                n["status"], n["abandoned_because"], n["verdict"] = "abandoned", why, None
                hit = True
        if hit:
            self.save()
        return hit

    def _frontier_abandoned(self) -> bool:
        """True if the most recently added line was abandoned — so replanning is salvaging a dead
        branch, and that synthesis spend is a dead end (conservative: a genuine pivot is tagged too,
        but the cost only exists because the branch failed)."""
        return bool(self.nodes) and self.nodes[-1].get("status") == "abandoned"

    def render(self) -> str:
        L = [f"Campaign: {self.name}", f"Question: {self.question}", ""]
        for n in self.nodes:
            arrow = f"  ({n['parent']} → {n['experiment_id']})" if n["parent"] else "  (root)"
            L.append(f"• {n['experiment_id']} [{n['status']}]{arrow}")
            if n.get("spawned_because"):
                L.append(f"    because: {n['spawned_because']}")
            if n.get("verdict"):
                L.append(f"    verdict: {n['verdict'][:160]}")
        return "\n".join(L)

    def next_step(self) -> str:
        node = self.latest_complete()
        if not node:
            return "No completed experiment to plan from."
        exp = node["experiment_id"]
        recs = _recommendations(exp)
        lineage = " → ".join(n["experiment_id"] for n in self.nodes)
        header = (f"Next-step proposal for campaign '{self.name}'\n"
                  f"  lineage so far: {lineage}\n"
                  f"  last experiment: {exp} — {node['verdict'][:160]}\n")
        proposal = _synthesize(self.question, exp, node["verdict"], recs,
                               dead_branch=self._frontier_abandoned())
        return header + "\n" + proposal


def _synthesize(question: str, last_exp: str, verdict: str, recs: str, dead_branch: bool = False) -> str:
    """Propose the next atomic experiment from the evaluator's recommendations + context.
    LLM-assisted (local); falls back to the raw recommendations if the model is
    unavailable. This is a PROPOSAL — a human approves it into the next experiment.

    `dead_branch`: the line being replanned was abandoned, so the synthesis spend is tagged
    dead_end for the token audit (ADR-0060)."""
    if not recs:
        return "  (no 'Recommended next steps' section found in the evaluation report)"
    try:
        import contextlib
        import llm
        import schemas
        import token_meter
        schema = {"type": "object", "properties": {
            "title": {"type": "string"}, "question": {"type": "string"},
            "key_change": {"type": "string"}, "rationale": {"type": "string"}},
            "required": ["title", "question", "key_change", "rationale"]}
        prompt = (
            f"Campaign question: {question}\n"
            f"Last experiment {last_exp} verdict: {verdict}\n"
            f"The evaluator recommended:\n{recs}\n\n"
            "Propose ONE concrete NEXT atomic experiment that follows from this. Give a "
            "short title, its question, the single most important design CHANGE from the "
            "last experiment (e.g. a better-powered cohort), and a one-line rationale. "
            "Keep it a small, testable, pre-registerable experiment.")
        with (token_meter.outcome("dead_end") if dead_branch else contextlib.nullcontext()):
            r = llm.parse([{"role": "user", "content": prompt}], schema, schemas.NextStep).model_dump()
        return (f"  PROPOSED NEXT EXPERIMENT (draft — needs human approval):\n"
                f"    title:      {r['title']}\n"
                f"    question:   {r['question']}\n"
                f"    key change: {r['key_change']}\n"
                f"    rationale:  {r['rationale']}\n"
                f"  (append as the next atomic experiment; do NOT mutate {last_exp}.)")
    except Exception as err:
        return (f"  Evaluator's recommended next steps (LLM synth unavailable: {err}):\n"
                + "\n".join("    " + ln for ln in recs.splitlines()[:12]))


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "show":
        print(Campaign.load(args[1]).render())
    elif len(args) == 2 and args[0] == "plan":
        print(Campaign.load(args[1]).next_step())
    else:
        print("usage: python campaign.py [show <name> | plan <name>]")
