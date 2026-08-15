# ADR-0055: Follow members and projects — a change digest since you last looked

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
The warm-start briefing (ADR-0049) answers "what changed in the lab, for ME" — scoped to your
own entities and the review queue. It has no notion of "the work I care about because a
colleague or a project is mine." In a multi-member lab, a researcher wants to open a session
and see, in one place, everything that moved on the people and projects they follow: hypothesis
and workflow status, new contributions, belief revisions, contradictions, exploratory findings.
Every one of those change surfaces is already timestamped and attributed — the missing piece is
a way to *register interest* and get a delta.

## Options considered
1. **Do nothing / rely on the generic briefing.** The briefing's "touches your entities" heuristic
   is entity-scoped, not people/project-scoped, and misses a colleague's work on entities you
   don't personally own. Insufficient for "follow Bob's projects."
2. **A first-class Project object** (owner + explicit member roster + linked hypotheses/campaigns)
   that people join, with subscriptions pointing at Projects. More explicit, but it introduces a
   new schema, a join/registration flow, and a backfill of all existing work into projects — a
   large change for a following feature.
3. **Reuse existing units** (chosen). Follow a `member:<name>` or a `project:<id>` (a hypothesis
   id or a campaign name). "Membership" is *inferred from attribution* — a member's projects are
   the ones their attributed work touches. No new ownership schema; the digest is a delta-scan of
   the logs that already exist.

## Decision
Add `subscriptions.py` — a per-person follow registry plus a change digest:

- **Registry** — append-only follow/unfollow events (`memory/subscriptions.jsonl`), folded to
  current state (last action per target wins). Attributed to the caller (`_caller()` over HTTP).
- **Digest** — a delta since a per-person `subscription_seen.json` marker (the same mechanism as
  the briefing), grouped by followed target:
  - `member:<name>` → that person's contributions, belief revisions, contradictions, and misc
    findings, plus the projects they're active on (inferred from their experiment-attributed
    contributions).
  - `project:<id>` → changes linked to the project by experiment-id in the event source (reliable
    for experiment findings) or by a declared entity (best-effort), plus the current
    hypothesis/workflow status or campaign lineage.
- **Two surfaces** — a dedicated `subscription_digest()` tool (the full view, which advances the
  marker) and a compact preview folded into the warm start (`briefing_lines`, which does *not*
  advance the marker, so the full digest still shows the detail). MCP personal-tier tools:
  `follow`, `unfollow`, `my_subscriptions`, `subscription_digest`.

## Rationale + evidence
- **Reuse over new schema.** Members, hypotheses, and campaigns already exist and are attributed;
  a following feature shouldn't require an ownership model. Inferring membership from attribution
  keeps the substrate honest — it reflects who actually did the work, not a roster that can drift.
- **Personal, not shared.** A follow list is a private preference, so it lives in the personal
  tier and never enters shared consensus — consistent with the tiering (ADR-0031) and with
  "assistant, not twin" (ADR-0052): it personalizes to the *work you track*, not to who you are.
- **Read-heavy, delta-driven.** The only writes are the tiny registry and seen-marker; everything
  else is a scan of existing logs, so it stays fast and adds no new source of truth.
- **Verified.** The hermetic demo follows a colleague and a project and renders a grouped,
  attributed digest (`member:bob` → 3 changes + "active on H002"; `project:H002` → the linked
  finding + belief move, attributed "← bob"). An integration test confirms the preview folds into
  the warm start and the seen-marker advances so the delta clears after viewing.

## Consequences
- A researcher can follow colleagues/projects and get a one-glance digest in the warm start and on
  demand — the Tier-3 "follow the work you care about" piece of the lab-brain review.
- The digest is only as rich as the attribution in the logs; project↔event linkage is strongest
  for experiment-derived events (experiment id in the source) and best-effort for literature
  events (declared entities). This is stated, not hidden.
- Clean seam left: the same registry + belief lifecycle can drive *push* notifications ("your
  followed edge just got contradicted") if the lab later wants alerts rather than a pull digest.
