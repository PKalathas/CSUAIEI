"""Claude (Anthropic) `LLMClient` implementation.

Wraps the official `anthropic` SDK so the rest of the package stays
provider-agnostic. The SDK is imported lazily — embedders that ship only
`AzureOpenAILLM` don't pay the import cost.

Auth (mirrors the Anthropic SDK's own precedence):
  - Default: `ANTHROPIC_API_KEY` env var.
  - Explicit: pass `api_key=` for an API key, or `auth_token=` for an
    OAuth bearer (e.g. a Claude Pro/Max subscription token).
  - Inject: pass a pre-built `client=` for tests or shared client reuse.

Defaults follow the `claude-api` skill's standing guidance:
  - Model is `claude-opus-4-7`.
  - Prompt caching is on for the system prompt — the policy/companion
    prompts in this app are static, so cache hits start paying out from
    the second turn onward.

Notes:
  - Opus 4.7 dropped `temperature`/`top_p`/`top_k` (they 400 the request);
    the caller's `temperature` is silently ignored when targeting one of
    those models. Older models still accept it.
  - Anthropic has no `response_format: json_object` toggle. When
    `json_mode=True` we reinforce in-prompt and strip markdown code
    fences from the response. Callers `json.loads()` the result.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


DEFAULT_MODEL = "claude-opus-4-7"

# Models that 400 if `temperature` / `top_p` / `top_k` is sent.
_NO_SAMPLING_MODELS = frozenset({"claude-opus-4-7"})

# Strip ```json ... ``` (or ``` ... ```) wrappers Claude sometimes adds
# despite the in-prompt instruction. Keeps the bytes we hand back to
# callers consistent with what AzureOpenAILLM returns in JSON mode.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$", re.DOTALL)


class ClaudeLLM:
    """`LLMClient` backed by `anthropic.Anthropic`.

    The model is bound to the instance, not passed at call time — that's
    what keeps agents and policy code vendor-agnostic.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        auth_token: Optional[str] = None,
        client: Optional[Any] = None,
    ) -> None:
        self._model = model
        if client is not None:
            self._client = client
            return

        from anthropic import Anthropic

        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if auth_token:
            kwargs["auth_token"] = auth_token
        # If neither is set, the SDK falls back to ANTHROPIC_API_KEY.
        self._client = Anthropic(**kwargs)

    def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.4,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        # Anthropic separates the system prompt from chat messages; pull
        # any system messages out (concatenated if there are multiple)
        # and pass the rest through.
        system_parts: list[str] = []
        chat_messages: list[dict] = []
        for m in messages:
            if m.get("role") == "system":
                system_parts.append(m.get("content", ""))
            else:
                chat_messages.append(m)

        system_prompt = "\n\n".join(p for p in system_parts if p)

        if json_mode:
            json_hint = (
                "Respond with ONLY a valid JSON object. No prose, no "
                "markdown, no code fences — just the JSON."
            )
            system_prompt = (
                f"{system_prompt}\n\n{json_hint}" if system_prompt else json_hint
            )

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": chat_messages,
            # Anthropic requires `max_tokens`. 4096 covers the tutoring-
            # style replies in this app and stays well under SDK timeout
            # thresholds for non-streaming requests.
            "max_tokens": max_tokens if max_tokens is not None else 4096,
        }
        if system_prompt:
            kwargs["system"] = system_prompt
            # Top-level cache_control auto-applies to the last cacheable
            # block. The policy classifier and verifier prompts repeat
            # every turn, so cache hits start paying out immediately.
            kwargs["cache_control"] = {"type": "ephemeral"}

        if self._model not in _NO_SAMPLING_MODELS:
            kwargs["temperature"] = temperature

        response = self._client.messages.create(**kwargs)

        text = "".join(
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ).strip()

        if json_mode:
            match = _FENCE_RE.match(text)
            if match:
                text = match.group(1).strip()

        return text
