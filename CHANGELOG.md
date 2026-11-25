# Changelog

All notable changes to ContextBoss. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2026-11-25

### Added
- **Benchmark harness** (`bench/`): key-fact recall, window compliance, and
  overhead metrics vs naive truncation and fixed allocation baselines.
  ContextBoss: 100% recall within budget; baselines 25-92%.
- **REST API** (`packages/contextboss-api`): FastAPI `/v1` with contexts
  CRUD, search, compact, inspect, assemble, stats, and sync
  (changes/export/import). Bearer auth, localhost by default.
- **Web connectors**: streamable-HTTP MCP transport
  (`contextboss-mcp serve --http`) with optional bearer auth, plus
  ChatGPT-style `search`/`fetch` tool aliases.
- **Dashboard** (`apps/dashboard`): Next.js UI for stats, search, tensions,
  version history, compaction, and an assemble playground.
- **Launch packaging**: Dockerfile + docker-compose with optional Caddy HTTPS
  profile, architecture doc, release guide.

## [0.1.0] - 2026-11-25

### Added
- **Core engine** (`contextboss-core`): SQLite-backed `ContextManager` with
  provenance, tags, namespaces, tiers, pinning, importance, versioning, FTS5
  search, tension detection, compaction, and budgeted assembly.
- **MCP server** (`contextboss-mcp`): nine stdio tools
  (`context_add/search/get/update/delete/compact/assemble/inspect/stats`)
  for Claude Code, Claude Desktop, and Codex.
- **CLI**: `contextboss add/search/get/inspect/assemble/stats/compact`.
- **GitHub Action** (`actions/remember`): persist CI findings into the store.
- CI: ruff, mypy, pytest on 3.10-3.12, reproducible wheel builds.
