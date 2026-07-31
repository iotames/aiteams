"""OpenAI-compatible API runner.

Drives any chat-completions-compatible HTTP endpoint (OpenAI, or any
OpenAI-compatible proxy/gateway) with the tools mechanism: the skill
description is exposed as a `skill_trigger` tool, and the model is instructed
to call it iff the query falls within the skill's scope. The model is
considered to have triggered the skill when its response contains a
`skill_trigger` tool call.

Configuration:
- `--openai-base-url` / OPENAI_BASE_URL (default https://api.openai.com/v1)
- `--openai-api-key` / OPENAI_API_KEY
- `--model` (required)

Uses only the Python standard library (urllib), so no extra dependency is
needed.
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from scripts.runners.base import SkillContext, TriggerResult

DEFAULT_BASE_URL = "https://api.openai.com/v1"

# Tool exposed to the model. The description field carries the skill's
# description; name must be unique per skill so a stale call can't match.
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
    """Build the chat.completions request body. Pure function, unit-testable."""
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
    """Decide whether a chat.completions response indicates a trigger.

    Returns (triggered, evidence). Pure function, unit-testable.
    """
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as e:
        return False, f"malformed response: {e}"

    tool_calls = message.get("tool_calls") or []
    for call in tool_calls:
        fn = call.get("function", {})
        if fn.get("name") == TOOL_NAME:
            args = fn.get("arguments", "")
            if skill_name in args:
                return True, f"tool_call {TOOL_NAME} with skill={skill_name}"
            return True, f"tool_call {TOOL_NAME} (arguments: {args[:120]})"
    return False, "no skill_trigger tool call in response"


class OpenAICompatRunner:
    """Trigger-evaluation backend that drives a chat-completions HTTP API."""

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
                evidence="--model is required for the openai runner",
                error="missing model",
            )
        if not self.api_key:
            return TriggerResult(
                triggered=False,
                evidence="OPENAI_API_KEY or --openai-api-key required",
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
                evidence=f"HTTP {e.code}: {detail}",
                error=f"http {e.code}",
            )
        except Exception as e:
            return TriggerResult(
                triggered=False,
                evidence=f"request failed: {e}",
                error=str(e),
            )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            return TriggerResult(
                triggered=False,
                evidence=f"non-JSON response: {e}",
                error=str(e),
            )

        triggered, evidence = triggered_by_response(payload, skill_ctx.skill_name)
        return TriggerResult(triggered=triggered, evidence=evidence)


if __name__ == "__main__":
    # Minimal self-check: print the request body for the first eval in an
    # eval-set file, without sending anything.
    import argparse
    import sys

    from scripts.utils import ensure_utf8_stdio

    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Inspect OpenAI runner request body")
    parser.add_argument("eval_set", help="Path to trigger-eval JSON (list of {query, should_trigger})")
    parser.add_argument("--skill-name", default="example-skill")
    parser.add_argument("--skill-description", default="Example description")
    parser.add_argument("--model", default="gpt-4o-mini")
    args = parser.parse_args()

    evals = json.loads(Path(args.eval_set).read_text(encoding="utf-8"))
    query = evals[0]["query"] if isinstance(evals, list) else evals["evals"][0]["query"]
    ctx = SkillContext(skill_name=args.skill_name, description=args.skill_description)
    print(json.dumps(build_chat_body(query, ctx, args.model), ensure_ascii=False, indent=2))
    sys.exit(0)
