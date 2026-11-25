"""ContextManager: the facade over storage, budgeting and assembly.

One object gives agents the whole lifecycle: add context, search it, pin it,
compress it, delete it for real, and assemble a window-safe prompt from it.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Union

from .assembler import ContextAssembler
from .models import ContextEntry
from .storage import InMemoryBackend, SQLiteBackend, StorageBackend
from .summarize import Summarizer, extractive_summary
from .tokenizer import Tokenizer, default_tokenizer
from .types import AssembledContext, Tier, ToolSpec

_TIER_BY_NAME = {t.label: t for t in Tier}
_VALID_TIERS = frozenset(_TIER_BY_NAME)


class ContextManager:
    """Persistent context store + budget-aware assembler.

    backend: a StorageBackend, a path for a SQLite database, ":memory:", or None
    (in-memory store).
    """

    def __init__(
        self,
        backend: Union[StorageBackend, str, None] = None,
        *,
        tokenizer: Optional[Tokenizer] = None,
        summarizer: Optional[Summarizer] = None,
        budget: int = 8000,
        output_reserve: int = 1000,
    ) -> None:
        self.tokenizer = tokenizer or default_tokenizer()
        self.summarizer = summarizer or extractive_summary(self.tokenizer)
        self.budget = budget
        self.output_reserve = output_reserve
        if backend is None or backend == ":memory:":
            self.store: StorageBackend = InMemoryBackend()
        elif isinstance(backend, (str, os.PathLike)):
            self.store = SQLiteBackend(str(backend))
        else:
            self.store = backend

    # -- lifecycle ---------------------------------------------------------
    def add(
        self,
        content: str,
        *,
        namespace: str = "default",
        tags: Optional[Sequence[str]] = None,
        provenance: str = "",
        tier: str = "memory",
        pinned: bool = False,
        importance: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextEntry:
        if tier not in _VALID_TIERS:
            raise ValueError(f"tier must be one of {sorted(_VALID_TIERS)}, got {tier!r}")
        entry = ContextEntry(
            content=content,
            namespace=namespace,
            tags=list(tags or ()),
            provenance=provenance,
            tier=tier,
            pinned=pinned,
            importance=importance,
            tokens=self.tokenizer.count(content),
            metadata=dict(metadata or {}),
        )
        return self.store.add(entry)

    def get(self, entry_id: str) -> Optional[ContextEntry]:
        return self.store.get(entry_id)

    def update(
        self,
        entry_id: str,
        content: Optional[str] = None,
        *,
        namespace: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        provenance: Optional[str] = None,
        tier: Optional[str] = None,
        pinned: Optional[bool] = None,
        importance: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextEntry:
        entry = self.store.get(entry_id)
        if entry is None:
            raise KeyError(f"no such entry: {entry_id}")
        if tier is not None and tier not in _VALID_TIERS:
            raise ValueError(f"tier must be one of {sorted(_VALID_TIERS)}, got {tier!r}")
        if content is not None:
            entry.content = content
        if namespace is not None:
            entry.namespace = namespace
        if tags is not None:
            entry.tags = list(tags)
        if provenance is not None:
            entry.provenance = provenance
        if tier is not None:
            entry.tier = tier
        if pinned is not None:
            entry.pinned = pinned
        if importance is not None:
            entry.importance = importance
        if metadata is not None:
            entry.metadata = dict(metadata)
        entry.tokens = self.tokenizer.count(entry.content)
        return self.store.update(entry)

    def delete(self, entry_id: str) -> bool:
        """Hard delete: the entry, its search index rows and its version history."""
        return self.store.delete(entry_id)

    def search(
        self,
        query: str = "",
        *,
        namespace: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        limit: int = 10,
    ) -> List[ContextEntry]:
        return self.store.search(query, namespace=namespace, tags=tags, limit=limit)

    def list(
        self,
        *,
        namespace: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        limit: int = 1000,
    ) -> List[ContextEntry]:
        return self.store.list(namespace=namespace, tags=tags, limit=limit)

    # -- compression ---------------------------------------------------------
    def compact(self, entry_id: str, target_tokens: Optional[int] = None) -> ContextEntry:
        """Shrink an entry in place with the summarizer. Keeps version history."""
        entry = self.store.get(entry_id)
        if entry is None:
            raise KeyError(f"no such entry: {entry_id}")
        target = target_tokens or max(40, entry.tokens // 2)
        if entry.tokens <= target:
            return entry
        short = self.summarizer(entry.content, target)
        if not short:
            return entry
        return self.update(entry_id, short)

    # -- assembly -------------------------------------------------------------
    def assemble(
        self,
        query: str = "",
        *,
        system: Optional[str] = None,
        task: Optional[str] = None,
        tools: Optional[Sequence[ToolSpec]] = None,
        namespace: Optional[str] = None,
        budget: Optional[int] = None,
        output_reserve: Optional[int] = None,
        k: int = 50,
    ) -> AssembledContext:
        """Build a window-safe context from stored entries.

        Pinned entries always rank first in their tier. When a query is given,
        memory and retrieval entries are ranked by search relevance.
        """
        asm = ContextAssembler(
            budget=budget or self.budget,
            output_reserve=self.output_reserve if output_reserve is None else output_reserve,
            tokenizer=self.tokenizer,
            summarizer=self.summarizer,
        )
        if system is not None:
            asm.system(system)
        if task is not None:
            asm.task(task)

        if query:
            entries = self.store.search(query, namespace=namespace, limit=k)
            seen = {e.id for e in entries}
            for e in self.store.list(namespace=namespace, limit=k):
                if e.pinned and e.id not in seen:
                    entries.append(e)
        else:
            entries = self.store.list(namespace=namespace, limit=k)

        for e in entries:
            priority = (1e9 if e.pinned else 0.0) + max(e.importance, 0.0)
            if e.tier == Tier.SYSTEM.label:
                asm.system(e.content)
            elif e.tier == Tier.TASK.label:
                asm.task(e.content)
            elif e.tier == Tier.RETRIEVAL.label:
                asm.retrieve(e.content, priority=priority, source=e.provenance)
            else:
                asm.memory(e.content, priority=priority)
        for spec in tools or ():
            asm.tool(spec)
        return asm.assemble()

    # -- introspection ---------------------------------------------------------
    def inspect(self, entry_id: str) -> Dict[str, Any]:
        entry = self.store.get(entry_id)
        if entry is None:
            raise KeyError(f"no such entry: {entry_id}")
        return {
            "entry": entry.to_dict(),
            "versions": self.store.list_versions(entry_id),
        }

    def get_version(self, entry_id: str, version: int) -> Optional[ContextEntry]:
        return self.store.get_version(entry_id, version)

    def stats(self, *, namespace: Optional[str] = None) -> Dict[str, Any]:
        return self.store.stats(namespace=namespace)

    def close(self) -> None:
        self.store.close()

    def __enter__(self) -> "ContextManager":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
