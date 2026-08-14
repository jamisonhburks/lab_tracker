#!/usr/bin/env python3
"""synthesize_session — Claude Code hook: prompt/synthesize before clear or compact.

Wired (see .claude/settings.json) to:
  - PreCompact  matcher "manual"  — user ran /compact. We can BLOCK, so the FIRST attempt is
                                    intercepted with a PROMPT: "synthesize the session first?"
                                    (once per session; re-running /compact then proceeds). This
                                    lets the model synthesize with FULL context before it's lost.
  - PreCompact  matcher "auto"    — automatic compaction (can't reasonably block the user): we
                                    heuristically synthesize the transcript into the session
                                    journal so nothing is lost, and note it.
  - SessionEnd  matcher "clear"   — user ran /clear (can't block a session end): synthesize the
                                    transcript into the journal now, and notify.

"Synthesize" = distil the conversation into the PERSONAL research journal (session_journal):
candidate hypotheses / experiments / findings, checkpointed with provenance, plus a
promotion_review flagging what's ready to climb to shared WIP. The manual-/compact path defers
to the model for a high-quality synthesis; the auto / clear paths do a heuristic pass so a lost
session still leaves a trail.

Output is JSON on stdout ({"continue": ..., "systemMessage": ...}) per the hooks contract.
"""
import json
import os
import sys
from pathlib import Path

PROJ = os.environ.get("CLAUDE_PROJECT_DIR", str(Path(__file__).resolve().parents[2]))


def _stdin() -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def _emit(obj: dict):
    print(json.dumps(obj))
    sys.exit(0)


def _transcript_text(path: str) -> str:
    """Flatten a Claude Code transcript (JSONL) into user+assistant text."""
    out = []
    try:
        for raw in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            msg = obj.get("message") if isinstance(obj, dict) else None
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, str):
                out.append(content)
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        out.append(b.get("text", ""))
    except Exception:
        pass
    return "\n".join(out)


def _synthesize(session_id: str, transcript: str) -> str:
    """Heuristic synthesis of the transcript into the session journal. Returns a summary."""
    sys.path.insert(0, PROJ)
    try:
        import session_journal
    except Exception as err:
        return f"(synthesis unavailable: {err})"
    j = session_journal.SessionJournal(session_id=f"claude-{session_id[:8]}")
    text = _transcript_text(transcript)
    seen, n = set(), 0
    for line in text.splitlines():
        s = line.strip().lstrip("-*#> ").strip()
        if len(s) < 12 or s in seen:
            continue
        if session_journal._classify(s):
            seen.add(s)
            j.note(s, kind="synth")
            n += 1
            if n >= 60:
                break
    j.checkpoint(force=True)
    return f"Synthesized {n} candidate component(s).\n" + j.promotion_review()


def main():
    data = _stdin()
    event = data.get("hook_event_name", "")
    session_id = str(data.get("session_id", "unknown"))
    transcript = data.get("transcript_path", "")
    auto = "--auto" in sys.argv
    marker = Path(f"/tmp/claude-synth-{session_id}.done")

    if event == "PreCompact" and not auto:                 # manual /compact — block once + prompt
        if not marker.exists():
            marker.write_text("prompted")
            _emit({"continue": False,
                   "stopReason": "Synthesize the session before compacting?",
                   "systemMessage": (
                       "⏸ Before compacting — synthesize this session into the research journal "
                       "first?\nAsk me to \"synthesize the session\" and I'll distil the "
                       "hypotheses / experiments / findings with full context and flag what's "
                       "ready for shared WIP. Then run /compact again to proceed — or just run "
                       "/compact again now to skip.")})
        _emit({"systemMessage": "Proceeding with compaction (already prompted to synthesize)."})

    if event == "PreCompact" and auto:                     # auto-compact — synthesize, don't block
        summary = _synthesize(session_id, transcript)
        _emit({"systemMessage": "Auto-compacting — synthesized the session to the journal first.\n"
                                + summary[:500]})

    if event == "SessionEnd":                              # /clear etc. — can't block; synthesize now
        summary = _synthesize(session_id, transcript)
        _emit({"systemMessage": "Session ending — synthesized to the research journal.\n"
                                + summary[:500]})

    _emit({})


if __name__ == "__main__":
    main()
