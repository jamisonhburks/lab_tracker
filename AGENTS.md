# AGENTS.md — read this first

You are looking at a **lab research substrate**, not an ordinary codebase. It stores
what the lab knows (curated knowledge graph + findings), what is in flight (hypotheses,
experiments, campaigns), and the tools to query and contribute to both. A fresh session
is meant to *think with* this substrate, and to leave its work in a shape the next
session — and the shared lab — can pick up.

## If a human just told you to start or organize a project

Route by intent, then follow the playbook. **Do not start scaffolding from memory —
read the playbook file first; it is the source of truth.**

- **"I'm new here / help me get set up / onboard me"**
  → read [`lab-standard/onboarding.md`](lab-standard/onboarding.md) and run the intake — **lightly**
    (call `onboarding_status` first; one short question at a time; never overwhelm the member).

- **"I'm making a new project about ___"**
  → read [`lab-standard/new-project.md`](lab-standard/new-project.md) and execute it.

- **"I've been working on X, make it conform to the lab standard"**
  → read [`lab-standard/conform-project.md`](lab-standard/conform-project.md) and execute it.

- **"How does this repo work / what can it do for me?"**
  → read [`lab-standard/START-HERE.md`](lab-standard/START-HERE.md).

## If you are doing research inside an already-scaffolded project

The project directory has its own `CLAUDE.md` (copied from
[`lab-standard/templates/project-CLAUDE.md`](lab-standard/templates/project-CLAUDE.md))
pointing back here. Follow, in order of what you are doing:

- forming a hypothesis → [`lab-standard/hypothesis-workflow.md`](lab-standard/hypothesis-workflow.md)
- implementing / running / evaluating → [`lab-standard/experiment-workflow.md`](lab-standard/experiment-workflow.md)
- deciding what to share and how → [`lab-standard/promotion.md`](lab-standard/promotion.md)
- where files go and what they are named → [`lab-standard/project-structure.md`](lab-standard/project-structure.md)

## The one idea to hold onto

Knowledge moves through **three tiers**, and your job is to move your work *up* them
without skipping a gate:

```
  local semantic  ──►  shared WIP ("group semantics")  ──►  shared consensus
  (your private        (the research PROCESS: hypotheses,     (curated findings the
   in-progress          experiments, validity, provenance —    lab believes — only
   thinking)            tracked centrally, provisional,        reachable through the
                        un-gated)                              critic-gated contribute())
```

Everything in the playbook exists to make that promotion cheap and honest. See
[`lab-standard/promotion.md`](lab-standard/promotion.md).
