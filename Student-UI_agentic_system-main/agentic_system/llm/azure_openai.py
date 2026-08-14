"""Azure OpenAI-backed `LLMClient` implementation.

The `openai` SDK is imported lazily so embedders that inject their own
LLM (or use a future non-OpenAI backend) don't pay the import cost.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AzureOpenAILLM:
    """`LLMClient` backed by `openai.AzureOpenAI`.

    The deployment name is held by the client, not passed at call time —
    that's what lets the rest of the package stay vendor-agnostic.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment: str,
        api_version: str = "2024-12-01-preview",
        client: Optional[Any] = None,
    ) -> None:
        self._deployment = deployment
        if client is not None:
            self._client = client
            return

        from openai import AzureOpenAI

        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )

    def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.4,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self._deployment,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_completion_tokens"] = max_tokens
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        return (response.choices[0].message.content or "").strip()
