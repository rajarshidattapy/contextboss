from __future__ import annotations

from .budget import DYNAMIC_TIERS, BudgetPolicy
from .memory import MemoryStore
from .retrieval import Retriever
from .summarize import Summarizer, extractive_summary
from .tokenizer import Tokenizer, default_tokenizer
from .types import (
    AssembledContext,
    ContextItem,
    Decision,
    Tier,
    TierUsage,
    ToolSpec,
)


class ContextOverflowError(ValueError):
    """The pinned content (system prompt) alone cannot fit in the window."""


class ContextAssembler:
    """Fills a fixed token window by priority, and never overflows it.

    Order of play:
      1. system + task are pinned (task is truncated if it must be).
      2. the rest of the window is split across memory / retrieval / tools
         by BudgetPolicy, with unused share flowing to hungry tiers.
      3. inside each tier: best priority first; if an item doesn't fit, try its
         compact form, then a summary, then drop it.
      4. leftover tokens are offered back to dropped items, in tier order.
      5. a final invariant check guarantees total <= window.
    """

    def __init__(
        self,
        budget: int = 8000,
        output_reserve: int = 1000,
        tokenizer: Tokenizer | None = None,
        policy: BudgetPolicy | None = None,
        summarizer: Summarizer | None = None,
        min_summary_tokens: int = 40,
    ) -> None:
        if output_reserve >= budget:
            raise ValueError("output_reserve must be smaller than budget")
        self.budget = budget
        self.output_reserve = output_reserve
        self.tokenizer = tokenizer or default_tokenizer()
        self.policy = policy or BudgetPolicy()
        self.summarizer = summarizer or extractive_summary(self.tokenizer)
        self.min_summary_tokens = min_summary_tokens
        self._items: list[ContextItem] = []
        self._previews: dict[str, str] = {}

    # ---- building the candidate set -------------------------------------
    def add(self, item: ContextItem) -> ContextItem:
        self._items.append(item)
        return item

    def system(self, text: str) -> ContextItem:
        return self.add(ContextItem(Tier.SYSTEM, text, id="system"))

    def task(self, text: str) -> ContextItem:
        return self.add(ContextItem(Tier.TASK, text, id="task"))

    def memory(self, text: str, priority: float = 1.0, compact: str | None = None) -> ContextItem:
        return self.add(ContextItem(Tier.MEMORY, text, priority, compact=compact))

    def retrieve(self, text: str, priority: float = 1.0, source: str = "") -> ContextItem:
        return self.add(
            ContextItem(Tier.RETRIEVAL, text, priority, metadata={"source": source})
        )

    def tool(self, spec: ToolSpec) -> ContextItem:
        return self.add(
            ContextItem(
                Tier.TOOLS, spec.full(), spec.priority, id=f"tool:{spec.name}", compact=spec.short()
            )
        )

    def load_memory(self, store: MemoryStore, query: str, k: int = 10) -> None:
        for m, score in store.recall(query, k):
            self.memory(m.text, priority=score)

    def load_retrieval(self, retriever: Retriever, query: str, k: int = 10) -> None:
        for chunk, score in retriever.search(query, k):
            self.retrieve(chunk.text, priority=score, source=chunk.source)

    # ---- assembly ---------------------------------------------------------
    def assemble(self) -> AssembledContext:
        window = self.budget - self.output_reserve
        decisions: list[Decision] = []
        chosen: list[ContextItem] = []

        items = [self._copy(i) for i in self._items]
        for it in items:
            it.tokens = self.tokenizer.count(it.content)
        self._previews = {i.id: " ".join(i.content.split())[:46] for i in items}

        # 1. pinned tiers
        system = [i for i in items if i.tier is Tier.SYSTEM]
        sys_tokens = sum(i.tokens for i in system)
        if sys_tokens > window:
            raise ContextOverflowError(
                f"system prompt is {sys_tokens} tokens, window is {window}"
            )
        for i in system:
            chosen.append(i)
            decisions.append(self._d(i.id, i.tier, "included", i.tokens, "pinned"))

        task_room = window - sys_tokens
        for i in (x for x in items if x.tier is Tier.TASK):
            if i.tokens > task_room:
                i.content = self.tokenizer.truncate(i.content, task_room)
                new = self.tokenizer.count(i.content)
                decisions.append(
                    self._d(i.id, i.tier, "summarized", new, f"task cut {i.tokens}->{new} to fit window")
                )
                i.tokens = new
            else:
                decisions.append(self._d(i.id, i.tier, "included", i.tokens, "pinned"))
            task_room -= i.tokens
            chosen.append(i)

        pool = max(0, task_room)

        # 2. split the pool
        by_tier: dict[Tier, list[ContextItem]] = {t: [] for t in DYNAMIC_TIERS}
        for i in items:
            if i.tier in by_tier:
                by_tier[i.tier].append(i)
        demand = {t: sum(i.tokens for i in lst) for t, lst in by_tier.items()}
        alloc = self.policy.allocate(pool, demand)

        # 3. fill each tier
        used: dict[Tier, int] = {t: 0 for t in DYNAMIC_TIERS}
        leftovers: list[ContextItem] = []
        for tier in DYNAMIC_TIERS:
            room = alloc[tier]
            for it in sorted(by_tier[tier], key=lambda x: -x.priority):
                room, kept = self._place(it, tier, room, decisions)
                if kept:
                    chosen.append(it)
                    used[tier] += it.tokens
                else:
                    leftovers.append(it)

        # 4. spill: unused window goes back to whoever got dropped
        free = pool - sum(used.values())
        for it in leftovers:
            if it.tokens <= free:
                free -= it.tokens
                used[it.tier] += it.tokens
                chosen.append(it)
                decisions = [d for d in decisions if not (d.item_id == it.id and d.action == "dropped")]
                decisions.append(self._d(it.id, it.tier, "included", it.tokens, "spill: window had room left"))

        chosen.sort(key=lambda x: (x.tier, -x.priority))

        # 5. invariant
        total = sum(i.tokens for i in chosen)
        if total > window:  # pragma: no cover - guards future edits
            raise ContextOverflowError(f"assembled {total} > window {window}")

        usage = [TierUsage(Tier.SYSTEM, sys_tokens, sys_tokens)]
        usage.append(
            TierUsage(Tier.TASK, sum(i.tokens for i in chosen if i.tier is Tier.TASK), sum(i.tokens for i in chosen if i.tier is Tier.TASK))
        )
        usage += [TierUsage(t, alloc[t], used[t]) for t in DYNAMIC_TIERS]
        return AssembledContext(chosen, decisions, usage, self.budget, self.output_reserve)

    # ---- internals --------------------------------------------------------
    def _place(self, it: ContextItem, tier: Tier, room: int, decisions: list[Decision]):
        """Try full, compact, summary, drop. Returns (room_left, kept)."""
        if it.tokens <= room:
            decisions.append(self._d(it.id, tier, "included", it.tokens, f"fits tier budget ({room} left)"))
            return room - it.tokens, True

        if it.compact is not None:
            n = self.tokenizer.count(it.compact)
            if n <= room:
                decisions.append(self._d(it.id, tier, "compacted", n, f"full {it.tokens} too big, used compact form"))
                it.content, it.tokens = it.compact, n
                return room - n, True

        if tier is not Tier.TOOLS and room >= self.min_summary_tokens:
            short = self.summarizer(it.content, room)
            n = self.tokenizer.count(short) if short else 0
            if short and n <= room:
                decisions.append(self._d(it.id, tier, "summarized", n, f"{it.tokens} -> {n} tokens to fit"))
                it.content, it.tokens = short, n
                return room - n, True

        decisions.append(self._d(it.id, tier, "dropped", 0, f"needs {it.tokens}, tier has {room}"))
        return room, False

    def _d(self, item_id, tier, action, tokens, reason):
        return Decision(item_id, tier, action, tokens, reason, preview=self._previews.get(item_id, ""))

    @staticmethod
    def _copy(i: ContextItem) -> ContextItem:
        return ContextItem(i.tier, i.content, i.priority, i.id, i.compact, dict(i.metadata))
