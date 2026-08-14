"""Knowledge-base abstraction.

`KnowledgeBase` is the protocol; `AzureSearchKB` and `NullKB` are the
shipped implementations.
"""

from .azure_search import AzureSearchKB
from .base import KnowledgeBase, RetrievedDoc, format_context
from .null import NullKB

__all__ = ["KnowledgeBase", "RetrievedDoc", "AzureSearchKB", "NullKB", "format_context"]
