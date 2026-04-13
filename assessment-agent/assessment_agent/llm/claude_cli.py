"""
LLM provider backed by the Claude Code CLI (`claude -p`).

Uses the user's Claude Code subscription for inference by spawning
the CLI in print mode. This avoids needing separate API keys.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess

from .base import LLMProvider, extract_json


def _get_claude_path() -> str:
    """Find the claude CLI binary."""
    path = shutil.which("claude")
    if not path:
        raise RuntimeError(
            "claude CLI not found in PATH. "
            "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code"
        )
    return path


class ClaudeCLIProvider:
    """LLM provider that shells out to the ``claude`` CLI."""

    def __init__(self, timeout: int = 180) -> None:
        self.timeout = timeout

    # -- internal --------------------------------------------------------

    def _invoke(self, prompt: str) -> str:
        """
        Call the claude CLI in print mode and return the response text.
        """
        claude_path = _get_claude_path()

        cmd = [
            claude_path,
            "-p",
            prompt,
            "--output-format", "text",
        ]

        # Clear CLAUDECODE env var so `claude -p` doesn't refuse to run.
        # This is safe: `-p` is stateless print mode, not an interactive session.
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            env=env,
        )

        if result.returncode != 0:
            raise RuntimeError(f"claude CLI error: {result.stderr.strip()}")

        return result.stdout.strip()

    # -- public API (satisfies LLMProvider protocol) ---------------------

    async def complete(self, prompt: str, system: str = "") -> str:
        """Send *prompt* to the Claude CLI and return the raw response."""
        if system:
            prompt = f"{system}\n\n{prompt}"
        return await asyncio.to_thread(self._invoke, prompt)

    async def complete_json(self, prompt: str, system: str = "") -> dict:
        """Send *prompt* to the Claude CLI, parse the response as JSON."""
        response = await self.complete(prompt, system)
        return extract_json(response)
