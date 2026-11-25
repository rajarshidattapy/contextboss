"""Pluggable storage backends.

SQLiteBackend is the default: WAL journaling, an FTS5 full-text index, a version
history table, and hard deletion that removes the entry, its index rows and its
history. InMemoryBackend implements the same contract for tests and ephemeral use.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable

from .models import ContextEntry


@runtime_checkable
class StorageBackend(Protocol):
    def add(self, entry: ContextEntry) -> ContextEntry: ...
    def get(self, entry_id: str) -> Optional[ContextEntry]: ...
    def update(self, entry: ContextEntry) -> ContextEntry: ...
    def delete(self, entry_id: str) -> bool: ...
    def search(
        self,
        query: str,
        *,
        namespace: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        limit: int = 10,
    ) -> List[ContextEntry]: ...
    def list(
        self,
        *,
        namespace: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        limit: int = 1000,
    ) -> List[ContextEntry]: ...
    def get_version(self, entry_id: str, version: int) -> Optional[ContextEntry]: ...
    def list_versions(self, entry_id: str) -> List[int]: ...
    def stats(self, *, namespace: Optional[str] = None) -> Dict[str, Any]: ...
    def close(self) -> None: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    provenance TEXT NOT NULL DEFAULT '',
    tier TEXT NOT NULL DEFAULT 'memory',
    pinned INTEGER NOT NULL DEFAULT 0,
    importance REAL NOT NULL DEFAULT 1.0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    tokens INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_entries_ns ON entries(namespace);
CREATE TABLE IF NOT EXISTS versions (
    entry_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    tokens INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL,
    PRIMARY KEY (entry_id, version)
);
"""


class SQLiteBackend:
    """SQLite-backed storage. WAL mode + busy timeout for concurrent readers."""

    def __init__(self, path: str = "contextboss.db") -> None:
        self.path = path
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("PRAGMA foreign_keys=ON")
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)
        self._fts = self._init_fts()

    def _init_fts(self) -> bool:
        try:
            with self._lock, self._db:
                self._db.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts "
                    "USING fts5(content, entry_id UNINDEXED)"
                )
            return True
        except sqlite3.OperationalError:
            return False  # FTS5 not compiled in; search falls back to LIKE

    # -- row mapping ------------------------------------------------------
    @staticmethod
    def _row_to_entry(row: tuple) -> ContextEntry:
        return ContextEntry(
            id=row[0],
            namespace=row[1],
            content=row[2],
            tags=json.loads(row[3]),
            provenance=row[4],
            tier=row[5],
            pinned=bool(row[6]),
            importance=row[7],
            version=row[8],
            created_at=row[9],
            updated_at=row[10],
            tokens=row[11],
            metadata=json.loads(row[12]),
        )

    _COLS = "id, namespace, content, tags, provenance, tier, pinned, importance, version, created_at, updated_at, tokens, metadata"

    @staticmethod
    def _tags_match(entry_tags: List[str], wanted: Optional[Sequence[str]]) -> bool:
        return not wanted or all(t in entry_tags for t in wanted)

    # -- writes -------------------------------------------------------------
    def add(self, entry: ContextEntry) -> ContextEntry:
        now = time.time()
        entry.created_at = entry.created_at or now
        entry.updated_at = now
        entry.version = 1
        with self._lock, self._db:
            self._db.execute(
                f"INSERT INTO entries ({self._COLS}) VALUES ({','.join('?' * 13)})",
                (
                    entry.id, entry.namespace, entry.content, json.dumps(entry.tags),
                    entry.provenance, entry.tier, int(entry.pinned), entry.importance,
                    entry.version, entry.created_at, entry.updated_at, entry.tokens,
                    json.dumps(entry.metadata),
                ),
            )
            if self._fts:
                self._db.execute(
                    "INSERT INTO entries_fts (content, entry_id) VALUES (?, ?)",
                    (entry.content, entry.id),
                )
        return entry

    def update(self, entry: ContextEntry) -> ContextEntry:
        with self._lock, self._db:
            cur = self._db.execute(
                f"SELECT {self._COLS} FROM entries WHERE id = ?", (entry.id,)
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(f"no such entry: {entry.id}")
            old = self._row_to_entry(row)
            self._db.execute(
                "INSERT INTO versions (entry_id, version, content, tags, metadata, tokens, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (old.id, old.version, old.content, json.dumps(old.tags),
                 json.dumps(old.metadata), old.tokens, old.updated_at),
            )
            entry.version = old.version + 1
            entry.created_at = old.created_at
            entry.updated_at = time.time()
            self._db.execute(
                "UPDATE entries SET namespace=?, content=?, tags=?, provenance=?, tier=?,"
                " pinned=?, importance=?, version=?, updated_at=?, tokens=?, metadata=?"
                " WHERE id=?",
                (
                    entry.namespace, entry.content, json.dumps(entry.tags),
                    entry.provenance, entry.tier, int(entry.pinned), entry.importance,
                    entry.version, entry.updated_at, entry.tokens,
                    json.dumps(entry.metadata), entry.id,
                ),
            )
            if self._fts:
                self._db.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry.id,))
                self._db.execute(
                    "INSERT INTO entries_fts (content, entry_id) VALUES (?, ?)",
                    (entry.content, entry.id),
                )
        return entry

    def delete(self, entry_id: str) -> bool:
        with self._lock, self._db:
            cur = self._db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            if cur.rowcount == 0:
                return False
            if self._fts:
                self._db.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry_id,))
            self._db.execute("DELETE FROM versions WHERE entry_id = ?", (entry_id,))
        return True

    # -- reads --------------------------------------------------------------
    def get(self, entry_id: str) -> Optional[ContextEntry]:
        with self._lock:
            row = self._db.execute(
                f"SELECT {self._COLS} FROM entries WHERE id = ?", (entry_id,)
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def search(
        self,
        query: str,
        *,
        namespace: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        limit: int = 10,
    ) -> List[ContextEntry]:
        if not query.strip():
            return self.list(namespace=namespace, tags=tags, limit=limit)
        with self._lock:
            if self._fts:
                try:
                    sql = (
                        f"SELECT e.{', e.'.join(self._COLS.split(', '))} FROM entries e"
                        " JOIN entries_fts f ON f.entry_id = e.id"
                        " WHERE entries_fts MATCH ?"
                    )
                    params: List[Any] = [query]
                    if namespace is not None:
                        sql += " AND e.namespace = ?"
                        params.append(namespace)
                    sql += " ORDER BY bm25(entries_fts) LIMIT ?"
                    params.append(max(limit * 4, limit) if tags else limit)
                    rows = self._db.execute(sql, params).fetchall()
                except sqlite3.OperationalError:
                    rows = self._like_search(query, namespace)
            else:
                rows = self._like_search(query, namespace)
        entries = [self._row_to_entry(r) for r in rows]
        out = [e for e in entries if self._tags_match(e.tags, tags)]
        return out[:limit]

    def _like_search(self, query: str, namespace: Optional[str]) -> List[tuple]:
        terms = [t.lower() for t in query.split() if t.strip()]
        sql = f"SELECT {self._COLS} FROM entries"
        params: List[Any] = []
        if namespace is not None:
            sql += " WHERE namespace = ?"
            params.append(namespace)
        rows = self._db.execute(sql, params).fetchall()

        def score(row: tuple) -> int:
            text = row[2].lower()
            return sum(text.count(t) for t in terms)

        return sorted((r for r in rows if score(r) > 0), key=score, reverse=True)

    def list(
        self,
        *,
        namespace: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        limit: int = 1000,
    ) -> List[ContextEntry]:
        sql = f"SELECT {self._COLS} FROM entries"
        params: List[Any] = []
        if namespace is not None:
            sql += " WHERE namespace = ?"
            params.append(namespace)
        sql += " ORDER BY pinned DESC, updated_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._db.execute(sql, params).fetchall()
        entries = [self._row_to_entry(r) for r in rows]
        return [e for e in entries if self._tags_match(e.tags, tags)]

    def get_version(self, entry_id: str, version: int) -> Optional[ContextEntry]:
        current = self.get(entry_id)
        if current is None:
            return None
        if version == current.version:
            return current
        with self._lock:
            row = self._db.execute(
                "SELECT content, tags, metadata, tokens, updated_at FROM versions"
                " WHERE entry_id = ? AND version = ?",
                (entry_id, version),
            ).fetchone()
        if row is None:
            return None
        return ContextEntry(
            id=entry_id, content=row[0], tags=json.loads(row[1]),
            metadata=json.loads(row[2]), updated_at=row[4], version=version,
            namespace=current.namespace, provenance=current.provenance,
            tier=current.tier, pinned=current.pinned, importance=current.importance,
            created_at=current.created_at, tokens=row[3],
        )

    def list_versions(self, entry_id: str) -> List[int]:
        with self._lock:
            old = [
                r[0]
                for r in self._db.execute(
                    "SELECT version FROM versions WHERE entry_id = ? ORDER BY version",
                    (entry_id,),
                ).fetchall()
            ]
        cur = self.get(entry_id)
        return old + ([cur.version] if cur else [])

    def stats(self, *, namespace: Optional[str] = None) -> Dict[str, Any]:
        sql = "SELECT namespace, tier, pinned, tokens FROM entries"
        params: List[Any] = []
        if namespace is not None:
            sql += " WHERE namespace = ?"
            params.append(namespace)
        with self._lock:
            rows = self._db.execute(sql, params).fetchall()
        by_ns: Dict[str, Dict[str, int]] = {}
        by_tier: Dict[str, Dict[str, int]] = {}
        total_tokens = 0
        pinned = 0
        for ns, tier, pin, tokens in rows:
            by_ns.setdefault(ns, {"entries": 0, "tokens": 0})
            by_ns[ns]["entries"] += 1
            by_ns[ns]["tokens"] += tokens
            by_tier.setdefault(tier, {"entries": 0, "tokens": 0})
            by_tier[tier]["entries"] += 1
            by_tier[tier]["tokens"] += tokens
            total_tokens += tokens
            pinned += pin
        return {
            "entries": len(rows),
            "tokens": total_tokens,
            "pinned": pinned,
            "namespaces": by_ns,
            "tiers": by_tier,
        }

    def close(self) -> None:
        with self._lock:
            self._db.close()


class InMemoryBackend:
    """Same contract as SQLiteBackend, nothing persisted. For tests and demos.

    Entries are copied in and out so caller-side mutation can't corrupt the store
    or its version history.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: Dict[str, ContextEntry] = {}
        self._versions: Dict[str, Dict[int, ContextEntry]] = {}

    @staticmethod
    def _copy(e: ContextEntry) -> ContextEntry:
        return ContextEntry(
            id=e.id, content=e.content, namespace=e.namespace, tags=list(e.tags),
            provenance=e.provenance, tier=e.tier, pinned=e.pinned,
            importance=e.importance, version=e.version, created_at=e.created_at,
            updated_at=e.updated_at, tokens=e.tokens, metadata=dict(e.metadata),
        )

    @staticmethod
    def _tags_match(entry_tags: List[str], wanted: Optional[Sequence[str]]) -> bool:
        return not wanted or all(t in entry_tags for t in wanted)

    def add(self, entry: ContextEntry) -> ContextEntry:
        now = time.time()
        entry.created_at = entry.created_at or now
        entry.updated_at = now
        entry.version = 1
        with self._lock:
            self._entries[entry.id] = self._copy(entry)
            self._versions[entry.id] = {}
        return entry

    def get(self, entry_id: str) -> Optional[ContextEntry]:
        with self._lock:
            e = self._entries.get(entry_id)
            return self._copy(e) if e else None

    def update(self, entry: ContextEntry) -> ContextEntry:
        with self._lock:
            old = self._entries.get(entry.id)
            if old is None:
                raise KeyError(f"no such entry: {entry.id}")
            self._versions[entry.id][old.version] = self._copy(old)
            entry.version = old.version + 1
            entry.created_at = old.created_at
            entry.updated_at = time.time()
            self._entries[entry.id] = self._copy(entry)
        return entry

    def delete(self, entry_id: str) -> bool:
        with self._lock:
            if entry_id not in self._entries:
                return False
            del self._entries[entry_id]
            self._versions.pop(entry_id, None)
        return True

    def search(
        self,
        query: str,
        *,
        namespace: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        limit: int = 10,
    ) -> List[ContextEntry]:
        terms = [t.lower() for t in query.split() if t.strip()]
        with self._lock:
            candidates = list(self._entries.values())

        def score(e: ContextEntry) -> float:
            text = e.content.lower()
            return sum(text.count(t) for t in terms) * max(e.importance, 0.01)

        hits = [
            e
            for e in candidates
            if (namespace is None or e.namespace == namespace)
            and self._tags_match(e.tags, tags)
            and (not terms or score(e) > 0)
        ]
        hits.sort(key=lambda e: (-score(e), -e.updated_at))
        return [self._copy(e) for e in hits[:limit]]

    def list(
        self,
        *,
        namespace: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        limit: int = 1000,
    ) -> List[ContextEntry]:
        with self._lock:
            entries = [
                e
                for e in self._entries.values()
                if (namespace is None or e.namespace == namespace)
                and self._tags_match(e.tags, tags)
            ]
        entries.sort(key=lambda e: (not e.pinned, -e.updated_at))
        return [self._copy(e) for e in entries[:limit]]

    def get_version(self, entry_id: str, version: int) -> Optional[ContextEntry]:
        current = self._entries.get(entry_id)
        if current is None:
            return None
        if version == current.version:
            return self._copy(current)
        old = self._versions.get(entry_id, {}).get(version)
        return self._copy(old) if old else None

    def list_versions(self, entry_id: str) -> List[int]:
        current = self._entries.get(entry_id)
        if current is None:
            return []
        return sorted(self._versions.get(entry_id, {})) + [current.version]

    def stats(self, *, namespace: Optional[str] = None) -> Dict[str, Any]:
        entries = [
            e for e in self._entries.values() if namespace is None or e.namespace == namespace
        ]
        by_ns: Dict[str, Dict[str, int]] = {}
        by_tier: Dict[str, Dict[str, int]] = {}
        for e in entries:
            by_ns.setdefault(e.namespace, {"entries": 0, "tokens": 0})
            by_ns[e.namespace]["entries"] += 1
            by_ns[e.namespace]["tokens"] += e.tokens
            by_tier.setdefault(e.tier, {"entries": 0, "tokens": 0})
            by_tier[e.tier]["entries"] += 1
            by_tier[e.tier]["tokens"] += e.tokens
        return {
            "entries": len(entries),
            "tokens": sum(e.tokens for e in entries),
            "pinned": sum(1 for e in entries if e.pinned),
            "namespaces": by_ns,
            "tiers": by_tier,
        }

    def close(self) -> None:
        pass
