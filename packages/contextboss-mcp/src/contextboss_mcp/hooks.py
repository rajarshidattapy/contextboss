"""Agent hooks: session snapshots and context injection.

These read hook events from stdin (JSON) and act on the ContextBoss store only.
They never write to the client's transcript or settings: session history belongs
to the provider, snapshots live as our own context entries.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from contextboss import ContextManager


def _manager() -> ContextManager:
    db = os.environ.get("CONTEXTBOSS_DB") or os.path.join(
        os.path.expanduser("~"), ".contextboss", "context.db"
    )
    if db != ":memory:":
        os.makedirs(os.path.dirname(db), exist_ok=True)
    return ContextManager(db)


def _read_event() -> dict[str, Any]:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return {}


def session_start() -> int:
    """Claude Code SessionStart hook: inject the most relevant stored context.

    Prints the SessionStart hook JSON with additionalContext on stdout.
    """
    mgr = _manager()
    entries = mgr.list(limit=8)
    lines = [
        f"- [{e.namespace}{' pinned' if e.pinned else ''}] {e.content[:200]}"
        for e in entries
    ]
    context = (
        "ContextBoss stored context (persistent across sessions):\n" + "\n".join(lines)
        if lines
        else ""
    )
    out = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }
    print(json.dumps(out))
    return 0


def snapshot() -> int:
    """PreCompact / Stop hook: store a snapshot of the session as our own entry.

    Records session metadata, and when the event carries a readable transcript
    path, a compacted digest of its tail. The transcript itself is only read,
    never modified.
    """
    event = _read_event()
    mgr = _manager()
    session_id = str(event.get("session_id") or "unknown")
    cwd = str(event.get("cwd") or "")
    tail = ""
    transcript = event.get("transcript_path")
    if transcript and os.path.isfile(transcript):
        try:
            with open(transcript, errors="replace") as fh:
                lines = fh.readlines()[-50:]
            texts = []
            for line in lines:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = row.get("message", {}).get("content") if isinstance(row, dict) else None
                if isinstance(content, str):
                    texts.append(content)
                elif isinstance(content, list):
                    texts.extend(
                        c.get("text", "") for c in content
                        if isinstance(c, dict) and c.get("type") == "text"
                    )
            joined = "\n".join(t for t in texts if t.strip())
            if joined.strip():
                tail = mgr.summarizer(joined, 300)
        except OSError:
            tail = ""
    body = f"Session snapshot for {session_id} (cwd: {cwd})."
    if tail:
        body += f"\n\nTail digest:\n{tail}"
    mgr.add(
        body,
        namespace="session-snapshots",
        tags=["snapshot", f"session:{session_id}"],
        provenance=f"claude-code session {session_id}",
        tier="memory",
        importance=0.8,
        metadata={"session_id": session_id, "cwd": cwd},
    )
    return 0


HOOKS = {"session-start": session_start, "snapshot": snapshot}


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    hook = HOOKS.get(name)
    if hook is None:
        print(f"usage: contextboss-hook [{'|'.join(HOOKS)}]", file=sys.stderr)
        sys.exit(2)
    sys.exit(hook())


if __name__ == "__main__":
    main()
