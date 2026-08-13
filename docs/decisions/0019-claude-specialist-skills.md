# ADR-0019: Claude specialist for scientific tool use (Agent Skills)

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
ADR-0014 flagged the k-dense-ai/scientific-agent-skills library (158 MIT skills) as a
possible tool/execution layer. The question was *how* to integrate it. The skills are
**Agent Skills** — `SKILL.md` prose procedures + `references/` + bundled `scripts/`,
built for progressive disclosure in a Skill-aware harness — **not** Python functions
for our local Qwen JSON tool-loop. Three mismatches make "inherit as inline tools"
wrong: format (markdown+scripts, not callables), model capability (a 14B can't reliably
drive multi-step SKILL.md procedures), and tool-routing (158 tools would swamp a 14B).

## Decision
Use **Claude for the tool/skill execution**, behind a single orchestrator bridge:
- **`run_specialist(task)`** — a new orchestrator tool. The local Qwen orchestrator
  delegates one scientific-computation task; the specialist runs on Claude.
- **`specialist.py`** — a Claude agent loop with three tools: `list_skills`,
  `read_skill(name[, file])` (progressive disclosure), `run_bash(cmd)` (execute a
  skill's scripts in an isolated workspace). It reads the relevant SKILL.md, runs its
  scripts, and returns a result summary.
- **`llm.chat(..., backend=, model=)`** — a per-call backend override so a local-Ollama
  orchestrator delegates *one step* to Claude without changing the process-wide backend.
- Skills are an **external, gitignored library** (`SPECIALIST_SKILLS_DIR`, cloned on
  demand) — not vendored — with a **curated allow-list** (`SPECIALIST_SKILLS`, default
  6 computational-medicine skills) so the specialist isn't swamped.

## Rationale & evidence
- **Layer, not inline tools**: skills fit the *specialist execution layer* of the
  multi-agent design (ADR-0011), consumed by a frontier model — exactly what the LLM
  adapter (ADR-0014) was built to enable.
- **Verified (deterministic layer, no key)**: discovery finds the 6 curated skills;
  `read_skill` returns real SKILL.md/scripts; `run_bash` executed
  `clinical-decision-support/scripts/cohort_table_generator.py` end-to-end and produced
  a real **disclosure-controlled aggregate cohort table** (small-cell suppression). The
  execution layer works today.
- **Verified (Claude driver, structural)**: with a bogus key the request returns
  **401 (auth), not 400** — the tool-loop request shape is well-formed (`anthropic
  0.121.0`). Live end-to-end needs `ANTHROPIC_API_KEY` (key-gated, per ADR-0014).
- **Privacy preserved (ADR-0001)**: patient-row data stays on the local orchestrator;
  the specialist gets only de-identified/aggregate/synthetic inputs — and the clinical
  skills are research-only by their own frontmatter (no PHI, no patient-specific
  decisions). `run_bash` is workspace-scoped with a timeout.
- **Curate, don't adopt all 158**: default allow-list is the modality-relevant subset
  (clinical-decision-support, clinical-reports, experimental-design,
  exploratory-data-analysis, analytical-method-validation, biopython).

## Consequences
- The orchestrator can now delegate real scientific computation (cohort tables,
  survival plans, biomarker eval, de-id checks, experimental design, stats, biopython)
  without reimplementing any of it — reuse an MIT library maintained by others.
- Requires `pip install anthropic`, `ANTHROPIC_API_KEY`, and the skills library cloned
  under `SPECIALIST_SKILLS_DIR`. Skills stay gitignored (491MB) like the KG caches.
- Live Claude round-trip is the one unverified step here (no key in this environment).
