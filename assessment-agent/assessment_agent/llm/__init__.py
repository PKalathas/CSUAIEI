"""
LLM provider package -- provider-agnostic interface for LLM inference.

Quick start
-----------
::

    from assessment_agent.llm import get_llm_provider

    provider = get_llm_provider()           # default: claude_cli
    result   = await provider.complete_json(prompt)

For backward compatibility the top-level ``claude_json`` helper is still
available and works exactly as before::

    from assessment_agent.llm import claude_json
    data = await claude_json(prompt)
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .base import LLMProvider, extract_json

if TYPE_CHECKING:
    pass

__all__ = [
    "LLMProvider",
    "extract_json",
    "get_llm_provider",
    "claude_json",
]


def get_llm_provider(provider_name: str | None = None) -> LLMProvider:
    """
    Factory that returns an :class:`LLMProvider` instance.

    Parameters
    ----------
    provider_name:
        ``"claude_cli"`` (default) or ``"anthropic"``.
        When *None*, falls back to the ``DEFAULT_LLM_PROVIDER`` env var,
        then to ``"claude_cli"``.
    """
    if provider_name is None:
        provider_name = os.environ.get("DEFAULT_LLM_PROVIDER", "claude_cli")

    if provider_name == "claude_cli":
        from .claude_cli import ClaudeCLIProvider

        return ClaudeCLIProvider()

    if provider_name == "anthropic":
        from .anthropic_api import AnthropicAPIProvider

        return AnthropicAPIProvider()

    raise ValueError(
        f"Unknown LLM provider {provider_name!r}. "
        f"Supported values: 'claude_cli', 'anthropic'."
    )


async def claude_json(prompt: str) -> dict:
    """
    Backward-compatible helper: call the Claude CLI and parse JSON.

    This is a drop-in replacement for the old ``assessment_agent.llm.claude_json``
    function. New code should use :func:`get_llm_provider` instead.
    """
    from .claude_cli import ClaudeCLIProvider

    provider = ClaudeCLIProvider()
    return await provider.complete_json(prompt)
