from __future__ import annotations

import argparse
import sys

from .demo import build
from .types import AssembledContext, Tier

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
COLORS = {
    "system": "\033[95m", "task": "\033[96m", "memory": "\033[92m",
    "retrieval": "\033[94m", "tools": "\033[93m",
}
ACTION = {
    "included": "\033[92m+ kept     ", "compacted": "\033[93m~ compacted", "summarized": "\033[93m~ summarized",
    "dropped": "\033[91m- dropped  ",
}


def bar(used: int, cap: int, width: int = 28) -> str:
    filled = 0 if cap <= 0 else min(width, round(width * used / cap))
    return "█" * filled + "░" * (width - filled)


def report(ctx: AssembledContext, color: bool) -> str:
    c = (lambda code: code) if color else (lambda code: "")
    out = []
    out.append(f"{c(BOLD)}contextboss{c(RESET)}  window {ctx.window} tokens  (budget {ctx.budget}, {ctx.output_reserve} reserved for output)\n")
    out.append(f"{c(BOLD)}Budget by tier{c(RESET)}")
    for u in ctx.usage:
        col = c(COLORS[u.tier.label])
        out.append(f"  {col}{u.tier.label:<10} {bar(u.used, max(u.allocated, u.used, 1))} {c(RESET)}{u.used:>5} / {max(u.allocated, u.used):<5}")
    pct = 100 * ctx.total_tokens / ctx.window
    out.append(f"\n  {c(BOLD)}total {ctx.total_tokens} / {ctx.window}  ({pct:.0f}% of window){c(RESET)}\n")
    out.append(f"{c(BOLD)}What happened to each item{c(RESET)}")
    for d in sorted(ctx.decisions, key=lambda d: (d.tier, d.action == "dropped")):
        label = ACTION[d.action] if color else {"included": "+ kept     ", "compacted": "~ compacted", "summarized": "~ summarized", "dropped": "- dropped  "}[d.action]
        out.append(f"  {label}{c(RESET)} {c(COLORS[d.tier.label])}{d.tier.label:<9}{c(RESET)} {d.preview:<46.46} {d.tokens:>4}t  {c(DIM)}{d.reason}{c(RESET)}")
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="contextboss", description="Context Assembler demo.")
    p.add_argument("--budget", type=int, default=680, help="total token budget (default 900)")
    p.add_argument("--reserve", type=int, default=256, help="tokens reserved for the model's reply")
    p.add_argument("--show", action="store_true", help="print the assembled prompt too")
    p.add_argument("--no-color", action="store_true")
    a = p.parse_args(argv)

    ctx = build(a.budget, a.reserve).assemble()
    print(report(ctx, color=not a.no_color and sys.stdout.isatty() or (not a.no_color and "FORCE_COLOR" in __import__("os").environ)))
    if a.show:
        print("\n" + "─" * 60 + "\n" + ctx.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
