"""calibration — is the lab's confidence actually CALIBRATED? (Tier 2 self-audit.)

`confidence.py` is explicit that its number is "heuristic and interpretable, not a calibrated
probability." A lab brain shouldn't just emit confidence — it should be ACCOUNTABLE for it:
of the edges it called 0.9, how many actually held up? This module turns the belief lifecycle
(ADR-0053) into a reliability check, so the substrate audits its own confidence instead of
flattering itself. That accountability is a rigor feature (ADR-0052): a system that never
checks its calibration drifts toward over-confidence.

Where do "realized outcomes" come from without a labelled gold set? From signals the substrate
ALREADY generates — two independent, clearly-labelled lenses:

  - ADJUDICATED — resolved contradictions. When a conflict on an edge the lab believed at
    confidence c is resolved `upheld`, that high-confidence belief was RIGHT (outcome 1);
    `overturned` means it was WRONG (outcome 0). `contested` is excluded (genuinely ambiguous).
    This is the strongest signal — an actual adjudication.
  - STABILITY — belief reversals. When the lab first SETTLED on a decisive belief
    (`supported`/`refuted`) at confidence c, did accumulating evidence keep it there (outcome 1)
    or flip it to the opposite/contested (outcome 0)? A confident call that later reversed was
    over-confident given what was then known.

These are the substrate's own proxies, NOT an external gold standard — every rendering says so,
and the audit stays HUMBLE below a data floor rather than reporting a misleading number.

Read-only over `beliefs` logs. Reports a reliability table, Expected Calibration Error (ECE),
Brier score, and a plain-English over/under-confidence verdict. Diagnostic only — it flags
miscalibration; fitting a recalibration map onto the scorer is a clean follow-on seam.
"""

from dataclasses import dataclass

import beliefs

MIN_OUTCOMES = 8                          # below this, calibration isn't meaningful — stay humble
_BINS = [(i / 10, (i + 1) / 10) for i in range(10)]      # 0.0–0.1 … 0.9–1.0
_DECISIVE = {"supported": "+", "refuted": "-"}           # statuses with a settled position
_BAR_W = 20


@dataclass
class Outcome:
    predicted: float      # the confidence the lab held
    hit: int              # 1 if the belief proved correct, 0 if not
    lens: str             # "adjudicated" | "stability"
    edge: str
    who: str | None = None  # the member whose confident call this outcome scores (None = unattributed)


def _edge_owner(key: str) -> str | None:
    """Who is accountable for an edge's ESTABLISHED confidence — the contributor of the most recent
    DECISIVE belief revision on it. The contradiction ledger stores no owner on the established
    belief, so we recover it from the belief-event history (attributes the adjudicated lens)."""
    owner = None
    for e in beliefs._events(key):
        if e.get("status") in _DECISIVE:
            c = (e.get("trigger") or {}).get("contributor")
            if c:
                owner = c
    return owner


# --------------------------------------------------------------------------- #
# Outcome extraction — the substrate's own realized signals.                   #
# --------------------------------------------------------------------------- #
def _adjudicated_outcomes() -> list:
    """Resolved contradictions: established-belief confidence vs. upheld(1)/overturned(0)."""
    events = beliefs._contra_events()
    opens = {e["id"]: e for e in events if e.get("event") == "open"}
    out = []
    for e in events:
        if e.get("event") != "resolve":
            continue
        opened = opens.get(e["id"])
        res = e.get("resolution")
        if not opened or res == "contested":
            continue
        conf = (opened.get("established") or {}).get("confidence")
        if conf is None:
            continue
        out.append(Outcome(float(conf), 1 if res == "upheld" else 0, "adjudicated",
                           opened["key"], who=_edge_owner(opened["key"])))
    return out


def _stability_outcomes() -> list:
    """Belief reversals: the confidence at the FIRST decisive reading of an edge vs. whether the
    final reading still agrees. Only edges revised at least once after settling are scored."""
    by_edge = {}
    for e in beliefs._events():
        by_edge.setdefault(e["key"], []).append(e)
    out = []
    for key, seq in by_edge.items():
        first = next((e for e in seq if e["status"] in _DECISIVE), None)
        if first is None or seq[-1] is first:            # never settled, or never re-tested
            continue
        final_class = _DECISIVE.get(seq[-1]["status"])   # None if it drifted to contested
        hit = 1 if final_class == _DECISIVE[first["status"]] else 0
        who = (first.get("trigger") or {}).get("contributor")   # who made the confident call
        out.append(Outcome(float(first["confidence"]), hit, "stability", key, who=who))
    return out


def _select(lens: str) -> list:
    adj, stab = _adjudicated_outcomes(), _stability_outcomes()
    return {"adjudicated": adj, "stability": stab}.get(lens, adj + stab)


# --------------------------------------------------------------------------- #
# Calibration math.                                                            #
# --------------------------------------------------------------------------- #
def _bins(outcomes: list) -> list:
    """Non-empty reliability bins: (lo, hi, n, mean_predicted, observed_accuracy)."""
    rows = []
    for lo, hi in _BINS:
        b = [o for o in outcomes if (lo <= o.predicted < hi) or (hi == 1.0 and o.predicted == 1.0)]
        if b:
            rows.append((lo, hi, len(b), sum(o.predicted for o in b) / len(b),
                         sum(o.hit for o in b) / len(b)))
    return rows


def _ece(outcomes: list, rows: list) -> float:
    n = len(outcomes)
    return sum((cnt / n) * abs(pred - obs) for _, _, cnt, pred, obs in rows) if n else 0.0


def _brier(outcomes: list) -> float:
    return sum((o.predicted - o.hit) ** 2 for o in outcomes) / len(outcomes) if outcomes else 0.0


def _net_bias(outcomes: list) -> float:
    """Mean(predicted − observed). > 0 over-confident, < 0 under-confident."""
    return sum(o.predicted - o.hit for o in outcomes) / len(outcomes) if outcomes else 0.0


def audit(lens: str = "all") -> dict:
    """Structured calibration report for `lens` in {all, adjudicated, stability}."""
    outcomes = _select(lens)
    rows = _bins(outcomes)
    return {"lens": lens, "n": len(outcomes), "bins": rows, "ece": _ece(outcomes, rows),
            "brier": _brier(outcomes), "net_bias": _net_bias(outcomes),
            "n_adjudicated": len(_adjudicated_outcomes()), "n_stability": len(_stability_outcomes())}


def audit_member(member: str, lens: str = "all") -> dict:
    """Calibration for ONE member — only the outcomes attributable to their confident calls.
    `meaningful` stays False until a member has >= MIN_OUTCOMES of their own, so we never grade a
    person on two data points. Same shape as audit(), plus `who`."""
    outcomes = [o for o in _select(lens) if o.who == member]
    rows = _bins(outcomes)
    return {"who": member, "lens": lens, "n": len(outcomes), "bins": rows,
            "ece": _ece(outcomes, rows), "brier": _brier(outcomes),
            "net_bias": _net_bias(outcomes), "meaningful": len(outcomes) >= MIN_OUTCOMES}


def audit_by_member(lens: str = "all") -> dict:
    """{member: audit_member(...)} for every attributed member — the per-member calibration map.
    Unattributed outcomes (who is None) are dropped. Callers decide what to show: a member's own
    view can name their lean; a lab-wide view should aggregate (don't rank colleagues)."""
    members = {o.who for o in _select(lens) if o.who}
    return {m: audit_member(m, lens) for m in members}


# --------------------------------------------------------------------------- #
# Rendering.                                                                   #
# --------------------------------------------------------------------------- #
_PROXY = ("(Outcomes are the substrate's OWN signals — resolved contradictions + belief "
          "reversals — not an external gold standard; calibration sharpens as more disputes "
          "are adjudicated.)")


def render(lens: str = "all") -> str:
    a = audit(lens)
    n = a["n"]
    if n < MIN_OUTCOMES:
        return (f"Not enough realized outcomes to calibrate yet "
                f"({n} so far — need ≥ {MIN_OUTCOMES}; adjudicated={a['n_adjudicated']}, "
                f"stability={a['n_stability']}).\n"
                "Calibration needs settled signal: resolve contradictions (resolve_contradiction) "
                "and let beliefs accumulate/reverse. Come back once the lab has settled a few "
                "disputes.\n" + _PROXY)

    lines = [f"Confidence calibration — {lens} lens, {n} realized outcome(s) "
             f"(adjudicated={a['n_adjudicated']}, stability={a['n_stability']})", ""]
    lines.append("  conf band    n   pred    held    gap           reliability (held-up rate)")
    for lo, hi, cnt, pred, obs in a["bins"]:
        gap = obs - pred
        tag = "over " if gap < -0.02 else "under" if gap > 0.02 else "  ok "
        bar = "█" * round(obs * _BAR_W)
        lines.append(f"  {lo:.1f}–{hi:.1f}   {cnt:3d}  {pred:.2f}   {obs:.2f}   "
                     f"{gap:+.2f} {tag}  ▕{bar:<{_BAR_W}}▏")

    ece, bias, brier = a["ece"], a["net_bias"], a["brier"]
    grade = ("WELL CALIBRATED" if ece < 0.05 else
             "MODERATELY MISCALIBRATED" if ece < 0.15 else "POORLY CALIBRATED")
    lean = ("OVER-confident (its numbers run higher than reality)" if bias > 0.02 else
            "UNDER-confident (its numbers run lower than reality)" if bias < -0.02 else
            "roughly unbiased")
    lines += ["", f"  ECE {ece:.2f} · Brier {brier:.2f} · net bias {bias:+.2f} → {grade}.",
              f"  Overall the lab is {lean}."]

    worst = max(a["bins"], key=lambda r: abs(r[4] - r[3]))
    lo, hi, cnt, pred, obs = worst
    if abs(obs - pred) >= 0.05:
        verb = "Trust" if obs < pred else "You can trust"
        lines.append(f"  Worst band {lo:.1f}–{hi:.1f}: called ~{pred:.2f} but {obs:.2f} held up "
                     f"(n={cnt}). {verb} these edges "
                     f"{'less' if obs < pred else 'more'} than the raw number suggests.")
    lines += ["", _PROXY]
    return "\n".join(lines)


if __name__ == "__main__":
    # Hermetic demo: synthesize a mildly OVER-confident lab (high-confidence calls that reversed)
    # and show the reliability audit. No real logs touched.
    def be(key, conf, status):
        return {"key": key, "confidence": conf, "status": status}

    synth_belief = []
    # High band 0.9–1.0: 6 settled-supported edges, 2 later reversed → over-confident up top.
    for i, (c0, final) in enumerate([(0.95, "supported"), (0.96, "supported"),
                                     (0.93, "supported"), (0.97, "supported"),
                                     (0.94, "refuted"), (0.92, "refuted")]):
        synth_belief += [be(f"hi{i}", c0, "supported"), be(f"hi{i}", 0.5, final)]
    # Mid band 0.6–0.7: 4 settled edges, 3 held → slightly under-confident.
    for i, final in enumerate(["supported", "supported", "supported", "refuted"]):
        synth_belief += [be(f"mid{i}", 0.65, "supported"), be(f"mid{i}", 0.7, final)]

    synth_contra = [
        {"event": "open", "id": "c1", "key": "hiA", "established": {"confidence": 0.95}},
        {"event": "resolve", "id": "c1", "resolution": "overturned"},
        {"event": "open", "id": "c2", "key": "hiB", "established": {"confidence": 0.90}},
        {"event": "resolve", "id": "c2", "resolution": "overturned"},
        {"event": "open", "id": "c3", "key": "midA", "established": {"confidence": 0.70}},
        {"event": "resolve", "id": "c3", "resolution": "upheld"},
    ]
    beliefs._events = lambda key=None: synth_belief
    beliefs._contra_events = lambda: synth_contra

    print(render("all"))
    print("\n--- stability lens only ---")
    print(render("stability"))
