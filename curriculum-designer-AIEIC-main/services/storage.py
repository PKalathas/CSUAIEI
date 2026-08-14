"""
Storage abstraction.

Stage A (v0.1): in-memory dict, thread-safe via a single Lock.
Stage D / v0.2: drop-in CosmosStore against container `curriculum`,
                partition key `/lab_id`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from threading import Lock

from models.curriculum import LabMaterial


class CurriculumStore(ABC):
    """Abstract base. All implementations must be safe for concurrent calls."""

    @abstractmethod
    def get(self, lab_id: str) -> LabMaterial | None: ...

    @abstractmethod
    def put(self, material: LabMaterial) -> None: ...

    @abstractmethod
    def list(self) -> list[LabMaterial]: ...

    @abstractmethod
    def delete(self, lab_id: str) -> bool: ...


class MemoryStore(CurriculumStore):
    """In-memory dict-backed store. Good enough for v0.1 + tests."""

    def __init__(self) -> None:
        self._data: dict[str, LabMaterial] = {}
        self._lock = Lock()

    def get(self, lab_id: str) -> LabMaterial | None:
        with self._lock:
            return self._data.get(lab_id)

    def put(self, material: LabMaterial) -> None:
        with self._lock:
            self._data[material.lab_id] = material

    def list(self) -> list[LabMaterial]:
        with self._lock:
            return list(self._data.values())

    def delete(self, lab_id: str) -> bool:
        with self._lock:
            return self._data.pop(lab_id, None) is not None


def build_store(backend: str) -> CurriculumStore:
    """Factory called from main.py during lifespan."""
    backend = backend.lower()
    if backend == "memory":
        return MemoryStore()
    if backend == "cosmos":
        raise NotImplementedError(
            "CosmosStore lands in v0.2 — set STORAGE_BACKEND=memory for now."
        )
    raise ValueError(f"Unknown storage backend: {backend!r}")
