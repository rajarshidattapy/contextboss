from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

_COUNTER = itertools.count(1)


class Tier(IntEnum):
    """Lower value = higher priority. Order is the order of injection."""

    SYSTEM = 0
    TASK = 1
    MEMORY = 2
    RETRIEVAL = 3
    TOOLS = 4

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass
class ContextItem:
    """One candidate block for the window."""

    tier: Tier
    content: str
    priority: float = 1.0  # relevance within its tier, higher wins
    id: str = ""
    # Cheaper stand-in used when the full item doesn't fit. Optional.
    compact: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tokens: int = 0  # filled in by the assembler

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"{self.tier.label}:{next(_COUNTER)}"


@dataclass
class ToolSpec:
    """A tool schema. Costs tokens every call, so it gets its own allocator."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    priority: float = 1.0

    def full(self) -> str:
        return json.dumps(
            {"name": self.name, "description": self.description, "parameters": self.parameters},
            separators=(",", ":"),
        )

    def short(self) -> str:
        return json.dumps({"name": self.name, "description": self.description}, separators=(",", ":"))


@dataclass
class Decision:
    item_id: str
    tier: Tier
    action: str  # included | compacted | summarized | dropped
    tokens: int
    reason: str
    preview: str = ""


@dataclass
class TierUsage:
    tier: Tier
    allocated: int
    used: int


@dataclass
class AssembledContext:
    messages: list[ContextItem]
    decisions: list[Decision]
    usage: list[TierUsage]
    budget: int
    output_reserve: int

    @property
    def total_tokens(self) -> int:
        return sum(m.tokens for m in self.messages)

    @property
    def window(self) -> int:
        return self.budget - self.output_reserve

    def render(self, sep: str = "\n\n") -> str:
        return sep.join(m.content for m in self.messages)

    def dropped(self) -> list[Decision]:
        return [d for d in self.decisions if d.action == "dropped"]
