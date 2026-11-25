"""The management CLI: add/search/assemble/serve/export/import and friends.

`contextboss` with no subcommand (or with the legacy demo flags) still runs the
demo, so the original quickstart keeps working.
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import load_settings
from .manager import ContextManager


def _manager(args: argparse.Namespace) -> ContextManager:
    settings = load_settings()
    db = getattr(args, "db", None) or settings.db
    return ContextManager(
        db,
        budget=getattr(args, "budget", None) or settings.budget,
        output_reserve=getattr(args, "reserve", None) or settings.reserve,
    )


def _print_entry(e) -> None:
    print(json.dumps(e.to_dict(), indent=2))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="contextboss")
    p.add_argument("--db", help="store path (default: CONTEXTBOSS_DB or ~/.contextboss/context.db)")
    p.add_argument("--budget", type=int, help="assembly token budget")
    p.add_argument("--reserve", type=int, help="assembly output reserve")
    sub = p.add_subparsers(dest="command")

    a = sub.add_parser("add", help="store context")
    a.add_argument("content")
    a.add_argument("--namespace", default="default")
    a.add_argument("--tag", action="append", default=[])
    a.add_argument("--provenance", default="")
    a.add_argument("--tier", default="memory")
    a.add_argument("--pinned", action="store_true")
    a.add_argument("--importance", type=float, default=1.0)

    s = sub.add_parser("search", help="full-text search")
    s.add_argument("query", nargs="?", default="")
    s.add_argument("--namespace")
    s.add_argument("--tag", action="append", default=[])
    s.add_argument("--limit", type=int, default=10)

    g = sub.add_parser("get")
    g.add_argument("entry_id")

    u = sub.add_parser("update")
    u.add_argument("entry_id")
    u.add_argument("--content")
    u.add_argument("--namespace")
    u.add_argument("--tag", action="append")
    u.add_argument("--tier")
    u.add_argument("--pinned", choices=["true", "false"])
    u.add_argument("--importance", type=float)

    d = sub.add_parser("delete")
    d.add_argument("entry_id")

    c = sub.add_parser("compact")
    c.add_argument("entry_id")
    c.add_argument("--target", type=int)

    asm = sub.add_parser("assemble", help="build a window-safe prompt")
    asm.add_argument("query", nargs="?", default="")
    asm.add_argument("--budget", type=int, default=None)
    asm.add_argument("--reserve", type=int, default=None)
    asm.add_argument("--system")
    asm.add_argument("--task")
    asm.add_argument("--namespace")
    asm.add_argument("--show-decisions", action="store_true")

    i = sub.add_parser("inspect")
    i.add_argument("entry_id")

    st = sub.add_parser("stats")
    st.add_argument("--namespace")

    li = sub.add_parser("list")
    li.add_argument("--namespace")
    li.add_argument("--tag", action="append", default=[])
    li.add_argument("--limit", type=int, default=50)

    ex = sub.add_parser("export", help="export entries to JSONL")
    ex.add_argument("path")
    ex.add_argument("--namespace")

    im = sub.add_parser("import", help="import entries from JSONL")
    im.add_argument("path")

    sub.add_parser("serve", help="run the MCP server (needs contextboss-mcp)")
    sub.add_parser("demo", help="run the demo")
    return p


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        from .cli import demo_main

        return demo_main([])
    if args.command is None:
        build_parser().print_help()
        return 2
    if args.command == "serve":
        try:
            from contextboss_mcp.server import main as serve_main
        except ImportError:
            print("contextboss-mcp is not installed: pip install contextboss-mcp",
                  file=sys.stderr)
            return 1
        serve_main()
        return 0

    mgr = _manager(args)
    try:
        if args.command == "add":
            _print_entry(mgr.add(args.content, namespace=args.namespace, tags=args.tag,
                                 provenance=args.provenance, tier=args.tier,
                                 pinned=args.pinned, importance=args.importance))
        elif args.command == "search":
            print(json.dumps(
                [e.to_dict() for e in mgr.search(args.query, namespace=args.namespace,
                                                 tags=args.tag, limit=args.limit)],
                indent=2,
            ))
        elif args.command == "get":
            e = mgr.get(args.entry_id)
            if e is None:
                print(f"no such entry: {args.entry_id}", file=sys.stderr)
                return 1
            _print_entry(e)
        elif args.command == "update":
            pinned = None if args.pinned is None else args.pinned == "true"
            try:
                _print_entry(mgr.update(args.entry_id, args.content,
                                        namespace=args.namespace, tags=args.tag,
                                        tier=args.tier, pinned=pinned,
                                        importance=args.importance))
            except KeyError:
                print(f"no such entry: {args.entry_id}", file=sys.stderr)
                return 1
        elif args.command == "delete":
            if not mgr.delete(args.entry_id):
                print(f"no such entry: {args.entry_id}", file=sys.stderr)
                return 1
            print(json.dumps({"deleted": True}))
        elif args.command == "compact":
            try:
                _print_entry(mgr.compact(args.entry_id, args.target))
            except KeyError:
                print(f"no such entry: {args.entry_id}", file=sys.stderr)
                return 1
        elif args.command == "assemble":
            ctx = mgr.assemble(args.query, system=args.system, task=args.task,
                               namespace=args.namespace)
            print(ctx.render())
            print(f"\n--- {ctx.total_tokens}/{ctx.window} tokens ---", file=sys.stderr)
            if args.show_decisions:
                for d in ctx.decisions:
                    print(f"{d.action:<11} {d.tier.label:<9} {d.preview} ({d.tokens}t)",
                          file=sys.stderr)
        elif args.command == "inspect":
            try:
                print(json.dumps(mgr.inspect(args.entry_id), indent=2))
            except KeyError:
                print(f"no such entry: {args.entry_id}", file=sys.stderr)
                return 1
        elif args.command == "stats":
            print(json.dumps(mgr.stats(namespace=args.namespace), indent=2))
        elif args.command == "list":
            for e in mgr.list(namespace=args.namespace, tags=args.tag, limit=args.limit):
                print(f"{e.id}  [{e.namespace}/{e.tier}]"
                      f"{' pinned' if e.pinned else ''}  {e.content[:80]}")
        elif args.command == "export":
            n = 0
            with open(args.path, "w") as fh:
                for e in mgr.list(namespace=args.namespace, limit=1_000_000):
                    fh.write(json.dumps(e.to_dict()) + "\n")
                    n += 1
            print(json.dumps({"exported": n, "path": args.path}))
        elif args.command == "import":
            n = skipped = 0
            with open(args.path) as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if mgr.get(str(data.get("id", ""))):
                        skipped += 1
                        continue
                    mgr.restore(data)
                    n += 1
            print(json.dumps({"imported": n, "skipped_existing": skipped}))
        return 0
    finally:
        mgr.close()
