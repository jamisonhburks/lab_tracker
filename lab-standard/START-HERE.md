# Lab Standard — START HERE

This directory is the **playbook**: a set of agent-followable rules that let any session
(a) scaffold a new project into a shape the lab can use, (b) conform an existing project
to that shape, and (c) do research inside it so the work promotes cleanly from private
thinking to shared lab knowledge.

The rules are written for *you*, an agent. They are imperative checklists, not prose to
skim. When a human gives you an intent, open the matching file and execute its steps.

---

## The substrate model (why any of this exists)

Starting a fresh Claude session and asking it to "generate hypotheses" gives you a
*thinker* with no memory, no grounding, and no way to hand off. This repo is the missing
half: a **substrate** the thinker stands on. It contributes what a bare session cannot —

- **grounding**: is a claimed link supported by a trustworthy knowledge graph, or a guess?
- **calibration**: is that link stronger than random degree-matched pairs, or a hub artifact?
- **novelty**: already published, or a genuinely new juxtaposition?
- **recall**: has this been tried before, and what happened (including negatives)?
- **audit**: how was a past result actually produced, tool call by tool call?
- **accrual**: a place for a finding to become *shared* knowledge, gated by a critic.

You reach all of that through the **MCP server** (`mcp_server.py`) — see
[`using-the-substrate.md`](using-the-substrate.md). If it is not connected, you can still
run the tools locally, but the point of the standard is that projects speak the same
protocol so their outputs interoperate.

## The three tiers (the spine of everything)

| Tier | What it is | Where it lives | Gate |
|---|---|---|---|
| **local semantic** | your in-progress thinking, notes, draft distillations | the project dir (`notes/`) + your personal memory | none — private |
| **shared WIP** ("group semantics") | the research *process*: hypotheses, experiments, validity gates, provenance, campaigns | the standard project dirs, tracked centrally | none — provisional, visibly in-progress |
| **shared consensus** | curated *findings* the lab believes, with confidence | the curated KG + `lab_contributions.jsonl` | **critic-gated `contribute()`** |

The distinction is **conclusion vs process**, not personal vs shared. Process is worth
sharing *before* there is a conclusion — so the group can see what is in flight and not
duplicate it. Only concluded interpretations need the gate. Full mechanics:
[`promotion.md`](promotion.md).

---

## Pick your flow

| A human said… | Open |
|---|---|
| "I'm making a new project about ___" | [`new-project.md`](new-project.md) |
| "Make my existing project conform to the standard" | [`conform-project.md`](conform-project.md) |
| "Let's form a hypothesis" | [`hypothesis-workflow.md`](hypothesis-workflow.md) |
| "Let's implement / run / evaluate it" | [`experiment-workflow.md`](experiment-workflow.md) |
| "What should we share, and how?" | [`promotion.md`](promotion.md) |
| "Where does this file go? / what do I name it?" | [`project-structure.md`](project-structure.md) |
| "How do I query the shared knowledge?" | [`using-the-substrate.md`](using-the-substrate.md) |

Templates you will copy from live in [`templates/`](templates/).

## Non-negotiables (inherited from the lab CLAUDE.md — never override)

- `data/raw/` is **read-only**. Never write to it. Never write code that re-identifies
  individuals or emits row-level patient data to unprotected locations.
- Significance is `p < 0.05` **with both** Bonferroni and Benjamini-Hochberg FDR
  correction when >1 hypothesis is tested. Always report **effect size**. **≥3 runs**
  before concluding from a stochastic experiment. Never call a result significant
  without naming the correction.
- Every run logs Python + key package versions, seed, and start/end timestamps.
- **Local-first**: keep de-identified health data on-device; the substrate emits
  associations / grounding / aggregates, never row-level data.
