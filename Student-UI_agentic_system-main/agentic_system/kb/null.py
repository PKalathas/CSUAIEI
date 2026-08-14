"""No-op knowledge base — used when no KB is configured."""

from __future__ import annotations

from .base import RetrievedDoc


class NullKB:
    """Always returns no results. Lab Companion proceeds without RAG context."""

    def search(self, query: str, top: int | None = None) -> list[RetrievedDoc]:  # noqa: ARG002
        return []
