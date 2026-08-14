"""LLM-client abstraction.

`LLMClient` is the protocol every agent and the policy engine talk to.
The shipped implementations are:

  - `AzureOpenAILLM` — default; talks to Azure OpenAI via the `openai` SDK.
  - `ClaudeLLM`      — talks to Anthropic via the `anthropic` SDK.

New providers (self-hosted, a stub for tests, etc.) implement the same
protocol and can be injected via `LabHarness.build(llm=...)`.
"""

from .azure_openai import AzureOpenAILLM
from .base import LLMClient
from .claude import ClaudeLLM

__all__ = ["LLMClient", "AzureOpenAILLM", "ClaudeLLM"]
