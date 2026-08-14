"""
Contract test — verifies that MemoryIntegrityClient and CosmosIntegrityClient
expose the same public interface. If one adds or removes a method, this test
catches the divergence before it causes a runtime failure when switching between
demo mode and production.
"""

import inspect

from cosmos_client import CosmosIntegrityClient
from cosmos_client_memory import MemoryIntegrityClient


def _public_methods(cls: type) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(cls, predicate=inspect.isfunction)
        if not name.startswith("_")
    }


def test_memory_client_implements_all_cosmos_methods():
    missing = _public_methods(CosmosIntegrityClient) - _public_methods(MemoryIntegrityClient)
    assert not missing, f"MemoryIntegrityClient is missing: {missing}"


def test_no_extra_methods_on_memory_client():
    extra = _public_methods(MemoryIntegrityClient) - _public_methods(CosmosIntegrityClient)
    assert not extra, f"MemoryIntegrityClient has extra methods not in CosmosIntegrityClient: {extra}"
