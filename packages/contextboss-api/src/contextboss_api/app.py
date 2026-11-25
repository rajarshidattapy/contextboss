"""FastAPI app factory. /v1 routes, bearer-key auth (hashed), localhost by default."""
from __future__ import annotations

import hashlib
import os
import secrets
from typing import Any

from contextboss import ContextManager
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field


def _configured_key_hashes() -> set:
    raw = os.environ.get("CONTEXTBOSS_API_KEYS", "")
    return {hashlib.sha256(k.strip().encode()).hexdigest() for k in raw.split(",") if k.strip()}


class AddContext(BaseModel):
    content: str
    namespace: str = "default"
    tags: list[str] = Field(default_factory=list)
    provenance: str = ""
    tier: str = "memory"
    pinned: bool = False
    importance: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateContext(BaseModel):
    content: str | None = None
    namespace: str | None = None
    tags: list[str] | None = None
    provenance: str | None = None
    tier: str | None = None
    pinned: bool | None = None
    importance: float | None = None
    metadata: dict[str, Any] | None = None


class CompactRequest(BaseModel):
    target_tokens: int | None = None


class AssembleRequest(BaseModel):
    query: str = ""
    system: str | None = None
    task: str | None = None
    namespace: str | None = None
    budget: int | None = None
    output_reserve: int | None = None


class ImportRequest(BaseModel):
    entries: list[dict[str, Any]]


def create_app(manager: ContextManager | None = None) -> FastAPI:
    mgr = manager or ContextManager(
        os.environ.get("CONTEXTBOSS_DB")
        or os.path.join(os.path.expanduser("~"), ".contextboss", "context.db")
    )
    key_hashes = _configured_key_hashes()
    app = FastAPI(title="ContextBoss API", version="0.2.0", docs_url="/v1/docs")

    async def auth(request: Request) -> None:
        if not key_hashes:
            return  # open mode: caller must keep this on localhost (see README)
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip()
        if not token:
            raise HTTPException(401, "missing bearer token")
        digest = hashlib.sha256(token.encode()).hexdigest()
        if not any(secrets.compare_digest(digest, k) for k in key_hashes):
            raise HTTPException(403, "invalid API key")

    @app.get("/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": app.version}

    @app.post("/v1/contexts", dependencies=[Depends(auth)], status_code=201)
    async def add_context(body: AddContext) -> dict[str, Any]:
        try:
            e = mgr.add(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return e.to_dict()

    @app.get("/v1/contexts", dependencies=[Depends(auth)])
    async def search_contexts(
        q: str = "", namespace: str | None = None, tag: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        entries = mgr.search(q, namespace=namespace, tags=tag, limit=limit)
        return [e.to_dict() for e in entries]

    @app.get("/v1/contexts/{entry_id}", dependencies=[Depends(auth)])
    async def get_context(entry_id: str) -> dict[str, Any]:
        e = mgr.get(entry_id)
        if e is None:
            raise HTTPException(404, f"no such entry: {entry_id}") from None
        return e.to_dict()

    @app.patch("/v1/contexts/{entry_id}", dependencies=[Depends(auth)])
    async def update_context(entry_id: str, body: UpdateContext) -> dict[str, Any]:
        try:
            e = mgr.update(entry_id, **body.model_dump(exclude_unset=True))
        except KeyError:
            raise HTTPException(404, f"no such entry: {entry_id}") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return e.to_dict()

    @app.delete("/v1/contexts/{entry_id}", dependencies=[Depends(auth)])
    async def delete_context(entry_id: str) -> dict[str, bool]:
        if not mgr.delete(entry_id):
            raise HTTPException(404, f"no such entry: {entry_id}") from None
        return {"deleted": True}

    @app.post("/v1/contexts/{entry_id}/compact", dependencies=[Depends(auth)])
    async def compact_context(entry_id: str, body: CompactRequest) -> dict[str, Any]:
        try:
            return mgr.compact(entry_id, body.target_tokens).to_dict()
        except KeyError:
            raise HTTPException(404, f"no such entry: {entry_id}") from None

    @app.get("/v1/contexts/{entry_id}/inspect", dependencies=[Depends(auth)])
    async def inspect_context(entry_id: str) -> dict[str, Any]:
        try:
            return mgr.inspect(entry_id)
        except KeyError:
            raise HTTPException(404, f"no such entry: {entry_id}") from None

    @app.post("/v1/assemble", dependencies=[Depends(auth)])
    async def assemble(body: AssembleRequest) -> dict[str, Any]:
        ctx = mgr.assemble(
            body.query, system=body.system, task=body.task, namespace=body.namespace,
            budget=body.budget, output_reserve=body.output_reserve,
        )
        return {
            "text": ctx.render(),
            "total_tokens": ctx.total_tokens,
            "window": ctx.window,
            "usage": [
                {"tier": u.tier.label, "allocated": u.allocated, "used": u.used}
                for u in ctx.usage
            ],
            "decisions": [
                {"item_id": d.item_id, "tier": d.tier.label, "action": d.action,
                 "tokens": d.tokens, "reason": d.reason, "preview": d.preview}
                for d in ctx.decisions
            ],
        }

    @app.get("/v1/stats", dependencies=[Depends(auth)])
    async def stats(namespace: str | None = None) -> dict[str, Any]:
        return mgr.stats(namespace=namespace)

    @app.get("/v1/sync/changes", dependencies=[Depends(auth)])
    async def sync_changes(since: float = 0.0, limit: int = 1000) -> dict[str, Any]:
        changed = [e for e in mgr.list(limit=limit) if e.updated_at > since]
        cursor = max((e.updated_at for e in changed), default=since)
        return {"entries": [e.to_dict() for e in changed], "cursor": cursor}

    @app.get("/v1/sync/export", dependencies=[Depends(auth)])
    async def sync_export(namespace: str | None = None) -> dict[str, Any]:
        return {"entries": [e.to_dict() for e in mgr.list(namespace=namespace, limit=1_000_000)]}

    @app.post("/v1/sync/import", dependencies=[Depends(auth)])
    async def sync_import(body: ImportRequest) -> dict[str, int]:
        imported = skipped = 0
        for data in body.entries:
            if mgr.get(str(data.get("id", ""))):
                skipped += 1
                continue
            mgr.restore(data)
            imported += 1
        return {"imported": imported, "skipped_existing": skipped}

    return app
