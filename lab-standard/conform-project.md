# Conform an Existing Project — reorganization flow

Trigger: a human says **"I've been working on X, make it conform to the lab standard."**
The goal is to reshape an existing, probably-messy project into the standard layout
**without losing or rewriting its science** — only its structure, naming, and metadata.

Rule: **move and annotate, do not re-run or re-interpret.** You are a librarian here, not
an experimenter. If something is ambiguous, ask rather than guess what a past result meant.

## 0. Survey first, touch nothing

- Read [`project-structure.md`](project-structure.md) and [`promotion.md`](promotion.md).
- Inventory what exists: scripts, notebooks, data files, results, any written findings.
  Produce `notes/00_conformance_audit.md` listing every artifact and your proposed
  destination + new name. **Show this to the human before moving anything.**
- Identify `data/raw/` candidates and mark them read-only in your plan.

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
- Move each experiment's code/results into `experiments/H{NNN}/` with the standard
  subpaths. Wrap loose scripts so there is a `run.py` with a `__main__` block; keep the
  original logic intact.
- Rename result write-ups to `reports/H{NNN}_evaluation.md`.

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

This creates only **missing** standard dirs and drops `CLAUDE.md` (so future sessions
conform), `README.md`, and `notes/00_conformance_audit.md` **only if absent** — it never
moves or overwrites your existing files. Then fill the README status + `H{NNN}` table by hand.
(By hand: copy from [`templates/`](templates/) and fill placeholders — the helper just does
that deterministically.)

## 5. Reconcile with the shared substrate, then stop

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
- [ ] Consensus candidates flagged for a later `contribute()` pass — not promoted here.
