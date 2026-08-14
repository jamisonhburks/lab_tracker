# ADR-0042: Synthesize-before-clear/compact (Claude Code hooks)

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The session journal (ADR-0041) keeps the personal tier alive during a session and synthesizes
on the research-agent REPL's `quit`. But a lab member working *through Claude Code* loses their
in-progress thinking at a different boundary: `/clear` and `/compact` (manual or automatic).
Compaction summarizes and drops detail; `/clear` wipes context entirely. Nothing prompted the
user to capture the session's hypotheses/experiments/findings before that happened.

## Decision
Add project **Claude Code hooks** (`.claude/settings.json` + `.claude/hooks/synthesize_session.py`)
that intervene at those boundaries:

- **`PreCompact` (manual `/compact`)** — `/compact` *can* be blocked, so the first attempt is
  intercepted with `{"continue": false}` and a **prompt**: "synthesize the session first?" The
  user can then ask the model to synthesize *with full context still present* (the high-quality
  path), then re-run `/compact` to proceed — or re-run immediately to skip. A per-session marker
  makes it prompt **once**, so it never loops.
- **`PreCompact` (auto-compact)** — can't reasonably block the user's flow, so it **heuristically
  synthesizes** the transcript into the session journal (candidate hypotheses/experiments/
  findings, checkpointed with provenance) and notes what it captured — nothing is silently lost.
- **`SessionEnd` (`/clear`)** — a session end can't be blocked, so it **synthesizes the
  transcript now** and surfaces a `systemMessage` summary + promotion review.

"Synthesize" reuses `session_journal`: it distils the conversation into the PERSONAL journal and
runs `promotion_review()` to flag what's ready to climb to shared WIP.

## Rationale & evidence
- **Prompt on the destructive, manual action; auto-preserve on the ones you can't stop.** The
  user asked to be *prompted* — so manual `/compact` blocks-and-asks (the only event that can),
  while auto-compact and `/clear` fall back to a safe heuristic synthesis so a lost session still
  leaves a trail. Best of both: consent where possible, safety-net everywhere.
- **Full-context synthesis is the good one.** Blocking manual `/compact` lets the *model* do the
  synthesis before context is summarized away; the transcript-heuristic path (auto/clear) is the
  fallback, honestly labelled as heuristic.
- **Reuses the journal + tier model.** Everything lands in the PERSONAL tier (`memory/` is
  gitignored — local, private); promotion to shared WIP stays a deliberate, recommended step.
- **Verified**: manual PreCompact with no marker returns `continue:false` + the prompt; second
  call returns "proceeding"; `SessionEnd` synthesizes 3 components from a fake transcript and
  routes them (hypothesis→YAML, experiment→dirs, finding→contribute). `settings.json` is valid.

## Consequences
- A lab member's Claude Code session now gets a chance to capture its research before `/clear`
  or `/compact` discards it — the last-mile of "never lose in-progress thinking."
- Hooks are **committed** so the behavior travels with the repo, but Claude Code requires the
  user to **review/approve** hooks before they run (a security feature) — they won't fire until
  trusted, and they never affect an already-running session.
- Follow-up: the manual-`/compact` prompt could offer a one-word `/synthesize` slash command to
  trigger the full-context synthesis, rather than a free-text ask.
