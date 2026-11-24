"""Demo scenario: a support agent with way too much context for its window."""
from __future__ import annotations

from .assembler import ContextAssembler
from .memory import MemoryStore
from .retrieval import Retriever
from .types import ToolSpec

SYSTEM = (
    "You are Atlas, a senior support engineer for Northwind Cloud. Be precise, cite "
    "sources from the provided docs, never invent API behavior, and ask a clarifying "
    "question when the ticket is ambiguous."
)
TASK = (
    "Ticket #4821: Our nightly export job started failing with HTTP 429 after we "
    "upgraded to the Pro plan. Retry logic is exponential backoff with no jitter. "
    "What is going on and what should we change?"
)

MEMORIES = [
    ("Customer is on the Pro plan since 2026-10-02, upgraded from Starter.", 2.0),
    ("Customer's export job runs at 00:00 UTC across 40 parallel workers.", 2.0),
    ("Customer prefers short answers with a code sample.", 1.0),
    ("Last ticket (#4710) was about invoice PDFs, unrelated to rate limits.", 0.5),
    ("Customer's account manager is Priya; escalate billing questions to her.", 0.6),
    ("Customer once asked about SOC 2 reports in March.", 0.3),
]

DOCS = {
    "rate-limits.md": (
        "Pro plan rate limits are 600 requests per minute per API key, enforced with a "
        "sliding window. Starter allowed 120 per minute but was not enforced per key.\n\n"
        "A 429 response includes a Retry-After header. Clients must honor it. Exponential "
        "backoff without jitter makes parallel workers retry in lockstep and trip the "
        "limit again.\n\n"
        "Bulk export endpoints accept a batch parameter of up to 500 records per call, "
        "which cuts request volume by roughly 50x versus single record calls. "
        "Batching is the recommended fix for jobs that hit the per key limit."
    ),
    "billing.md": (
        "Invoices are generated on the first of each month. Proration applies when you "
        "change plans mid cycle. Refunds are issued to the original payment method within "
        "ten business days.\n\n"
        "Enterprise customers can pay by purchase order. Contact sales for terms."
    ),
    "sdk-python.md": (
        "The Python SDK retries 429 and 5xx responses by default with full jitter. Set "
        "max_retries to control it. The SDK reads Retry-After automatically.\n\n"
        "Upgrade to SDK 3.2 or later to get jitter. Older versions retry on a fixed schedule."
    ),
    "status-history.md": (
        "2026-10-14: elevated 429 rates on the export gateway for 22 minutes. Resolved.\n\n"
        "2026-09-02: scheduled maintenance, no customer impact.\n\n"
        "2026-08-11: elevated latency in eu-west. Resolved."
    ),
}

TOOLS = [
    ToolSpec(
        "lookup_account",
        "Fetch plan, limits and usage for an account id.",
        {"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]},
        priority=3.0,
    ),
    ToolSpec(
        "get_rate_limit_usage",
        "Return per-minute request counts for an API key over a time window, with 429 counts.",
        {
            "type": "object",
            "properties": {
                "api_key_id": {"type": "string"},
                "from": {"type": "string", "format": "date-time"},
                "to": {"type": "string", "format": "date-time"},
                "granularity": {"type": "string", "enum": ["minute", "hour"]},
            },
            "required": ["api_key_id", "from", "to"],
        },
        priority=2.5,
    ),
    ToolSpec(
        "create_jira_issue",
        "File an engineering issue with title, body, severity and labels attached.",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "labels": {"type": "array", "items": {"type": "string"}},
                "assignee": {"type": "string"},
            },
            "required": ["title", "body"],
        },
        priority=1.0,
    ),
    ToolSpec(
        "send_invoice_copy",
        "Email a copy of a past invoice to the billing contact.",
        {"type": "object", "properties": {"invoice_id": {"type": "string"}, "to": {"type": "string"}}},
        priority=0.4,
    ),
]


def build(budget: int, output_reserve: int = 256, tokenizer=None) -> ContextAssembler:
    asm = ContextAssembler(budget=budget, output_reserve=output_reserve, tokenizer=tokenizer)
    asm.system(SYSTEM)
    asm.task(TASK)

    store = MemoryStore()
    for text, imp in MEMORIES:
        store.add(text, imp)
    asm.load_memory(store, TASK, k=6)

    retriever = Retriever()
    for src, text in DOCS.items():
        retriever.index(src, text)
    asm.load_retrieval(retriever, TASK, k=8)

    for t in TOOLS:
        asm.tool(t)
    return asm
