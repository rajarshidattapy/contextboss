"""A tiny in-process memory store. Swap for a vector DB; keep the interface."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List, Tuple

_WORD = re.compile(r"[a-z0-9]+")


def _terms(text: str) -> set:
    return set(_WORD.findall(text.lower()))


@dataclass
class Memory:
    text: str
    importance: float = 1.0
    seq: int = 0


class MemoryStore:
    """Scores by keyword overlap x importance x recency decay."""

    def __init__(self, half_life: int = 20) -> None:
        self._items: List[Memory] = []
        self.half_life = half_life

    def add(self, text: str, importance: float = 1.0) -> Memory:
        m = Memory(text, importance, seq=len(self._items))
        self._items.append(m)
        return m

    def recall(self, query: str, k: int = 10) -> List[Tuple[Memory, float]]:
        q = _terms(query)
        now = len(self._items)
        scored = []
        for m in self._items:
            overlap = len(q & _terms(m.text)) / (len(q) or 1)
            recency = 0.5 ** ((now - 1 - m.seq) / self.half_life)
            score = (0.15 + overlap) * m.importance * (0.5 + 0.5 * recency)
            scored.append((m, round(score, 4)))
        scored.sort(key=lambda p: p[1], reverse=True)
        return scored[:k]
