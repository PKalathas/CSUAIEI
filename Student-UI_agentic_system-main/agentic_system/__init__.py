"""
ADFEL — student-facing agentic tutoring harness.

Public API:

    from agentic_system import LabHarness, SystemConfig

    harness = LabHarness.build()
    state   = harness.start_session()
    result  = harness.handle_turn(state, "explain Thevenin equivalents")
    print(result.response, result.guidance_level)
    harness.end_session(state)

Custom backends (swap SQLite for a remote API, KB for a different
retriever, or the LLM for a different model) can be injected:

    harness = LabHarness.build(
        config=SystemConfig.from_env(),
        participant_store=MyRemoteStore(...),
        guardian_store=MyRemoteStore(...),
        knowledge_base=MyKB(...),
        llm=MyLLMClient(...),
    )
"""

from .api import LabHarness
from .config import SystemConfig
from .kb import AzureSearchKB, KnowledgeBase, NullKB, RetrievedDoc
from .llm import AzureOpenAILLM, ClaudeLLM, LLMClient
from .models import (
    GuidanceLevel,
    QuestionClassification,
    SessionState,
    TurnResult,
    ValidateResult,
    VerifyResult,
)
from .store import (
    GuardianStore,
    ParticipantStore,
    SqliteGuardianStore,
    SqliteParticipantStore,
    SqliteSystemStore,
    SystemStore,
)

__all__ = [
    # facade
    "LabHarness",
    "SystemConfig",
    # types the embedder reads
    "SessionState",
    "TurnResult",
    "GuidanceLevel",
    "QuestionClassification",
    "ValidateResult",
    "VerifyResult",
    # extension points
    "ParticipantStore",
    "GuardianStore",
    "SystemStore",
    "SqliteParticipantStore",
    "SqliteGuardianStore",
    "SqliteSystemStore",
    "KnowledgeBase",
    "RetrievedDoc",
    "AzureSearchKB",
    "NullKB",
    "LLMClient",
    "AzureOpenAILLM",
    "ClaudeLLM",
]
