# ADR-0043: The exploratory lane — ad-hoc analyses, misc findings, match + group

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The Research Workflow assumes a session starts from a pre-registered hypothesis. But a lot of
real lab work isn't that: someone is *just running analyses*. Forcing every session through
formalization either blocks that work or, worse, loses it. Two honest needs fell out of this:
(1) when a session is clearly a *series of tests with no setup*, offer to formalize
retroactively — but don't force it; (2) when the work genuinely isn't tied to a hypothesis,
still let it into the lab record as **miscellaneous** — rigor-checked — and then see whether it
matches known work or whether scattered misc findings cluster into something coherent.

## Decision
Add an **exploratory lane** alongside the formal one.

- **Detect + ask (`session_journal`)**: `session_mode()` classifies a session as
  `hypothesis_driven`, `adhoc_series` (≥2 experiments/findings, no hypothesis), or `sparse`.
  When `adhoc_series`, `workflow_suggestion()` (surfaced in `promotion_review` and the MCP
  `session_check` tool) **asks**: attach the Research Workflow retroactively, or log as misc?
  `formalize_retroactively()` drafts a hypothesis + method stub from the session's notes
  (recurring entities → the link; experiment notes → the method) for the thinker to complete.
- **Log, rigor-gated (`misc_research.log_misc`)**: a miscellaneous finding enters the lab's
  exploratory pool (`memory/misc_findings.jsonl`) only after a **rigor** check — a claim + a
  method + some evidence (effect / p / n / source). Missing a claim → reject; missing method or
  evidence → **flag** (logged but marked "needs rigor", not dropped). The rigor verdict is
  thinker-suppliable (`rigor_verdict`, ADR-0040 pattern) with a heuristic fallback.
- **Match (`match_misc`)**: every misc finding is checked against the coherent lab knowledge —
  KG grounding + curated consensus + active hypotheses — and labelled `corroborates_consensus`
  / `relates_to_active_work (Hxxx)` / `grounded_but_uncurated` / `orphan`. No LLM.
- **Group (`group_misc`)**: orphan/misc findings are clustered by shared entities (connected
  components). A cluster of ≥2 is a **latent theme** — scattered analyses that together may
  imply a hypothesis worth formalizing. No LLM.

MCP: shared tier gains `log_misc_finding`, `match_misc_finding`, `group_misc_findings`,
`list_misc_findings` (18 shared tools); personal tier gains `session_check`,
`formalize_retroactively` (7 personal tools).

## Rationale & evidence
- **Meets researchers where they are.** Exploratory work is first-class, not shoehorned — but
  it still passes a rigor bar and stays *attributable* and *matchable*, so the misc pool doesn't
  become a junk drawer.
- **Same substrate discipline.** Misc findings are append-only + attributed; matching reuses
  `check_connection`/`kg_writer`; grouping is transparent entity overlap; the rigor gate mirrors
  the thinker-suppliable critic. Nothing here is a black box.
- **Turns scatter into structure.** Match connects a lone analysis to known work; group turns a
  pile of misc findings into candidate hypotheses — the path back to the coherent lab record.
- **Verified**: rigor accept/flag/reject; `match_misc(T2D, AD)` → `relates_to_active_work
  (H001, H002)`; four AF-touching findings → one latent theme with per-finding match status;
  `session_mode` detects an `adhoc_series` and prompts; `formalize_retroactively` drafts a stub.
  Shared MCP = 18 tools, personal = 7; all modules import clean; `memory/` gitignored.

## Consequences
- Two lanes now: hypothesis-driven (pre-registered → tested → consensus) and exploratory
  (misc → rigor → match/group → *maybe* formalize). Both feed the same lab KG.
- The exploratory pool is pre-consensus; a matched/grouped finding graduates via
  `formalize_retroactively` → shared WIP, or `contribute()` once tested.
- Follow-up: `group_misc` could hand a cluster straight to `formalize_retroactively` to draft the
  hypothesis, and semantic (not just exact-entity) grouping would catch synonymous entities.
