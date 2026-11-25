# contextboss-api

Versioned REST API over a ContextManager.

```bash
pip install -e .
CONTEXTBOSS_DB=~/.contextboss/context.db contextboss-api            # 127.0.0.1:8788
CONTEXTBOSS_API_KEYS=secret1,secret2 contextboss-api                # bearer auth required
contextboss-api --host 0.0.0.0 --port 8788                          # remote: put behind HTTPS (see deploy/)
```

Auth: when `CONTEXTBOSS_API_KEYS` is set, every request needs
`Authorization: Bearer <key>` (keys are stored hashed, never logged). Without
keys the API is open, so it binds localhost by default; only expose it
remotely behind HTTPS with keys configured.

Routes (all under `/v1`):

- `POST /v1/contexts` add, `GET /v1/contexts` search/list, `GET/PATCH/DELETE /v1/contexts/{id}`
- `POST /v1/contexts/{id}/compact`, `GET /v1/contexts/{id}/inspect`
- `POST /v1/assemble`, `GET /v1/stats`
- sync: `GET /v1/sync/changes?since=<epoch>` (upserts since a cursor),
  `GET /v1/sync/export`, `POST /v1/sync/import`

Deletion is hard deletion; sync propagates upserts. A client that needs
tombstones should track deletes via `DELETE` responses.
