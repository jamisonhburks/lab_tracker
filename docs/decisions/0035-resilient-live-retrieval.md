# ADR-0035: Resilient live retrieval (`net.py`, tenacity-optional)

- **Date:** 2026-08-14
- **Status:** Accepted

## Context
The project makes many external fetches — PubMed E-utilities (`search_pubmed`,
`_fetch_articles`, novelty co-mention counts, the critic's abstract fetch), the arXiv API
(ML seed authorship), and large KG dumps (Monarch, Hetionet, HGNC). Each was a bare
`urllib.request.urlopen(...)`, so any transient failure aborted the work: NCBI rate-limits
un-keyed clients to ~3 req/s (novelty fires several counts in a row and gets throttled),
arXiv and the Dataverse-style hosts intermittently 503, and connections drop. `novelty.py`
had grown its own ad-hoc retry loop; nothing else had any. The failure modes were transient
and retryable, but the code treated them as fatal.

## Decision
Add one shared helper, **`net.py`**, that every live-retrieval call site routes through:

- `urlopen_retry(url_or_req)` → an open response, for streaming a large dump to disk
  (`with ... as r: copyfileobj(r, out)`).
- `fetch_bytes` / `fetch_text` → the whole body, for parse-in-memory (JSON / XML / text).

Retries are limited to **genuinely transient** failures — connection errors, timeouts, and
HTTP `429/500/502/503/504`; a `404`/`400` fails fast. Backoff is exponential with jitter.
`net.py` uses **tenacity if installed** (`wait_exponential_jitter`, `stop_after_attempt`,
`retry_if_exception`) and otherwise runs an **equivalent manual loop with the same policy**,
so tenacity stays an *optional* dependency and offline/reproducibility runs never hard-require
a network library.

Swapped every call site (`agent.py`, `novelty.py`, `critic.py`, `ml_seed.py`, `gene_norm.py`,
`kg_memory.py` Hetionet+Monarch) onto the helper and deleted `novelty.py`'s bespoke loop.

## Rationale & evidence
- **One policy, one place.** A single retry policy beats seven inconsistent ones; the
  novelty module's hand-rolled loop is gone. Call sites read the same as before — a string
  URL or a `Request` in, bytes/text/response out.
- **Retry only what's transient.** Retrying a 404 or a malformed query wastes time and hides
  bugs; the exception predicate distinguishes transient (retry) from permanent (fail fast).
- **Optional dependency, graceful fallback.** The manual loop mirrors tenacity's behavior so
  the two are interchangeable — important given the local-first, minimal-dependency posture.
- **Verified both paths.** With tenacity: retry-then-succeed (3rd call), fail-fast on 404 (1
  call), retry on 503, and reraise-after-exhaustion all pass. Forcing `_HAVE_TENACITY=False`:
  identical retry-then-succeed and 404 fail-fast. All touched modules import clean; no raw
  `urlopen` remains outside `net.py`.

## Consequences
- A throttled PubMed burst or a flaky arXiv/Monarch response now backs off and recovers
  instead of aborting a run; the novelty check keeps its meaningful `-1` ("could not query")
  vs a real `0`.
- Stage-4 bulk ingestion (ADR-0036) inherits this resilience for free — it fetches through
  the same helper.
- `tenacity>=8.0` added to `requirements.txt` under an explicit "optional — graceful
  fallback" note. Not applied to mid-stream read failures on huge streamed downloads (only
  the connect is retried there); a resumable-download layer is possible future work.
