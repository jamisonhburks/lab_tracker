# ADR-0026: Pydantic validation + retry on the structured-output boundary

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The flakiest part of an LLM agent is the parse boundary: every structured-output call
did `json.loads(resp.text)` inside a bare try/except. Constrained decoding (Ollama
`format` / Anthropic `output_config`) makes valid output *likely* but not guaranteed —
the local 14B still occasionally emits a slightly-off reply (missing field, wrong type,
a stray code fence), which crashed or silently dropped the result. We considered whether
a framework (LangChain/LangGraph) was warranted and concluded it was overkill and
against the project's transparency/minimal-deps ethos — but a *targeted* boundary
hardening was worth it.

## Decision
Add **`schemas.py`** (Pydantic models for the 6 structured outputs) and **`llm.parse()`**:
it keeps the existing hand-written JSON schema driving **constrained decoding**
(unchanged — the proven path), and adds a validation layer that
`model_cls.model_validate_json(...)` the result, **retrying on failure** by feeding the
validation error back to the model. Returns a validated Pydantic instance. Also strips
stray markdown code fences before parsing. The 6 call sites (agent ×4, critic, campaign)
now use `llm.parse(msgs, SCHEMA, Model)` instead of raw `json.loads`.

We deliberately did NOT: adopt a framework, replace constrained decoding with
Pydantic-derived schemas (avoids the `$ref`/`$defs` incompatibility with Ollama's
grammar-constrained decoding), or send anything off-machine.

## Rationale & evidence
- **Verified** the four hardening behaviors on `llm.parse`: broken JSON → retry; valid
  JSON missing a required field → retry; a fenced reply → fence-stripped + validated;
  **type coercion** (`sample_size: "250"` → `int 250`). All 6 rewired modules import.
- **Proportionate, ethos-aligned**: one small, stable, widely-used dependency
  (pydantic 2), no hidden control flow, no cloud tracing, decoding path untouched — so
  the tool-ledger/provenance auditability is fully preserved.

## Consequences
- The "model returned slightly-off JSON" failure class is caught and corrected instead
  of crashing or silently dropping data; types are coerced at the boundary.
- Pydantic models are the single validation authority; the inline JSON schemas remain the
  decoding contract (kept adjacent to their call sites).
- Frameworks (LangGraph) remain deferred until/unless unattended, crash-resumable
  autonomous runs justify them (see the discussion behind this ADR).
