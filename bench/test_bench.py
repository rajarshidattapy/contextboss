"""The benchmark harness runs, and ContextBoss never trails the baselines."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "contextboss-core", "src"))

from bench.benchmark import run, summarize  # noqa: E402


def test_contextboss_beats_or_matches_baselines():
    rows = run(budgets=(400, 800), seeds=(1, 2))
    s = summarize(rows)
    assert s["contextboss"]["key_fact_recall"] >= s["naive"]["key_fact_recall"]
    assert s["contextboss"]["key_fact_recall"] >= s["fixed"]["key_fact_recall"]


def test_contextboss_window_compliance_always():
    rows = run(budgets=(400, 800, 1600), seeds=(1, 2, 3))
    assert all(r["contextboss_compliant"] for r in rows)


def test_naive_drops_key_facts_under_pressure():
    rows = run(budgets=(400,), seeds=(1, 2, 3))
    # the point of the benchmark: naive truncation loses key facts sometimes
    assert any(r["naive_recall"] < 1.0 for r in rows)
