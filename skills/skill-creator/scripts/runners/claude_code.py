"""Claude Code runner — the original trigger-evaluation backend.

Drives the `claude -p` CLI: the skill is injected by writing a command file
under `.claude/commands/` (Claude Code's skill discovery mechanism), then the
query is sent and the `stream-json` output is parsed for `Skill`/`Read`
tool_use events that reference the injected skill name.

The stream parsing is factored into :class:`ClaudeStreamTriggerParser` as a
pure, stateful, testable unit — it only consumes lines and returns decisions.
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
    """Find the project root by walking up from cwd looking for .claude/.

    Mimics how Claude Code discovers its project root, so the command file
    we create ends up where claude -p will look for it.
    """
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".claude").is_dir():
            return parent
    return current


@dataclass(frozen=True)
class TriggerDecision:
    """A settled decision from the stream parser, if any."""

    settled: bool
    triggered: bool


class ClaudeStreamTriggerParser:
    """Stateful parser for `claude -p --output-format stream-json` output.

    feed() each stdout line; it returns a TriggerDecision as soon as the
    stream has settled the outcome, or None to keep parsing. Mirrors the
    original inline logic of run_eval.py.
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
    """Trigger-evaluation backend that drives the `claude -p` CLI."""

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
            # Use YAML block scalar to avoid breaking on quotes in description
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

            # Remove CLAUDECODE env var to allow nesting claude -p inside a
            # Claude Code session. The guard is for interactive terminal
            # conflicts; programmatic subprocess usage is safe.
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
                                evidence=f"stream decision at type={line[:60]!r}",
                            )
            finally:
                # Clean up process on any exit path (return, exception, timeout)
                if process.poll() is None:
                    process.kill()
                    process.wait()

            if decision is not None:
                return TriggerResult(triggered=decision.triggered, evidence="end of stream")
            return TriggerResult(
                triggered=False,
                evidence="no decision before timeout/EOF",
                error="timeout or empty stream",
            )
        except FileNotFoundError as e:
            return TriggerResult(
                triggered=False,
                evidence=f"claude CLI not found: {e}",
                error=str(e),
            )
        except Exception as e:
            return TriggerResult(
                triggered=False,
                evidence=f"runner error: {e}",
                error=str(e),
            )
        finally:
            if command_file.exists():
                command_file.unlink()
