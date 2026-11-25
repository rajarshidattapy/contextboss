"""ContextBoss MCP server: 9 tools over stdio, backed by a ContextManager.

Configuration via environment:
  CONTEXTBOSS_DB       SQLite path (default ~/.contextboss/context.db), ":memory:" allowed
  CONTEXTBOSS_BUDGET   token budget for context_assemble (default 8000)
  CONTEXTBOSS_RESERVE  output reserve for context_assemble (default 1000)
"""
from __future__ import annotations

import json
import os
from typing import Any

from contextboss import ContextManager
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("contextboss")

_manager: ContextManager | None = None


def get_manager() -> ContextManager:
    global _manager
    if _manager is None:
        db = os.environ.get("CONTEXTBOSS_DB") or os.path.join(
            os.path.expanduser("~"), ".contextboss", "context.db"
        )
        if db != ":memory:":
            os.makedirs(os.path.dirname(db), exist_ok=True)
        _manager = ContextManager(
            db,
            budget=int(os.environ.get("CONTEXTBOSS_BUDGET", "8000")),
            output_reserve=int(os.environ.get("CONTEXTBOSS_RESERVE", "1000")),
        )
    return _manager


def _entry_json(e: Any) -> str:
    return json.dumps(e.to_dict(), indent=2)


@mcp.tool()
def context_add(
    content: str,
    namespace: str = "default",
    tags: list[str] | None = None,
    provenance: str = "",
    tier: str = "memory",
    pinned: bool = False,
    importance: float = 1.0,
) -> str:
    """Store a piece of context. tier: system/task/memory/retrieval. Pinned entries
    always survive assembly. Returns the stored entry as JSON, including its id."""
    e = get_manager().add(
        content, namespace=namespace, tags=tags, provenance=provenance,
        tier=tier, pinned=pinned, importance=importance,
    )
    return _entry_json(e)


@mcp.tool()
def context_search(
    query: str = "",
    namespace: str | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> str:
    """Full-text search over stored context, ranked by relevance. Filters:
    namespace, tags (must all match). Returns JSON list of entries."""
    entries = get_manager().search(query, namespace=namespace, tags=tags, limit=limit)
    return json.dumps([e.to_dict() for e in entries], indent=2)


@mcp.tool()
def context_get(entry_id: str) -> str:
    """Fetch one entry by id. Returns the entry JSON, or an error object."""
    e = get_manager().get(entry_id)
    if e is None:
        return json.dumps({"error": f"no such entry: {entry_id}"})
    return _entry_json(e)


@mcp.tool()
def context_update(
    entry_id: str,
    content: str | None = None,
    namespace: str | None = None,
    tags: list[str] | None = None,
    provenance: str | None = None,
    tier: str | None = None,
    pinned: bool | None = None,
    importance: float | None = None,
) -> str:
    """Update an entry. Bumps its version; the old version stays in history."""
    try:
        e = get_manager().update(
            entry_id, content, namespace=namespace, tags=tags,
            provenance=provenance, tier=tier, pinned=pinned, importance=importance,
        )
    except KeyError:
        return json.dumps({"error": f"no such entry: {entry_id}"})
    return _entry_json(e)


@mcp.tool()
def context_delete(entry_id: str) -> str:
    """Hard-delete an entry: the entry, its search index rows and its whole
    version history are removed. Returns {"deleted": true|false}."""
    return json.dumps({"deleted": get_manager().delete(entry_id)})


@mcp.tool()
def context_compact(entry_id: str, target_tokens: int | None = None) -> str:
    """Summarize an entry down to target_tokens (default: half its size),
    keeping version history. Returns the updated entry."""
    try:
        e = get_manager().compact(entry_id, target_tokens)
    except KeyError:
        return json.dumps({"error": f"no such entry: {entry_id}"})
    return _entry_json(e)


@mcp.tool()
def context_assemble(
    query: str = "",
    system: str | None = None,
    task: str | None = None,
    namespace: str | None = None,
    budget: int | None = None,
    output_reserve: int | None = None,
) -> str:
    """Assemble a window-safe prompt from stored context. Pinned entries rank
    first; with a query, memory/retrieval entries rank by relevance. The result
    never exceeds budget - output_reserve. Returns JSON with the rendered text,
    token usage per tier, and the decision log (what got in, shrunk or dropped)."""
    ctx = get_manager().assemble(
        query, system=system, task=task, namespace=namespace,
        budget=budget, output_reserve=output_reserve,
    )
    return json.dumps(
        {
            "text": ctx.render(),
            "total_tokens": ctx.total_tokens,
            "window": ctx.window,
            "usage": [
                {"tier": u.tier.label, "allocated": u.allocated, "used": u.used}
                for u in ctx.usage
            ],
            "decisions": [
                {
                    "item_id": d.item_id, "tier": d.tier.label, "action": d.action,
                    "tokens": d.tokens, "reason": d.reason, "preview": d.preview,
                }
                for d in ctx.decisions
            ],
        },
        indent=2,
    )


@mcp.tool()
def context_inspect(entry_id: str) -> str:
    """Inspect an entry: full metadata plus its version history (version numbers)."""
    try:
        return json.dumps(get_manager().inspect(entry_id), indent=2)
    except KeyError:
        return json.dumps({"error": f"no such entry: {entry_id}"})


@mcp.tool()
def context_stats(namespace: str | None = None) -> str:
    """Store statistics: entry/token counts, pinned count, per-namespace and
    per-tier breakdowns."""
    return json.dumps(get_manager().stats(namespace=namespace), indent=2)


def main() -> None:
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "serve" and "--http" in sys.argv:
        port = 8787
        host = "127.0.0.1"
        if "--port" in sys.argv:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        if "--host" in sys.argv:
            host = sys.argv[sys.argv.index("--host") + 1]
        http_main(host, port)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "install":
        sys.argv = [sys.argv[0]] + sys.argv[1:]
        from .install import main as install_main

        install_main()
        return
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()


# -- ChatGPT connector-style aliases (deep research expects search/fetch) -------

@mcp.tool()
def search(query: str) -> str:
    """ChatGPT connector-style search: returns {"results": [{id, title, text, url}]}.
    Thin alias over context_search for custom MCP apps that require it."""
    entries = get_manager().search(query, limit=10)
    return json.dumps({
        "results": [
            {
                "id": e.id,
                "title": e.content[:60],
                "text": e.content[:400],
                "url": f"contextboss://entries/{e.id}",
            }
            for e in entries
        ]
    })


@mcp.tool()
def fetch(id: str) -> str:
    """ChatGPT connector-style fetch: returns the full entry for an id from search."""
    e = get_manager().get(id)
    if e is None:
        return json.dumps({"error": f"no such entry: {id}"})
    return json.dumps({
        "id": e.id,
        "title": e.content[:60],
        "text": e.content,
        "url": f"contextboss://entries/{e.id}",
        "metadata": {"namespace": e.namespace, "tags": e.tags, "version": e.version},
    })


def create_http_app():
    """Streamable-HTTP ASGI app with optional bearer auth.

    Deploy behind HTTPS for Claude Web / ChatGPT custom connectors. When
    CONTEXTBOSS_API_KEYS is set, every request needs Authorization: Bearer <key>.
    """
    import hashlib
    import secrets as _secrets

    raw = os.environ.get("CONTEXTBOSS_API_KEYS", "")
    key_hashes = {
        hashlib.sha256(k.strip().encode()).hexdigest() for k in raw.split(",") if k.strip()
    }

    # Fresh server instance per app: StreamableHTTPSessionManager.run() is
    # single-use, so reusing the module-level `mcp` breaks a second app in the
    # same process (tests, embedders). Tool objects are shareable.
    clone = FastMCP("contextboss")
    clone._tool_manager._tools = dict(mcp._tool_manager._tools)  # mcp 1.x API
    app = clone.streamable_http_app()

    if not key_hashes:
        return app

    class BearerAuth:
        def __init__(self, inner):
            self.inner = inner

        async def __call__(self, scope, receive, send):
            if scope["type"] == "http":
                headers = dict(scope.get("headers") or [])
                token = headers.get(b"authorization", b"").decode().removeprefix("Bearer ").strip()
                digest = hashlib.sha256(token.encode()).hexdigest()
                if not token or not any(
                    _secrets.compare_digest(digest, k) for k in key_hashes
                ):
                    from starlette.responses import JSONResponse

                    resp = JSONResponse({"error": "unauthorized"}, status_code=401)
                    await resp(scope, receive, send)
                    return
            await self.inner(scope, receive, send)

    return BearerAuth(app)


def http_main(host: str = "127.0.0.1", port: int = 8787) -> None:
    import uvicorn

    uvicorn.run(create_http_app(), host=host, port=port)
