"""Runner registry for skill-trigger evaluation backends.

Add a new backend by implementing the Runner protocol (scripts/runners/base.py)
and registering it here. See references/runners.md for the extension guide.

Important: the runner is only the *evaluation test rig* — it decides which
real agent executes the trigger queries. The skill itself (SKILL.md + scripts)
stays model-agnostic and is never coupled to any runner.

Selection policy: the CLI asks the USER which backend to use (interactive
prompt); detection only lists candidates and never decides on its own.
`get_runner()` therefore requires an explicit name — pass one, or call
detect_available_runners() first and let the user pick.
"""

import inspect
import os
import shutil

from scripts.runners.base import Runner, SkillContext, TriggerResult
from scripts.runners.claude_code import ClaudeCodeRunner, ClaudeStreamTriggerParser
from scripts.runners.openai import OpenAICompatRunner

_RUNNERS: dict[str, type] = {
    "claude-code": ClaudeCodeRunner,
    "claude": ClaudeCodeRunner,          # alias
    "openai": OpenAICompatRunner,
    "openai-compatible": OpenAICompatRunner,  # alias
}


def _filter_kwargs(cls: type, kwargs: dict) -> dict:
    """Pass only kwargs the target class __init__ actually accepts."""
    if not kwargs:
        return {}
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return {}
    accepted = {p for p in params if p != "self"}
    return {k: v for k, v in kwargs.items() if k in accepted}


def detect_available_runners() -> dict[str, str]:
    """Probe the local environment; return {runner_name: note} candidates.

    Probing is advisory only — it never picks a backend. "claude" existing on
    PATH does NOT mean it is usable; the user must confirm the choice.
    """
    found: dict[str, str] = {}
    if shutil.which("claude"):
        found["claude-code"] = "检测到 claude CLI（PATH 中存在，可用性未验证，需你确认）"
    if os.environ.get("OPENAI_API_KEY"):
        found["openai"] = "已设置 OPENAI_API_KEY（可配合 OPENAI_BASE_URL）"
    return found


def get_runner(name: str, **kwargs) -> Runner:
    """Build a runner by explicit name. Unknown names raise ValueError.

    `name` is required — the CLI asks the user which backend to use and passes
    the result here; detection never decides automatically. Provider-specific
    kwargs (e.g. base_url/api_key for openai) are passed to the runner
    constructor; kwargs the chosen implementation doesn't accept are ignored.
    """
    key = name.lower()
    if key not in _RUNNERS:
        raise ValueError(
            f"Unknown runner '{name}'. Available: {sorted(set(_RUNNERS))}"
        )
    return _RUNNERS[key](**_filter_kwargs(_RUNNERS[key], kwargs))


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
