"""Dynamic token budgeting.

System and task are pinned. Whatever is left is split across memory, retrieval and
tools by weight, capped per tier, and unused share flows to tiers that still want it
(water-filling). So a quiet tier never wastes tokens a hungry one could use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .types import Tier

DYNAMIC_TIERS = (Tier.MEMORY, Tier.RETRIEVAL, Tier.TOOLS)


@dataclass
class BudgetPolicy:
    # Guaranteed share of the flexible pool, per tier. Must sum to ~1.
    weights: Dict[Tier, float] = field(
        default_factory=lambda: {Tier.MEMORY: 0.30, Tier.RETRIEVAL: 0.50, Tier.TOOLS: 0.20}
    )
    # Hard ceiling per tier, as a fraction of the flexible pool.
    caps: Dict[Tier, float] = field(
        default_factory=lambda: {Tier.MEMORY: 0.50, Tier.RETRIEVAL: 0.75, Tier.TOOLS: 0.35}
    )

    def allocate(self, pool: int, demand: Dict[Tier, int]) -> Dict[Tier, int]:
        """Split `pool` tokens across dynamic tiers given each tier's demand."""
        alloc = {t: 0 for t in DYNAMIC_TIERS}
        ceiling = {t: int(pool * self.caps[t]) for t in DYNAMIC_TIERS}
        want = {t: min(demand.get(t, 0), ceiling[t]) for t in DYNAMIC_TIERS}

        # Pass 1: everyone gets their guaranteed share, or their demand if smaller.
        total_w = sum(self.weights[t] for t in DYNAMIC_TIERS) or 1.0
        for t in DYNAMIC_TIERS:
            alloc[t] = min(want[t], int(pool * self.weights[t] / total_w))

        # Pass 2+: hand spare tokens to tiers that still want more, by weight.
        spare = pool - sum(alloc.values())
        while spare > 0:
            hungry = [t for t in DYNAMIC_TIERS if alloc[t] < want[t]]
            if not hungry:
                break
            w = sum(self.weights[t] for t in hungry) or 1.0
            moved = 0
            for t in hungry:
                give = min(want[t] - alloc[t], max(1, int(spare * self.weights[t] / w)))
                give = min(give, spare - moved)
                alloc[t] += give
                moved += give
            if moved == 0:
                break
            spare -= moved
        return alloc
