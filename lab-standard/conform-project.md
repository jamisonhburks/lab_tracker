# Conform an Existing Project — reorganization flow

Trigger: a human says **"I've been working on X, make it conform to the lab standard."**
The goal is to reshape an existing, probably-messy project into the standard layout
**without losing or rewriting its science** — only its structure, naming, and metadata.

Rule: **move and annotate, do not re-run or re-interpret.** You are a librarian here, not
an experimenter. If something is ambiguous, ask rather than guess what a past result meant.

> **Non-destructive guarantee (enforced in code, not just here).** Conforming a project must
> NEVER edit a file's contents and NEVER delete the owner's work — it may only RELOCATE artifacts
> and ADD standard files. **Do every move through `conform.py`, never with raw `mv`/`rm`/edits.**
> `conform.py` refuses to overwrite, prefers `git mv` (or else COPIES, leaving the original in
> place), and records a reversible manifest (`conform.py undo`). If you catch yourself about to
> rewrite or delete an original, STOP and ask the human.

## 0. Survey first, touch nothing — then produce the audit with the tool

```sh
python <substrate>/conform.py plan <path-to-existing-project>
```

This writes `notes/00_conformance_audit.md` + `conform_plan.json`: every artifact with a proposed
`move | leave | skip | review` action and destination. **It touches nothing.** Read
[`project-structure.md`](project-structure.md) and [`promotion.md`](promotion.md), then correct the
plan by hand — fix destinations, downgrade anything uncertain to `leave`/`review`, and confirm
`data/raw/` candidates are marked read-only. **Show the audit to the human before applying.**

Only after review:

```sh
python <substrate>/conform.py apply <path>    # relocates ONLY reviewed `move` rows; reversible
```

## 1. Classify each artifact into a tier

For every artifact, decide which tier it belongs to — this determines where it goes:

- **local semantic** (rough notes, scratch, half-ideas) → `notes/`. No metadata required.
- **shared WIP** (a real hypothesis, an experiment, a validity check, a provenance trail)
  → the standard dirs, given an `H{NNN}` id and a status.
- **shared consensus candidate** (a *concluded, defensible finding*) → keep as a report,
  and flag it for `contribute()` later (Step 5). Do not contribute during conformance.

When in doubt, classify **down** (WIP, not consensus). Promotion is a deliberate act.

## 2. Assign IDs and rename

- Turn each distinct research question into `hypotheses/H{NNN}_{slug}.yaml`. If the
  original had no written hypothesis, reconstruct one from the code/results with the human
  and mark `status:` honestly (`complete` if it was actually run and evaluated; `draft`
  if only sketched). Use [`templates/hypothesis.yaml`](templates/hypothesis.yaml).
- `conform.py apply` stages research artifacts into `experiments/_unsorted/`, `data/`, `reports/`,
  etc. — it deliberately does NOT invent `H{NNN}` structure. From those staging buckets, relocate
  each experiment's code/results into `experiments/H{NNN}/` **with `conform.py` moves** (or `git mv`);
  never hand-delete an original. Wrapping a loose script so it has a `run.py` `__main__` is a NEW
  file that imports the original logic — do not rewrite the original in place.
- Rename result write-ups to `reports/H{NNN}_evaluation.md` (a move, not an edit).

## 3. Backfill the metadata that makes it promotable

Existing projects almost always lack these three; add them (see the tracking rules in
[`project-structure.md`](project-structure.md)):

1. **IDs** — every artifact gets its `H{NNN}` / campaign slug. No orphans.
2. **Status** — set each hypothesis `status:` from the vocabulary; set experiment stage.
3. **Provenance** — write `experiments/H{NNN}/provenance.md` reconstructing how the
   result was formed and tested, *from what is on disk*. Where you are inferring rather
   than reading, say so explicitly ("reconstructed, source unclear"). Log versions/seed
   into `logs/run.log` if recoverable; note `unknown` where not.

Reproducibility gaps are common in legacy work — **record them as gaps, don't fabricate**
a seed or a version you can't verify.

## 4. Add the standard-carrying files (one command — non-destructive)

```sh
python scaffold.py conform <path-to-existing-project> --title "<Project Title>"
```

This creates only **missing** standard dirs and adds `CLAUDE.md` (so future sessions conform) and
`README.md`. If either name is already taken it writes a `.lab-standard` sidecar for you to merge
rather than overwrite the original — **even with `--force`**. It never moves or edits existing
files. (The audit itself comes from `conform.py plan` in Step 0.) Then fill the README status +
`H{NNN}` table by hand.

## 5. Register the project, then reconcile, then stop

- **`register_project(<project path>)`** — THIS is what makes the conformed work visible. A project's
  hypotheses/experiments live in its own directory, so until you register it, `list_active_work` (and
  every colleague) can't see it. Do this right after the moves are applied. Verify with
  `list_active_work` — your `H{NNN}`s should now appear tagged with the project name.
- Run `list_active_work` and `query_curated_findings` — is any of this already tracked or
  already consensus in the lab? Note overlaps in the audit file; don't re-contribute what
  the lab already has.
- For each artifact you classified as a **consensus candidate**, list it at the bottom of
  the audit file as "ready for contribute()", with the finding stated as
  subject–predicate–object plus its evidence. Leave the actual promotion to a deliberate
  pass following [`promotion.md`](promotion.md) — conformance ends here.

## Definition of done

- [ ] `notes/00_conformance_audit.md` maps every original artifact → destination, tier, id.
- [ ] Layout and names match `project-structure.md`; `data/raw/` untouched.
- [ ] Every hypothesis/experiment has id + status + provenance (gaps marked, not faked).
- [ ] `CLAUDE.md` + `README.md` in place; no science re-run or re-interpreted.
- [ ] **`register_project` called** — the project's `H{NNN}`s appear in `list_active_work`.
- [ ] Consensus candidates flagged for a later `contribute()` pass — not promoted here.
