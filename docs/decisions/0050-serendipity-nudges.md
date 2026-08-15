# ADR-0050: Serendipity nudges (surprising, relevant connections)

- **Date:** 2026-08-15
- **Status:** Accepted

## Context
The warm-start briefing (ADR-0049) opened the "enjoyable" direction with *momentum*. The next
lever is *serendipity* — the delight of a relevant connection you didn't go looking for. A lab
that shares one accumulating brain is unusually rich in these: your work quietly meets other
people's, and the KG holds latent links between your own entities. Surfacing a few of those, well,
is a real joy hit — but only if it's *relevant* (about your work) and *low-frequency* (not spam).

## Decision
Add **`serendipity.py`** — a read-only nudge generator over existing signals, deduped per user so
each nudge is shown once:

- **cluster** — one of YOUR misc findings shares an entity with a COLLEAGUE's (social serendipity;
  "a joint hypothesis?").
- **resurfacing** — your entity just gained a NEW neighbor in someone's consensus/WIP edge ("a lead
  you didn't go looking for").
- **collaborator** — an active hypothesis touches one of your entities (word-boundary match, so
  short gene symbols like IL6 hit safely) — "worth comparing notes."
- **bridge** (deep) — two of YOUR entities connect through a KG bridge you may not have noticed —
  the Swanson move, applied to your own interests.

The cheap nudges (cluster/resurfacing/collaborator) are pure file reads and ride along in the
**warm-start briefing** (a `✨ Serendipity` section); the `bridge` nudge traverses the KG, so it's
opt-in via the MCP personal `serendipity` tool (`deep=True`). A per-user `serendipity_seen.json`
tracks shown nudge keys so nothing repeats.

## Rationale & evidence
- **Relevance + surprise, not noise.** Every nudge is anchored to *your* entities/findings (from
  your own contributions/misc), but points at something you didn't author — a colleague's finding,
  a new neighbor, a latent bridge. That's the serendipity sweet spot.
- **Low-frequency by construction.** Dedup vs a per-user seen set means a nudge fires once; the
  briefing shows at most two, the tool a few more. It delights because it's rare.
- **Cheap where it needs to be.** The briefing stays fast/no-network (cluster/resurfacing/
  collaborator are file reads); the KG-traversing `bridge` nudge is opt-in.
- **Composes on the briefing's own overlap detection** — no new heavy machinery, just a lens that
  frames overlaps as invitations. The briefing's suggested-next-step now points at a nudge when
  nothing else is pending ("those connections found you").
- **Verified**: seeded data yields a cluster nudge (your IL6 finding + a colleague's), a resurfacing
  nudge (IL6 → a new neighbor via another's edge), and a collaborator nudge (a hypothesis touching
  IL6 — matched via word boundary despite being 3 chars); a second call is correctly **empty**
  (deduped); `deep=True` adds KG bridges without error. Personal MCP tier = **9 tools**
  (＋`serendipity`); all modules import clean; `memory/` gitignored so the seen-set stays local.

## Consequences
- The lab's shared memory now actively *hands you* connections — the KG and your colleagues'
  work earning their keep as a source of delight, not just rigor.
- Follow-ups on the same idea: a "collision" nudge when someone contradicts your finding (worth
  resolving), an impact echo when your distilled edge becomes graduation-ready, and tuning nudge
  cadence per researcher once preference/persona memory exists.
