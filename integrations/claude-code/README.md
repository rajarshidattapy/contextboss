# ContextBoss for Claude Code

## Quick install

```bash
pip install contextboss-mcp      # or: pip install -e packages/contextboss-mcp
contextboss-mcp install claude-code
```

That merges into `~/.claude/settings.json`:

- the `contextboss` MCP server (`contextboss-mcp`, stdio)
- a SessionStart hook injecting your most relevant stored context
- PreCompact and Stop hooks storing session snapshots as ContextBoss entries

`contextboss-mcp install claude-code --print` shows the merged settings without
writing. Existing settings are preserved; the merge is idempotent.

Or add the MCP server by hand:

```bash
claude mcp add contextboss -- contextboss-mcp
```

## What lands where

ContextBoss keeps its own store (`~/.contextboss/context.db`, override with
`CONTEXTBOSS_DB`). Snapshots and injected context are ContextBoss entries.
Your Claude conversation history is provider-owned: ContextBoss never reads it
into the store beyond compacted, per-session snapshot digests, and never
modifies it.

## Files here

- `hooks/hooks.json` - the hook definitions, if you prefer to copy them yourself
- `skills/contextboss/SKILL.md` - teaches the agent how to use the tools
- `.claude-plugin/plugin.json` - plugin packaging
