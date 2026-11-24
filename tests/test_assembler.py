import pytest

from contextboss import (
    BudgetPolicy, ContextAssembler, ContextOverflowError, HeuristicTokenizer, MemoryStore,
    Retriever, Tier, ToolSpec,
)
from contextboss.demo import build

TOK = HeuristicTokenizer()


def make(budget=400, reserve=50):
    return ContextAssembler(budget=budget, output_reserve=reserve, tokenizer=TOK)


@pytest.mark.parametrize("budget", [120, 300, 600, 900, 2000, 8000])
def test_never_overflows(budget):
    ctx = build(budget, output_reserve=40, tokenizer=TOK).assemble()
    assert ctx.total_tokens <= ctx.window


def test_priority_order_and_tier_order():
    a = make(budget=2000)
    a.retrieve("doc", 1.0)
    a.memory("mem low", 0.1)
    a.memory("mem high", 5.0)
    a.task("do it")
    a.system("be good")
    ctx = a.assemble()
    tiers = [m.tier for m in ctx.messages]
    assert tiers == sorted(tiers)
    mem = [m.content for m in ctx.messages if m.tier is Tier.MEMORY]
    assert mem == ["mem high", "mem low"]


def test_low_priority_dropped_first():
    a = make(budget=200, reserve=20)
    a.system("sys")
    a.task("task")
    a.retrieve("x" * 300, priority=9.0)   # ~86 tokens
    a.retrieve("y" * 300, priority=0.1)
    a.retrieve("z" * 300, priority=0.2)
    ctx = a.assemble()
    kept = {m.content[0] for m in ctx.messages if m.tier is Tier.RETRIEVAL}
    assert "x" in kept and "y" not in kept


def test_summarizes_instead_of_dropping():
    a = make(budget=300, reserve=20)
    a.system("sys")
    a.task("task")
    a.retrieve(" ".join(f"Sentence number {i} has some filler words." for i in range(60)), 1.0)
    ctx = a.assemble()
    assert any(d.action == "summarized" for d in ctx.decisions)
    assert ctx.total_tokens <= ctx.window


def test_tools_fall_back_to_compact_schema():
    a = make(budget=260, reserve=20)
    a.system("s")
    a.task("t")
    a.tool(ToolSpec("big", "does a thing", {"type": "object", "properties": {f"p{i}": {"type": "string"} for i in range(40)}}))
    ctx = a.assemble()
    d = [d for d in ctx.decisions if d.item_id == "tool:big"][0]
    assert d.action in {"compacted", "included"}


def test_unused_budget_flows_to_hungry_tier():
    pool = 1000
    alloc = BudgetPolicy().allocate(pool, {Tier.MEMORY: 10, Tier.RETRIEVAL: 5000, Tier.TOOLS: 0})
    assert alloc[Tier.MEMORY] == 10
    assert alloc[Tier.TOOLS] == 0
    assert alloc[Tier.RETRIEVAL] > 500  # more than its 50% guarantee
    assert alloc[Tier.RETRIEVAL] <= 750  # but never past its cap
    assert sum(alloc.values()) <= pool


def test_oversized_task_is_truncated_not_fatal():
    a = make(budget=120, reserve=20)
    a.system("sys")
    a.task("word " * 500)
    ctx = a.assemble()
    assert ctx.total_tokens <= ctx.window


def test_oversized_system_raises():
    a = make(budget=100, reserve=20)
    a.system("x" * 1000)
    with pytest.raises(ContextOverflowError):
        a.assemble()


def test_memory_and_retrieval_rank_relevant_first():
    s = MemoryStore()
    s.add("The user likes sushi")
    s.add("Rate limit upgrades happened last week")
    assert s.recall("rate limit", 1)[0][0].text.startswith("Rate limit")
    r = Retriever()
    r.index("a", "cats and dogs\n\nrate limits and 429 errors")
    assert "429" in r.search("429 rate limit", 1)[0][0].text


def test_reassemble_with_new_budget_is_pure():
    a = build(900, tokenizer=TOK)
    first = a.assemble().total_tokens
    a.budget = 3000
    assert a.assemble().total_tokens >= first
    a.budget = 900
    assert a.assemble().total_tokens == first
