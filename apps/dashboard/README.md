# ContextBoss Dashboard

Next.js dashboard over the ContextBoss REST API (`packages/contextboss-api`).

## Run

```bash
# terminal 1: the API
pip install -e ../../packages/contextboss-api
contextboss-api  # serves http://127.0.0.1:8787

# terminal 2: the dashboard
npm install
CONTEXTBOSS_API_URL=http://127.0.0.1:8787 npm run dev
```

Open http://localhost:3000. If the API has `CONTEXTBOSS_API_KEYS` set, pass one
as `CONTEXTBOSS_API_KEY`.

## Pages

- **Overview**: entry/token counts, namespaces, hot tier, recent entries.
- **Entries**: full-text search with namespace filter.
- **Entry detail**: content, tags, tension report, version history, similar
  entries, one-click compaction.
- **Assemble**: playground for the context assembler with a live budget.
