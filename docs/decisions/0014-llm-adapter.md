# ADR-0014: LLM provider adapter (Ollama ↔ Claude swappable)

- **Date:** 2026-08-13
- **Status:** Accepted

## Context
The system is local-first on Qwen3-14B via Ollama (ADR-0001), but there are good
reasons to sometimes use a frontier model (Claude): much stronger long-horizon
agentic reasoning and cleaner extraction — which would directly reduce the noise
the critic has to catch. The question was how plug-and-play that swap is.

## Options considered
- Hard-code Ollama (status quo) — not swappable.
- Swap by editing the ~4 `ollama.chat` call sites each time — error-prone.
- **A thin adapter** isolating provider differences behind one call.

## Decision
Introduce **`llm.py`**: `chat(messages, tools=None, schema=None) -> Response(text,
tool_calls)`, dispatching to Ollama or Anthropic by `LLM_BACKEND` (default
`ollama`). The 4 call sites (loop, `_consolidate`, `curate_literature`, `critic`)
use `llm.chat`; nothing else in the system knows the provider.

## Rationale & evidence
- ~90% of the system was already model-agnostic; only the model I/O differed
  (tool-call shape, structured-output mechanism, thinking param). The adapter
  normalizes a neutral message format and converts per backend.
- **Verified:** the full Ollama path (tool loop, schema-constrained consolidation,
  critic) runs unchanged through the adapter (agent run-8; critic verdicts).
- The Anthropic backend (adaptive thinking, `output_config.format`, tool_use blocks)
  is implemented **best-effort / untested** here — no SDK or API key in this
  environment; documented as such.
- The real decision is the **privacy trade-off**, not the code: Claude means data
  leaves the machine, forfeiting the on-device privacy that motivated ADR-0001. A
  **hybrid** (Claude for reasoning-heavy non-sensitive steps, local for anything
  touching patient data) is the intended use.

## Consequences
- `LLM_BACKEND=anthropic` + `pip install anthropic` + an API key would run on
  Claude; verify the Anthropic path before relying on it.
- Related external option: the Agent Skills ecosystem (e.g. k-dense-ai's 161
  scientific skills) could serve as a tool/execution layer this orchestration sits
  on top of.
