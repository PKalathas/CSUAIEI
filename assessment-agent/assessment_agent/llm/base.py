"""
Base protocol and shared utilities for LLM providers.
"""
from __future__ import annotations

import json
from typing import Protocol


class LLMProvider(Protocol):
    """Provider-agnostic interface for LLM inference."""

    async def complete(self, prompt: str, system: str = "") -> str:
        """Send a prompt and return the raw text response."""
        ...

    async def complete_json(self, prompt: str, system: str = "") -> dict:
        """Send a prompt and return the response parsed as JSON."""
        ...


def extract_json(text: str) -> dict:
    """
    Extract and parse JSON from an LLM response.

    Handles markdown code-block wrappers (```json ... ```) and falls back
    to locating the first '{' to the last '}' when a straight parse fails.
    """
    text = text.strip()

    # Strip markdown code-block wrappers
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object within the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise
