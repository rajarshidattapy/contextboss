"""Retrieval stub: TF-IDF over paragraph chunks. Replace with your real retriever."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import List, Tuple

_WORD = re.compile(r"[a-z0-9]+")


@dataclass
class Chunk:
    source: str
    text: str


class Retriever:
    def __init__(self) -> None:
        self._chunks: List[Chunk] = []
        self._tf: List[Counter] = []
        self._df: Counter = Counter()

    def index(self, source: str, text: str) -> None:
        for para in re.split(r"\n\s*\n", text.strip()):
            para = para.strip()
            if not para:
                continue
            tf = Counter(_WORD.findall(para.lower()))
            self._chunks.append(Chunk(source, para))
            self._tf.append(tf)
            self._df.update(tf.keys())

    def search(self, query: str, k: int = 10) -> List[Tuple[Chunk, float]]:
        n = len(self._chunks) or 1
        q = _WORD.findall(query.lower())
        out = []
        for chunk, tf in zip(self._chunks, self._tf):
            length = sum(tf.values()) or 1
            score = sum(
                (tf[t] / length) * math.log(1 + n / (1 + self._df[t])) for t in q if t in tf
            )
            if score > 0:
                out.append((chunk, round(score, 4)))
        out.sort(key=lambda p: p[1], reverse=True)
        return out[:k]
