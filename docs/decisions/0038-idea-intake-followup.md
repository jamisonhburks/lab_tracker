# ADR-0038: Idea intake — `assess_idea` (evaluate → propose → opt-in refine)

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The lab's routine move is to start a follow-up from a rough idea or a prior result: take a
general hypothesis, run the same evaluation the substrate offers (is it grounded? already
published? merely potential? off-graph?), and — based on what that finds — refine it and lay
out the downstream workflow. Every *piece* of this already existed as a separate tool
(`check_connection`/`calibrate_link`/`novelty` for evaluation, `refine_hypothesis` for the
curate+critic loop, `propose_experiment` for the workflow, `campaign.next_step` for
prior-work follow-ups), but nothing (a) accepted a **free-text idea** — the tools require a
resolved `(entity_a, entity_c)` pair — or (b) ran the whole chain as one step.

## Decision
Add **`idea.py`** with two layers, plus tool wiring:

- **`assess(entity_a, entity_c, refine=False)`** — the LLM-free core. EVALUATE (grounding +
  permutation calibration + PubMed novelty → a verdict with guidance) → PROPOSE the downstream
  workflow → then RECOMMEND the refinement pass. Fast first; the expensive
  novelty-triaged curate+critic loop runs only when `refine=True` (per the "generation is
  cheap, verification is the paid half" finding).
- **`assess_idea(idea, refine=False)`** — intake on top: accepts a **free-text idea** OR a
  **prior `H{NNN}`** (seeded from its title + question + evaluated finding), uses the local
  (frozen) model to EXTRACT the testable entity pair(s), then runs `assess` on each.

Wiring reflects the substrate/thinker split:
- **Agent tool `assess_idea`** — includes the extraction (a thinking step), so it lives on the
  agent side.
- **MCP shared tool `assess_link(entity_a, entity_c)`** — exposes only the **LLM-free** `assess`
  core. The client's model extracts the entities (thinking); the substrate evaluates + proposes
  (no generation inside the server — ADR-0030 preserved). Refinement, which generates, stays
  agent-side.

## Rationale & evidence
- **Orchestration, not new modeling.** The only genuinely new capability is entity extraction
  from free text — extraction, not learning, so it's consistent with the frozen-model / no-RL
  stance (ADR: no RLHF/RL). Everything else is existing substrate tools composed in order.
- **The verdict is explicit.** `_verdict(grounding, novelty)` turns the raw signals into the
  "valid / published / potential / off-graph" call the lab actually makes: grounded+published →
  "largely known (replication)"; grounded+novel → "promising & testable"; weakly → "potential";
  off-graph → "ungrounded — establish a link first".
- **Fast-then-opt-in.** Evaluate + propose run with no PubMed-fetch/critic cost; the expensive
  pass is recommended with the exact opt-in call, never run silently.
- **Verified.** LLM-free core on the demo KG: `atrial fibrillation ↔ ischemic stroke` →
  "largely known" (grounded, 8 483 co-mentions, calibration 100th pct), full workflow, refine
  recommended-not-run. Verdict matrix correct across all five cases. Prior-work seed: `H001`
  loads title+question+finding. Full path (local model up): free-text idea → extracted pair →
  evaluated; `H001` → 7 pairs, top 2 assessed. Graceful message if the model is unavailable.
  Agent DISPATCH advertises `assess_idea`; MCP shared exposes `assess_link` (13 shared tools).

## Consequences
- One entry point for the follow-up move: idea/prior-work → evaluated, workflow-ready hypothesis.
- The substrate/thinker boundary is kept crisp: extraction + refinement (generation) are
  agent-side; grounding/calibration/novelty/propose (no generation) are substrate-side and
  MCP-exposed.
- Natural follow-up: hang the result as a new `campaign` node off the prior `H{NNN}` for lineage
  (today it reports the follow-up provenance but doesn't auto-create the node).
