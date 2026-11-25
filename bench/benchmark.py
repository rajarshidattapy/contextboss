"""Benchmark: ContextBoss assembly vs naive truncation vs fixed allocation.

Scenario: an agent accumulates context (system prompt, task, memories, retrieved
docs, tool schemas). Some entries are KEY facts the answer depends on. Under a
shrinking token window we measure:

  key_fact_recall  - fraction of key facts that survive into the final context
  window_compliant - total tokens never exceeds the window

Run:  python -m bench.benchmark            (writes docs/benchmarks.md + bench/results.json)
"""
from __future__ import annotations

import json
import os
import random
import sys
from dataclasses import dataclass, field
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "contextboss-core", "src"))

from contextboss import ContextManager, HeuristicTokenizer  # noqa: E402

TOPICS = [
    ("deploy freeze", "staging freezes deploys on fridays since the october incident"),
    ("billing", "billing migrated to stripe in october, webhooks on /billing/hooks"),
    ("auth", "auth tokens rotate every 12 hours, refresh via /auth/refresh"),
    ("search", "search index rebuilds nightly at 3am utc, expect stale results"),
    ("cache", "redis cache ttl is 900s for product pages, 60s for inventory"),
    ("onboarding", "new signups get a 14 day trial, no card required"),
    ("limits", "rate limit is 100 req/min per api key, 429 includes retry-after"),
    ("logging", "request logs live in loki, 30 day retention, trace id in header"),
]
FILLER = [
    "the quarterly offsite is planned for goa in march and the team vote is still pending",
    "a new espresso machine arrived at the bangalore office on the second floor pantry",
    "the design system migration to tokens v2 is about sixty percent complete",
    "parking validation now requires a badge tap at the lobby kiosk every morning",
    "the book club picked a systems thinking title for this month and meets weekly",
    "the frontend guild meets on alternate tuesdays and keeps notes in the wiki",
    "the old jira board was archived and everyone should use the linear project",
    "intern demo day is scheduled for the last friday of the month in the main hall",
    "the cafeteria menu rotates weekly and thursday biryani is the crowd favorite",
    "the wifi password changes every quarter and it is posted near the reception",
]


def make_noise(rng: random.Random, n: int = 30, sentences=(4, 8)) -> List[str]:
    """Retrieval-style noise paragraphs, each far too long to all fit a small window."""
    docs = []
    for _ in range(n):
        k = rng.randint(*sentences)
        docs.append(". ".join(rng.choice(FILLER) for _ in range(k)) + ".")
    return docs


@dataclass
class Scenario:
    key_facts: Dict[str, str]          # query -> fact that answers it
    noise: List[str] = field(default_factory=list)


def build_store(mgr: ContextManager, scenario: Scenario, rng: random.Random) -> None:
    entries = [(fact, 2.0, True) for fact in scenario.key_facts.values()]
    entries += [(n, 1.0, False) for n in scenario.noise]
    rng.shuffle(entries)
    for content, importance, _ in entries:
        mgr.add(content, importance=importance, tier="memory")


def naive_truncation(texts: List[str], window: int, tok) -> str:
    out, used = [], 0
    for t in texts:
        cost = tok.count(t)
        if used + cost > window:
            break
        out.append(t)
        used += cost
    return "\n".join(out)


def fixed_allocation(facts: List[str], noise: List[str], window: int, tok) -> str:
    out, used = [], 0
    for group in (facts, noise):
        cap = window // 3
        for t in group:
            cost = tok.count(t)
            if used + cost > window or cost > cap:
                continue
            out.append(t)
            used += cost
            cap -= cost
    return "\n".join(out)


def recall(ctx_text: str, facts: List[str]) -> float:
    if not facts:
        return 1.0
    return sum(1 for f in facts if f in ctx_text) / len(facts)


def run(budgets=(400, 800, 1600, 3200), seeds=(1, 2, 3)) -> List[Dict]:
    tok = HeuristicTokenizer()
    rows = []
    for budget in budgets:
        window = budget - 64
        for seed in seeds:
            rng = random.Random(seed)
            scenario = Scenario(key_facts={q: f for q, f in TOPICS}, noise=make_noise(rng))
            queries = list(scenario.key_facts)
            query = queries[seed % len(queries)]
            target = scenario.key_facts[query]
            other_facts = [f for q, f in scenario.key_facts.items() if q != query]

            # naive: insertion order, query-relevant position random
            all_texts = [target] + other_facts + scenario.noise
            rng.shuffle(all_texts)
            naive = naive_truncation(all_texts, window, tok)
            fixed_facts = [target] + other_facts
            rng.shuffle(fixed_facts)  # fixed allocation gets no relevance ordering
            fixed = fixed_allocation(fixed_facts, scenario.noise, window, tok)

            mgr = ContextManager(":memory:", budget=budget, output_reserve=64, tokenizer=tok)
            build_store(mgr, scenario, rng)
            ctx = mgr.assemble(query, system="ops assistant", task="answer the oncall question")
            cb_text = ctx.render()

            rows.append({
                "budget": budget, "seed": seed,
                "naive_recall": recall(naive, [target]),
                "fixed_recall": recall(fixed, [target]),
                "contextboss_recall": recall(cb_text, [target]),
                "contextboss_compliant": ctx.total_tokens <= ctx.window,
                "naive_compliant": tok.count(naive) <= window,
                "fixed_compliant": tok.count(fixed) <= window,
            })
            mgr.close()
    return rows


def summarize(rows: List[Dict]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for strategy in ("naive", "fixed", "contextboss"):
        recalls = [r[f"{strategy}_recall"] for r in rows]
        comp = [r[f"{strategy}_compliant"] for r in rows]
        out[strategy] = {
            "key_fact_recall": sum(recalls) / len(recalls),
            "window_compliance": sum(comp) / len(comp),
        }
    return out


def render_markdown(rows: List[Dict], summary: Dict[str, Dict[str, float]]) -> str:
    lines = [
        "# Benchmarks",
        "",
        "ContextBoss assembly vs naive truncation and fixed allocation. Metric:",
        "does the fact that answers the query survive into the window",
        "(key-fact recall), and does the result respect the window.",
        "",
        "| budget | naive recall | fixed recall | contextboss recall |",
        "| --- | --- | --- | --- |",
    ]
    budgets = sorted({r["budget"] for r in rows})
    for b in budgets:
        sub = [r for r in rows if r["budget"] == b]
        def avg(k):
            return sum(r[k] for r in sub) / len(sub)
        lines.append(
            f"| {b} | {avg('naive_recall'):.0%} | {avg('fixed_recall'):.0%} | {avg('contextboss_recall'):.0%} |"
        )
    lines += [
        "",
        "Window compliance: "
        + ", ".join(
            f"{s} {v['window_compliance']:.0%}" for s, v in summary.items()
        )
        + ".",
        "",
        "Reproduce: `python -m bench.benchmark`.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = run()
    summary = summarize(rows)
    root = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(root, "bench", "results.json"), "w") as fh:
        json.dump({"rows": rows, "summary": summary}, fh, indent=2)
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    with open(os.path.join(root, "docs", "benchmarks.md"), "w") as fh:
        fh.write(render_markdown(rows, summary))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
