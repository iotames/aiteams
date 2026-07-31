"""OpenAI 兼容 API runner。

驱动任意 chat-completions 兼容的 HTTP 端点（OpenAI，或任意
OpenAI 兼容代理/网关），使用工具机制：技能描述作为 `skill_trigger`
工具暴露给模型，并指示模型仅在 query 落在技能范围内时调用它。
模型响应中出现 `skill_trigger` 工具调用即视为触发了技能。

配置：
- `--openai-base-url` / OPENAI_BASE_URL（默认 https://api.openai.com/v1）
- `--openai-api-key` / OPENAI_API_KEY
- `--model`（必需）

仅使用 Python 标准库（urllib），无需额外依赖。
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from scripts.runners.base import SkillContext, TriggerResult

DEFAULT_BASE_URL = "https://api.openai.com/v1"

# 暴露给模型的工具。描述字段承载技能描述；名称必须对每个技能唯一，
# 避免过期的调用被误匹配。
TOOL_NAME = "skill_trigger"

SYSTEM_PROMPT_TEMPLATE = (
    "You are evaluating whether a skill should be activated for a user query.\n"
    "Skill name: {skill_name}\n"
    "Skill description: {description}\n\n"
    "If and only if the user's query falls within this skill's scope, call the "
    "{tool} tool. If the query is out of scope, reply with a short refusal and "
    "do NOT call the tool."
)


def build_chat_body(
    query: str,
    skill_ctx: SkillContext,
    model: str,
) -> dict:
    """构造 chat.completions 请求体。纯函数，可单元测试。"""
    tool_description = (
        f"Activate the skill '{skill_ctx.skill_name}'. "
        f"Skill description: {skill_ctx.description}"
    )
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT_TEMPLATE.format(
                    skill_name=skill_ctx.skill_name,
                    description=skill_ctx.description,
                    tool=TOOL_NAME,
                ),
            },
            {"role": "user", "content": query},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": TOOL_NAME,
                    "description": tool_description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill": {
                                "type": "string",
                                "description": f"The skill name: {skill_ctx.skill_name}",
                            }
                        },
                        "required": ["skill"],
                    },
                },
            }
        ],
        "tool_choice": "auto",
        "temperature": 0,
    }


def triggered_by_response(payload: dict, skill_name: str) -> tuple[bool, str]:
    """判断 chat.completions 响应是否表示触发。

    返回 (triggered, evidence)。纯函数，可单元测试。
    """
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as e:
        return False, f"响应格式异常：{e}"

    tool_calls = message.get("tool_calls") or []
    for call in tool_calls:
        fn = call.get("function", {})
        if fn.get("name") == TOOL_NAME:
            args = fn.get("arguments", "")
            if skill_name in args:
                return True, f"工具调用 {TOOL_NAME}，skill={skill_name}"
            return True, f"工具调用 {TOOL_NAME}（参数：{args[:120]}）"
    return False, "响应中无 skill_trigger 工具调用"


class OpenAICompatRunner:
    """驱动 chat-completions HTTP API 的触发评测后端。"""

    name = "openai"

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""

    def run_query(
        self,
        query: str,
        skill_ctx: SkillContext,
        model: str | None,
        timeout: int,
        project_root: str | None = None,
    ) -> TriggerResult:
        if not model:
            return TriggerResult(
                triggered=False,
                evidence="openai runner 需要 --model",
                error="missing model",
            )
        if not self.api_key:
            return TriggerResult(
                triggered=False,
                evidence="需要 OPENAI_API_KEY 或 --openai-api-key",
                error="missing api key",
            )

        body = build_chat_body(query, skill_ctx, model)
        url = f"{self.base_url}/chat/completions"
        request = urllib.request.Request(
            url,
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
            return TriggerResult(
                triggered=False,
                evidence=f"HTTP {e.code}：{detail}",
                error=f"http {e.code}",
            )
        except Exception as e:
            return TriggerResult(
                triggered=False,
                evidence=f"请求失败：{e}",
                error=str(e),
            )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            return TriggerResult(
                triggered=False,
                evidence=f"非 JSON 响应：{e}",
                error=str(e),
            )

        triggered, evidence = triggered_by_response(payload, skill_ctx.skill_name)
        return TriggerResult(triggered=triggered, evidence=evidence)


if __name__ == "__main__":
    # 最小自检：打印 eval-set 文件中第一条 eval 的请求体，不发送任何请求。
    import argparse
    import sys

    from scripts.utils import ensure_utf8_stdio

    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="检查 OpenAI runner 请求体")
    parser.add_argument("eval_set", help="触发评测 JSON 路径（list of {query, should_trigger}）")
    parser.add_argument("--skill-name", default="example-skill")
    parser.add_argument("--skill-description", default="Example description")
    parser.add_argument("--model", default="gpt-4o-mini")
    args = parser.parse_args()

    evals = json.loads(Path(args.eval_set).read_text(encoding="utf-8"))
    query = evals[0]["query"] if isinstance(evals, list) else evals["evals"][0]["query"]
    ctx = SkillContext(skill_name=args.skill_name, description=args.skill_description)
    print(json.dumps(build_chat_body(query, ctx, args.model), ensure_ascii=False, indent=2))
    sys.exit(0)
