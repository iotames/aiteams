"""Claude Code runner —— 最早的触发评测后端。

通过 `claude -p` CLI 驱动：技能通过 `.claude/commands/` 下的命令文件注入
（Claude Code 的技能发现机制），然后把 query 发出去，并解析 `stream-json`
输出中的 `Skill`/`Read` tool_use 事件是否引用注入的技能名。

流解析被拆成 :class:`ClaudeStreamTriggerParser`：一个纯函数、有状态的、
可测试单元——它只消费行并返回判定。
"""

import json
import os
import select
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from scripts.runners.base import SkillContext, TriggerResult


def find_project_root() -> Path:
    """从 cwd 向上寻找项目根（找到包含 .claude/ 的目录）。

    模拟 Claude Code 的项目根发现逻辑，确保我们创建的命令文件位于
    claude -p 会去查找的位置。
    """
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".claude").is_dir():
            return parent
    return current


@dataclass(frozen=True)
class TriggerDecision:
    """流解析器得出的最终判定（如果有的话）。"""

    settled: bool
    triggered: bool


class ClaudeStreamTriggerParser:
    """`claude -p --output-format stream-json` 输出的有状态解析器。

    feed() 每行 stdout 内容；一旦流已经定案就返回 TriggerDecision，否则
    返回 None 继续解析。复刻了 run_eval.py 原有的内联逻辑。
    """

    def __init__(self, clean_name: str):
        self.clean_name = clean_name
        self.pending_tool_name: str | None = None
        self.accumulated_json = ""
        self.triggered = False

    def feed(self, line: str) -> TriggerDecision | None:
        line = line.strip()
        if not line:
            return None
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return None

        if event.get("type") == "stream_event":
            return self._feed_stream_event(event.get("event", {}))
        if event.get("type") == "assistant":
            return self._feed_assistant_message(event.get("message", {}))
        if event.get("type") == "result":
            return TriggerDecision(settled=True, triggered=self.triggered)
        return None

    def _feed_stream_event(self, se: dict) -> TriggerDecision | None:
        se_type = se.get("type", "")

        if se_type == "content_block_start":
            cb = se.get("content_block", {})
            if cb.get("type") == "tool_use":
                tool_name = cb.get("name", "")
                if tool_name in ("Skill", "Read"):
                    self.pending_tool_name = tool_name
                    self.accumulated_json = ""
                else:
                    return TriggerDecision(settled=True, triggered=False)

        elif se_type == "content_block_delta" and self.pending_tool_name:
            delta = se.get("delta", {})
            if delta.get("type") == "input_json_delta":
                self.accumulated_json += delta.get("partial_json", "")
                if self.clean_name in self.accumulated_json:
                    return TriggerDecision(settled=True, triggered=True)

        elif se_type in ("content_block_stop", "message_stop"):
            if self.pending_tool_name:
                return TriggerDecision(
                    settled=True, triggered=self.clean_name in self.accumulated_json
                )
            if se_type == "message_stop":
                return TriggerDecision(settled=True, triggered=False)

        return None

    def _feed_assistant_message(self, message: dict) -> TriggerDecision | None:
        for content_item in message.get("content", []):
            if content_item.get("type") != "tool_use":
                continue
            tool_name = content_item.get("name", "")
            tool_input = content_item.get("input", {})
            if tool_name == "Skill" and self.clean_name in tool_input.get("skill", ""):
                self.triggered = True
            elif tool_name == "Read" and self.clean_name in tool_input.get("file_path", ""):
                self.triggered = True
            return TriggerDecision(settled=True, triggered=self.triggered)
        return None


class ClaudeCodeRunner:
    """驱动 `claude -p` CLI 的触发评测后端。"""

    name = "claude-code"

    def run_query(
        self,
        query: str,
        skill_ctx: SkillContext,
        model: str | None,
        timeout: int,
        project_root: str | None = None,
    ) -> TriggerResult:
        root = Path(project_root) if project_root else find_project_root()
        unique_id = uuid.uuid4().hex[:8]
        clean_name = f"{skill_ctx.skill_name}-skill-{unique_id}"
        project_commands_dir = root / ".claude" / "commands"
        command_file = project_commands_dir / f"{clean_name}.md"

        try:
            project_commands_dir.mkdir(parents=True, exist_ok=True)
            # 使用 YAML 块标量，避免描述中的引号导致解析出错
            indented_desc = "\n  ".join(skill_ctx.description.split("\n"))
            command_content = (
                f"---\n"
                f"description: |\n"
                f"  {indented_desc}\n"
                f"---\n\n"
                f"# {skill_ctx.skill_name}\n\n"
                f"This skill handles: {skill_ctx.description}\n"
            )
            command_file.write_text(command_content, encoding="utf-8")

            cmd = [
                "claude",
                "-p", query,
                "--output-format", "stream-json",
                "--verbose",
                "--include-partial-messages",
            ]
            if model:
                cmd.extend(["--model", model])

            # 移除 CLAUDECODE 环境变量，允许在 Claude Code 会话内嵌套
            # claude -p。该守卫针对交互式终端冲突；编程式子进程调用是安全的。
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=str(root),
                env=env,
            )

            parser = ClaudeStreamTriggerParser(clean_name)
            decision = None
            start_time = time.time()
            buffer = ""

            try:
                while time.time() - start_time < timeout:
                    if process.poll() is not None:
                        remaining = process.stdout.read()
                        if remaining:
                            buffer += remaining.decode("utf-8", errors="replace")
                        break

                    ready, _, _ = select.select([process.stdout], [], [], 1.0)
                    if not ready:
                        continue

                    chunk = os.read(process.stdout.fileno(), 8192)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", errors="replace")

                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        decision = parser.feed(line)
                        if decision is not None and decision.settled:
                            return TriggerResult(
                                triggered=decision.triggered,
                                evidence=f"流事件判定 type={line[:60]!r}",
                            )
            finally:
                # 任何退出路径（return、异常、超时）都清理进程
                if process.poll() is None:
                    process.kill()
                    process.wait()

            if decision is not None:
                return TriggerResult(triggered=decision.triggered, evidence="流结束")
            return TriggerResult(
                triggered=False,
                evidence="超时/EOF 前未得到判定",
                error="timeout or empty stream",
            )
        except FileNotFoundError as e:
            return TriggerResult(
                triggered=False,
                evidence=f"未找到 claude CLI：{e}",
                error=str(e),
            )
        except Exception as e:
            return TriggerResult(
                triggered=False,
                evidence=f"runner 错误：{e}",
                error=str(e),
            )
        finally:
            if command_file.exists():
                command_file.unlink()
