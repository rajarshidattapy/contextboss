# Releasing

PyPI publishing is manual and happens only on explicit sign-off.

## Versioning

SemVer. Bump `version` in each package's `pyproject.toml` together
(core/mcp/api ship in lockstep) and add a CHANGELOG entry.

## Checklist

1. `ruff check packages` clean.
2. `python -m mypy packages/contextboss-core/src/contextboss` clean.
3. Full test suite green: `pytest packages bench -q`.
4. `python bench/benchmark.py` regenerated if engine behavior changed;
   commit `bench/results.json`.
5. Reproducible builds: `python -m build packages/contextboss-core` (and the
   other packages); wheel smoke-import `contextboss`.
6. Tag: `git tag vX.Y.Z && git push --tags`.

## Publishing to PyPI (only with the owner's explicit OK)

```bash
python -m build packages/contextboss-core
python -m build packages/contextboss-mcp
python -m build packages/contextboss-api
twine upload packages/contextboss-core/dist/* \
            packages/contextboss-mcp/dist/* \
            packages/contextboss-api/dist/*
```

Package names on PyPI: `contextboss-core`, `contextboss-mcp`,
`contextboss-api`. The import package stays `contextboss`.

## Docker

```bash
docker build -t contextboss .
docker run -v contextboss-data:/data -p 127.0.0.1:8787:8787 \
  -e CONTEXTBOSS_API_KEYS=change-me contextboss
# MCP over HTTP (connectors): docker run contextboss contextboss-mcp serve --http --host 0.0.0.0
```
