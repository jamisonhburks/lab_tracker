# Changelog

Reverse-chronological summary of substantive changes. Each entry links a PR to the
decision behind it (see `docs/decisions/`). Dates are approximate build dates.

## 2026-08-16
- **Lab-workflow retrospective — a coach, not a scoreboard** (`lab_retro.py`, `calibration.py`,
  `mcp_server.py`, `briefing.py`) — a read-only step-back across everyone that composes the
  substrate's OWN process signals (cleared-bar findings, seeds burned on a losing design, runs
  killed by HALT gates, stalled hypotheses, re-hit dead ends, calibration bias, ADOPTABLE unused
  method gaps, promotion backlog, duplicated effort) into **WORKING / NEEDS ATTENTION / OPTIMIZE**.
  **Coaching, not surveillance, enforced in code:** the lab view aggregates and de-identifies
  attention items (names hypotheses + counts, never a person; a test asserts the run author never
  appears); pointed feedback needs `member=<name>` and is framed as that person's own private view;
  no member ranking. Adds **per-member calibration attribution** — `calibration` tags each realized
  `Outcome` with the member whose confident call it scores (stability lens via first-revision
  contributor, adjudicated lens via `_edge_owner()`), with `audit_member()` / `audit_by_member()`
  staying humble below `MIN_OUTCOMES`. Surfaced via the `lab_retro` MCP tool + a warm-start preview.
  10 hermetic tests (`tests/test_lab_retro.py`, `tests/test_calibration_attribution.py`). (ADR-0059).
- **Verified audit + ignition spec** (`docs/audit-kg-and-bloat.md`, `docs/ignition-spec.md`, docs-only)
  — a from-the-code assessment (every finding cited file:line and checked against disk state, not the
  docs): edge-confidence gaps, literature-ingestion robustness, and a proportionality read (~1,550 LOC
  of wired-but-never-run tier, no test suite, two non-overlapping front doors). The ignition spec is
  the cold-start plan for a ~12-person lab starting from zero (day-0 seeding, cold-start fallbacks, one
  unified surface + a weekly ritual, an effort-tagged build list). (PR #71).
- **KG information-processing correctness** (`confidence.py`, `kg_writer.py`, `deep_search.py`,
  `contribute.py`, `beliefs.py`, `agent.py`) — six fixes to how a claim earns its number.
  **B1**: the distillation path normalizes entities to canonical nodes (lazy, degrades to raw string),
  so surface variants merge into one edge instead of fragmenting evidence. **B4**: the structural junk
  filter always runs — `rigor_verdict` can only tighten (`reject` drops the batch), `accept` no longer
  bypasses it. **A7**: `research_group` (last-author independence signal) is now first-class, persisted,
  round-tripping, populated on both ingestion paths. **A1**: `score_association` discounts correlated
  same-group evidence (strongest full, each extra `+1/√rank`); unknown-group evidence stays independent,
  so it is inert on current data and engages automatically as the signal populates (zero regression).
  **A2**: confidence is the mean of a **Beta posterior** (Jeffreys prior) with a **credible interval**,
  replacing the ad-hoc sigmoid — the interval separates "0.49 from two weak studies" from a settled
  number; status vocabulary preserved so downstream consumers are unaffected. **A5**: the curated KG
  feeds its **own** grounding prior via length-2 path corroboration (capped below the trusted-KG floor,
  no double-counting), closing the flywheel loop. (PR #71).
- **Ignition — a fresh lab is non-empty on day 1** (`lab_profile.py`, `subscriptions.py`,
  `briefing.py`, `serendipity.py`, `agent.py`, `import_publications.py`) — roster + `list_members`
  (colleagues followable before they've contributed); a dependency-free BibTeX importer that turns the
  coverage map into a real agenda; cold-start fallbacks so warm start / serendipity orient from the lab
  profile + active hypotheses instead of going blank; and a `:jot` REPL quick-capture into the
  exploratory pool. (PR #71).
- **The active-work loop** (`worklog.py`, `experiments/H001/run.py`, `misc_research.py`,
  `contribute.py`, `mcp_server.py`, `agent.py`) — the previously-missing support for the messy middle,
  where researchers actually work. A per-hypothesis **run ledger** (`log_run`, auto-filled from
  `run.py`), **stability** across seeds, a persistent **worklog** (`note`), and a "where am I"
  **status dashboard** (`:status <H>` / `hypothesis_status`). The warm start surfaces "your experiments
  in flight." An **evidence bridge** (`contribute_result`) routes a finished, passing experiment
  through the critic gate without re-typing the numbers; a **sanity-check** (`sanity_check`) gut-checks
  an observation (lab-KG match + dead-end + novelty) without the full ceremony; a **pre-registration
  guardrail** (`preregistration`) flags the success_metric drifting after runs began (anti-p-hacking);
  and a **decision log** (`log_decision`) captures analysis choices for reproducibility. First
  automated `tests/` suite (55 hermetic tests). (PR #71).

## 2026-08-15
- **Simplify the slide diagrams** (docs-only) — reworked all 11 Mermaid diagrams to short, glanceable
  labels (the prose carries the detail) so a viewer gets each in seconds; consistent colour coding
  and cleaner flow. Regenerated `docs/diagrams/*.mmd` + `*.svg`.
- **Architecture overview** (`docs/architecture-overview.md`, docs-only) — a presentation companion:
  a parent diagram of the whole system, a zoom-in per block (trust tiers, knowledge graphs,
  epistemics/honesty, self-awareness, memory tiers, experience), the intended "day in the life"
  workflow, and a dedicated **"how the brain grows"** section (the ingestion flywheel, the pathways
  table, how a paper becomes normalized/reified nodes & edges, the governance that keeps quality up
  at scale, and measured scaling properties). 10 Mermaid diagrams; every module maps to its ADR.
- **Coverage / knowledge-gap map** (`coverage.py`, ADR-0058) — the capstone of the coverage work:
  `scope − covered` over the ML methods KG at the method-capability grain (modality × task ×
  learning-paradigm), disease-agnostic. Each gap cell is classified OPEN FRONTIER (no established
  method → candidate contribution — the class this lab cares about) vs ADOPTABLE (a method exists
  in the ML KG / literature — go use it), plus DEEPEN (covered cells missing an in-scope paradigm)
  and a META note on how much of the lab's own axes the KG even resolves (if low, "frontier" partly
  means "not in OUR KG" → distill literature in). Two honesty safeguards: concept-form resolution
  (not token overlap — fixed `OCT-longitudinal` wrongly matching `longitudinal EHR`), and a
  CONSERVATIVE clinical→ML task crosswalk (trajectory-simulation / disentanglement are deliberately
  NOT aliased — they stay frontier rather than being mislabelled adoptable). Offline-first (KG
  traversal); `deep=True` adds a best-effort PubMed pass that degrades to "literature unchecked"
  rather than over-claiming. Substrate-side/LLM-free; the thinker consumes lab_profile() context to
  prioritise. Shared MCP tool `coverage_map(member, deep)`. Pairs with the dead-end store (ADR-0056):
  dead ends mark closed avenues, coverage marks unopened ones. Verified hermetically (adoptable vs
  frontier split correct; KG resolution reported) (PR #66).
- **Modular lab/researcher prior-work profile** (`lab_profile.py` + `profiles/<id>.yaml`, ADR-0057)
  — the baseline that makes a coverage/knowledge-gap map meaningful for a SPECIFIC lab. Reframes the
  gap grain from biomedical entity-pairs to the **method-capability level: (modality × task ×
  learning-paradigm), disease-agnostic** — how an AI-for-health lab actually reasons (disease is a
  filter, not the axis). A profile declares its SCOPE (axes worked along) and records PUBLICATIONS
  tagged onto those axes (explicit or heuristic auto-tag from the title); `scope()` and `covered()`
  are the structured sets the coverage map will diff (`scope − covered`), and `profile_context()`
  serves the profile + tagged pubs as IN-CONTEXT grounding for the thinker to phrase gaps and
  propose the next method (substrate serves, thinker reasons — ADR-0030/0040). Modular: each lab
  ships `profiles/<id>.yaml` (`SUBSTRATE_LAB` selects), per-researcher views filter by author; a
  seed `profiles/helmholtz-ai-health.yaml` ships as the example. A work/publication corpus is WORK-
  not-person personalization (ADR-0052). Shared MCP tools `lab_profile` / `record_publication` /
  `covered_capabilities`. Verified hermetically (scope/covered/context; `OCT-longitudinal` kept
  distinct via a normalization fix). Sets up PR B (`coverage.py`: adoptable vs open-frontier gaps)
  (PR #65).
- **Negative-knowledge / dead-end store** (`deadends.py`, ADR-0056) — the lab now remembers what
  DIDN'T work and warns about it at INTAKE, so failed effort isn't repeated. Harvests dead ends
  from existing signals (well-powered `refuted` edges, `abandoned` hypotheses, `overturned`
  contradictions, failed `halt` validity gates) + explicit `record_dead_end(...)` notes. Key rigor
  distinction: EVIDENCED dead ends ("don't just repeat it") vs SOFT ones (abandoned/underpowered/
  set-aside → revisit-worthy, not disqualifying — encoding "absence of evidence ≠ evidence of
  absence"), with an optional `revisit_if` condition. `check()` matches a candidate line (pair/
  entity/approach, best-effort entity normalization) and is wired into `idea.assess()` so every
  idea assessment flags prior dead ends right under the verdict (⛔ evidenced / ⚠ soft / clear).
  Harvest is derived-on-read (always in sync); only explicit records are stored. Shared + attributed
  (negative knowledge is collective). MCP shared tools `check_dead_ends` / `record_dead_end` /
  `list_dead_ends`. Verified with a hermetic demo (evidenced pair → avoid; soft pair → revisit;
  unrelated → clear) (PR #64).
- **Follow members & projects** (`subscriptions.py`, ADR-0055) — lab members can now FOLLOW a
  colleague (`member:<name>`) or a project (`project:<H0xx|campaign>`) and, when asking for a
  summary, get a DELTA of everything that changed on what they follow since they last looked —
  hypothesis/workflow status, contributions, belief revisions (ADR-0053), contradictions, and
  exploratory findings — grouped by target and attributed. Reuses existing units (no new project/
  ownership schema); "membership" is inferred from attribution (a member's projects are the ones
  their attributed work touches). Read-heavy delta-scan of the existing timestamped/attributed
  logs; the only writes are the per-person follow registry (append-only) and a `subscription_seen`
  marker (same mechanism as the warm start). Two surfaces: a dedicated `subscription_digest()`
  (full view, advances the marker) and a compact preview folded into the warm-start briefing
  (preview, doesn't advance — so the full digest still shows the detail). Personal-tier MCP tools
  `follow` / `unfollow` / `my_subscriptions` / `subscription_digest`; a suggested-next hook in the
  briefing. Personal, never shared consensus (ADR-0031/0052). Verified: hermetic demo (member +
  project digest, attributed) + integration test (preview folds into warm start, seen-marker
  advances) (PR #63).
- **Calibration audit** (`calibration.py`, ADR-0054) — the substrate audits its OWN confidence
  (Tier 2 of the lab-brain gap review). `confidence.py` says its number is "not a calibrated
  probability"; this scores that number against realized outcomes the belief lifecycle already
  generates — resolved contradictions (ADJUDICATED: upheld=1 / overturned=0) and belief reversals
  (STABILITY: did a settled decisive belief hold as evidence accrued?). Reports a reliability
  table (per-bin predicted vs. held-up rate), ECE, Brier, net over/under-confidence bias, and a
  plain-English verdict pointing at the worst-calibrated band. Read-only; no new epistemics; it
  MEASURES, it doesn't alter the scorer. Stays HUMBLE below a data floor (≥8 outcomes) rather than
  reporting a misleading number, and every rendering states the outcomes are the substrate's own
  proxies, not a gold standard — accountability as a rigor feature (ADR-0052). MCP shared tool
  `calibration_audit(lens=all|adjudicated|stability)`. Verified: hermetic self-demo flags a
  synthesized over-confident lab (0.9 band called ~0.94, only ~0.50 held → ECE 0.32, "over-
  confident"); real empty logs return the humble floor message. Recalibration map left as a clean
  follow-on seam (PR #62).
- **The belief lifecycle** (`beliefs.py`, ADR-0053) — makes `confidence.py`'s stateless scorer
  into LIVING STATE so the substrate reads as a lab brain with updating knowledge. (1) belief is
  PERSISTED per edge (projected from accumulated `kg_writer` evidence + KG grounding — the same
  projection `query_curated_findings` shows); (2) every corroborating contribution RE-SCORES the
  edge and records the DELTA (`0.95 → 0.97, +0.02`), hooked into `contribute()`'s auto-merge;
  (3) an append-only belief TRAJECTORY (`memory/belief_log.jsonl`) — both the "updating knowledge"
  trail and the provenance of the confidence itself; (4) a CONTRADICTION LEDGER
  (`memory/contradictions.jsonl`) — a claim that OPPOSES an established belief (refutes a supported
  edge / supports a refuted one) is kept as a first-class, thinker-resolvable conflict instead of
  being silently gated away; corroborating evidence held for review opens no conflict. No new
  epistemics (reuses the scorer), event-sourced + `store_lock`-guarded (contribution-log ethos),
  substrate-records-thinker-judges (ADR-0040). MCP shared tools `belief`, `belief_history`,
  `contradictions`, `resolve_contradiction`; `query_curated_findings` gains a live trend arrow.
  Verified: hermetic self-demo (0.54→0.89→0.95 as sources accrue) + integration test through the
  real `contribute()` path (auto-merge revision, contradiction on refutation, no spurious conflict
  on corroboration, clean resolution). Tier 1 of the lab-brain gap review (PR #61).
- **Design principle — assistant, not twin** (ADR-0052, docs-only) — recorded the decision to
  DECLINE persona/preference memory. The system personalizes to the WORK (entities, pending items,
  WIP, project arc — the warm start / serendipity / research story) but NOT to the PERSON (voice,
  style, identity). Extends "substrate, not thinker" and protects rigor (a twin drifts toward
  telling you what you want to hear). Future persona-modeling proposals should be declined (PR #60).
- **Research story** (`research_story.py`) — an HONEST narrative of a project's arc, NOT a highlight
  reel. Per step it weaves what went well + the evaluator's verdict with CAVEATS (failed validity
  gates, weak/novel grounding, already-published core, min_runs, SYNTHETIC-vs-real data, and the
  evaluator's own limitation sentences) and concrete ways to SOLIDIFY (power up, replicate, confirm
  on real data, widen the panel, get independent corroboration), closing on the arc's WEAKEST link.
  MCP shared `research_story(campaign)` + CLI. Verified on the real T2D–AD arc: H001 flagged
  synthetic-data (→ confirm on real data), H002 flagged its data_scale anomaly + "underpowered" +
  "binding limitation is power" and named the weakest link. Shared MCP = 26 tools (PR #59 · ADR-0051).
- **Serendipity nudges** (`serendipity.py`) — surprising, RELEVANT connections you didn't go
  looking for, deduped per user so they delight not spam. Types: CLUSTER (your finding shares an
  entity with a colleague's), RESURFACING (your entity gained a new neighbor in someone's edge),
  COLLABORATOR (an active hypothesis touches your entity — word-boundary match so IL6-style short
  symbols hit), and BRIDGE (two of YOUR entities connect via a KG bridge — the Swanson move,
  opt-in/deep). Cheap nudges ride in the warm-start briefing (✨ section + they can become the
  suggested next step); the KG-bridge nudge is the MCP personal `serendipity` tool (9 personal
  tools). Verified: cluster/resurfacing/collaborator fire, second call deduped-empty, deep runs
  (PR #58 · ADR-0050).
- **Warm-start briefing** (`briefing.py`) — the first "make it enjoyable" feature: opening a
  session greets you like a colleague catching you up, not a blank prompt. Four parts — WHERE YOU
  LEFT OFF (your last session journal), WHAT'S NEW in the lab since you were last here (new
  consensus + contributions touching YOUR entities, a real delta vs a per-user `briefing_seen`
  marker), WAITING ON YOU (review queue, promotion candidates, stale topics), and ONE suggested
  next step. Read-only composition of existing signals; fast, no network, calibrated tone, no
  leaderboard. Printed at agent-REPL startup; MCP personal `warm_start` (8 personal tools).
  Verified: four sections render; the "what's new" delta goes quiet on the second open
  (PR #57 · ADR-0049).
- **Scheduled refresh + source independence** — (1) `deep_search.stale_topics()` + `refresh_stale.py`
  (cron): a scheduled job re-distils topics whose cache went stale (runs the local agent's
  `curate_literature`), so the primary KG self-heals without waiting for a re-ask; MCP `stale_topics`
  surfaces them. (2) `deep_search.independent_count()` groups PMIDs by LAST AUTHOR (same group → one
  source, persisted meta cache), and graduation now requires ≥N **independent** sources (cheap
  distinct-source pre-filter, network only on candidates) — so one group citing itself can't game
  the bar. MCP shared +1 (`stale_topics` = 25). Verified: stale detection (latest-per-topic),
  independence (3 PMIDs/2 authors → 2), anti-gaming graduation rejected at min=3 (PR #56 · ADR-0048).
- **Deep-search cache maturation** — three follow-ups. (1) EXPIRY: `search_status` ages cache hits
  (`STALE_AFTER_DAYS`=180) → "COVERED BUT STALE, refresh" vs "covered, skip". (2) GRADUATION:
  `graduation_candidates(min_sources)` surfaces distilled edges backed by ≥N independent sources not
  yet in consensus; `graduate(s,p,o,critic_verdict)` routes them from the evidence layer into GATED
  consensus via `contribute()` (well-corroborated → auto-merge; borderline → review). (3)
  `curate_literature` now checks `search_status` first + `mark_searched` after, so the local agent
  shares the cache and avoids redundant sweeps. MCP shared +2 (`graduation_candidates`, `graduate`
  = 24). Verified: 957-day hit flagged stale; 3-source edge graduates + drops off candidates
  (PR #55 · ADR-0047).
- **Deep-search distillation → primary KG** (`deep_search.py`) — cache expensive literature sweeps
  so the lab doesn't repeat them. `search_status(topic, a, c)` checks a deep-search cache
  (`memory/search_cache.jsonl`) + curated coverage BEFORE a big search ("already covered → skip").
  `deep_fetch` does a broad multi-query PubMed fetch (no LLM) → corpus for the thinker to distill.
  `record_distillation` writes the thinker's distilled associations into the primary KG (kg_writer)
  with provenance (junk-checked, attributed via `_caller()`, locked) + caches the topic. Substrate
  fetches/writes/caches; the thinker (Claude) distills. MCP shared +3 (`deep_search_status`,
  `deep_fetch`, `record_distillation` = 22). Verified: status→record→status flips to COVERED, edges
  land in the primary KG, live PubMed fetch (PR #54 · ADR-0046).
- **Remote/HTTP MCP deployment** — one shared substrate for the whole lab. `MCP_TRANSPORT=http`
  (host/port) runs the FastMCP streamable-HTTP transport (default stays stdio, so nothing breaks);
  one instance on a cluster node loads the reference KG ONCE and serves everyone. Per-request
  attribution via `_caller()` (reads `X-Substrate-Contributor` from a reverse proxy after auth) →
  new `contributor=` on `contribute()`/`log_misc()` so writes are attributed to the real person.
  New `store_lock` (POSIX flock) serializes the append-only logs + the curated-KG read-modify-write
  for safe concurrent contributions. `docs/deployment.md` (systemd/container, TLS+auth proxy,
  client config, git role, privacy). Verified: locked append, off-HTTP attribution fallback,
  explicit-contributor attribution, HTTP boot (uvicorn up, /mcp 406s a plain GET) (PR #53 · ADR-0045).

## 2026-08-14
- **`docs/related-work.md`** — verified prior-art map + honest novelty positioning. A multi-agent
  literature/GitHub sweep followed by a VERIFICATION pass (each source fetched from an independent
  host — Crossref, Nature/OUP, PMC, GitHub API; none hallucinated). Records: foundations we build
  on and must NOT claim (Swanson LBD, Rephetio DWPC/permutation-null, GraphRAG/ToG, SciMON); the
  closest twins to differentiate from (caura/MemClaw, Graphiti, BioRouter/SPOKEAgent, AgentRxiv,
  Google co-scientist); the surviving wedges (fused bio+ML method-selection KG; the specific
  gated/tiered union) and the ablations needed to publish. Verdict: novel integration, not novel
  components (docs-only).
- **Semantic grouping + one-step formalize** — misc-finding grouping now clusters SYNONYMS, and a
  cluster drafts a hypothesis in one call. `_canon_key` keys entities by KG node id (gene aliases,
  disease synonyms) so ontology synonyms collapse; `_semantic_merge` adds a precision-first
  embedding pass (threshold 0.80, calibrated) for off-graph surface variants, graceful if the
  embedder is down. A shared `hypothesis_stub` backs both `session_journal.formalize_retroactively`
  and the new `misc_research.formalize_group(theme)` (MCP `formalize_misc_group`, 19 shared tools),
  so a cluster → draft hypothesis in the same format a session gives. Verified: `myocardial
  infarction`≈`acute myocardial infarction` merge clusters two different-subject findings; unrelated
  stays separate (PR #51 · ADR-0044).
- **Exploratory lane** (`misc_research.py`) — for sessions that just run analyses, not a
  pre-registered hypothesis. `session_journal.session_mode()` detects an `adhoc_series` (≥2
  experiments/findings, no hypothesis) and asks: attach the Research Workflow retroactively
  (`formalize_retroactively()` drafts a hypothesis+method stub) OR log as miscellaneous. Misc
  findings enter a rigor-gated pool (`memory/misc_findings.jsonl`) — claim+method+evidence, else
  flagged (not dropped); rigor verdict thinker-suppliable. Each is MATCHED vs the lab KG /
  consensus / active hypotheses (corroborates / relates_to_Hxxx / grounded_novel / orphan), and
  orphans are GROUPED by shared entities into latent themes to formalize. MCP: shared +4
  (`log_misc_finding`/`match_misc_finding`/`group_misc_findings`/`list_misc_findings` = 18),
  personal +2 (`session_check`/`formalize_retroactively` = 7). Verified rigor/match/group/detect
  (PR #50 · ADR-0043).
- **Synthesize before clear/compact** — Claude Code hooks (`.claude/settings.json` +
  `.claude/hooks/synthesize_session.py`) so a lab member's session captures its research before
  context is lost. Manual `/compact` (`PreCompact`) BLOCKS once with a **prompt** — "synthesize
  first?" — so the model can distil the session with full context, then re-run to proceed (or
  re-run to skip). Auto-compact and `/clear` (`SessionEnd`) can't block, so they heuristically
  synthesize the transcript into the session journal + `promotion_review` and notify. Reuses
  `session_journal`; everything lands in the local personal tier. Hooks require the user's
  Claude Code trust approval before they run. Verified all paths (PR #49 · ADR-0042).
- **Session journal** — `session_journal.py` keeps the PERSONAL tier alive DURING a live session,
  not just at run boundaries. `note()` appends to `memory/sessions/<id>/notes.md`; `checkpoint()`
  diffs against the last snapshot and, if anything changed, appends an append-only, hashed,
  timestamped delta to `journal.jsonl` (no-op on no change); `start(interval=3600)` runs a daemon
  thread that checkpoints hourly even mid-session; `promotion_review()` classifies accrued notes
  into candidate components (hypothesis/experiment/finding) and recommends how each climbs to
  SHARED WIP — a recommendation, never auto-promotion. Wired into the agent REPL (hourly
  background + per-turn notes + exit review) and the MCP personal tier (`journal_note`,
  `journal_checkpoint`, `promotion_review` — 5 personal tools; client drives the cadence).
  Verified: delta capture, no-op on no-change, time-gating, background daemon (2 ticks), promotion
  routing (PR #48 · ADR-0041).
- **Thinker-supplied critic verdict** — the critic on the consensus path can now be Claude (the
  client thinker), not the local model, keeping the substrate LLM-free. `contribute(critic_verdict=)`
  uses a client-supplied `accept`/`reject` (fail-closed) instead of running the local critic; every
  gate logs `critic_by` ∈ {thinker, local, provenance}. New no-LLM `hypothesis_tools.refine_evidence`
  gathers each bridge's mechanism + PubMed triple count + abstracts for the thinker to judge;
  `refine_hypothesis(critic_fn=)` accepts a thinker critic. MCP: `contribute_finding` gains
  `critic_verdict`, new shared tool `refine_evidence` (14 shared tools) — a Claude client does the
  whole gather→judge→record cycle with no LLM in the server. Verified: thinker accept→pending_review
  in 0.14s (no model), fail-closed normalize, `refine_evidence` output (PR #47 · ADR-0040).
- **MeSH↔HPO symptom/phenotype merge (combined KG)** — the last un-harmonized class in the
  `combined` backend. Hetionet's MeSH `Symptom` nodes now merge onto Monarch's HPO
  `PhenotypicFeature` nodes, so a Hetionet disease→symptom edge and a Monarch phenotype→gene edge
  meet at one node. Monarch's HPO nodes carry NO MeSH xref (only UMLS/SNOMED), so this is a
  lexical, PRECISION-FIRST crosswalk (exact name + exact-synonym, + de-plural + MeSH-inversion) —
  a miss leaves a node un-linked (prior behavior), a wrong merge would forge a false path. 183/438
  symptoms merged (the unmatched are mostly MeSH "symptoms" that are actually diseases). Reuses the
  proven `_apply_id_map` (PR #46 · ADR-0039).
- **Idea intake — `assess_idea`** — one entry point for the follow-up move: a free-text idea OR
  a prior `H{NNN}` → the local model extracts the testable entity pair(s) → EVALUATE (grounding +
  calibration + PubMed novelty → verdict: grounded/published/potential/off-graph) → PROPOSE the
  downstream workflow → RECOMMEND the costly refine pass (opt in with `refine=True`). Fast first,
  expensive on request. LLM-free core `idea.assess(a, c)` is exposed as MCP `assess_link`
  (substrate half — client extracts entities, no generation in the server); `assess_idea` (with
  extraction) is an agent tool. Verified verdict matrix + prior-work seeding + full path
  (PR #45 · ADR-0038).
- **Bulk method ingestion (Stage 4)** — `ml_ingest.py`: harmonize an external ML method corpus
  into the fused schema, deduped vs the curated 61 and written to a SEPARATE lower-trust seed
  (`seeds/ml_bulk.json`), edges tagged `paperswithcode (bulk)`. Curated = author-VERIFIED; bulk
  = paper-LINKED, not author-verified (explicit step down). PwC is sunset (media URL redirects
  to HTML), so the pipeline tries live, verifies gzip-JSON, and falls back to a vendored
  snapshot (43 real methods not in the curated set) — path printed, never silent. New
  `KG_BACKEND=ml_full` merges curated + bulk. Verified: bulk→curated lineage
  (`DETR —derived_from→ Transformer —suited_to→ ECG`); ml_full = 404 nodes / 494 edges, 104
  METHOD nodes (61+43) (PR #44 · ADR-0037).
- **ML bridge breadth (Stage 2)** — broadened the curated disease↔modality↔task↔architecture
  bridge in `ml_seed.py` (one appended block, no schema change): +6 diseases (glaucoma, AD,
  heart failure, sepsis, diabetic retinopathy, epilepsy), +6 modalities (fundus, OCT, MRI/CT,
  histopathology WSI, EEG, clinical text), +7 tasks, +5 losses, +7 metrics, +6 caveats, ~100
  edges wiring EXISTING arXiv-attributed architectures to them. Seed 281→318 nodes / 316→419
  edges, all 61 methods preserved. `recommend_methods("glaucoma")` now returns fundus/OCT/
  genomic methods with authorship, losses, metrics + caveats (PR #43 · ADR-0036).
- **Resilient live retrieval (`net.py`)** — one shared helper (`urlopen_retry` / `fetch_bytes`
  / `fetch_text`) that every external fetch routes through (PubMed, arXiv, Monarch, Hetionet,
  HGNC). Retries only transient failures (connection/timeout, HTTP 429/5xx; 404 fails fast)
  with exponential backoff + jitter — tenacity if installed, else an equivalent manual loop
  (so the dep is OPTIONAL). Replaced novelty's bespoke retry loop; deleted all raw `urlopen`
  call sites. Verified both paths (retry-then-succeed, 404 fail-fast, 503 retry, exhaust-
  reraise) (PR #42 · ADR-0035).
- **`scaffold.py` onboarding helper** — automates the mechanical half of the `new-project` /
  `conform-project` flows (stdlib-only, no deps). `new` builds the standard tree + fills
  `CLAUDE.md`/`README.md` placeholders (computed substrate path, status `scaffolding`) +
  `.gitignore` + a `notes/00_charter.md` stub listing the substrate checks for the next
  session to run; `conform` is NON-destructive (missing dirs + files only, never overwrites).
  Idempotent (`--force` to overwrite). Deliberately does the copy-and-fill, NOT the thinking
  (grounding/hypotheses stay agent-driven). Verified: fill, idempotency, non-destructive
  conform (PR #41 · ADR-0034).
- **Lab-standard onboarding playbook** — a self-describing layer (docs only) so a fresh
  session can scaffold a new project or conform an existing one to the standard, then keep
  future sessions on-standard. Root `AGENTS.md` routes by intent → `lab-standard/`:
  `START-HERE`, `new-project`, `conform-project`, `hypothesis-workflow`,
  `experiment-workflow`, `promotion` (local semantic → shared WIP → shared consensus),
  `project-structure`, `using-the-substrate`, plus `templates/` (`hypothesis.yaml` with
  explicit `provenance:`/`validity_gates:` blocks, `project-README.md`, and
  `project-CLAUDE.md` dropped into each project so the rules travel with the work). No new
  code/deps — pure guidance over the existing MCP tools, 4-agent split, gates, and
  `contribute()` (PR #40 · ADR-0033).
- **`contribute()` write-path** — `contribute.py`: findings flow into shared CONSENSUS
  (the one gated tier) — normalized, critic-gated (literature→abstract, experiment→committed
  provenance), routed conservatively (novel/contradictory→pending_review, corroborating-
  supported→auto_merged, junk→rejected), appended with ATTRIBUTION; auto-merge aggregates
  evidence + confidence. Exposed as MCP shared-tier tools (contribute_finding, review_queue).
  Git deploy: append=PR, critic=CI, review=approval. Also fixed a latent cold-start bug in
  `_norm_index`. Verified all 3 routes (PR #39 · ADR-0032).
- **Three-tier substrate scoping + WIP group semantics** — `SUBSTRATE_SCOPE`
  (personal|shared|all) on the MCP server: PERSONAL (episodic + personal semantic, local),
  SHARED WIP (`list_active_work` — every tracked hypothesis/experiment/campaign with STATUS
  + validity-gate counts, provisional/un-gated), SHARED CONSENSUS (critic-gated curated
  findings). Run a shared deployment (hosted, over git-repo KG) + a personal one (local).
  Distinction is CONCLUSION vs PROCESS: process is shareable mid-flight, findings are gated
  (PR #38 · ADR-0031).
- **KG-grounded method selection (Stage 3)** — `method_select.recommend_methods` turns
  'what method for this data?' into a GRAPH TRAVERSAL (modality→suited_to→used_for→
  trained_with→evaluated_by + caveats + authorship + trust split), backend-independent.
  Wired into `propose_experiment` (appends after the study-design essentials) and exposed
  as a tool. Verified: ECG→Transformer; T2D event-based→Transformer/GRU vs tabular→XGBoost
  (PR #36 · ADR-0029).
- **MCP substrate server** — `mcp_server.py`: exposes the substrate over MCP (local
  stdio) so a fresh Claude session (Claude Desktop / Claude Code) can think WITH it —
  ground_claim, calibrate_link, check_novelty, find_paths, query_curated_findings,
  recall_prior_work, recommend_methods, propose_experiment + audit resources
  (provenance/report/ledger/hypothesis). No LLM inside (substrate, not thinker); returns
  evidence, not just answers. Verified: 9 tools + 5 resources register, live call returns
  grounding. Realizes 'substrate, not thinker' (PR #37 · ADR-0030).
- **ML layer — Stage 1 curated expansion** — grew the arXiv-seeded method set 13→61
  seminal methods (NLP/CV/graph/generative/SSL/RL/tabular) with REAL first/last-author +
  year from arXiv, hand-curated lineage, and a title-keyword GUARD that drops any mistyped
  id before it can mis-attribute authorship (all 61 passed). Added XGBoost so tabular-EHR
  bridges. Split EHR by data STRUCTURE — longitudinal event-based (OMOP-CDM/MEDS
  → Transformer/GRU) vs aggregated tabular (→ XGBoost); MIMIC/eICU modeled as
  realizable-as-either. 281 nodes / 316 edges (ADR-0028).
- **Reified benchmarks + real ML seeding** — `ml_schema.BenchmarkResult` reifies
  (model, dataset, metric, VALUE, DATE) as a traversable node + `leaderboard()` temporal
  view; `ml_seed.py` fetches REAL authorship/dates from the arXiv API for ~13 seminal
  methods → `seeds/ml_fused.json` (`KG_BACKEND=ml`). Verified: real authorship (ResNet
  He/Sun 2015, ViT Dosovitskiy/Houlsby 2020); GLUE churn RoBERTa 88.5(2019)>BERT 80.5(2018)
  (PR #34 · ADR-0028).
- **Fused ML+biomedical schema** — `ml_schema.py` + `KG_BACKEND=ml_demo`: an ML/method
  layer built around methods being epistemically distinct from phenomena — authorship
  (first/last author, lab), Publication+year, lineage (`derived_from`/`superseded_by`),
  and an edge epistemic class where `achieves`/`outperforms` are LOW-trust (benchmark-
  relative, non-stationary) vs stable `suited_to`/`trained_with`. Bridge = Disease→
  DataModality→Architecture. Verified: cross-domain path (AF→ECG→Transformer), lineage
  (RoBERTa→BERT→Transformer), and the trust split grounds benchmark edges weak. Plugs into
  the existing traversal unchanged (PR #33 · ADR-0027).
- **Pydantic validation on structured output** — `schemas.py` + `llm.parse()`:
  keeps the proven constrained-decoding schema, adds Pydantic validation of the RESULT
  with retry-on-failure (feeds the error back) + code-fence stripping + type coercion.
  All 6 structured-output sites (agent ×4, critic, campaign) hardened. Verified: bad-JSON
  retry, missing-field retry, fenced-reply strip, `"250"`→int. A targeted boundary
  hardening — no framework (LangChain/LangGraph judged overkill) (PR #32 · ADR-0026).
- **Validity gates** — `validity.py`: pre-registered, hypothesis-ORTHOGONAL interim
  checks (cohort integrity, data scale, positive/negative controls) declared in the
  spec's `validity_gates` block. A `halt` gate stops a broken run (marked invalid, not
  "negative"); a `flag` warns. Catches machinery bugs WITHOUT steering the analysis
  (p-hacking safeguard). Verified: H001 all-pass (null-gene FDR check = 0.011); a
  cohort gate halts the `{AD:0}` case (the H002 `AD='AA'` bug); on H002 the data-scale
  gate FLAGGED GSE48350's max=59.24 — a real log-scale anomaly the original run missed.
  Folded into the provenance card (PR #30 · ADR-0024).
- **Campaign / program object** — `campaign.py`: a lineage (DAG) of atomic experiments
  (`campaigns/{name}.json`) where result-driven adaptivity safely lives. Auto-syncs each
  node's verdict from its evaluation report; `next_step()` proposes the NEXT atomic
  experiment from the last verdict + the evaluator's recommendations (LLM-assisted,
  human-approved draft). Verified: H001->H002 lineage; planner proposed H003 (ROSMAP
  snRNA-seq, powered, cell-type-aware) tagged draft/do-not-mutate-H002 (PR #31 · ADR-0025).

## 2026-08-13
- **Scaling profile + `scaling.py`** — content accounting per experiment (bytes/lines/
  tokens + scientific-op count; `python scaling.py` for a cross-experiment table).
  Measured: real-data H002 vs synthetic H001 ≈ 1.8× on-disk (run log 24×) and ~3× Claude
  subagent tokens (~73k→218k), dominated by runner+evaluator. Finding: **generation is
  token-free (local Qwen); testing/interpreting is the paid, dominant half** — cheap to
  propose, expensive to test honestly (PR #29 · ADR-0023).
- **Unified provenance view** — `provenance.py`: a deterministic (no-LLM) assembler that
  stitches an experiment's own artifacts (spec, formation method + pre-registration, the
  ordered scientific-op tool ledger, metrics, and the evaluation verdict) into one
  `experiments/{id}/provenance.md` — "how the hypothesis was formed and how it was tested"
  in one place. Verified on H001 (17-op synthetic pipeline) and H002 (13-op real-data
  pipeline; instrumented + re-run, deterministic) (PR #28 · ADR-0022).
- **Tool ledger (intended vs actual, across the loop)** — `tool_ledger.py`: (1) every
  orchestrator run declares the tools it EXPECTS to need (pre-flight plan) and records the
  ones it ACTUALLY calls in order → intended→actual→diff trace; (2) the specialist records
  its skill-call trace; (3) each experiment's `run.py` records its actual SCIENTIFIC ops
  (data gen/fetch, per-gene tests, `multipletests`, effect sizes, plotting) →
  `experiments/{id}/tool_ledger.json`. Verified: orchestrator run-11 (planned 4/used 3;
  ledger caught the 14B over-planning 11→3, fixed via a selectivity nudge); H001 emitted
  its 17-step scientific trace. Only the pipeline subagents' harness tools (Write/Bash)
  remain out of scope (harness telemetry) (PR #27 · ADR-0021).
- **H002 — first REAL-DATA run through the loop** — the T2D↔AD shared-gene panel tested
  on public GEO brain expression (GSE48350 discovery + GSE122063 replication, prep-matched
  bulk-vs-bulk, covariate-adjusted, panel-restricted Bonferroni+BH, cross-platform
  direction replication). **Honest null**: no central gene BH-significant + replicated
  (APOE borderline p_bh≈0.054, decreased); 3 panel BH hits all reversed sign in
  replication; replication arm underpowered (n≈23, power 0.09–0.22) so the null is bounded,
  not a refutation. Human-approved (draft→approved gate); runner caught the AD='AA' GEO
  coding gotcha. Contrast with H001's synthetic success — the loop reports real nulls
  faithfully. `hypotheses/H002*.yaml`, `experiments/H002/`, `reports/H002_evaluation.md`
  (PR #26 · ADR-0020).
- **Closed the scientific loop** — orchestrated `hypothesis-planner → code-implementer
  → experiment-runner → results-evaluator` (separation of concerns) to take a KG-
  generated hypothesis through formalize → implement → run → evaluate. Demo H001 (T2D↔AD
  shared genes) ran end-to-end on synthetic data with known ground truth: recovered 7/7
  planted genes at BH-FDR<0.05 & |d|≥0.5 across 3 seeds, 1 expected FDR false positive
  (Bonferroni rejected it). Validates the loop + stats machinery, not biology; evaluator
  caught + we fixed a duplicate-logging bug. Adds `hypotheses/H001*.yaml`,
  `experiments/H001/`, `src/utils/log_run_metadata.py`, `reports/H001_evaluation.md`
  (PR #25 · ADR-0020).
- **Claude specialist for scientific tool use** — `run_specialist(task)` delegates
  scientific computation to a Claude agent (`specialist.py`) that runs k-dense Agent
  Skills (`list_skills`/`read_skill`/`run_bash`). Skills are an external gitignored
  library with a curated allow-list; `llm.chat` gains a per-call backend override so
  the local orchestrator delegates one step to Claude. Verified: discovery/read/execute
  work (ran a skill to produce a disclosure-controlled cohort table); Claude driver
  401-not-400. Live round-trip needs an API key (PR #24 · ADR-0019).
- **Combined KG (Hetionet + Monarch)** — `KG_BACKEND=combined`: `load_combined()`
  harmonizes genes→Entrez (HGNC crosswalk), diseases→MONDO (DOID xrefs), and drugs→
  CHEBI (DrugBank xrefs), merging both graphs → ~174k nodes / 4.2M edges. A disease
  node inherits GWAS gene edges (Hetionet) AND phenotype/PPI edges (Monarch); drugs
  merge onto CHEBI (metformin→treats→T2D). Recovers T2D↔Alzheimer shared genes
  Monarch-alone lacked. MeSH↔HPO symptoms not merged (no in-data crosswalk, low value).
  A local slice of PrimeKG; no new downloads (PR #23 · ADR-0018).
- **Monarch KG backend** — `KG_BACKEND=monarch`: `load_monarch()` loads a focused
  human subgraph (~148k nodes / 1.9M edges) with 36k MONDO diseases + HPO phenotypes
  (vs Hetionet's 137 diseases, no phenotypes). Strong for phenotype/Mendelian
  hypotheses (Marfan↔Loeys-Dietz via shared phenotypes); sparse on GWAS gene-disease
  (complementary to Hetionet, not a replacement). PrimeKG/OptimusKG stayed Dataverse-
  202-blocked. Adds category-aware `_resolve` + STRING low-trust (PR #23 · ADR-0017).
- **Refinement loop** — `refine_hypothesis`: per bridge, novelty (cheap PubMed
  count) filters which links deserve the expensive `curate_literature` + `criticize`
  pass; triages each as known / supported-real / spurious and persists verified links
  to the curated KG. Verified end-to-end on AF↔stroke (`warfarin` supported, `KCNQ1`
  speculative); added `-1` `unknown_bridge` guard + rate-limit backoff (PR #22 · ADR-0016).
- **Novelty flag + hybrid generation** — `novelty.check_novelty` (rediscovery vs
  new juxtaposition, judged on the A–bridge–C triple) and `generate_hypothesis`
  (KG retrieves the subgraph → model synthesizes a mechanism CONSTRAINED to it →
  grounding + novelty regularize the claim). Novelty flag reproduces the lit-agent's
  gene tiering independently (CTF1 → `novel_bridge`) (PR #21 · ADR-0015).
- **LLM adapter** — `llm.py`: model reached via `chat()`; Ollama ↔ Claude is a
  config flag (`LLM_BACKEND`). Ollama path verified; Anthropic best-effort
  (PR #19 · ADR-0014).
- **Critic hardened** — accession pre-filter + multi-vote + expanded 12-case eval;
  gold set caught an accession gap → fixed to 1.00 (PR #18 · ADR-0013).
- **Critic agent** — adversarial verifier (`criticize_curated_kg`) + test-driven
  eval harness (`eval_critic.py`); catches hallucinations/junk while preserving
  novel valid links (PR #17 · ADR-0013).
- **B4 persistent KG (REPL)** — `python agent.py` with no arg keeps the KG + model
  warm across questions (PR #15).
- **B3 permutation-null calibration** — `calibrate_link`: percentile/p-value vs a
  degree-matched null, exposing density inflation (PR #14 · ADR-0010).
- **B2 grounding → confidence** — KG grounding folded into the confidence score;
  novel/off-graph never penalized (PR #13 · ADR-0008).
- **B1.6 type-aware normalization** — HGNC gene dictionary + BioLORD; fixes
  `IL8 → CXCL8` (PR #12 · ADR-0009).
- **B1.5 semantic normalization** — BioLORD (opt-in); catches disease synonyms;
  found to fail on gene symbols (PR #11 · ADR-0009).
- Curator: better synthesizer — per-paper extraction (exact PMID) + study stats
  (PR #9 · ADR-0011).

## 2026-08-12
- **B1 entity normalization** — canonical-node dedup, junk flagged (PR #10 · ADR-0009).
- **Synthesizer → KG-curator** — writable KG, literature→KG loop (PR #9 · ADR-0011).
- **Multi-agent architecture** design note (PR #8 · ADR-0011).
- **KG-as-verifier grounding check** — novel ≠ false (PR #7 · ADR-0008).
- **Power-weighted negative evidence** + confidence scorer (PR #6 · ADR-0007).
- **Reified-association schema** — phase 2 + spec (PRs #1, #5 · ADR-0006).
- **Hypothesis tools** — realism (degree-weighted) + experiment planner (PR #4).
- **Hetionet backend** + scalable indexed traversal (PR #2 · ADR-0004).
- Private repo + git workflow established (ADR-0012).

## 2026-08-11 (pre-repo prototype)
- Local Qwen3-14B agent via Ollama (ADR-0001).
- Layered memory (working / episodic / semantic) with claim-level provenance
  (ADR-0002).
- Retrieval scorers: recency-decay, hybrid BM25+dense (RRF), MMR, threshold
  (ADR-0003).
- KG (ontological) memory: typed traversal, A→B→C path discovery.

## Deferred / open
- **OptimusKG** — Dataverse locked (HTTP 202, likely 2.0 reingest); Hetionet used
  meanwhile, one-call swap when it unlocks (ADR-0004).
- Hybrid over pure KG-pretraining, pending honest (time-sliced/cold-start) eval
  (ADR-0005).
- Next specialist: **critic** agent. Autonomous execution half needs the compute
  cluster + human-in-the-loop.
