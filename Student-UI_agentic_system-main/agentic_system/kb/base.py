"""Knowledge-base protocol.

Lab Companion calls `kb.search(question)` once per turn to fetch RAG
context. Any backend that returns `list[RetrievedDoc]` works.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RetrievedDoc:
    content: str
    source: str
    uid: str


@runtime_checkable
class KnowledgeBase(Protocol):
    def search(self, query: str, top: int | None = None) -> list[RetrievedDoc]:
        """Return relevant chunks for `query`. May return [] when disabled."""


def format_context(docs: list[RetrievedDoc], max_content_chars: int = 1000) -> str:
    """Render retrieved docs into the system-prompt context block."""
    if not docs:
        return "(no course resources retrieved for this question)"

    def _truncate(text: str, max_len: int) -> str:
        return text if len(text) <= max_len else text[:max_len] + "... [truncated]"

    return "\n\n".join(
        f"Source: {d.source}\nContent: {_truncate(d.content, max_content_chars)}"
        for d in docs
    )
