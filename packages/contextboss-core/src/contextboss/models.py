"""The persistent unit of context: one entry in the store."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List


def _now() -> float:
    return time.time()


@dataclass
class ContextEntry:
    """A stored piece of context with provenance, tags and versioning.

    `tier` is the assembly hint: system / task / memory / retrieval / tools.
    """

    content: str
    namespace: str = "default"
    tags: List[str] = field(default_factory=list)
    provenance: str = ""  # where this came from: tool name, file, url, session id...
    tier: str = "memory"
    pinned: bool = False
    importance: float = 1.0
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    version: int = 1
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "namespace": self.namespace,
            "tags": list(self.tags),
            "provenance": self.provenance,
            "tier": self.tier,
            "pinned": self.pinned,
            "importance": self.importance,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tokens": self.tokens,
            "metadata": dict(self.metadata),
        }
