# HANDOFF — lab_tracker

A descriptive orientation for a fresh session. It states what the project is and how
it is laid out. It makes **no claim** about whether the design is good, correct, or
complete — form your own assessment from the code and docs.

## What it is

A biomedical research agent that runs fully locally: a Qwen3-14B model (via Ollama)
driven in a manual tool-calling loop, over a knowledge graph and a layered memory
store. The model can be swapped for Claude via an adapter (`LLM_BACKEND=anthropic`).

The loop: call the model → if it requested a tool, execute it and feed the result
back → repeat until it answers. The model orchestrates ~11 tools spanning literature
search/curation, memory recall, KG traversal/path-finding, and hypothesis
assessment/calibration. The KG backend is selectable (`KG_BACKEND=demo|hetionet|optimuskg`).

## Repository layout

**57 Python modules at the repo root**, grouped by role (each file has a one-line
docstring):

- **Agent core / interface** — `agent.py` (loop), `llm.py` (Ollama↔Claude adapter),
  `schemas.py` (Pydantic output models), `mcp_server.py` (substrate over MCP, 3 tiers),
  `specialist.py` (Claude-backed skill executor).
- **Knowledge graph (domain)** — `kg_memory.py` (typed traversal), `kg_schema.py`
  (reified-association types), `kg_writer.py` (agent's writable KG), `entity_norm.py`
  + `gene_norm.py` (normalization), `novelty.py`.
- **ML/method KG layer** — `ml_schema.py`, `ml_seed.py`, `ml_ingest.py`, `method_select.py`.
- **Memory** — `memory.py` (episodic), `semantic_memory.py`, `session_journal.py`,
  `briefing.py` (warm start).
- **Literature / retrieval** — `deep_search.py`, `net.py`, `refresh_stale.py`,
  `misc_research.py`.
- **Hypothesis / experiment / campaign** — `hypothesis_tools.py`, `idea.py`,
  `campaign.py`, `provenance.py`, `validity.py`, `scaling.py`.
- **Confidence / evidence / verification** — `confidence.py`, `calibration.py`,
  `beliefs.py`, `critic.py`, `eval_critic.py`, `deadends.py`, `serendipity.py`.
- **Collaboration / substrate ops** — `contribute.py`, `subscriptions.py`,
  `store_lock.py`, `tool_ledger.py`, `lab_profile.py`, `coverage.py`,
  `research_story.py`, `scaffold.py`.
- **Evaluation** — `biology_evals.py` (benchmark harness entry point) + the `evals/`
  package (`hypothesis_generation`, `literature_grounding`, `_scorer` with bootstrap CIs
  and the multi-vote judge, `_dataset`). Measures the *LLM backend's* biomedical capability
  — the ceiling the agent is bounded by — not just the agent's own claims (ADR-0062/0063).

**Directories:**

- `docs/decisions/` — 63 Architecture Decision Records (`0001`–`0063`), one per design
  choice, with stated alternatives and rationale.
- `docs/` — `architecture-overview.md`, `agent-architecture.md`, `kg-schema-spec.md`,
  `related-work.md`, `deployment.md`, `diagrams/`.
- `lab-standard/` — an onboarding playbook (`START-HERE.md`, `new-project.md`,
  `conform-project.md`, workflow docs) plus `templates/`.
- `hypotheses/`, `experiments/`, `campaigns/`, `reports/` — research artifacts (empty until a
  member adds their own; the synthetic t2d-ad/H003 demos were removed).
- `data/` (`external`, `processed`, `specialist_workspace`, `eval_datasets/` — the only
  version-controlled data: hand-labeled eval ground truth), `results/evals/` (per-run
  benchmark dumps, gitignored), `memory/` (`sessions`, `tool_ledgers`), `seeds/`,
  `profiles/`, `reports/`, `src/utils/`, `external/scientific-agent-skills/`, `.claude/hooks/`.

## State

- Git: `main`, ~150 commits, private GitHub remote. Work is tracked as PRs (most recent
  merged `#84`; the biology eval harness is landing via `#85`). ADRs run to `0063`.
- No seeded experiments — the synthetic demos (t2d-ad campaign, `H001`/`H002`, and the H003
  substrate-lift benchmark) were removed so the brain starts clean.
- The last ~10 PRs added: belief lifecycle, calibration self-audit, member/project
  subscriptions, a negative-knowledge/dead-end store, a per-lab prior-work profile,
  a coverage/knowledge-gap map, presentation docs + diagrams, and a backend-agnostic
  biology evaluation harness (ADR-0062) with an eval-driven-development case study
  (ADR-0063).

## Where to start reading

- `AGENTS.md` — the intended entry point for an agent opening the repo; routes to the
  `lab-standard/` playbook by intent.
- `README.md` — what it does, setup, run commands.
- `docs/decisions/` — the rationale trail behind each design choice.
- `docs/architecture-overview.md` — a diagrammed walkthrough of the modules.

## Run

```sh
ollama pull qwen3:14b
pip install -r requirements.txt
export KG_BACKEND=hetionet
python agent.py "How are Crohn's disease and ulcerative colitis connected?"   # single-shot
python agent.py                                                               # persistent REPL
```
