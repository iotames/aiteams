"""技能触发评测后端的注册表。

新增后端：实现 Runner 协议（scripts/runners/base.py）并在本文件注册。
扩展指南见 references/runners.md。

重要：runner 只是*评测试金石*——它决定由哪个真实智能体执行触发查询。
技能本体（SKILL.md + scripts）保持模型无关，绝不与任何 runner 耦合。

选择策略：CLI 会询问**用户**使用哪个后端（交互式提示）；探测只列出候选，
绝不自行决定。因此 `get_runner()` 要求显式名称——要么传一个，要么先调用
detect_available_runners() 再由用户选择。
"""

import os
import shutil

from scripts.runners.base import Runner, SkillContext, TriggerResult
from scripts.runners.claude_code import ClaudeCodeRunner, ClaudeStreamTriggerParser
from scripts.runners.openai import OpenAICompatRunner
from scripts.utils import filter_kwargs

_RUNNERS: dict[str, type] = {
    "claude-code": ClaudeCodeRunner,
    "claude": ClaudeCodeRunner,          # 别名
    "openai": OpenAICompatRunner,
    "openai-compatible": OpenAICompatRunner,  # 别名
}


def detect_available_runners() -> dict[str, str]:
    """探测本地环境，返回 {runner_name: 说明} 候选。

    探测仅供参考——绝不代用户选择后端。"claude" 存在于 PATH 并不代表可用；
    用户必须确认选择。
    """
    found: dict[str, str] = {}
    if shutil.which("claude"):
        found["claude-code"] = "检测到 claude CLI（PATH 中存在，可用性未验证，需你确认）"
    if os.environ.get("OPENAI_API_KEY"):
        found["openai"] = "已设置 OPENAI_API_KEY（可配合 OPENAI_BASE_URL）"
    return found


def get_runner(name: str, **kwargs) -> Runner:
    """按显式名称构造 runner。未知名称抛 ValueError。

    `name` 是必需的——CLI 询问用户使用哪个后端并把结果传到这里；探测
    从不自动决定。提供方相关的 kwargs（如 openai 的 base_url/api_key）
    会传给 runner 构造函数；所选实现不接受的 kwargs 会被忽略。
    """
    key = name.lower()
    if key not in _RUNNERS:
        raise ValueError(
            f"未知 runner '{name}'。可用：{sorted(set(_RUNNERS))}"
        )
    return _RUNNERS[key](**filter_kwargs(_RUNNERS[key], kwargs))


__all__ = [
    "Runner",
    "SkillContext",
    "TriggerResult",
    "ClaudeCodeRunner",
    "ClaudeStreamTriggerParser",
    "OpenAICompatRunner",
    "get_runner",
    "detect_available_runners",
]
