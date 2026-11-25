"""ContextManager facade tests: lifecycle, compression, budget invariants."""
import random

import pytest
from contextboss import ContextManager


@pytest.fixture
def mgr(tmp_path):
    m = ContextManager(str(tmp_path / "m.db"), budget=800, output_reserve=100)
    yield m
    m.close()


class TestLifecycle:
    def test_add_search_get_update_delete(self, mgr):
        e = mgr.add("the deploy pipeline broke on friday", tags=["incident"],
                    provenance="slack:#eng", tier="memory")
        assert e.tokens > 0
        assert mgr.search("deploy pipeline")[0].id == e.id
        mgr.update(e.id, "the deploy pipeline broke on friday, fixed monday",
                   tags=["incident", "resolved"])
        got = mgr.get(e.id)
        assert got.version == 2
        assert "fixed monday" in got.content
        assert mgr.get_version(e.id, 1).content.endswith("friday")
        assert mgr.delete(e.id) is True
        assert mgr.get(e.id) is None
        assert mgr.search("pipeline") == []

    def test_invalid_tier_rejected(self, mgr):
        with pytest.raises(ValueError):
            mgr.add("x", tier="bogus")

    def test_namespaces_isolated(self, mgr):
        mgr.add("alpha note", namespace="a")
        mgr.add("alpha note", namespace="b")
        assert mgr.stats(namespace="a")["entries"] == 1
        assert len(mgr.search("alpha", namespace="b")) == 1


class TestCompact:
    def test_compact_shrinks_and_versions(self, mgr):
        long_text = ". ".join(f"sentence number {i} with some extra words" for i in range(60))
        e = mgr.add(long_text)
        before = e.tokens
        out = mgr.compact(e.id, target_tokens=40)
        assert out.tokens <= 40
        assert out.tokens < before
        assert mgr.inspect(e.id)["versions"] == [1, 2]
        assert mgr.get_version(e.id, 1).tokens == before

    def test_compact_short_entry_is_noop(self, mgr):
        e = mgr.add("tiny")
        assert mgr.compact(e.id).version == 1


class TestAssemble:
    def test_never_exceeds_window(self, mgr):
        rng = random.Random(42)
        for trial in range(30):
            m = ContextManager(budget=rng.randint(200, 4000),
                               output_reserve=rng.randint(50, 199))
            for _ in range(rng.randint(1, 40)):
                m.add("lorem ipsum dolor sit amet " * rng.randint(1, 60),
                      importance=rng.uniform(0.1, 3.0),
                      pinned=rng.random() < 0.1,
                      tier=rng.choice(["memory", "retrieval"]))
            ctx = m.assemble("lorem", system="you are helpful", task="answer the question")
            assert ctx.total_tokens <= ctx.window, f"trial {trial} overflowed"
            m.close()

    def test_pinned_entries_survive_tight_budgets(self, mgr):
        mgr.add("filler " * 500)
        mgr.add("the critical fact", pinned=True)
        ctx = mgr.assemble("", budget=800, output_reserve=100)
        assert "the critical fact" in ctx.render()

    def test_system_and_task_pinned(self, mgr):
        mgr.add("some memory about cats")
        ctx = mgr.assemble("cats", system="SYS", task="TSK")
        text = ctx.render()
        assert "SYS" in text and "TSK" in text

    def test_stored_system_tier_entries_included(self, mgr):
        mgr.add("stored system prompt", tier="system")
        mgr.add("stored task text", tier="task")
        ctx = mgr.assemble("")
        assert "stored system prompt" in ctx.render()
        assert "stored task text" in ctx.render()

    def test_query_ranks_relevant_first(self, mgr):
        mgr.add("notes about database indexing and b-trees")
        mgr.add("a recipe for tomato soup")
        ctx = mgr.assemble("database indexing", budget=300, output_reserve=50)
        assert "b-trees" in ctx.render()


class TestInspectAndStats:
    def test_inspect(self, mgr):
        e = mgr.add("v1 text")
        mgr.update(e.id, "v2 text")
        info = mgr.inspect(e.id)
        assert info["entry"]["version"] == 2
        assert info["versions"] == [1, 2]

    def test_stats(self, mgr):
        mgr.add("one")
        mgr.add("two", pinned=True, tier="retrieval")
        s = mgr.stats()
        assert s["entries"] == 2
        assert s["pinned"] == 1
        assert s["tiers"]["retrieval"]["entries"] == 1


class TestPersistenceEndToEnd:
    def test_manager_reopen(self, tmp_path):
        path = str(tmp_path / "e2e.db")
        m = ContextManager(path)
        e = m.add("remember this fact", tags=["x"])
        m.close()
        m2 = ContextManager(path)
        assert m2.get(e.id).content == "remember this fact"
        assert m2.search("remember this", tags=["x"])
        m2.close()
