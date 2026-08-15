# ADR-0052: Assistant, not twin — personalize to the work, not the person

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
Making the workflow enjoyable (ADR-0049 warm start, ADR-0050 serendipity, ADR-0051 research story)
opened a fourth candidate: **preference / persona memory** — the agent remembering *how a researcher
likes to work* (their voice, tone, style, private preferences) and adapting to it. It was declined,
deliberately. The word "personalization" hides two very different things, and the line between them
is a product boundary worth stating explicitly so it isn't crossed by accident later.

## Decision
The system **personalizes to the WORK, not to the PERSON.**

- **In bounds — personalize to the work:** a researcher's entities, pending items, WIP, campaigns,
  and project arc. This is what the warm-start briefing, serendipity nudges, and research story do,
  and it is squarely assistant behavior.
- **Out of bounds — model the person:** voice, tone, writing style, private working habits, a
  persona/identity model of the individual. No feature may model or adapt to *who the researcher
  is*. **No persona/preference memory.**

Concretely: don't build features like "write in your voice," "learn your habits," or a per-person
identity profile. Enjoyment features stay about the work and the lab, never about impersonating or
mirroring the researcher.

## Rationale
- **The process is an assistant, not a twin.** (The user's framing.) It should help a researcher do
  their work — not become a digital double of them.
- **It extends "substrate, not thinker" (ADR-0030) one step further.** The substrate is shared
  *infrastructure* the whole lab stands on. A per-person identity model would quietly turn it into N
  private companions and fragment the one shared brain the whole design exists to build.
- **It protects rigor.** A system that models *you* drifts toward telling you what you want to hear.
  Keeping it an assistant is part of what lets the research story keep its caveats, the critic gate
  stay independent, and grounding stay honest — a twin would be tempted to soften all three.
  Personalization must never be allowed to shape the rigor layer.

## Consequences
- Persona / preference memory is off the roadmap; future proposals in that direction should be
  declined with reference to this ADR.
- The three shipped enjoyment features already sit on the correct (work) side of the line and need
  no change.
- Personalization-by-work is still encouraged — it's how those features earn their delight. The
  boundary is specifically about modeling the individual's identity, not about being useful to them.
