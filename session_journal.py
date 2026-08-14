"""session_journal — keep the PERSONAL tier alive DURING a live session.

Even mid-session (not just at the end), the agent should periodically write to its personal
notes, record the PROVENANCE of what changed — append-only, timestamped, content-hashed, the
same discipline as the rest of the substrate — and, once enough has accrued, RECOMMEND which
pieces are ready to climb from PERSONAL (local semantic) to SHARED WIP (group semantics).

Files, per session, under memory/sessions/<id>/:
  notes.md        the session's personal notes (written via note(), or edited by hand)
  journal.jsonl   append-only checkpoints: what CHANGED, when, how many lines, content hash
  .snapshot       last checkpointed notes text (so a checkpoint can DIFF against it)

Cadence: `start(interval=3600)` runs a daemon thread that checkpoints every hour even while
the session is active; `maybe_checkpoint()` is the time-gated pull version for a loop; an MCP
client drives it with its own scheduler. A checkpoint with no change is a no-op (no noise).

    j = SessionJournal()
    j.note("hypothesis: PTPN1 loss -> JAK-STAT, shared PMBL/Hodgkin")
    j.start(interval=3600)          # hourly, in the background
    ...
    print(j.promotion_review())     # "these components look ready for shared WIP"
"""
import difflib
import hashlib
import json
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent / "memory" / "sessions"

# lightweight signals for classifying a note line into a promotable component type
_HYP = ("hypothes", "->", "→", "associat", "cause", "drive", "regulat", " vs ",
        "shared", "link between", "predict", "mechanism")
_EXP = ("experiment", "method", "assay", "cohort", "dataset", "gwas", "rna-seq",
        "measure", "protocol", "test plan", "study", "crispr", "sequenc")
_FIND = ("result", "found", "significant", "p=", "p <", "p<", "effect size",
         "auroc", "fdr", "confirmed", "cohen", "odds ratio")


def _classify(line: str):
    low = line.lower()
    if any(k in low for k in _FIND):
        return "finding"
    if any(k in low for k in _EXP):
        return "experiment"
    if any(k in low for k in _HYP):
        return "hypothesis"
    return None


class SessionJournal:
    def __init__(self, session_id: str = None, root=None):
        self.session_id = session_id or f"sess-{datetime.now():%Y%m%d-%H%M%S}"
        base = Path(root) if root else ROOT
        self.dir = base / self.session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.notes = self.dir / "notes.md"
        self.log = self.dir / "journal.jsonl"
        self.snap = self.dir / ".snapshot"
        self._last = time.time()                 # gates maybe_checkpoint()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    # --- writing + checkpointing -------------------------------------------- #
    def note(self, text: str, kind: str = "note") -> None:
        """Append a note to this session's personal notes (with a timestamped header)."""
        stamp = datetime.now().isoformat(timespec="seconds")
        with self._lock, self.notes.open("a", encoding="utf-8") as f:
            f.write(f"\n### {stamp} · {kind}\n{str(text).strip()}\n")

    def _read(self) -> str:
        return self.notes.read_text(encoding="utf-8") if self.notes.exists() else ""

    def checkpoint(self, force: bool = False):
        """Evaluate what CHANGED in the notes since the last checkpoint; if anything did,
        append an append-only journal entry (delta + provenance) and update the snapshot.
        Returns a one-line summary, or None if nothing changed."""
        with self._lock:
            cur = self._read()
            prev = self.snap.read_text(encoding="utf-8") if self.snap.exists() else ""
            added = [ln[2:] for ln in difflib.ndiff(prev.splitlines(), cur.splitlines())
                     if ln.startswith("+ ") and ln[2:].strip() and not ln[2:].startswith("###")]
            self._last = time.time()
            if not added and not force:
                return None
            entry = {"ts": datetime.now().isoformat(timespec="seconds"),
                     "session": self.session_id, "kind": "checkpoint",
                     "n_added_lines": len(added), "added": added[:40],
                     "chars": len(cur), "hash": hashlib.sha1(cur.encode()).hexdigest()[:12],
                     "source": "session-checkpoint"}
            with self.log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
            self.snap.write_text(cur, encoding="utf-8")
            return f"checkpoint {entry['hash']}: +{len(added)} line(s), {len(cur)} chars total"

    def maybe_checkpoint(self, interval: float = 3600):
        """Checkpoint only if `interval` seconds have passed since the last one (loop-driven)."""
        return self.checkpoint() if time.time() - self._last >= interval else None

    # --- background cadence ------------------------------------------------- #
    def start(self, interval: float = 3600) -> None:
        """Checkpoint every `interval` seconds in a daemon thread — even while the session is
        active. No-op if already running."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def _loop():
            while not self._stop.wait(interval):
                try:
                    self.checkpoint()
                except Exception:
                    pass

        self._thread = threading.Thread(target=_loop, name=f"journal-{self.session_id}",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    # --- promotion recommendation ------------------------------------------- #
    def _counts(self) -> dict:
        counts = {"hypothesis": 0, "experiment": 0, "finding": 0}
        for line in self._read().splitlines():
            s = line.strip()
            if s and not s.startswith("#") and (c := _classify(s)):
                counts[c] += 1
        return counts

    def session_mode(self) -> str:
        """Classify the session shape: 'hypothesis_driven' (a hypothesis was stated),
        'adhoc_series' (>=2 experiments/findings but NO hypothesis — a series of tests with no
        setup), or 'sparse' (not much yet)."""
        c = self._counts()
        if c["hypothesis"] >= 1:
            return "hypothesis_driven"
        if c["experiment"] + c["finding"] >= 2:
            return "adhoc_series"
        return "sparse"

    def workflow_suggestion(self) -> str:
        """If the session is an ad-hoc series with no hypothesis/setup, ASK whether to attach
        the Research Workflow retroactively — or log the work as miscellaneous."""
        if self.session_mode() != "adhoc_series":
            return ""
        return ("\n⚠ This session looks like a SERIES OF ANALYSES with no hypothesis/setup. Attach"
                " the Research Workflow?\n"
                "   (a) FORMALIZE RETROACTIVELY — draft a hypothesis + methods from what you ran"
                " → session_journal formalize_retroactively(); or\n"
                "   (b) LOG AS MISCELLANEOUS — if this isn't tied to a hypothesis, send findings to"
                " the lab's exploratory pool (rigor-checked + matched to the lab KG):"
                " misc_research.log_misc(claim, subject, object, method, ...).")

    def formalize_retroactively(self) -> str:
        """'Attach the Research Workflow' after the fact: assemble a hypothesis + method STUB
        from a series of analyses that had no setup (recurring entities → the link; experiment
        notes → the method; findings → observed). A DRAFT the thinker reviews/completes."""
        import collections
        import re
        text = self._read()
        exp, find = [], []
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            c = _classify(s)
            if c == "experiment":
                exp.append(s)
            elif c == "finding":
                find.append(s)
        top = [t for t, _ in collections.Counter(
            re.findall(r"\b[A-Z][A-Za-z0-9\-]{2,}\b", text)).most_common(4)]
        import misc_research                              # shared stub builder — one format
        return misc_research.hypothesis_stub(
            top, exp, find,
            header="# RETROACTIVELY DRAFTED from an ad-hoc session — REVIEW + COMPLETE before use.")

    def promotion_review(self, min_chars: int = 300) -> str:
        """Once enough content has accrued, recommend which components are ready to propose
        from PERSONAL notes up to SHARED WIP. Heuristic + honest: it FLAGS candidates for a
        human/thinker to promote, it does not promote anything itself. If the session is an
        ad-hoc series with no hypothesis, it also asks whether to attach the Research Workflow."""
        cur = self._read()
        cands = {"hypothesis": [], "experiment": [], "finding": []}
        for line in cur.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            c = _classify(s)
            if c:
                cands[c].append(s[:120])
        n = sum(len(v) for v in cands.values())
        if len(cur) < min_chars or n == 0:
            return (f"[promotion] not enough yet — {len(cur)} chars, {n} candidate "
                    "component(s). Keep working; components get flagged as they accrue."
                    + self.workflow_suggestion())
        label = {"hypothesis": "Hypotheses  → formalize as hypotheses/H00N_*.yaml",
                 "experiment": "Experiment ideas  → experiments/ (pre-register first)",
                 "finding":    "Findings  → contribute() AFTER they're tested"}
        out = [f"[promotion] {len(cur)} chars accrued; {n} candidate component(s) ready to "
               "consider for SHARED WIP:"]
        for k in ("hypothesis", "experiment", "finding"):
            if cands[k]:
                out.append(f"  {label[k]}:")
                for s in list(dict.fromkeys(cands[k]))[:8]:
                    out.append(f"    - {s}")
        out.append("Promote the hypotheses/experiments to shared WIP (formalize as YAML / "
                   "experiment dirs); findings go via contribute() once tested. Nothing is "
                   "promoted automatically — this is a recommendation.")
        return "\n".join(out) + self.workflow_suggestion()

    def status(self) -> str:
        n_ck = sum(1 for _ in self.log.open()) if self.log.exists() else 0
        return (f"session {self.session_id}: {len(self._read())} chars of notes, "
                f"{n_ck} checkpoint(s), notes at {self.notes}")


if __name__ == "__main__":       # tiny self-demo (short interval)
    j = SessionJournal()
    j.note("hypothesis: PTPN1 loss activates JAK-STAT, shared between PMBL and Hodgkin")
    j.note("experiment: CRISPR-KO PTPN1 in Karpas-1106P + ruxolitinib rescue; measure pSTAT")
    print(j.checkpoint(force=True))
    print(j.promotion_review())
