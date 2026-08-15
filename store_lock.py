"""store_lock — serialize writes to the shared substrate files.

In the shared HTTP deployment (many lab members → one server on the cluster, over the same
repo on a shared filesystem), the append-only logs and the read-modify-write curated KG can be
touched concurrently — by the async server handling parallel requests, or by a stray local
writer. This wraps writes in a POSIX advisory file lock (an `flock` on a sidecar `.lock`), so:

  - append_jsonl(path, obj)  — locked append (contribution log, misc-findings log)
  - critical(path)           — a lock context for a load→modify→save section (kg_writer)

Advisory locks on a sidecar file, not the data file, so readers are never blocked. No-op-safe
where `fcntl` is unavailable (non-POSIX) — the single-process stdio default doesn't need it.
"""
import contextlib
import json
from pathlib import Path

try:
    import fcntl
    _HAVE_FCNTL = True
except Exception:                                  # non-POSIX — locking becomes a no-op
    _HAVE_FCNTL = False


@contextlib.contextmanager
def _flock(lockpath: str):
    if not _HAVE_FCNTL:
        yield
        return
    p = Path(lockpath)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a+") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def critical(path) -> contextlib.AbstractContextManager:
    """Hold an exclusive lock for a load→modify→save critical section on `path`."""
    return _flock(str(path) + ".lock")


def append_jsonl(path, obj) -> None:
    """Append one JSON object as a line, under an exclusive lock (safe for concurrent writers)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _flock(str(path) + ".lock"), path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")
