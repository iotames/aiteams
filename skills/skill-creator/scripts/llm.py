"""LLM text-completion abstraction for skill-creator's own model calls.

Used by improve_description.py (and anything else that asks a model to
generate text). Two backends:

- ClaudeCLIClient: runs `claude -p` (uses the session's Claude Code auth).
- OpenAICompatClient: POSTs to any chat-completions-compatible endpoint.

The factory `get_llm_client()` selects the backend by name, mirroring the
runner selection in scripts/runners/.
"""

import inspect
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol


class LLMClient(Protocol):
    """Minimal text-completion client."""

    def complete(self, prompt: str, model: str | None = None, timeout: int = 300) -> str:
        """Return the model's text response for `prompt`."""
        ...


class ClaudeCLIClient:
    """Runs `claude -p` as a subprocess (session auth, no API key needed)."""

    name = "claude"

    def complete(self, prompt: str, model: str | None = None, timeout: int = 300) -> str:
        cmd = ["claude", "-p", "--output-format", "text"]
        if model:
            cmd.extend(["--model", model])

        # Remove CLAUDECODE env var to allow nesting claude -p inside a
        # Claude Code session. The guard is for interactive terminal conflicts;
        # programmatic subprocess usage is safe.
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"claude -p exited {result.returncode}\nstderr: {result.stderr}"
            )
        return result.stdout


class OpenAICompatClient:
    """Chat-completions HTTP client (OpenAI or any compatible endpoint)."""

    name = "openai"

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""

    def complete(self, prompt: str, model: str | None = None, timeout: int = 300) -> str:
        if not model:
            raise ValueError("model is required for the openai LLM client")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY or api_key is required for the openai LLM client")

        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"HTTP {e.code}: {detail}") from e

        try:
            payload = json.loads(raw)
            return payload["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Malformed chat.completions response: {e}") from e


_CLIENTS: dict[str, type] = {
    "claude": ClaudeCLIClient,
    "openai": OpenAICompatClient,
    "openai-compatible": OpenAICompatClient,  # alias
}


def detect_available_llms() -> dict[str, str]:
    """Probe the local environment; return {client_name: note} candidates.

    Advisory only — never picks a backend. The user confirms the choice.
    """
    found: dict[str, str] = {}
    if shutil.which("claude"):
        found["claude"] = "检测到 claude CLI（PATH 中存在，可用性未验证，需你确认）"
    if os.environ.get("OPENAI_API_KEY"):
        found["openai"] = "已设置 OPENAI_API_KEY（可配合 OPENAI_BASE_URL）"
    return found


def get_llm_client(name: str, **kwargs) -> LLMClient:
    """Build an LLM client by explicit name. Unknown names raise ValueError.

    `name` is required — the CLI asks the user which backend to use and passes
    the result here; detection never decides automatically. Provider-specific
    kwargs (base_url/api_key) are passed through only to implementations that
    accept them.
    """
    key = name.lower()
    if key not in _CLIENTS:
        raise ValueError(f"Unknown LLM client '{name}'. Available: {sorted(set(_CLIENTS))}")
    cls = _CLIENTS[key]
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        params = {}
    accepted = {p for p in params if p != "self"}
    filtered = {k: v for k, v in kwargs.items() if k in accepted}
    return cls(**filtered)
