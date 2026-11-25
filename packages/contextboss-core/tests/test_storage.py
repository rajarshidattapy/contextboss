"""Storage contract tests, run against both backends."""
import threading

import pytest

from contextboss import ContextEntry, InMemoryBackend, SQLiteBackend


@pytest.fixture(params=["sqlite", "memory"])
def backend(request, tmp_path):
    if request.param == "sqlite":
        b = SQLiteBackend(str(tmp_path / "test.db"))
    else:
        b = InMemoryBackend()
    yield b
    b.close()


def make(content="alpha beta gamma", **kw):
    return ContextEntry(content=content, **kw)


class TestCRUD:
    def test_add_get_roundtrip(self, backend):
        e = backend.add(make(namespace="proj", tags=["a", "b"], provenance="test",
                             tier="retrieval", pinned=True, importance=2.5,
                             tokens=7, metadata={"k": "v"}))
        got = backend.get(e.id)
        assert got is not None
        assert got.content == "alpha beta gamma"
        assert got.namespace == "proj"
        assert got.tags == ["a", "b"]
        assert got.provenance == "test"
        assert got.tier == "retrieval"
        assert got.pinned is True
        assert got.importance == 2.5
        assert got.tokens == 7
        assert got.metadata == {"k": "v"}
        assert got.version == 1
        assert got.created_at > 0 and got.updated_at > 0

    def test_get_missing(self, backend):
        assert backend.get("nope") is None

    def test_update_missing_raises(self, backend):
        with pytest.raises(KeyError):
            backend.update(make())

    def test_delete_missing(self, backend):
        assert backend.delete("nope") is False


class TestVersioning:
    def test_update_bumps_version_and_keeps_history(self, backend):
        e = backend.add(make("first version"))
        e.content = "second version"
        backend.update(e)
        e2 = backend.get(e.id)
        e2.content = "third version"
        backend.update(e2)
        assert backend.get(e.id).version == 3
        assert backend.list_versions(e.id) == [1, 2, 3]
        assert backend.get_version(e.id, 1).content == "first version"
        assert backend.get_version(e.id, 2).content == "second version"
        assert backend.get_version(e.id, 3).content == "third version"

    def test_created_at_survives_updates(self, backend):
        e = backend.add(make())
        e.content = "new"
        backend.update(e)
        assert backend.get(e.id).created_at == e.created_at


class TestDeletion:
    def test_delete_removes_entry_versions_and_index(self, backend):
        e = backend.add(make("uniqueword zebra crossing"))
        e.content = "uniqueword zebra changed"
        backend.update(e)
        assert backend.search("uniqueword")
        assert backend.delete(e.id) is True
        assert backend.get(e.id) is None
        assert backend.search("uniqueword") == []
        assert backend.list_versions(e.id) == []
        assert backend.get_version(e.id, 1) is None

    def test_delete_does_not_touch_other_entries(self, backend):
        a = backend.add(make("shared words here"))
        b = backend.add(make("shared words there"))
        backend.delete(a.id)
        assert backend.get(b.id) is not None
        assert [x.id for x in backend.search("shared")] == [b.id]


class TestSearch:
    def test_relevance_ranking(self, backend):
        backend.add(make("the cat sat"))
        best = backend.add(make("cat cat cat cats everywhere"))
        backend.add(make("unrelated stuff entirely"))
        results = backend.search("cat")
        assert results[0].id == best.id
        assert len(results) == 2

    def test_namespace_filter(self, backend):
        backend.add(make("needle one", namespace="a"))
        b2 = backend.add(make("needle two", namespace="b"))
        results = backend.search("needle", namespace="b")
        assert [r.id for r in results] == [b2.id]

    def test_tag_filter(self, backend):
        backend.add(make("needle one", tags=["x"]))
        b2 = backend.add(make("needle two", tags=["x", "y"]))
        results = backend.search("needle", tags=["y"])
        assert [r.id for r in results] == [b2.id]

    def test_fts_special_chars_do_not_crash(self, backend):
        backend.add(make("plain content"))
        # FTS5 operators and junk must not raise
        assert backend.search('AND OR "unclosed (paren') is not None
        assert backend.search("***") is not None

    def test_empty_query_lists(self, backend):
        backend.add(make("one"))
        assert len(backend.search("")) == 1

    def test_limit(self, backend):
        for i in range(20):
            backend.add(make(f"common term {i}"))
        assert len(backend.search("common", limit=5)) == 5


class TestListAndStats:
    def test_pinned_first(self, backend):
        backend.add(make("old"))
        p = backend.add(make("pinned", pinned=True))
        assert backend.list()[0].id == p.id

    def test_stats_shape(self, backend):
        backend.add(make("a", namespace="n1", tokens=10, pinned=True))
        backend.add(make("b", namespace="n1", tier="retrieval", tokens=5))
        backend.add(make("c", namespace="n2", tokens=1))
        s = backend.stats()
        assert s["entries"] == 3
        assert s["tokens"] == 16
        assert s["pinned"] == 1
        assert s["namespaces"]["n1"] == {"entries": 2, "tokens": 15}
        assert s["tiers"]["retrieval"]["entries"] == 1
        assert backend.stats(namespace="n2")["entries"] == 1


class TestConcurrency:
    def test_parallel_writers(self, backend):
        errors = []

        def worker(n):
            try:
                for i in range(25):
                    backend.add(make(f"thread {n} entry {i}", namespace=f"t{n}"))
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert backend.stats()["entries"] == 200
        ids = [e.id for e in backend.list(limit=500)]
        assert len(set(ids)) == 200


class TestSQLitePersistence:
    def test_reopen_keeps_data(self, tmp_path):
        path = str(tmp_path / "persist.db")
        b = SQLiteBackend(path)
        e = b.add(make("durable words", tokens=3))
        b.close()
        b2 = SQLiteBackend(path)
        assert b2.get(e.id).content == "durable words"
        assert b2.search("durable")
        b2.close()

    def test_wal_recovery_second_connection(self, tmp_path):
        # A second connection sees committed writes without a checkpoint: WAL works.
        path = str(tmp_path / "wal.db")
        b1 = SQLiteBackend(path)
        e = b1.add(make("written before crash"))
        b2 = SQLiteBackend(path)  # separate connection, same file
        assert b2.get(e.id) is not None
        b1.close()
        b2.close()

    def test_concurrent_connections_write(self, tmp_path):
        path = str(tmp_path / "multi.db")
        a, b = SQLiteBackend(path), SQLiteBackend(path)
        ea = a.add(make("from a"))
        eb = b.add(make("from b"))
        assert a.get(eb.id) is not None
        assert b.get(ea.id) is not None
        a.close()
        b.close()
