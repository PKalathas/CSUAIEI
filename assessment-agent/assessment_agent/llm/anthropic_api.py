"""
LLM provider backed by the Anthropic Messages API.

Requires the ``anthropic`` Python package and a valid API key
(passed explicitly or set in the ``ANTHROPIC_API_KEY`` env var).
"""
from __future__ import annotations

import os
import time
from typing import Any

from .base import LLMProvider, extract_json


class AnthropicAPIProvider:
    """LLM provider that calls the Anthropic Messages API directly."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "An Anthropic API key is required. Pass it explicitly or set "
                "the ANTHROPIC_API_KEY environment variable."
            )
        self.model = model
        self._client: Any = None  # lazily initialised

    @property
    def model_id(self) -> str:
        return self.model

    # -- internal --------------------------------------------------------

    def _get_client(self) -> Any:
        """Return (and lazily create) an ``AsyncAnthropic`` client."""
        if self._client is None:
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "The 'anthropic' package is required for the Anthropic API "
                    "provider. Install it with: pip install anthropic"
                )
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    # -- public API (satisfies LLMProvider protocol) ---------------------

    async def complete(self, prompt: str, system: str = "") -> str:
        """Send *prompt* via the Anthropic API and return the raw response."""
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system

        message = await client.messages.create(**kwargs)
        return message.content[0].text

    async def complete_with_raw(self, prompt: str, system: str = "") -> tuple[dict, str, int]:
        """Send *prompt* via the Anthropic API, return (parsed_json, raw_response, latency_ms)."""
        start = time.monotonic()
        raw = await self.complete(prompt, system)
        latency_ms = int((time.monotonic() - start) * 1000)
        return extract_json(raw), raw, latency_ms

    async def complete_json(self, prompt: str, system: str = "") -> dict:
        """Send *prompt* via the Anthropic API, parse the response as JSON."""
        parsed, _, _ = await self.complete_with_raw(prompt, system)
        return parsed
