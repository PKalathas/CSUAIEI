"""Azure AI Search-backed knowledge base."""

from __future__ import annotations

import logging

from .base import RetrievedDoc

logger = logging.getLogger(__name__)


class AzureSearchKB:
    """Backed by `azure.search.documents.SearchClient`.

    The `azure-search-documents` package is imported lazily so the harness
    doesn't hard-require it when only `NullKB` is in use.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        index_name: str,
        *,
        default_top: int = 3,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._index = index_name
        self._default_top = default_top

    def search(self, query: str, top: int | None = None) -> list[RetrievedDoc]:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        client = SearchClient(
            endpoint=self._endpoint,
            index_name=self._index,
            credential=AzureKeyCredential(self._api_key),
        )
        results = client.search(search_text=query, top=top or self._default_top)

        docs: list[RetrievedDoc] = []
        for result in results:
            try:
                uid = f"{result['parent_id']}_{result['chunk_id']}"
                content = result["chunk"]
                source = result["title"]
            except (KeyError, TypeError):
                continue
            docs.append(RetrievedDoc(content=content, source=source, uid=uid))
        return docs
