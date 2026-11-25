"""End-to-end: spawn the real server over stdio and drive all 9 tools.

Synchronous tests wrapping asyncio.run so the suite needs no async plugin.
"""
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
CORE_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "contextboss-core", "src")
)


def server_params(db_path):
    env = dict(os.environ)
    env["CONTEXTBOSS_DB"] = str(db_path)
    env["PYTHONPATH"] = os.pathsep.join([SRC, CORE_SRC, env.get("PYTHONPATH", "")])
    return StdioServerParameters(
        command=sys.executable, args=["-m", "contextboss_mcp"], env=env
    )


async def call(session, tool, **args):
    result = await session.call_tool(tool, args)
    assert not result.isError, f"{tool} failed: {result.content}"
    return json.loads(result.content[0].text)


def test_all_nine_tools(tmp_path):
    async def run():
        async with stdio_client(server_params(tmp_path / "mcp.db")) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = await s.list_tools()
                names = {t.name for t in tools.tools}
                assert names == {
                    "context_add", "context_search", "context_get", "context_update",
                    "context_delete", "context_compact", "context_assemble",
                    "context_inspect", "context_stats",
                    "search", "fetch",  # ChatGPT connector-style aliases
                }

                added = await call(
                    s, "context_add",
                    content="the migration to postgres finished on tuesday",
                    namespace="proj", tags=["db"], provenance="test", pinned=True,
                )
                eid = added["id"]
                assert added["version"] == 1 and added["pinned"] is True

                hits = await call(s, "context_search", query="postgres migration")
                assert hits[0]["id"] == eid

                got = await call(s, "context_get", entry_id=eid)
                assert got["content"].startswith("the migration")

                updated = await call(s, "context_update", entry_id=eid,
                                     content="the postgres migration finished wednesday")
                assert updated["version"] == 2

                long_id = (await call(
                    s, "context_add",
                    content=". ".join(f"detail {i} about the rollout plan" for i in range(80)),
                ))["id"]
                compacted = await call(s, "context_compact", entry_id=long_id,
                                       target_tokens=40)
                assert compacted["tokens"] <= 40

                assembled = await call(s, "context_assemble", query="postgres",
                                       system="sys", task="report status",
                                       budget=800, output_reserve=100)
                assert assembled["total_tokens"] <= assembled["window"]
                assert "sys" in assembled["text"]
                assert assembled["decisions"]

                info = await call(s, "context_inspect", entry_id=eid)
                assert info["versions"] == [1, 2]

                stats = await call(s, "context_stats")
                assert stats["entries"] == 2

                assert (await call(s, "context_delete", entry_id=eid))["deleted"] is True
                assert (await call(s, "context_search", query="postgres")) == []
                assert "error" in await call(s, "context_get", entry_id=eid)
                assert (await call(s, "context_delete", entry_id=eid))["deleted"] is False

    asyncio.run(run())


def test_error_paths(tmp_path):
    async def run():
        async with stdio_client(server_params(tmp_path / "err.db")) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                assert "error" in await call(s, "context_get", entry_id="missing")
                assert "error" in await call(s, "context_update", entry_id="missing",
                                             content="x")
                assert "error" in await call(s, "context_compact", entry_id="missing")
                assert "error" in await call(s, "context_inspect", entry_id="missing")

    asyncio.run(run())


def test_persistence_across_server_restarts(tmp_path):
    async def run():
        params = server_params(tmp_path / "restart.db")
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool("context_add", {"content": "durable fact"})
                return json.loads(res.content[0].text)["id"], params

    async def check(eid, params):
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool("context_get", {"entry_id": eid})
                assert json.loads(res.content[0].text)["content"] == "durable fact"

    eid, params = asyncio.run(run())
    asyncio.run(check(eid, params))
