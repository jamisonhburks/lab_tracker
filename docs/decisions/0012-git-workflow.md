# ADR-0012: Git workflow — private, no co-author, small PRs

- **Date:** 2026-08-12
- **Status:** Accepted

## Context
Once the prototype was working, we set up version control to track changes and
share with collaborators.

## Decision
- **Private** GitHub repository.
- Commits authored by the user **only** — no `Co-Authored-By` trailer.
- **Small, contained, reviewable PRs** on feature branches; merge to `main`.
- Generated run-data (`memory/`, `data/`) is gitignored to keep diffs clean.

## Rationale & evidence
- Clean, trackable history with sole authorship attribution.
- Contained PRs keep each change auditable and reviewable — which, with detailed
  commit/PR messages, forms the audit trail this decision log now completes.

## Consequences
- Stacked PRs need care: deleting a branch that another PR is stacked on
  auto-closes the child (learned when PR #3's base was deleted → reopened as #4).
- This ADR log (`docs/decisions/`) + `CHANGELOG.md` extend the audit trail with the
  *reasoning and evidence* that commit messages summarize but don't fully carry.
