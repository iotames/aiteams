"""
提示词加载器 — 从 prompts/*.md 文件加载 Agent 和 Task 定义。

职责：
- 将 prompts/ 目录下的 Markdown 文件解析为结构字典
- 供 crew.py 在构建 Agent/Task 时使用
- 完全解耦提示词与 Python 代码

文件格式约定：
- 每个 .md 文件使用 ## 二级标题作为键（如 "## Role", "## Description"）
- ## 标题后的正文内容作为对应的值
- 列表项和代码块原样保留
"""

from functools import lru_cache
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = BASE_DIR / "prompts"


def load_prompt(file_path: Path) -> dict[str, str]:
    """解析 Markdown 提示词文件，返回 {section_name: content} 字典。

    Args:
        file_path: .md 文件的路径

    Returns:
        包含各节内容的字典，键为小写的节名称（如 'role', 'goal', 'backstory'）

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式不符合预期
    """
    if not file_path.exists():
        raise FileNotFoundError(f"提示词文件不存在: {file_path}")

    text = file_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            # 保存上一个节
            if current_key is not None:
                sections[current_key] = _clean_content(current_lines)
            # 新节开始
            current_key = line[3:].strip().lower()
            current_lines = []
        else:
            if current_key is not None:
                current_lines.append(line)

    # 保存最后一个节
    if current_key is not None:
        sections[current_key] = _clean_content(current_lines)

    return sections


def _clean_content(lines: list[str]) -> str:
    """清理节内容：去除首尾空行、合并多余空行"""
    # 去除首尾空白行
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[-1].strip() == "":
        lines.pop()
    return "\n".join(lines)


@lru_cache(maxsize=32)
def load_agent(name: str) -> dict[str, str]:
    """加载一个 Agent 的提示词。

    Args:
        name: Agent 名称，对应 prompts/agents/{name}.md

    Returns:
        包含 role, goal, backstory 的字典
    """
    path = PROMPTS_DIR / "agents" / f"{name}.md"
    return load_prompt(path)


@lru_cache(maxsize=32)
def load_task(name: str) -> dict[str, str]:
    """加载一个 Task 的提示词。

    Args:
        name: Task 名称，对应 prompts/tasks/{name}.md

    Returns:
        包含 description, expected_output 的字典
    """
    path = PROMPTS_DIR / "tasks" / f"{name}.md"
    return load_prompt(path)


def load_requirements() -> str:
    """加载产品需求规格文档的内容。

    Returns:
        完整的 Markdown 格式需求文档字符串
    """
    path = PROMPTS_DIR / "requirements" / "ims-requirements.md"
    return path.read_text(encoding="utf-8")
