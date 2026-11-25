"""`contextboss-mcp install <client>`: wire ContextBoss into an agent client.

Writes are minimal, marked and idempotent. Existing settings are preserved.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

BEGIN = "# >>> contextboss >>>"
END = "# <<< contextboss <<<"

AGENTS_SNIPPET = f"""{BEGIN}
## ContextBoss

A ContextBoss MCP server (`contextboss-mcp`) is configured for this environment.
Use its tools to remember and recall project context across sessions:

- `context_add` to store decisions, conventions and findings (set provenance).
- `context_search` / `context_get` to recall them.
- `context_assemble` to build a budget-checked prompt from stored context.
- `context_compact` / `context_delete` to keep the store lean. Deletes are permanent.
{END}"""


def _claude_settings_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".claude", "settings.json")


def install_claude_code(print_only: bool = False) -> str:
    path = _claude_settings_path()
    try:
        with open(path) as fh:
            settings: Dict[str, Any] = json.load(fh)
    except (OSError, json.JSONDecodeError):
        settings = {}

    servers = settings.setdefault("mcpServers", {})
    servers["contextboss"] = {"command": "contextboss-mcp"}

    hooks = settings.setdefault("hooks", {})

    def _hook(command: str) -> Dict[str, Any]:
        return {"hooks": [{"type": "command", "command": command}]}

    def _merge(event: str, command: str) -> None:
        entries = hooks.setdefault(event, [])
        for entry in entries:
            for h in entry.get("hooks", []):
                if h.get("command") == command:
                    return
        entries.append(_hook(command))

    _merge("SessionStart", "contextboss-hook session-start")
    _merge("PreCompact", "contextboss-hook snapshot")
    _merge("Stop", "contextboss-hook snapshot")

    rendered = json.dumps(settings, indent=2) + "\n"
    if not print_only:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(rendered)
    return f"wrote {path}" if not print_only else f"would write {path}:\n{rendered}"


def install_codex(project_dir: str = ".", print_only: bool = False) -> str:
    config_path = os.path.join(os.path.expanduser("~"), ".codex", "config.toml")
    block = "\n".join(
        [
            "",
            BEGIN,
            "[mcp_servers.contextboss]",
            'command = "contextboss-mcp"',
            END,
            "",
        ]
    )
    try:
        with open(config_path) as fh:
            config = fh.read()
    except OSError:
        config = ""
    out = []
    if "[mcp_servers.contextboss]" in config:
        out.append(f"{config_path} already configured")
    else:
        if not print_only:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, "a") as fh:
                fh.write(block)
        out.append(f"wrote {config_path}" if not print_only else f"would append to {config_path}:{block}")

    agents_path = os.path.join(project_dir, "AGENTS.md")
    try:
        with open(agents_path) as fh:
            agents = fh.read()
    except OSError:
        agents = ""
    if BEGIN in agents:
        out.append(f"{agents_path} already has the ContextBoss block")
    else:
        new = agents.rstrip() + "\n\n" + AGENTS_SNIPPET + "\n" if agents.strip() else AGENTS_SNIPPET + "\n"
        if not print_only:
            with open(agents_path, "w") as fh:
                fh.write(new)
        out.append(f"wrote {agents_path}" if not print_only else f"would write {agents_path}")
    return "\n".join(out)


def main() -> None:
    args = [a for a in sys.argv[1:]]
    print_only = "--print" in args
    args = [a for a in args if a != "--print"]
    if not args or args[0] not in ("claude-code", "codex"):
        print("usage: contextboss-mcp install <claude-code|codex> [--print]", file=sys.stderr)
        sys.exit(2)
    if args[0] == "claude-code":
        print(install_claude_code(print_only=print_only))
    else:
        print(install_codex(print_only=print_only))


if __name__ == "__main__":
    main()
