"""skill-creator 自身模型调用的文本补全抽象。

供 improve_description.py（以及其他需要向模型请求文本的地方）使用。
支持两种后端：

- ClaudeCLIClient：运行 `claude -p`（复用当前会话的 Claude Code 认证）。
- OpenAICompatClient：POST 到任意 chat-completions 兼容端点。

工厂函数 `get_llm_client()` 按名称选择后端，与 scripts/runners/ 中的
runner 选择方式一致。
"""

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol

from scripts.utils import filter_kwargs


class LLMClient(Protocol):
    """最小文本补全客户端。"""

    def complete(self, prompt: str, model: str | None = None, timeout: int = 300) -> str:
        """返回模型对 `prompt` 的文本响应。"""
        ...


class ClaudeCLIClient:
    """以子进程方式运行 `claude -p`（使用会话认证，无需 API key）。"""

    name = "claude"

    def complete(self, prompt: str, model: str | None = None, timeout: int = 300) -> str:
        cmd = ["claude", "-p", "--output-format", "text"]
        if model:
            cmd.extend(["--model", model])

        # 移除 CLAUDECODE 环境变量，允许在 Claude Code 会话内嵌套
        # claude -p。该守卫针对交互式终端冲突；编程式子进程调用是安全的。
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
                f"claude -p 退出码 {result.returncode}\nstderr: {result.stderr}"
            )
        return result.stdout


class OpenAICompatClient:
    """chat-completions HTTP 客户端（OpenAI 或任意兼容端点）。"""

    name = "openai"

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""

    def complete(self, prompt: str, model: str | None = None, timeout: int = 300) -> str:
        if not model:
            raise ValueError("openai LLM 客户端需要 model")
        if not self.api_key:
            raise ValueError("需要 OPENAI_API_KEY 或 api_key")

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
            raise RuntimeError(f"HTTP {e.code}：{detail}") from e

        try:
            payload = json.loads(raw)
            return payload["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"chat.completions 响应格式异常：{e}") from e


_CLIENTS: dict[str, type] = {
    "claude": ClaudeCLIClient,
    "openai": OpenAICompatClient,
    "openai-compatible": OpenAICompatClient,  # 别名
}


def detect_available_llms() -> dict[str, str]:
    """探测本地环境，返回 {client_name: 说明} 候选。

    仅供参考——绝不代用户选择后端。用户确认后才会实际使用。
    """
    found: dict[str, str] = {}
    if shutil.which("claude"):
        found["claude"] = "检测到 claude CLI（PATH 中存在，可用性未验证，需你确认）"
    if os.environ.get("OPENAI_API_KEY"):
        found["openai"] = "已设置 OPENAI_API_KEY（可配合 OPENAI_BASE_URL）"
    return found


def get_llm_client(name: str, **kwargs) -> LLMClient:
    """按显式名称构造 LLM 客户端。未知名称抛 ValueError。

    `name` 是必需的——CLI 询问用户使用哪个后端并把结果传到这里；探测
    从不自动决定。提供方相关的 kwargs（base_url/api_key）只传给接受它们的
    实现。
    """
    key = name.lower()
    if key not in _CLIENTS:
        raise ValueError(f"未知 LLM 客户端 '{name}'。可用：{sorted(set(_CLIENTS))}")
    cls = _CLIENTS[key]
    return cls(**filter_kwargs(cls, kwargs))
