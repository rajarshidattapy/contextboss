# Architecture

ContextBoss is a local-first context management layer for LLM agents. One
store, every tool.

## Packages

| Package | Role |
| --- | --- |
| `contextboss-core` (`packages/contextboss-core`, imports as `contextboss`) | The engine: `ContextManager` over SQLite. Entries with provenance, tags, namespaces, tiers (hot/warm/cold), pinning, importance, versioning, FTS5 search, tension detection, compaction, and budgeted context assembly. |
| `contextboss-mcp` (`packages/contextboss-mcp`) | MCP server over the core. stdio for Claude Code / Desktop / Codex (`contextboss-mcp`), streamable-HTTP for Claude Web and ChatGPT connectors (`contextboss-mcp serve --http`), including the ChatGPT `search`/`fetch` tool contract. |
| `contextboss-api` (`packages/contextboss-api`) | FastAPI REST surface (`/v1`) for anything that is not an MCP client: CRUD, search, compact, inspect, assemble, stats, and sync endpoints. Bearer auth via `CONTEXTBOSS_API_KEYS`. |
| `apps/dashboard` | Next.js dashboard over the REST API: stats, search, tensions, versions, one-click compaction, assemble playground. |

## Data flow

```
Claude Code / Codex / Claude Desktop        Claude Web / ChatGPT
        | stdio MCP                               | streamable HTTP MCP
        v                                         v
+----------------------+        +--------------------------------------+
|   contextboss-mcp    |        |   contextboss-api (REST /v1)         |
+----------------------+        +--------------------------------------+
        |                                         |
        +----------------> contextboss-core <-----+
                        (SQLite, single file)
                                 ^
                                 | HTTP
                          apps/dashboard
```

Every surface reads and writes the same store, so context added from Claude
Code is searchable from ChatGPT and visible in the dashboard.

## Key design decisions

- **Local-first SQLite**: zero services to run; FTS5 gives instant search;
  the whole store is one file you can back up or sync (`/v1/sync/*`).
- **Provenance on every entry**: who said it, when, from which tool. Assembly
  prefers fresh, high-importance, pinned entries; inspection reports tensions
  (contradictions, staleness, duplicates) instead of silently merging.
- **Budgeted assembly**: `assemble()` packs system prompt, task, and ranked
  entries into a token budget with an output reserve, degrading gracefully by
  tier (hot -> warm -> cold) and compacting oversized entries.
- **Bearer keys hashed at rest**: `CONTEXTBOSS_API_KEYS` values are
  whitespace-stripped and sha256-hashed, compared with `secrets.compare_digest`.
- **mcp SDK pinned `<2`**: v2 renames `FastMCP`; the pin keeps the stdio and
  HTTP transports stable.

## Deployment

- Local: `pip install` the packages; stdio MCP needs nothing else.
- Server: `docker compose up` runs the REST API; the `https` profile adds
  Caddy with automatic TLS for web connectors.
