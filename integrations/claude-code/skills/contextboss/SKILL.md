---
name: contextboss
description: "Remember and recall project context across sessions with the ContextBoss MCP tools: store decisions and findings with context_add, recall with context_search, build budget-checked prompts with context_assemble. Use when the user asks to remember something, when starting work that depends on earlier sessions, or when the context store needs pruning."
---

# ContextBoss

ContextBoss is a persistent context layer. The store survives sessions; the
provider's conversation history does not. Store durable knowledge as you go.

## When to write

Call `context_add` when the user states a decision, convention, constraint or
finding that will matter later. Always set `provenance` (where it came from)
and useful `tags`. Use `pinned: true` for facts that must never drop out of
assembled context (environments, hard constraints).

## When to read

- Starting a task: `context_search` for the project or topic first.
- Answering "what did we decide about X?": `context_search`, then `context_get`
  for the full entry and `context_inspect` for its history.

## Housekeeping

- Prefer `context_update` over deleting and re-adding: history is preserved.
- `context_compact` shrinks stale long entries; `context_delete` is permanent
  (entry, index and version history). Confirm with the user before deleting.
- `context_stats` shows store size by namespace and tier.

## Assembly

`context_assemble` builds a prompt that provably fits the token window, with a
decision log explaining what was included, compacted or dropped.
