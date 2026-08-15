# ADR-0058: Coverage map — scope − covered, adoptable vs open frontier

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
With the lab profile (ADR-0057) supplying SCOPE (the axes a lab works along) and COVERED (the
(modality, task) cells its publications touch), the remaining piece of the lab-brain review is the
map itself: point at what the lab *doesn't* know, at the method-capability grain, and separate
"a method already exists, go use it" from "no method exists — this is a contribution." The second
class is the one an AI-for-Health methods lab actually cares about.

The hazard is dishonesty in two directions: over-claiming a cell as ADOPTABLE (implying a method
exists when the match was spurious), or over-claiming a cell as OPEN FRONTIER (implying no method
exists when really the KG is just incomplete or the check was offline).

## Decision
Add `coverage.py`: `scope − covered` over the ML methods KG (+ optional literature), each gap cell
classified.

- **Gap cells** = `scope.modalities × scope.tasks` minus `covered.pairs`.
- **Classification** per cell via the ML KG (`ml_schema.load_fused_seed`, `suited_to`/`used_for`):
  - **ADOPTABLE** — a method connects the cell (or, with `deep=True`, a PubMed co-mention exists).
  - **OPEN FRONTIER** — no method connects it. A candidate contribution.
- **DEEPEN** — covered cells missing an in-scope PARADIGM (e.g. OCT×classification but never
  self-supervised) — extend what you already have.
- **META** — how many of the lab's own modalities/tasks the ML KG even resolves; when low, the
  honest reading is "frontier partly means *not in our KG*", with a pointer to distill literature
  in (deep_fetch → record_distillation) and re-run with `deep=True`.

Two honesty safeguards proved necessary and are built in:
1. **Concept-form resolution, not token overlap.** Axis values resolve to KG nodes via the
   profile's concept vocabulary (ADR-0057), checking *all* candidate nodes — after a token-overlap
   version wrongly matched `OCT-longitudinal` to `longitudinal event-based EHR` on the shared
   qualifier word "longitudinal".
2. **Conservative clinical→ML task crosswalk.** `disease-classification` aliases to the KG's
   `…classification`, but `trajectory-simulation` and `disentanglement` are deliberately NOT
   aliased — they are this lab's contribution space, so they stay OPEN FRONTIER rather than being
   quietly mapped onto "forecasting"/"representation" and mislabelled adoptable.

Offline-first: the KG pass is a pure traversal; the literature pass (`deep=True`) is best-effort
and degrades to "literature unchecked/unreachable" rather than silently promoting a cell to
frontier. Shared-tier MCP tool `coverage_map(member, deep)`.

## Rationale + evidence
- **Right grain, disease-agnostic.** Cells are (modality × task), with paradigm as the DEEPEN axis
  — the method-capability altitude this lab reasons in; disease is a filter (ADR-0057, researcher-
  domain memory).
- **Honesty over completeness.** Both safeguards err toward *under*-claiming: a spurious adoptable
  is worse than an extra frontier, and an unchecked literature cell says so. The META note keeps
  the incompleteness of the KG explicit rather than dressing it up as discovery.
- **Substrate-side, LLM-free (ADR-0030/0040).** Classification is graph traversal + optional
  co-mention counts; the thinker consumes `lab_profile()` context to phrase and prioritise the
  gaps. The map surfaces structure; it does not decide the research agenda.
- **Verified.** On a demo profile the map correctly lists `ECG×classification→Transformer`,
  `genomic×survival→XGBoost`, `OCT-longitudinal×classification→ResNet` as adoptable, keeps
  `*×trajectory-simulation` and `*×disentanglement` as open frontier, flags covered classification
  cells as missing self-supervised/foundation/neural-ODE paradigms, and reports KG resolution
  (5/6 modalities, 2/4 tasks). On the shipped Helmholtz profile (no publications yet) all 54 cells
  are honestly gaps.

## Consequences
- The lab-brain review's coverage/knowledge-gap piece is complete: a per-lab map that generates a
  research agenda (frontier) and quick wins (adoptable), and points at its own blind spots (META).
- It pairs with the dead-end store (ADR-0056): dead ends mark *closed* avenues, the coverage map
  marks *unopened* ones — together, where not to go and where to go next.
- Accuracy is bounded by the ML KG's breadth and the crosswalk; both are conservative by design and
  improve as the KG is enriched by distillation. `deep=True` sharpens frontier-vs-unindexed at the
  cost of network calls.
