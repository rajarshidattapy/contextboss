# ContextBoss for Codex

## Quick install

```bash
pip install contextboss-mcp
contextboss-mcp install codex            # run from your project root
```

That:

- appends the `contextboss` server to `~/.codex/config.toml`:

  ```toml
  [mcp_servers.contextboss]
  command = "contextboss-mcp"
  ```

- adds a marked ContextBoss block to your project's `AGENTS.md` so the agent
  knows when to store and recall context

`contextboss-mcp install codex --print` previews without writing. Both writes
are idempotent and preserve existing content.

The store lives at `~/.contextboss/context.db` (override with `CONTEXTBOSS_DB`).
Provider conversation history is never modified; snapshots and context are
ContextBoss's own entries.
