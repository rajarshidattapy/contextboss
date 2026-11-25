# contextboss-mcp

MCP server exposing the ContextBoss context layer to any MCP-capable agent
(Claude Code, Codex, Claude Desktop, ...). Tools:

`context_add`, `context_search`, `context_get`, `context_update`,
`context_delete`, `context_compact`, `context_assemble`, `context_inspect`,
`context_stats`

Run over stdio:

```bash
pip install -e .
contextboss-mcp                                   # store: ~/.contextboss/context.db
CONTEXTBOSS_DB=/path/to.db contextboss-mcp        # custom store
```

Claude Code: `claude mcp add contextboss -- contextboss-mcp`
Codex: see `integrations/codex` in the repository root.

The server stores its own context entries. It never reads or modifies the
client's conversation history.
