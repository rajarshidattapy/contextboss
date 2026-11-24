"""Token counting. tiktoken when available, a conservative heuristic otherwise."""
from __future__ import annotations

from typing import Protocol


class Tokenizer(Protocol):
    def count(self, text: str) -> int: ...

    def truncate(self, text: str, max_tokens: int) -> str: ...


class TiktokenTokenizer:
    """Exact counts for OpenAI-style encodings."""

    def __init__(self, encoding: str = "cl100k_base") -> None:
        import tiktoken

        self._enc = tiktoken.get_encoding(encoding)

    def count(self, text: str) -> int:
        return len(self._enc.encode(text, disallowed_special=()))

    def truncate(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0:
            return ""
        ids = self._enc.encode(text, disallowed_special=())
        return text if len(ids) <= max_tokens else self._enc.decode(ids[:max_tokens])


class HeuristicTokenizer:
    """~3.5 chars per token. Rounds up, so it errs on the safe side."""

    CHARS_PER_TOKEN = 3.5

    def count(self, text: str) -> int:
        return int(len(text) / self.CHARS_PER_TOKEN) + (1 if text else 0)

    def truncate(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0:
            return ""
        return text[: int(max_tokens * self.CHARS_PER_TOKEN)]


def default_tokenizer() -> Tokenizer:
    try:
        return TiktokenTokenizer()
    except Exception:  # missing package or offline vocab download
        return HeuristicTokenizer()
