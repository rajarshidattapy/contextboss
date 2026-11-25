# ContextBoss all-in-one: core engine + MCP server (stdio) + REST API.
FROM python:3.12-slim AS base
WORKDIR /app
COPY packages/contextboss-core packages/contextboss-core
COPY packages/contextboss-mcp packages/contextboss-mcp
COPY packages/contextboss-api packages/contextboss-api
RUN pip install --no-cache-dir \
    packages/contextboss-core \
    packages/contextboss-mcp \
    packages/contextboss-api
ENV CONTEXTBOSS_DB=/data/contextboss.db
VOLUME ["/data"]
EXPOSE 8787
# Default: REST API. For Claude Code/Desktop MCP over stdio, run:
#   docker run -i contextboss contextboss-mcp
CMD ["python", "-m", "uvicorn", "contextboss_api.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8787"]
