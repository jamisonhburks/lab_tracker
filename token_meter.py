"""token_meter — attribute every LLM token to a RESEARCH ACTIVITY and an OUTCOME.

The audit question a PI actually asks is not "how many tokens did we spend" but "where
did they go, and how much was wasted?". Answering it needs TWO orthogonal labels per LLM
call, because waste lives almost entirely in the second one:

  ACTIVITY  — what kind of work the tokens did
              (lit_search, kg_traversal, planning, code_impl, critique, ...)
  OUTCOME   — whether it advanced the research
              productive | retry | redundant | dead_end | speculative | unknown

"40k tokens on lit_search" is neither good nor bad until you know how many were `redundant`
(re-fetching what memory already held) or `retry` (re-asking after a bad parse).

Capture is automatic and central: `llm.chat` / `llm.parse` call `on_llm_call()` with the
token usage the provider already returns (Ollama `prompt_eval_count`/`eval_count`; Anthropic
`.usage`). The ACTIVITY/OUTCOME come from the context the caller set with `activity(...)`,
so instrumenting the agent's tool loop in ONE place attributes every tool-internal LLM call.
A bound sink (typically a ToolLedger) collects the events; if nothing is bound, it is a no-op
(so experiments, tests, and bare scripts are unaffected).

Local Ollama tokens are COUNTED but priced at $0 — cost-free, not effort-free (ADR-0060).
Claude/specialist tokens are priced per model. So both "paid spend by activity" and "total
effort by activity" are answerable, and the local↔frontier asymmetry (ADR-0023) is explicit.
"""
from __future__ import annotations

import atexit
import contextvars
import json
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# Vocabularies — the single source of truth (documented in ADR-0060).          #
# --------------------------------------------------------------------------- #
ACTIVITIES = {
    # discovery / retrieval
    "lit_search", "kg_traversal", "file_nav", "memory_recall",
    # reasoning / synthesis
    "hypothesis_gen", "evidence_assess", "planning", "interpretation",
    # production
    "code_impl", "experiment_run", "writing",
    # verification
    "critique", "novelty_check",
    # overhead
    "normalization", "bookkeeping",
    # fallback
    "uncategorized",
}

OUTCOMES = {"productive", "retry", "redundant", "dead_end", "speculative", "unknown"}
# `speculative` is open-ended by design (serendipity) — tolerated, not counted as waste.
WASTE_OUTCOMES = {"retry", "redundant", "dead_end"}

# tool name -> activity. Grounded in agent.py TOOLS + mcp_server.py @mcp.tool set.
TOOL_ACTIVITY = {
    "search_pubmed": "lit_search",
    "curate_literature": "lit_search",
    "deep_search": "lit_search",
    "deep_fetch": "lit_search",
    "read_file": "file_nav",
    "find_paths": "kg_traversal",
    "query_kg": "kg_traversal",
    "query_graph": "kg_traversal",
    "query_curated_kg": "kg_traversal",
    "query_curated_findings": "kg_traversal",
    "recall": "memory_recall",
    "recall_memory": "memory_recall",
    "generate_hypothesis": "hypothesis_gen",
    "refine_hypothesis": "hypothesis_gen",
    "assess_hypothesis": "evidence_assess",
    "calibrate_link": "evidence_assess",
    "criticize_curated_kg": "critique",
}


def activity_for_tool(name: str) -> str:
    """Map a tool name to its research-activity label (uncategorized if unknown)."""
    return TOOL_ACTIVITY.get(name, "uncategorized")


def resolve_activity(name: str) -> tuple[str, bool, str]:
    """Resolve a tool/context name to (label, provisional, hint).

    When we cannot CONFIDENTLY map the work to a known activity, we do NOT silently drop it into
    `uncategorized` — that hides emerging kinds of work. Instead we flag it PROVISIONAL and keep a
    semantic `hint` (here, the tool name). A later discovery pass (label_discovery.py) clusters
    provisional hints across runs/users to surface activity groups we simply have no name for yet.
    """
    if name in TOOL_ACTIVITY:
        return (TOOL_ACTIVITY[name], False, "")
    return ("uncategorized", True, name or "")


# --------------------------------------------------------------------------- #
# Pricing — USD per 1M tokens (input, output). Local generation is $0.         #
# List-price ESTIMATES; editable at runtime via set_prices(). Counts, not the  #
# exact dollar figure, are the load-bearing audit signal.                      #
# --------------------------------------------------------------------------- #
_PRICES = {
    "claude-opus-4-8":   (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5":  (1.0, 5.0),
}


def set_prices(mapping: dict) -> None:
    """Override/extend the per-model (input, output) $/1M-token table."""
    _PRICES.update(mapping)


def _match_model(model: str) -> str | None:
    m = (model or "").lower()
    for key in _PRICES:
        if m.startswith(key):            # tolerate suffixes like [1m] / dated variants
            return key
    return None


def price_usd(backend: str, model: str, in_tok: int, out_tok: int) -> float:
    """Cost of a call. Non-anthropic backends (local Ollama) are cost-free ($0)."""
    if (backend or "").lower() != "anthropic":
        return 0.0
    key = _match_model(model)
    if key is None:
        return 0.0
    pin, pout = _PRICES[key]
    return (in_tok / 1e6) * pin + (out_tok / 1e6) * pout


# --------------------------------------------------------------------------- #
# Spend events + in-memory meter                                               #
# --------------------------------------------------------------------------- #
@dataclass
class SpendEvent:
    activity: str
    outcome: str
    backend: str
    model: str
    in_tok: int
    out_tok: int
    usd: float
    layer: str = "orchestrator"      # orchestrator | specialist | experiment | external
    provisional: bool = False        # activity could not be confidently resolved
    hint: str = ""                   # semantic hint for later label discovery
    run_id: str = ""
    ts: str = ""

    @property
    def total_tok(self) -> int:
        return self.in_tok + self.out_tok

    @property
    def is_waste(self) -> bool:
        return self.outcome in WASTE_OUTCOMES

    @property
    def is_paid(self) -> bool:
        return self.usd > 0.0


class SpendMeter:
    """Accumulates SpendEvents and rolls them up for the audit."""

    def __init__(self):
        self.events: list[SpendEvent] = []

    def add(self, ev: SpendEvent) -> None:
        self.events.append(ev)

    # -- rollups --
    def by_activity(self) -> dict:
        out: dict[str, dict] = {}
        for e in self.events:
            a = out.setdefault(e.activity, {"tok": 0, "usd": 0.0, "waste_tok": 0, "calls": 0})
            a["tok"] += e.total_tok
            a["usd"] += e.usd
            a["calls"] += 1
            if e.is_waste:
                a["waste_tok"] += e.total_tok
        return out

    def by_activity_outcome(self) -> dict:
        out: dict[tuple, dict] = {}
        for e in self.events:
            a = out.setdefault((e.activity, e.outcome), {"tok": 0, "usd": 0.0, "calls": 0})
            a["tok"] += e.total_tok
            a["usd"] += e.usd
            a["calls"] += 1
        return out

    def totals(self) -> dict:
        tok = sum(e.total_tok for e in self.events)
        waste = sum(e.total_tok for e in self.events if e.is_waste)
        return {"tok": tok, "in_tok": sum(e.in_tok for e in self.events),
                "out_tok": sum(e.out_tok for e in self.events),
                "usd": sum(e.usd for e in self.events), "calls": len(self.events),
                "waste_tok": waste,
                "waste_frac": (waste / tok) if tok else 0.0}

    def waste_report(self) -> list[dict]:
        """Per-activity waste share, worst first — the audit's headline."""
        rows = []
        for act, a in self.by_activity().items():
            frac = (a["waste_tok"] / a["tok"]) if a["tok"] else 0.0
            rows.append({"activity": act, "tok": a["tok"], "usd": a["usd"],
                         "waste_tok": a["waste_tok"], "waste_frac": frac})
        return sorted(rows, key=lambda r: (-r["waste_frac"], -r["tok"]))


# --------------------------------------------------------------------------- #
# Capture — ALWAYS-ON so EVERY paid call is covered, from any entry point.      #
#                                                                              #
# Capture lives at the provider adapter (llm.py), so the agent loop, the       #
# specialist (Claude), tools, and standalone experiments are all metered with  #
# no per-call wiring. A process-global meter always accumulates; optional       #
# observers get a live copy; flush() persists to a durable token ledger. Paid   #
# tokens that bypass the adapter (harness subagents, batch jobs) are logged     #
# with record_external() so nothing paid escapes the audit.                    #
# --------------------------------------------------------------------------- #
LEDGER_DIR = Path(__file__).parent / "memory" / "token_ledgers"

_activity: contextvars.ContextVar[str] = contextvars.ContextVar("tm_activity", default="uncategorized")
_outcome: contextvars.ContextVar[str] = contextvars.ContextVar("tm_outcome", default="productive")
_provisional: contextvars.ContextVar[bool] = contextvars.ContextVar("tm_provisional", default=False)
_hint: contextvars.ContextVar[str] = contextvars.ContextVar("tm_hint", default="")
_layer: contextvars.ContextVar[str] = contextvars.ContextVar("tm_layer", default="orchestrator")
_run_id: contextvars.ContextVar[str] = contextvars.ContextVar("tm_run_id", default="")

_meter = SpendMeter()          # process-global, always-on
_observers: list = []          # optional callables(SpendEvent) for live readouts
_flushed = 0                   # how many events are already persisted
_autoflush = False


def meter() -> SpendMeter:
    """The process-global meter accumulating every captured call this session."""
    return _meter


def reset() -> None:
    """Clear the global meter (mainly for tests)."""
    global _flushed
    _meter.events.clear()
    _flushed = 0


def observe(fn) -> None:
    """Register an extra callable(SpendEvent) — e.g. a live per-run readout."""
    _observers.append(fn)


def bind(fn) -> None:          # back-compat alias; capture no longer REQUIRES a sink
    observe(fn)


def unbind() -> None:
    _observers.clear()


@contextmanager
def activity(label: str, outcome: str = "productive", provisional: bool = False, hint: str = ""):
    """Mark all LLM calls in this block as `label` work (with outcome + optional provisional/hint)."""
    a = _activity.set(label if label in ACTIVITIES else "uncategorized")
    o = _outcome.set(outcome if outcome in OUTCOMES else "unknown")
    p = _provisional.set(bool(provisional))
    h = _hint.set(hint or "")
    try:
        yield
    finally:
        _activity.reset(a); _outcome.reset(o); _provisional.reset(p); _hint.reset(h)


@contextmanager
def outcome(label: str):
    """Override just the OUTCOME for LLM calls in this block (retry/redundant/dead_end/...)."""
    o = _outcome.set(label if label in OUTCOMES else "unknown")
    try:
        yield
    finally:
        _outcome.reset(o)


@contextmanager
def run(run_id: str = "", layer: str = "orchestrator"):
    """Tag LLM calls in this block with a run id and a cost LAYER (orchestrator/specialist/...)."""
    r = _run_id.set(run_id or "")
    l = _layer.set(layer or "orchestrator")
    try:
        yield
    finally:
        _run_id.reset(r); _layer.reset(l)


def _emit(ev: SpendEvent) -> SpendEvent:
    _meter.add(ev)
    for fn in _observers:
        try:
            fn(ev)
        except Exception:          # telemetry must never break the run
            pass
    return ev


def on_llm_call(backend: str, model: str, in_tok: int, out_tok: int) -> SpendEvent:
    """Record one adapter-routed LLM call under the current activity/outcome/layer/run."""
    in_tok, out_tok = int(in_tok or 0), int(out_tok or 0)
    return _emit(SpendEvent(
        activity=_activity.get(), outcome=_outcome.get(),
        backend=(backend or "").lower(), model=model or "",
        in_tok=in_tok, out_tok=out_tok, usd=price_usd(backend, model, in_tok, out_tok),
        layer=_layer.get(), provisional=_provisional.get(), hint=_hint.get(),
        run_id=_run_id.get(), ts=datetime.now().isoformat(timespec="seconds")))


def record_external(activity_label: str, backend: str, model: str, in_tok: int, out_tok: int, *,
                    outcome: str = "productive", layer: str = "external", run_id: str = "",
                    provisional: bool = False, hint: str = "") -> SpendEvent:
    """Log PAID tokens that did NOT flow through llm.py — harness subagents, batch jobs, the
    frontier judge in experiments — so 'cover all external tokens' holds even off the adapter path."""
    in_tok, out_tok = int(in_tok or 0), int(out_tok or 0)
    return _emit(SpendEvent(
        activity=activity_label if activity_label in ACTIVITIES else "uncategorized",
        outcome=outcome if outcome in OUTCOMES else "unknown",
        backend=(backend or "").lower(), model=model or "",
        in_tok=in_tok, out_tok=out_tok, usd=price_usd(backend, model, in_tok, out_tok),
        layer=layer, provisional=provisional, hint=hint,
        run_id=run_id, ts=datetime.now().isoformat(timespec="seconds")))


def flush(path: str | Path | None = None) -> Path | None:
    """Append not-yet-persisted events as JSONL to the durable token ledger. Best-effort."""
    global _flushed
    new = _meter.events[_flushed:]
    if not new:
        return None
    if path is None:
        LEDGER_DIR.mkdir(parents=True, exist_ok=True)
        path = LEDGER_DIR / f"spend-{datetime.now().strftime('%Y%m%d')}.jsonl"
    path = Path(path)
    try:
        with path.open("a", encoding="utf-8") as f:
            for ev in new:
                f.write(json.dumps(asdict(ev)) + "\n")
        _flushed = len(_meter.events)
    except Exception:
        return None
    return path


def enable_autoflush() -> None:
    """Persist the session's spend at process exit — call from long-lived entry points."""
    global _autoflush
    if not _autoflush:
        atexit.register(flush)
        _autoflush = True


def event_dict(ev: SpendEvent) -> dict:
    return asdict(ev)


def summary_line(events: list | None = None) -> str:
    """One-line spend readout for a run (defaults to the whole session)."""
    evs = _meter.events if events is None else events
    if not evs:
        return ""
    tok = sum(e.total_tok for e in evs)
    paid = sum(e.usd for e in evs)
    waste = sum(e.total_tok for e in evs if e.is_waste)
    prov = sum(1 for e in evs if e.provisional)
    top = sorted({e.activity for e in evs},
                 key=lambda a: -sum(e.total_tok for e in evs if e.activity == a))[:3]
    share = {a: sum(e.total_tok for e in evs if e.activity == a) for a in top}
    parts = " ".join(f"{a} {round(100*share[a]/tok)}%" for a in top if tok)
    prov_note = f" · {prov} provisional" if prov else ""
    return (f"[tokens: {tok:,} · ${paid:.2f} paid · {parts} · "
            f"waste {round(100*waste/tok) if tok else 0}%{prov_note}]")
