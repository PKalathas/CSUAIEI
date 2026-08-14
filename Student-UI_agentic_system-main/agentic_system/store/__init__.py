"""Storage abstraction for the ADFEL harness.

Three protocols — `ParticipantStore`, `GuardianStore`, `SystemStore` —
define the entire persistence surface. The first two are per-course
(injected into `LabHarness`); `SystemStore` holds multi-tenant
metadata (users, courses, enrollments) and is used by the server layer.
"""

from .base import GuardianStore, ParticipantStore, SystemStore
from .sqlite import SqliteGuardianStore, SqliteParticipantStore
from .system import SqliteSystemStore

__all__ = [
    "ParticipantStore",
    "GuardianStore",
    "SystemStore",
    "SqliteParticipantStore",
    "SqliteGuardianStore",
    "SqliteSystemStore",
]
