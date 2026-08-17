# Audit — KG information-processing, ingestion robustness, and bloat

**Date:** 2026-08-16 · **Method:** direct code reading + disk-state inspection. Every finding
below was verified against the source (file:line cited) and against the actual contents of
`memory/`. Nothing here is taken from the docs — several docs describe behavior the code does
not implement, and those gaps are called out.

**Headline.** The architecture is sound and the decomposition is mostly justified — this is not
a "delete half the modules" situation. The real problems are (1) the KG confidence/ingestion
pipeline has correctness gaps where its own schema already anticipated the right design but the
write/score path never wired it in, and (2) ~16% of the code is machinery that has **never
written a byte to disk** because nothing cheap produces the data it consumes. The two are the
same problem seen from two ends: *the flywheel has no fuel*.

Disk state at audit time (the ground truth):

```
memory/curated_kg.jsonl        1 line     ← the lab's "own" KG is essentially empty
memory/semantic.jsonl         57 lines
memory/episodic.jsonl         11 lines
memory/lab_contributions.jsonl 4 lines    ← all one contributor
belief_log / contradictions / deadends / subscriptions / misc_findings /
serendipity_seen / briefing_seen           ← ALL MISSING (never created)
```

Findings are grouped: **A** = how a claim earns confidence, **B** = how literature gets in,
**C** = bloat/structural. Each carries an effort tag (S ≤ half-day · M ≈ 1–3 days · L ≈ week+).

## Status — updated 2026-08-16 (PR #71)

**Shipped:** B1, B4, A7, A1, A2, A5 — the confidence/ingestion correctness core — plus the first
automated tests toward C2 (55 hermetic). Marked ✅ on each item below.

**Deferred by design:** A3/A4 (CI/effect/power) wait on **B2** full-text — without it those fields
stay null. A6 (calibration recalibration loop) is self-contained but won't fire until ≥8 adjudicated
outcomes exist. B3, B5–B7 and C1/C3–C5 remain open.

**Also shipped alongside** (beyond this audit's scope): the ignition S-tier and a full per-hypothesis
active-work loop (`worklog.py` — run ledger, status dashboard, evidence bridge, sanity-check,
pre-registration guardrail, decision log). See `docs/ignition-spec.md` and `CHANGELOG.md`.

---

## A · Edge confidence — how a claim earns its number

### A1 · Source independence is ignored in the confidence *number* (only gates graduation) — **M** · ✅ SHIPPED (PR #71)
**Verified:** `score_association` sums `e.informativeness()` over supporting/refuting evidence
with no author/lab/dataset de-duplication (`confidence.py:90–92`). The independence machinery
(`independent_count`, last-author grouping) exists but is called **only** at the graduation gate
(`contribute.py:225,252`), never in the score.

**Why it matters:** three papers from one lab (or one lab citing itself) move confidence exactly
as much as three independent groups — the opposite of what `docs/kg-schema-spec.md` §7 specifies
("count independent groups, not raw publications"). This is the single biggest correctness gap in
scoring: corroboration is the whole point of the curated KG, and it's mismeasured.

**Fix:** group supporting evidence by `research_group` (see A7) and apply a diminishing return per
additional same-group study (e.g. contribution `= informativeness · 1/√(rank_within_group)`, or a
capped per-group total). The last-author data is already fetchable via
`deep_search._resolve_meta`. Depends on A7 to have the field populated.

### A2 · Confidence is an ad-hoc sigmoid with no uncertainty band — **M** · ✅ SHIPPED (PR #71)
**Verified:** confidence is `_sigmoid(net)` where `net = support − refute` and
`_sigmoid(x)=1/(1+e^{-1.2x})` (`confidence.py:44–45, 102–108`), plus a hard-coded 0.45–0.55 pin in
the under-investigated branch (`confidence.py:99`).

**Why it matters:** a point estimate can't distinguish "0.72 from 2 weak studies" from "0.72 from
8 strong ones" — exactly the distinction a research lab needs. There is no credible interval, so
the honesty story the project sells ("we know how sure we are") isn't expressible.

**Fix:** replace the squash with a **Beta posterior** over evidence mass. Supporting evidence adds
to α, refuting to β (weighted by `informativeness`), grounding contributes prior pseudo-counts;
confidence = posterior mean, uncertainty = the 90% credible interval (or posterior variance).
Status thresholds map cleanly onto `(mean, total pseudo-count)` — the `investigation < INVEST_FLOOR`
floor becomes "total pseudo-count below k → under-investigated." Interpretable *and* principled,
~40 lines, no new dependencies.

### A3 · The effect-size / CI machinery is fully built and never called — **M**
**Verified:** `Evidence.covers_effect()` (`kg_schema.py:157–165`) — the method that separates an
*inconclusive* null (CI still admits a real effect) from a *true* negative — has **zero call
sites** (`grep covers_effect` → only its def). `ci_low/ci_high` exist on the dataclass
(`kg_schema.py:140–141`) but `add_association` persists only 7 keys and drops them
(`kg_writer.py:62–64`); `to_association` never rebuilds them (`kg_writer.py:88–97`).

**Why it matters:** the "absence of evidence ≠ evidence of absence" principle — the project's
intellectual centerpiece — currently rests entirely on the coarse `informativeness` heuristic, not
on interval coverage as the schema intended. The rigorous version was designed and left unwired.

**Fix:** persist `ci_low/ci_high` in the evidence dict and reconstruct them in `to_association`;
call `covers_effect` in the refuted-vs-`promising_but_poorly_tested` branch so a null with a wide
CI is never labeled `refuted`. Needs CI values at extraction time (→ B2).

### A4 · "Power-weighting" collapses to a flat 0.5 in practice — **S** (schema) / **M** (estimation)
**Verified:** the extraction schema captures `sample_size/effect_size/p_value/risk_of_bias` but
**not `power`** (`agent.py:88–94, 146–149`), so `Evidence.power` is `None` on every real row and
`informativeness()` falls to `risk_of_bias` or a default **0.5** (`kg_schema.py:151–155`).

**Why it matters:** the celebrated "underpowered null ≈ likelihood ratio 1" degrades to a 3-level
bias lookup, or — when the LLM omits bias — a flat **0.5 against the edge** for an unpowered null.
Two mediocre studies then outrank one excellent study purely on count.

**Fix:** (a) add `power` to the extract schema; (b) when unreported, *estimate* it from
`sample_size` + `effect_size` via a normal-approx power calc rather than defaulting; (c) lower the
no-information default for a refuting null below 0.5 so an uninformative null can't quietly refute.

### A5 · The curated KG never feeds its own grounding prior — **M** · ✅ SHIPPED (PR #71)
**Verified:** the grounding prior comes from `kg.check_connection` over the read-only Hetionet/demo
index (`contribute.py:97`, `confidence.grounding_prior`), while accumulated evidence lives in a
*separate* `curated_kg.jsonl`. A claim the lab has corroborated many times still gets prior **0.0**
(`off_graph`) if its entities aren't in Hetionet (`confidence.py:31–36`).

**Why it matters:** the flywheel is supposed to close — the lab's own growing knowledge should
raise its own priors. Today it doesn't; the brain can't learn to trust its own corroborated edges.

**Fix:** add an "internal corroboration" term to the prior: if the curated KG already holds the
edge (or a short path) with ≥k independent sources, contribute a modest prior — distinct from the
evidence sum to avoid double-counting. Cap it below the Hetionet-grounded prior so external
reference still dominates.

### A6 · Calibration is diagnostic-only — it never corrects the scorer — **M**
**Verified:** ECE/Brier/reliability are genuinely computed (`calibration.py:106–126`) but gated by
`MIN_OUTCOMES=8` (`calibration.py:34,140`) and the module's own docstring admits "fitting a
recalibration map onto the scorer is a clean follow-on seam" (`calibration.py:26–27`). A "POORLY
CALIBRATED" verdict changes nothing downstream.

**Why it matters:** a self-audit that can't act is a dashboard, not a control loop. And for a new
lab the 8-outcome floor won't be reached for weeks (outcomes only come from adjudicated
contradictions + belief reversals) — see the ignition spec for how to reach it deliberately.

**Fix:** once `n ≥ MIN_OUTCOMES`, fit an isotonic (or Platt) map from predicted→observed and apply
it as a post-hoc transform in `score_association`; keep the raw number for audit. Stay diagnostic
below the floor.

### A7 · `research_group` — the schema's designated independence signal — is never populated — **S** · ✅ SHIPPED (PR #71)
**Verified:** `research_group` appears exactly once in the codebase: the dataclass field
(`kg_schema.py:131`). Nothing writes it. Independence is instead reconstructed post-hoc by
re-fetching last-authors at gate time, which needs the network and only works for `PMID:` sources.

**Fix:** at write time, resolve last-author (already cached by `deep_search._resolve_meta`) and
store it as `research_group` on the evidence. Unblocks A1 and makes independence a stored property
rather than a network round-trip at the gate.

---

## B · Literature ingestion — robustness of the paper → edge path

### B1 · The distillation path skips entity normalization → the graph fragments — **S** · ✅ SHIPPED (PR #71)
**Verified:** `record_distillation` (the thinker-facing ingestion path) writes **raw strings** with
no `normalize_entity` and no canonical ids (`deep_search.py:166–170`), while `curate_literature`
*does* normalize (`agent.py:166`). Dedup then falls back to `subject.strip().lower()`
(`kg_writer.py:42–46`).

**Why it matters:** "type 2 diabetes" / "T2DM" / "diabetes mellitus type 2" become three separate
edges, each accruing evidence independently — fragmenting confidence exactly where corroboration
should concentrate it. This is the highest-value single fix in ingestion, and it's a few lines.

**Fix:** call `normalize_entity` in `record_distillation` and pass `subject_id/object_id` through,
mirroring `curate_literature`.

### B2 · Abstract-only ingestion starves the quantitative machinery — **L**
**Verified:** `_fetch_articles` extracts only `AbstractText` (`agent.py:119`); `deep_fetch`
likewise works on abstracts.

**Why it matters:** abstracts systematically under-report N, CI, and power — which is the root
cause that keeps A3 and A4 dark. Without results-section text, the effect/CI/power fields are
usually absent no matter how good the extractor is.

**Fix:** add open-access full-text (Europe PMC / PMC OA) when available and extract from the
results section; degrade to abstract otherwise. Larger lift, but it's what lights up A3/A4.

### B3 · Extraction is unvalidated at write time; the critic runs off the write path — **M**
**Verified:** `curate_literature` writes whatever the LLM returns if `subj/pred/obj` are non-empty
(`agent.py:157–177`); the hallucination-checking critic is a **separate** tool,
`criticize_curated_kg` (`agent.py:187`), run later and manually.

**Why it matters:** `query_curated_kg` can return possibly-hallucinated edges that no critic has
ever seen. The gate protects *consensus*, but the evidence layer is unguarded.

**Fix:** either run a lightweight structural+source check inline before writing, or mark edges
`unverified` until criticized and have `query_curated_kg` label/segregate them.

### B4 · `rigor_verdict="accept"` bypasses even the junk filter — **S** · ✅ SHIPPED (PR #71)
**Verified:** `if rigor_verdict != "accept" and not _ok(a): skip` (`deep_search.py:163`) — an
`accept` verdict skips `_ok`, which is the only guard against bare accessions / malformed triples.

**Fix:** always run `_ok` structurally; let `rigor_verdict` govern only the *rigor* decision, not
the malformed-input guard.

### B5 · Dedup is brittle across surface forms without a canonical id — **S** (follows B1)
**Verified:** `_rec_key` falls back to lowercased raw text (`kg_writer.py:42–46`); normalization
returns `None` on any miss and callers keep the raw string. The one real stored record has
`subject_id: null, object_id: null`.

**Fix:** mostly resolved by B1 (normalize on all paths). Additionally, add an alias/fuzzy fallback
for near-miss surface forms so novel-but-real entities still converge.

### B6 · No retraction / venue / study-type signal from retrieval — **M**
**Verified:** retrieval is raw NCBI E-utilities (`_fetch_articles`, `deep_search._pubmed`); the
only metadata pulled downstream is last-author + journal for independence (`deep_search:222–240`).

**Why it matters:** a **retracted** or preprint-only paper currently corroborates an edge just like
a peer-reviewed one. Nothing checks publication type or retraction status.

**Fix:** enrich via OpenAlex / Europe PMC (retraction flag, publication type, venue, and a real
author-disambiguated independence signal that also serves A1/A7).

### B7 · Search is user-initiated, never demand-driven by the KG's own gaps/uncertainty — **M**
**Verified:** every ingestion path starts from a human query; nothing consults the coverage map or
edge uncertainty to choose what to read next. The flywheel diagram (`docs/architecture-overview.md`
§4.1) describes "coverage finds the gap → search fills it" but no code closes that loop.

**Fix:** a tool that picks the next query from (a) the coverage gap map or (b) edges sitting near a
confidence decision boundary, and runs a targeted sweep. This is what turns the diagram into a
running loop — and pairs naturally with the ignition plan's scheduled refresh.

---

## C · Bloat / structural

### C1 · ~1,550 LOC of epistemic/social machinery has never run — **defer, don't delete**
**Verified:** `beliefs.py`, `calibration.py`, `deadends.py`, `subscriptions.py`, `serendipity.py`,
`briefing.py` are all wired into MCP but **every one of their backing stores is missing on disk**
(`belief_log`, `contradictions`, `deadends`, `subscriptions`, `misc_findings`, `serendipity_seen`,
`briefing_seen` — all absent). This is premature generalization, not bad code.

**Action:** don't cut it — the ideas are good and the ignition plan is designed to *light it up*.
But **freeze expansion** of this tier until real usage shapes it. The instinct to add another
epistemic module per PR is the actual bloat vector.

### C2 · No automated test suite for a system whose entire pitch is rigor — **M, high value**
**Verified:** no `tests/`, no `pytest`/`unittest` imports in any project module; the 130+ test files
all live under the vendored `external/scientific-agent-skills/`. "Testing" is 21 `__main__` demo
blocks.

**Action:** add a small pytest suite for the load-bearing pure functions first — `confidence`,
`kg_writer` dedup/merge, `deep_search.independent_count`, `entity_norm`. These are exactly the
functions the A/B fixes touch, so tests here also de-risk the changes above.

### C3 · Two front doors; the best half is unreachable from the REPL — **M** (the real UX bug)
**Verified:** `agent.py` DISPATCH exposes 18 tools; `mcp_server.py` exposes 51 tools + 5 resources.
All collaboration/experience tools (`contribute`, `warm_start`, `serendipity`, `follow`,
`coverage_map`, `research_story`, `review_queue`) exist **only** on the MCP side and are absent from
the REPL the README tells you to run. Addressed head-on in the ignition spec.

### C4 · `eval_critic.py` is a true orphan — **S**
**Verified:** zero importers; a manual `python eval_critic.py` harness only. Either wire it into
C2's test suite or move it under a `dev/` folder so it stops reading as production surface.

### C5 · The documentation apparatus is sized for a funded platform — **process note**
58 ADRs + a 39 KB CHANGELOG + rendered diagrams for a solo scaffold. Not harmful, but adding an ADR
and a diagram per PR is now a tax. Suggest: ADRs for genuinely load-bearing/contested decisions
only; let the code + this audit carry the rest.

---

## Suggested order (correctness first, cheapest-per-value)

1. **B1 + B4 + A7** (all S) — stop fragmentation, close the junk-filter bypass, start storing the
   independence signal. Small, isolated, immediately improve every future edge.
2. **A1** (M) — make independence count in the number. The biggest correctness win; needs A7.
3. **A2** (M) — Beta posterior with a credible interval. Makes confidence honest and legible.
4. **A3 + A4** (M) — wire the effect/CI/power machinery that's already designed; pairs with **B2**
   (L) when you're ready to ingest full text.
5. **A5, A6, B3, B6, B7** — the "close the loop" tier; sequence against real usage.
6. **C2** throughout — test the pure functions as you touch them.

The ignition plan (`docs/ignition-spec.md`) is the other half: it produces the data that makes
A5/A6 and the whole C1 tier actually run, for a 12-person lab starting from an empty scaffold.
</content>
</invoke>
