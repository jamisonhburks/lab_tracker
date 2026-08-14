"""net — resilient HTTP for the live-retrieval call sites.

Every external fetch in the project (PubMed E-utilities, arXiv API, Monarch / Hetionet
dumps, HGNC) goes through here, so a transient blip — NCBI rate-limiting without an API
key, a dropped connection, a 503 — retries with exponential backoff instead of aborting a
run mid-way. Retries are limited to genuinely transient failures (connection errors,
timeouts, and HTTP 429/5xx); a 404 or a malformed URL fails fast.

Uses `tenacity` if installed (exponential backoff + jitter); otherwise falls back to an
equivalent bounded manual loop, so the dependency stays OPTIONAL and offline/repro runs
never hard-require it.

Two shapes cover every call site:
  - urlopen_retry(url_or_req)  -> an open response, for `with ... as r: copyfileobj(r, out)`
                                  (streaming a large dump straight to disk)
  - fetch_bytes / fetch_text   -> the whole body, for parse-in-memory (JSON / XML / text)
"""
import random
import time
import urllib.error
import urllib.request

ATTEMPTS = 4                                   # total tries (1 initial + 3 retries)
_MAX_WAIT = 8.0
_TRANSIENT_HTTP = {429, 500, 502, 503, 504}    # retry these; a 404/400 is permanent


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in _TRANSIENT_HTTP
    # URLError (DNS/refused), socket timeout, reset — all transient
    return isinstance(exc, (urllib.error.URLError, TimeoutError, ConnectionError, OSError))


def _as_request(url_or_req):
    if isinstance(url_or_req, urllib.request.Request):
        return url_or_req
    return urllib.request.Request(url_or_req, headers={"User-Agent": "curl"})


def _backoff(attempt: int) -> None:
    time.sleep(min(_MAX_WAIT, 0.5 * (2 ** attempt)) * (0.5 + random.random()))


try:
    from tenacity import (Retrying, retry_if_exception, stop_after_attempt,
                          wait_exponential_jitter)
    _HAVE_TENACITY = True
except Exception:                              # tenacity optional — manual fallback below
    _HAVE_TENACITY = False


def _run(fn, attempts: int):
    """Call fn() with retry-on-transient-error. Same policy with or without tenacity."""
    if _HAVE_TENACITY:
        retryer = Retrying(
            stop=stop_after_attempt(attempts),
            wait=wait_exponential_jitter(initial=0.5, max=_MAX_WAIT),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        return retryer(fn)
    last = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:               # noqa: BLE001 — re-raised below
            last = exc
            if not _is_retryable(exc) or attempt == attempts - 1:
                raise
            _backoff(attempt)
    raise last                                 # unreachable, for type-checkers


def urlopen_retry(url_or_req, timeout: float = 60, attempts: int = ATTEMPTS):
    """Return an OPEN response (retrying the connect). Use as a context manager for
    streaming a large body to disk; a mid-stream read failure is not retried."""
    req = _as_request(url_or_req)
    return _run(lambda: urllib.request.urlopen(req, timeout=timeout), attempts)


def fetch_bytes(url_or_req, timeout: float = 60, attempts: int = ATTEMPTS) -> bytes:
    """Fetch and fully read the body as bytes (connect AND read are retried)."""
    req = _as_request(url_or_req)

    def _do():
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    return _run(_do, attempts)


def fetch_text(url_or_req, timeout: float = 60, encoding: str = "utf-8",
               errors: str = "replace", attempts: int = ATTEMPTS) -> str:
    """Fetch and decode the body as text."""
    return fetch_bytes(url_or_req, timeout=timeout, attempts=attempts).decode(encoding, errors)
