"""tool_ledger — per-run record of INTENDED vs ACTUAL tool use.

Answers the audit question: what tools did the agent think it would need, which did
it ACTUALLY use, in what order, and across which layer (orchestrator / specialist)?
Each run/experiment gets one JSON trace so plan-vs-actual is auditable — the tool
analogue of the reproducibility log.

Intended tools come from a pre-flight planning step (the agent declares, before
acting, which tools it expects to need and why). Actual tools are recorded as they
fire, in order. `diff()` surfaces the gap: planned-but-unused and used-but-unplanned
— a direct read on the agent's tool-selection calibration.

Ledgers are written under memory/tool_ledgers/ (gitignored run data). Attach one to
an experiment by passing experiment_id + saving into experiments/{id}/tool_ledger.json.
"""

import json
from datetime import datetime
from pathlib import Path

LEDGER_DIR = Path(__file__).parent / "memory" / "tool_ledgers"


class ToolLedger:
    """Records intended and actual tool calls for one run, in order."""

    def __init__(self, task: str = "", run_id: str = "", experiment_id: str | None = None):
        self.task = task
        self.run_id = run_id
        self.experiment_id = experiment_id
        self.intended: list = []     # [{"tool": str, "why": str}]
        self.actual: list = []       # [{"seq","tool","layer","args","ts"}]
        self.spend: list = []        # [SpendEvent-as-dict] — this run's token spend (co-located)
        self._seq = 0

    def attach_spend(self, events) -> None:
        """Co-locate this run's token spend (token_meter.SpendEvent list) with its tool trace.
        The durable audit source is memory/token_ledgers/; this is a per-run convenience copy."""
        from dataclasses import asdict, is_dataclass
        self.spend = [asdict(e) if is_dataclass(e) else dict(e) for e in (events or [])]

    def plan(self, intended: list) -> None:
        """Declare the tools the agent expects to need (names or {tool, why} dicts)."""
        self.intended = [{"tool": i} if isinstance(i, str) else
                         {"tool": i.get("tool", ""), "why": i.get("why", "")}
                         for i in (intended or []) if (i if isinstance(i, str) else i.get("tool"))]

    def record(self, tool: str, args: dict | None = None, layer: str = "orchestrator") -> None:
        """Record one actual tool call, in firing order."""
        self._seq += 1
        self.actual.append({"seq": self._seq, "tool": tool, "layer": layer,
                            "args": args or {}, "ts": datetime.now().isoformat(timespec="seconds")})

    def diff(self) -> dict:
        planned = [i["tool"] for i in self.intended]
        used_order = [a["tool"] for a in self.actual]
        planned_set, used_set = set(planned), set(used_order)
        return {
            "planned": planned,
            "used_in_order": used_order,
            "planned_not_used": [t for t in dict.fromkeys(planned) if t not in used_set],
            "used_not_planned": [t for t in dict.fromkeys(used_order) if t not in planned_set],
        }

    def to_dict(self) -> dict:
        return {"run_id": self.run_id, "experiment_id": self.experiment_id,
                "task": self.task, "intended": self.intended, "actual": self.actual,
                "spend": self.spend, "diff": self.diff()}

    def save(self, path: str | Path | None = None) -> Path:
        if path is None:
            LEDGER_DIR.mkdir(parents=True, exist_ok=True)
            path = LEDGER_DIR / f"{self.run_id or 'run'}.json"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    def summary(self) -> str:
        """One-block plan-vs-actual readout."""
        d = self.diff()
        lines = [f"[tool ledger: {self.run_id or 'run'}]",
                 f"  intended ({len(d['planned'])}): {', '.join(d['planned']) or '(none declared)'}",
                 f"  actual   ({len(d['used_in_order'])}): {' → '.join(d['used_in_order']) or '(none)'}"]
        if d["planned_not_used"]:
            lines.append(f"  planned but NOT used: {', '.join(d['planned_not_used'])}")
        if d["used_not_planned"]:
            lines.append(f"  used but NOT planned: {', '.join(d['used_not_planned'])}")
        return "\n".join(lines)
