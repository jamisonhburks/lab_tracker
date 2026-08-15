# ADR-0057: Modular lab/researcher prior-work profile — coverage relative to a real frontier

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
The lab-brain review's coverage/knowledge-gap idea was originally scoped at the biomedical
entity grain (disease × gene, thin entities). That is the wrong altitude for this lab (AI for
Health, Helmholtz Munich): its questions are **method/representation-level and deliberately
multi-disease** — "simulate a latent OCT trajectory from longitudinal imaging + treatment
events", "separate physiological EHR representations from workflow sampling", "multimodal
foundation model for downstream disease". None is an entity link; all are
**(modality × task × learning-paradigm)** cells.

"What don't we know" is also only meaningful *relative to a specific lab*. A generic KG can't say
whether a cell is a gap — only the lab's own prior work can. And different labs have different
frontiers, so the baseline must be modular. This ADR establishes that baseline; the coverage map
that consumes it is the next step.

## Options considered
1. **Bake a fixed taxonomy + assume the whole KG is the baseline.** Not modular, and it can't
   distinguish "the lab hasn't done this" from "no one has" — the distinction that makes a gap
   actionable.
2. **A first-class Project/ontology model.** Heavier than needed for a baseline, and it duplicates
   what publications already encode.
3. **A modular per-lab / per-researcher prior-work profile** (chosen): the lab declares its SCOPE
   (axes it works along) and records its PUBLICATIONS, tagged onto those axes. Coverage is then
   `scope − covered`, per lab.

## Decision
Add `lab_profile.py` + `profiles/<id>.yaml`. The atoms are the method-capability grain:
**modality** (incl. combinations), **task/question-type**, **learning-paradigm** — with a seeded,
open (extensible) AI-for-health vocabulary and a heuristic keyword auto-tagger.

- **Scope** (`scope()`) — the lab's declared axes; the RELEVANT region the coverage map spans.
- **Covered** (`covered()`) — the modality×task pairs and full cells the lab's PUBLICATIONS touch;
  the set the coverage map subtracts. `record_publication()` tags a paper onto the axes
  (explicit, or auto-tagged from the title), attributed + append-only.
- **Context** (`profile_context()`) — the profile + tagged publications rendered as IN-CONTEXT
  grounding for the thinker, so Claude can phrase gaps in the lab's language and propose the next
  method. The "in-context learning" is thinker-side; the substrate only stores and serves.

Modular by construction: each lab ships its own `profiles/<id>.yaml` (`SUBSTRATE_LAB` selects
one); per-researcher views filter publications by author. A seed `profiles/helmholtz-ai-health.yaml`
ships as the concrete example. Shared-tier MCP tools: `lab_profile`, `record_publication`,
`covered_capabilities`.

## Rationale + evidence
- **Right grain for this lab.** Framing gaps as (modality × task × paradigm), disease-agnostic,
  matches how the lab actually reasons; disease is a filter, not the axis (see the researcher-
  domain memory). All three motivating questions map cleanly to cells.
- **Coverage needs a baseline, and it must be modular.** Publications are the honest, already-
  existing record of "what we've done"; a per-lab profile makes the gap relative and portable.
- **Substrate stays LLM-free (ADR-0030/0040).** Structured scope/covered sets are computed without
  a model; the profile context feeds the thinker, which does the reasoning. The auto-tagger is
  keyword-based (a convenience), and explicit tags always override it.
- **In bounds for "assistant, not twin" (ADR-0052).** A publication/work corpus personalizes to
  the WORK — the lab's research frontier — not to the person's identity or voice.
- **Verified.** The hermetic demo seeds a profile, records two publications (auto-tagged onto the
  axes), and produces the scope, the covered pairs/cells, and the thinker context — with
  `OCT-longitudinal` preserved as a distinct axis (a normalization fix so a specific value isn't
  swallowed by a shorter one).

## Consequences
- The substrate now holds each lab's frontier at the method-capability grain, ready for the
  coverage map to diff against.
- Next (PR B, `coverage.py`): `scope − covered` over the ML methods KG + literature, foregrounding
  two gap classes — **adoptable** (a method exists but the lab hasn't used it) vs **open frontier**
  (no established method → a candidate contribution).
- The auto-tagger is heuristic; richer tagging (from full abstracts) is a thinker step, and
  explicit tags override. The seeded vocabulary is extensible, not closed.
