"""LLM-client protocol.

Every LLM call inside the package goes through this interface, so swapping
the underlying provider (Azure OpenAI today, Anthropic / a self-hosted
model / a stub for tests tomorrow) is a single point of change.

The protocol is deliberately minimal — one method that takes a list of
chat messages and returns the completion text. It hides:

  - the SDK shape (`client.chat.completions.create(...)` vs. anything else)
  - the model/deployment identifier (the implementation owns that)
  - JSON-mode plumbing (callers say `json_mode=True`; the impl translates)

Callers that want JSON parse the returned string themselves. Implementations
should ensure that, when `json_mode=True`, the returned string is parseable
JSON (or raise).
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.4,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ):
        """Run a single chat completion.

        Args:
          messages: OpenAI-style chat messages (`{"role": ..., "content": ...}`).
            System messages, if any, are already included by the caller.
          temperature: Sampling temperature.
          max_tokens: Optional cap on output tokens.
          json_mode: If True, the implementation must constrain the model to
            emit valid JSON (e.g. via OpenAI's `response_format`).

        Returns:
          The assistant's message content as a string. Stripped of leading/
          trailing whitespace.
        """
