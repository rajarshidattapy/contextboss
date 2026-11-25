"""Streamable-HTTP transport: real uvicorn server, real MCP client, auth on/off."""
import asyncio
import json
import threading
import time

import pytest
import uvicorn
from contextboss_mcp.server import create_http_app
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PORT = 18931


@pytest.fixture
def http_server(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTBOSS_DB", str(tmp_path / "http.db"))
    monkeypatch.delenv("CONTEXTBOSS_API_KEYS", raising=False)
    import contextboss_mcp.server as srv

    srv._manager = None  # fresh manager per server
    config = uvicorn.Config(create_http_app(), host="127.0.0.1", port=PORT, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{PORT}/mcp"
    server.should_exit = True
    thread.join(timeout=5)
    srv._manager = None


async def _session(url, headers=None):
    async with streamablehttp_client(url, headers=headers or {}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return s


def test_http_roundtrip(http_server):
    async def run():
        async with streamablehttp_client(http_server) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = {t.name for t in (await s.list_tools()).tools}
                assert {"context_add", "context_search", "search", "fetch"} <= tools
                res = await s.call_tool("context_add", {"content": "http stored fact"})
                eid = json.loads(res.content[0].text)["id"]
                res = await s.call_tool("fetch", {"id": eid})
                doc = json.loads(res.content[0].text)
                assert doc["text"] == "http stored fact"
                res = await s.call_tool("search", {"query": "http stored"})
                assert json.loads(res.content[0].text)["results"][0]["id"] == eid

    asyncio.run(run())


AUTH_PORT = 18932


def test_http_auth(tmp_path, monkeypatch):
    """With CONTEXTBOSS_API_KEYS set, no token -> connection refused, token -> ok."""
    monkeypatch.setenv("CONTEXTBOSS_DB", str(tmp_path / "auth.db"))
    monkeypatch.setenv("CONTEXTBOSS_API_KEYS", "sekret")
    import contextboss_mcp.server as srv

    srv._manager = None
    config = uvicorn.Config(create_http_app(), host="127.0.0.1", port=AUTH_PORT,
                            log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    url = f"http://127.0.0.1:{AUTH_PORT}/mcp"

    async def try_session(headers):
        async with streamablehttp_client(url, headers=headers) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return True

    async def unauthenticated():
        try:
            await try_session({})
        except Exception:
            return False
        return True

    assert asyncio.run(unauthenticated()) is False
    assert asyncio.run(try_session({"Authorization": "Bearer sekret"})) is True
    server.should_exit = True
    thread.join(timeout=5)
    srv._manager = None


def test_connector_aliases_unit(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTEXTBOSS_DB", str(tmp_path / "alias.db"))
    import contextboss_mcp.server as srv

    srv._manager = None
    add = srv.context_add.fn if hasattr(srv.context_add, "fn") else srv.context_add
    search = srv.search.fn if hasattr(srv.search, "fn") else srv.search
    fetch = srv.fetch.fn if hasattr(srv.fetch, "fn") else srv.fetch
    eid = json.loads(add(content="alias check fact"))["id"]
    assert json.loads(search(query="alias check"))["results"][0]["id"] == eid
    doc = json.loads(fetch(id=eid))
    assert doc["metadata"]["version"] == 1
    assert "error" in json.loads(fetch(id="missing"))
    srv._manager = None
