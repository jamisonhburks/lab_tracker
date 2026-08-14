# Promotion Pathway — local semantic → shared WIP → shared consensus

This is the doc the whole standard exists to serve. Knowledge earns its way up three
tiers. Each promotion is a deliberate act with a clear trigger and, at the top, a gate.
The point is that moving work up is **cheap** (because the standard pre-loads the needed
metadata) and **honest** (because the gate is a critic, not a rubber stamp).

```
  ┌─ local semantic ──────────┐   formalize    ┌─ shared WIP ─────────────┐   contribute()   ┌─ shared consensus ───┐
  │ notes/, personal memory   │ ─────────────► │ hypotheses/ experiments/ │ ───────────────► │ curated KG +          │
  │ your in-progress thinking │  (write it as  │ campaigns/ reports/      │  (critic gate +  │ lab_contributions     │
  │ private · no gate         │   a hypothesis │ tracked · provisional ·  │   conservative   │ .jsonl · what the lab │
  │                           │   or result)   │ un-gated                 │   routing)       │ believes · gated      │
  └───────────────────────────┘                └──────────────────────────┘                  └───────────────────────┘
```

## Tier 1 → 2: local semantic → shared WIP ("group semantics")

**What tier 1 is.** Scratch: `notes/`, half-formed distillations, your personal episodic
and semantic memory. Private. No metadata required. This is where thinking happens.

**The trigger to promote.** The moment a note becomes either
(a) a **testable link** → write it as a hypothesis via
[`hypothesis-workflow.md`](hypothesis-workflow.md), or
(b) a **result** (you ran something) → capture it as an experiment via
[`experiment-workflow.md`](experiment-workflow.md).

**Why WIP is shared but un-gated.** WIP is *process*, self-evidently provisional. Sharing
it early is pure upside: the group sees what's in flight and doesn't duplicate it; a future
session can pick up your half-done campaign. There is no conclusion to be wrong about yet,
so there is nothing to gate. `list_active_work` is the window onto this tier.

**What "promotion" means here.** It is not a special command — it is *conforming the
artifact*: give it an `H{NNN}` id, a status, and provenance (see
[`project-structure.md`](project-structure.md)). Once it lives in the standard dirs with
that metadata, it is WIP, and the shared tier can see it. That's the whole step.

**A negative result belongs here too.** An honest null, an abandoned hypothesis with a
recorded reason, a validity-gate flag — all are valuable WIP. They stay WIP (they're
process); they do not become consensus, but they *do* save the next session a dead end.

## Tier 2 → 3: shared WIP → shared consensus (the gated step)

**What tier 3 is.** Curated *findings the lab believes*, each with power-weighted
confidence and KG grounding, in the curated KG and the append-only
`memory/lab_contributions.jsonl`. This is the only tier behind a gate. `query_curated_findings`
is the window onto it.

**The trigger.** A `complete` experiment (or a well-sourced literature association) with a
defensible, gate-clean finding — i.e. a genuine **conclusion**, not process.

**How you promote: `contribute_finding` / `contribute()`.** State the finding as
`subject, predicate, object` plus its evidence (`source`, `direction=supports|refutes`,
`source_kind=experiment|literature`, and for experiments the committed provenance; for
literature the `sample_size` / `effect_size` / `p_value` / `abstract`). The pipeline then:

1. **Normalizes** the entities against the KG vocabulary.
2. **Critic-gates** it. Literature: the critic reads the abstract for support and
   junk-checks it. Experiment: it verifies a committed provenance/report actually exists on
   disk for that `H{NNN}` — you cannot contribute a conclusion whose experiment isn't there.
3. **Routes conservatively** (this is the safety property — see below).
4. **Appends** the outcome to `lab_contributions.jsonl` with your attribution.

**Conservative routing — the default that keeps consensus trustworthy:**

| Situation | Route | Why |
|---|---|---|
| corroborates an existing `supported` finding, same direction, critic accepts | **auto-merged** | it only reinforces what's believed; low risk |
| **novel** (no existing edge) or **contradicts** an existing finding | **pending_review** | genuinely new or conflicting claims need a human — `review_queue` lists these |
| fails the critic / looks like junk / no provenance on disk | **rejected** | never enters consensus |

When unsure, the pipeline routes **down** (to review, or reject) — never up. Novelty and
contradiction are *not* auto-merged, because those are exactly the claims where being wrong
is expensive. Check `review_queue` to see what's awaiting a human.

**Attribution and lineage.** Every contribution records who made it (`SUBSTRATE_CONTRIBUTOR`
or `$USER`) and its evidence, so consensus is auditable back to a person and a source. This
is the git-like model: `contribute()` is a PR, the critic is CI, `pending_review` is
awaiting approval, `auto_merged` is a fast-forward, `rejected` is a closed PR.

## The rules that make all of this work

- **Never skip a tier.** A raw note does not go straight to consensus. It becomes a
  hypothesis/experiment (WIP) first, gets tested, *then* the conclusion is contributed.
- **Process is shareable early; conclusions are gated.** If you're unsure whether something
  is process or conclusion: if it has a *verdict*, it's a conclusion (gate it); otherwise
  it's process (share it as WIP).
- **Provenance is the toll.** You can't cross into consensus without it. That's why the
  hypothesis and experiment workflows make you record it as you go — so promotion is free
  later instead of a scramble.
- **Underpowered ≠ negative.** A null from a tiny cohort is `promising_but_poorly_tested`,
  and the confidence scoring treats it that way. Don't contribute it as a refutation.

## Definition of done (for a promotion pass)

- [ ] The artifact carries id + status + provenance before you touch `contribute_finding`.
- [ ] You called `contribute_finding` with entities, direction, source_kind, and evidence.
- [ ] You read the routing outcome and, if `pending_review`, noted it for a human.
- [ ] You did **not** force novel/contradictory findings into consensus by hand.
