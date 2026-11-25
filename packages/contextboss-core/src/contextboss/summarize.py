"""Graceful degradation: shrink text to fit instead of dropping it."""
from __future__ import annotations

import re
from collections.abc import Callable

from .tokenizer import Tokenizer

# (text, max_tokens) -> shorter text. Swap in an LLM summarizer if you want one.
Summarizer = Callable[[str, int], str]

_SENT = re.compile(r"(?<=[.!?])\s+")


def extractive_summary(tokenizer: Tokenizer) -> Summarizer:
    """Keep leading sentences until the budget runs out, then mark the cut."""

    def run(text: str, max_tokens: int) -> str:
        marker = " [...]"
        room = max_tokens - tokenizer.count(marker)
        if room <= 0:
            return ""
        out, used = [], 0
        for sentence in _SENT.split(text.strip()):
            cost = tokenizer.count(sentence) + 1
            if used + cost > room:
                break
            out.append(sentence)
            used += cost
        if not out:  # first sentence alone is too long: hard cut
            return tokenizer.truncate(text, room).rstrip() + marker
        return " ".join(out) + marker

    return run
