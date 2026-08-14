# ADR-0033: Lab-standard onboarding playbook (self-describing repo → conforming projects)

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The substrate is only useful if *projects* speak its protocol. A researcher who clones
this repo and opens a fresh session to "start a new project" or "organize an old one" has
no way, today, to produce a project whose artifacts are grounded, tracked, and promotable
without re-deriving all the conventions by hand each time. The three-tier model
(ADR-0030/0031) and the `contribute()` write-path (ADR-0032) define *how knowledge moves*,
but nothing makes a **new local project** conform so its work can actually enter that flow.

The gap is onboarding: premade, **agent-followable** documents that a session reads and
*executes* to scaffold or conform a project — and that then persist inside the project to
keep future sessions on-standard. Without this, "local semantic → shared WIP → shared
consensus" has no on-ramp; every project reinvents structure and most never become
promotable.

## Decision
Add a **self-describing onboarding layer**, all documentation (no code), in two places:

- **Root `AGENTS.md`** — the discoverable entry point. Routes a fresh session by intent
  ("new project" / "conform existing" / "how does this work") to the playbook, and states
  the three-tier idea up front.
- **`lab-standard/`** — the playbook of imperative, checklist-style rules:
  - `START-HERE.md` (router + substrate model + tier table + non-negotiables),
  - `new-project.md` and `conform-project.md` (the two intent flows, each with a
    definition-of-done),
  - `hypothesis-workflow.md`, `experiment-workflow.md` (the research recipes, wired to the
    real MCP tools, the 4-agent separation of concerns, validity gates, and the stats/
    reproducibility standards),
  - `promotion.md` (the spine: local → WIP → consensus, triggers + the critic-gated,
    conservatively-routed `contribute()` step),
  - `project-structure.md` (layout, `H{NNN}` naming, status vocabulary, the id+status+
    provenance tracking rule that makes an artifact promotable),
  - `using-the-substrate.md` (the MCP tool/resource reference and the honesty rules),
  - `templates/` — `hypothesis.yaml` (canonical fields + explicit `provenance:` /
    `validity_gates:` extension blocks), `project-README.md`, and crucially
    **`project-CLAUDE.md`**, dropped into the new project so *every future session in that
    directory* follows the standard automatically.

## Rationale & evidence
- **Self-describing beats out-of-band docs.** `AGENTS.md` at the root is what a fresh
  Claude session actually reads first; routing from there means onboarding needs no human
  to paste instructions. The playbook is written as checklists with definitions-of-done so
  a session *executes* rather than paraphrases.
- **The load-bearing move is `project-CLAUDE.md`.** Scaffolding a project once isn't
  enough; the standard has to persist. Dropping a CLAUDE.md into the new project makes the
  rules travel with the work, so session N+1 conforms without being told — this is what
  turns a one-time scaffold into a durable pipeline from local work to shared knowledge.
- **Promotion metadata is made first-class, not incidental.** The hypothesis template adds
  explicit `provenance:` and `validity_gates:` blocks (previously buried in prose / only in
  `pre_registration:`), because provenance is the toll to consensus — recording it *as you
  go* is what makes the eventual `contribute()` free instead of a scramble.
- **No new code, no new dependencies.** This layer is pure guidance over the mechanisms
  that already exist (MCP tools, the 4 specialist agents, validity gates, `contribute()`).
  It cannot regress runtime behavior; it only makes the existing capabilities reachable
  from a cold start.

## Consequences
- A cloned repo is now onboardable: "I'm making a new project about ___" and "conform my
  project X" have concrete, executable flows that end in a standard-shaped, promotable project.
- Projects created this way interoperate: their artifacts are visible to `list_active_work`
  and eligible for `contribute()` by construction.
- The docs reference `contribute_finding` / `contribute()` (ADR-0032, PR #39). Until that
  merges, the promotion tooling it names lands alongside; the playbook is written to the
  intended, merged state.
- Follow-ups: a tiny `scaffold` helper could automate template copying + placeholder fill;
  and once a remote/HTTP MCP deployment exists, `using-the-substrate.md` gains the hosted
  connection details.
