"""Shared utilities for skill-creator scripts."""

import io
import sys
from pathlib import Path


def ensure_utf8_stdio() -> None:
    """Reconfigure stdout/stderr to UTF-8 so non-ASCII output never crashes
    on Windows consoles (GBK) or other locale-dependent terminals.

    Safe no-op when reconfigure is unavailable (Python < 3.7).
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, io.UnsupportedOperation):
            pass


def prompt_choose_backend(kind: str, candidates: dict[str, str], flag: str,
                          recommended: str | None = None) -> str:
    """Ask the user which model backend to use for evaluation/improvement.

    Detection only *lists* candidates — the choice is always the user's.
    Prints candidates, lets the user type a name or press Enter for the
    recommended default. Raises RuntimeError in non-interactive environments
    (no stdin) so callers can require an explicit --runner/--llm flag.

    Args:
        kind: human label, e.g. "评测后端 (runner)" / "描述改进模型 (llm)"
        candidates: {name: note} from detect_available_runners()/llms()
        flag: the CLI flag to suggest, e.g. "--runner"
        recommended: name to offer as default (first candidate if None)
    """
    if not candidates:
        raise RuntimeError(
            f"未检测到可用的{kind}。请安装并配置后端后重试，"
            f"或通过 {flag} 显式指定。"
        )
    default = recommended if recommended in candidates else next(iter(candidates))

    print(f"请选择{kind}（当前环境探测到的候选）：", file=sys.stderr)
    for name, note in candidates.items():
        marker = " [推荐]" if name == default else ""
        print(f"  {name}{marker}: {note}", file=sys.stderr)
    print(f"直接回车使用 {default}，或输入其他名称：", file=sys.stderr, end=" ")

    try:
        answer = input()
    except EOFError:
        raise RuntimeError(
            f"当前环境无法交互（stdin 不可用）。请用 {flag} 显式指定后端，"
            f"可用：{', '.join(sorted(candidates))}"
        )

    choice = answer.strip().lower()
    if not choice:
        return default
    if choice not in candidates:
        raise ValueError(
            f"未知的{kind} '{answer}'。可用：{', '.join(sorted(candidates))}"
        )
    return choice


def parse_skill_md(skill_path: Path) -> tuple[str, str, str]:
    """Parse a SKILL.md file, returning (name, description, full_content)."""
    content = (skill_path / "SKILL.md").read_text(encoding="utf-8")
    lines = content.split("\n")

    if lines[0].strip() != "---":
        raise ValueError("SKILL.md missing frontmatter (no opening ---)")

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise ValueError("SKILL.md missing frontmatter (no closing ---)")

    name = ""
    description = ""
    frontmatter_lines = lines[1:end_idx]
    i = 0
    while i < len(frontmatter_lines):
        line = frontmatter_lines[i]
        if line.startswith("name:"):
            name = line[len("name:"):].strip().strip('"').strip("'")
        elif line.startswith("description:"):
            value = line[len("description:"):].strip()
            # Handle YAML multiline indicators (>, |, >-, |-, >+, |+)
            if value in (">", "|", ">-", "|-", ">+", "|+"):
                continuation_lines: list[str] = []
                i += 1
                while i < len(frontmatter_lines) and (frontmatter_lines[i].startswith("  ") or frontmatter_lines[i].startswith("\t")):
                    continuation_lines.append(frontmatter_lines[i].strip())
                    i += 1
                description = " ".join(continuation_lines)
                continue
            else:
                description = value.strip('"').strip("'")
        i += 1

    return name, description, content
