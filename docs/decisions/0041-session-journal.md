# ADR-0041: Session journal — keep the personal tier alive during a live session

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The personal tier (episodic + in-progress semantic) was written mostly at run *boundaries* —
a finished `run_agent` call distils findings into memory. But a real working session is long
and continuous: ideas, candidate hypotheses, methods, and partial results accrue *during* it,
and today they only get captured if the session happens to end cleanly. Nothing periodically
snapshots the in-progress thinking, records the provenance of what changed, or notices when
enough has accrued to be worth promoting toward shared WIP.

## Decision
Add **`session_journal.py`** — an append-only, provenance-carrying journal for the current
session, plus periodic checkpointing and a promotion recommender:

- **`note(text)`** appends to `memory/sessions/<id>/notes.md` (timestamped).
- **`checkpoint()`** DIFFS the notes against the last snapshot; if anything changed, it appends
  a journal entry to `journal.jsonl` — the added lines, a content hash, char count, timestamp,
  source — and updates the snapshot. No change → no-op (no noise). Same append-only, hashed,
  timestamped discipline as the rest of the substrate.
- **`start(interval=3600)`** runs a daemon thread that checkpoints **every hour even while the
  session is active**; **`maybe_checkpoint(interval)`** is the loop-driven (time-gated) pull.
- **`promotion_review()`** — once enough content has accrued, classifies note lines into
  candidate components (hypothesis / experiment / finding) and recommends how each climbs to
  SHARED WIP (hypotheses → YAML, experiments → dirs, findings → `contribute()` after testing).
  A recommendation only; it promotes nothing itself.

Wiring:
- **Agent REPL** (`python agent.py`): starts the journal (hourly background thread), notes each
  query + its grounded findings, `maybe_checkpoint()` per turn, and prints a final checkpoint +
  `promotion_review()` on exit.
- **MCP personal tier**: `journal_note`, `journal_checkpoint`, `promotion_review` — so a Claude
  *client* journals ITS own session (the client drives the hourly cadence with its scheduler).

## Rationale & evidence
- **Fits the tier model.** The journal is squarely PERSONAL (local, private — `memory/` is
  gitignored). Promotion is a deliberate, recommended step up to shared WIP, never automatic —
  the same conclusion-vs-process line the substrate already draws.
- **Provenance, not just a dump.** Every checkpoint is an append-only, hashed, timestamped
  delta — you can see *what* was added *when*, exactly like the contribution log and the
  experiment provenance cards.
- **Recommend, don't auto-promote.** `promotion_review` flags candidates for a human/thinker to
  formalize; it echoes the "substrate returns evidence, the thinker decides" principle.
- **Verified**: delta capture (+1, then +2 lines), no-op on no-change, time-gated
  `maybe_checkpoint`, and a **background daemon** recording 2 checkpoints on a 1 s cadence
  capturing both notes; `promotion_review` correctly sorts a hypothesis/experiment/finding into
  the right promotion routes. Personal MCP tier = **5 tools**; all modules import clean.

## Consequences
- A long session now leaves a durable, auditable trail and surfaces promotion candidates
  proactively, instead of losing in-progress thinking when the window closes.
- Cadence is configurable (`JOURNAL_INTERVAL` for the REPL; the client's scheduler over MCP).
- Natural follow-up: have `promotion_review` optionally hand its candidates straight into the
  scaffolder (`hypotheses/H00N.yaml` stubs) so promotion is one step, not two.
