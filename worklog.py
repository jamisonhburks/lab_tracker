"""worklog — the researcher's ACTIVE working record for a hypothesis (the messy middle).

The substrate is strong at the bookends — formulating a hypothesis (assess_idea, generate_hypothesis)
and promoting a finding (contribute, graduation). But the majority of real work happens BETWEEN
them, in the researcher's own experiment loop: run the analysis, log what came out, iterate across
seeds, and watch progress toward the PRE-REGISTERED success_metric and min_runs. This module is that
loop's memory:

  - a per-hypothesis RUN LEDGER (each run's metrics, seed, pass/fail vs the bar, validity),
  - a persistent WORKLOG (what you tried / open questions — survives across sessions, unlike the
    per-session journal),
  - a "where am I" STATUS view (spec + progress + stability + validity + a suggested next step).

Stores under experiments/<hyp>/runs.jsonl and experiments/<hyp>/worklog.md — alongside the existing
config.yaml / validity.json / tool_ledger.json. Personal tier: in-progress process, not consensus;
runs that clear the bar feed propose_experiment / contribute later. LLM-free.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import store_lock

ROOT = Path(__file__).parent
HYP = ROOT / "hypotheses"
EXP = ROOT / "experiments"


def _who(contributor) -> str:
    return contributor or os.environ.get("SUBSTRATE_CONTRIBUTOR") or os.environ.get("USER") or "you"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hyp_id(hyp: str) -> str:
    """Normalize 'H001' / 'H001_slug' / a path into the bare id (H001)."""
    return Path(str(hyp)).stem.split("_")[0].strip()


# --------------------------------------------------------------------------- #
# The hypothesis spec (pre-registration) + per-hypothesis paths.               #
# --------------------------------------------------------------------------- #
def load_hypothesis(hyp: str) -> dict:
    hid = _hyp_id(hyp)
    hits = sorted(HYP.glob(f"{hid}*.y*ml")) if HYP.exists() else []
    if not hits:
        return {}
    try:
        import yaml
        return yaml.safe_load(hits[0].read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _exp_dir(hyp: str) -> Path:
    return EXP / _hyp_id(hyp)


def _runs_path(hyp: str) -> Path:
    return _exp_dir(hyp) / "runs.jsonl"


def _worklog_path(hyp: str) -> Path:
    return _exp_dir(hyp) / "worklog.md"


# --------------------------------------------------------------------------- #
# The run ledger.                                                              #
# --------------------------------------------------------------------------- #
def log_run(hyp: str, metrics: dict = None, seed=None, passed: bool = None,
            valid: bool = None, note: str = "", contributor=None) -> str:
    """Record ONE experiment run against a hypothesis: its metric(s), seed, whether it met the
    pre-registered success_metric (`passed` — the researcher/thinker's call, no NL parsing), and
    validity (`valid=False` = a halt gate failed). Builds the ledger the min_runs discipline needs."""
    hid = _hyp_id(hyp)
    entry = {"ts": _now(), "by": _who(contributor), "seed": seed,
             "metrics": metrics or {}, "passed": passed, "valid": valid, "note": (note or "").strip()}
    _exp_dir(hyp).mkdir(parents=True, exist_ok=True)
    store_lock.append_jsonl(_runs_path(hyp), entry)
    n = len(runs(hyp))
    minr = load_hypothesis(hyp).get("min_runs")
    prog = f" ({n}/{minr} runs toward min_runs)" if minr else f" ({n} run(s) logged)"
    tag = "" if passed is None else ("  ✓ met the bar" if passed else "  ✗ below the bar")
    return f"logged run for {hid}{prog}{tag}."


def runs(hyp: str) -> list:
    p = _runs_path(hyp)
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()] if p.exists() else []


def stability(hyp: str) -> dict:
    """Per-metric {n, mean, sd, min, max} across logged runs — the reproducibility read the spec's
    'reproducibly across >= N seeds' demands. Only numeric metrics are summarized."""
    rs = runs(hyp)
    keys = {k for r in rs for k, v in (r.get("metrics") or {}).items() if isinstance(v, (int, float))}
    out = {}
    for k in sorted(keys):
        vals = [r["metrics"][k] for r in rs if isinstance((r.get("metrics") or {}).get(k), (int, float))]
        n = len(vals)
        mean = sum(vals) / n
        sd = (sum((v - mean) ** 2 for v in vals) / n) ** 0.5
        out[k] = {"n": n, "mean": mean, "sd": sd, "min": min(vals), "max": max(vals)}
    return out


# --------------------------------------------------------------------------- #
# The persistent worklog (notes that survive across sessions).                 #
# --------------------------------------------------------------------------- #
def note(hyp: str, text: str, contributor=None) -> str:
    """Append a working note to the hypothesis's persistent worklog — the 'what I tried / open
    questions' record, distinct from the per-session journal."""
    hid = _hyp_id(hyp)
    _exp_dir(hyp).mkdir(parents=True, exist_ok=True)
    p = _worklog_path(hyp)
    with store_lock.critical(p):
        header = "" if p.exists() else f"# Worklog — {hid}\n\n"
        with p.open("a", encoding="utf-8") as f:
            f.write(header + f"- {_now()} ({_who(contributor)}): {text.strip()}\n")
    return f"noted to {hid} worklog."


# --------------------------------------------------------------------------- #
# "Where am I" — the active-work status view.                                  #
# --------------------------------------------------------------------------- #
def _next_step(spec: dict, n: int, minr, n_pass: int, n_invalid: int) -> str:
    st = spec.get("status")
    if st and st not in ("approved", "running", "complete"):
        return f"hypothesis is '{st}' — get it approved before committing to runs."
    if n == 0:
        return "no runs yet — run the experiment and log_run its result (metrics, seed, passed)."
    if n_invalid:
        return "a run was invalidated (a validity HALT gate failed) — fix the pipeline, then re-run."
    if minr and n < minr:
        return f"{n}/{minr} runs — run again with a NEW seed to satisfy min_runs."
    if minr and n_pass >= minr:
        return "min_runs met and consistently passing → propose_experiment / contribute the finding."
    if minr and n >= minr and n_pass < minr:
        return ("min_runs met but the success_metric isn't consistently met — the result may be "
                "negative or underpowered; check stability, consider a better-powered test.")
    return "log runs as you iterate (log_run), and jot open questions to the worklog (worklog_note)."


def summary(hyp: str) -> dict:
    """Compact active-work summary for one hypothesis — id/title/status, run counts, and the
    next-step heuristic. Feeds the warm start's 'your experiments in flight' section."""
    spec, rs = load_hypothesis(hyp), runs(hyp)
    minr = spec.get("min_runs")
    n = len(rs)
    n_pass = sum(1 for r in rs if r.get("passed") is True)
    n_invalid = sum(1 for r in rs if r.get("valid") is False)
    return {"id": _hyp_id(hyp), "title": spec.get("title", ""), "status": spec.get("status"),
            "n_runs": n, "min_runs": minr, "n_pass": n_pass, "n_invalid": n_invalid,
            "next": _next_step(spec, n, minr, n_pass, n_invalid)}


def active_hypotheses(statuses=("approved", "running")) -> list:
    """Summaries for in-flight hypotheses (status in `statuses`), most-worked first — so the warm
    start can point a researcher back to where they should resume their own experiments."""
    out = []
    for f in (sorted(HYP.glob("*.y*ml")) if HYP.exists() else []):
        try:
            import yaml
            spec = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if spec.get("status") in statuses:
            out.append(summary(f.stem.split("_")[0]))
    return sorted(out, key=lambda s: (-s["n_runs"], s["id"]))


def status(hyp: str) -> str:
    """The active-work dashboard: spec + success_metric, runs vs min_runs, per-run results,
    stability across seeds, latest validity gates, and a suggested next step."""
    hid = _hyp_id(hyp)
    spec, rs = load_hypothesis(hyp), runs(hyp)
    if not spec and not rs:
        return f"No hypothesis {hid} (hypotheses/{hid}*.yaml) and no runs logged."

    minr = spec.get("min_runs")
    n = len(rs)
    n_pass = sum(1 for r in rs if r.get("passed") is True)
    n_invalid = sum(1 for r in rs if r.get("valid") is False)
    scored = any(r.get("passed") is not None for r in rs)

    out = [f"■ Hypothesis {hid} — status: {spec.get('status', '?')}"]
    if spec.get("title"):
        out.append(f"  {str(spec['title']).strip()[:100]}")
    if spec.get("success_metric"):
        out.append(f"  success metric: {str(spec['success_metric']).strip()[:160]}")

    out.append(f"\n  runs logged: {(f'{n}/{minr}' if minr else n)}"
               + (f" · {n_pass} met the bar" if scored else "")
               + (f" · {n_invalid} invalidated" if n_invalid else ""))
    for r in rs[-5:]:
        mets = ", ".join(f"{k}={v}" for k, v in (r.get("metrics") or {}).items())
        flag = "✓" if r.get("passed") else "✗" if r.get("passed") is False else "·"
        seed = f"seed={r['seed']} " if r.get("seed") is not None else ""
        inv = " [INVALID]" if r.get("valid") is False else ""
        out.append(f"    {flag} {r['ts'][:16]} {seed}{mets}{inv}"
                   + (f"  — {r['note'][:50]}" if r.get("note") else ""))

    st = stability(hyp)
    if st:
        out.append("\n  stability across runs:")
        for k, s in st.items():
            out.append(f"    {k}: mean {s['mean']:.4g} ± {s['sd']:.3g}  "
                       f"(n={s['n']}, range {s['min']:.4g}–{s['max']:.4g})")

    vpath = _exp_dir(hyp) / "validity.json"
    if vpath.exists():
        try:
            gates = json.loads(vpath.read_text(encoding="utf-8"))
            npass = sum(1 for g in gates if g.get("passed"))
            halt = any((not g.get("passed")) and g.get("severity") == "halt" for g in gates)
            out.append(f"\n  validity gates (last saved): {npass}/{len(gates)} passed"
                       + ("  [INVALID — halt failed]" if halt else ""))
        except Exception:
            pass

    out.append(f"\n→ next: {_next_step(spec, n, minr, n_pass, n_invalid)}")
    return "\n".join(out)


if __name__ == "__main__":   # hermetic demo: temp dirs, a stub hypothesis, three runs, a status view
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    HYP = tmp / "hypotheses"
    EXP = tmp / "experiments"
    HYP.mkdir()
    (HYP / "H001_demo.yaml").write_text(
        'id: H001\ntitle: "T2D-AD shared genes differential expression"\n'
        'success_metric: ">=3 shared genes at BH-FDR<0.05 and |d|>=0.5, across >=3 seeds"\n'
        'min_runs: 3\nstatus: approved\n', encoding="utf-8")

    for s, nsig, ok in [(1, 4, True), (2, 5, True), (3, 3, True)]:
        print(log_run("H001", metrics={"n_sig": nsig, "min_d": 0.6}, seed=s, passed=ok, valid=True))
    print(note("H001", "IDE and IAPP are the most stable hits across seeds"))
    print("\n" + status("H001"))
