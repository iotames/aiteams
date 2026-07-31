"""skill-creator 各脚本共享的工具函数。"""

import inspect
import io
import os
import sys
from pathlib import Path

import yaml


def ensure_utf8_stdio() -> None:
    """将 stdout/stderr 重新配置为 UTF-8，避免非 ASCII 输出在
    Windows 控制台（GBK）等依赖区域设置的终端中崩溃。

    当 reconfigure 不可用（Python < 3.7）时安全地跳过。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError, io.UnsupportedOperation):
            pass


def can_open_browser() -> bool:
    """判断当前环境是否可能打开图形浏览器。

    macOS 与 Windows 视为有图形环境；Linux 依赖 DISPLAY 或 WAYLAND_DISPLAY，
    无显示环境（服务器、CI、容器）返回 False。仅供参考——实际打开失败不会
    影响功能，但默认在无头环境下自动跳过 webbrowser.open。
    """
    if sys.platform == "darwin" or sys.platform == "win32":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def filter_kwargs(cls: type, kwargs: dict) -> dict:
    """只返回目标类 __init__ 实际接受的 kwargs。

    用于后端工厂（runners/__init__.py、llm.py），这样 base_url/api_key 等
    提供方相关的选项可以传给支持它们的实现，而被其余实现无害地忽略。
    """
    if not kwargs:
        return {}
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return {}
    accepted = {p for p in params if p != "self"}
    return {k: v for k, v in kwargs.items() if k in accepted}


def prompt_choose_backend(kind: str, candidates: dict[str, str], flag: str,
                          recommended: str | None = None) -> str:
    """询问用户使用哪个模型后端进行评测/改进。

    探测只负责*列出*候选——选择权始终在用户。打印候选列表，允许用户输入
    名称或回车使用推荐项。在非交互环境（无 stdin）下抛 RuntimeError，
    要求调用方显式传入 --runner/--llm 参数。

    参数：
        kind: 人类可读标签，例如 "评测后端 (runner)" / "描述改进模型 (llm)"
        candidates: detect_available_runners()/llms() 返回的 {名称: 说明}
        flag: 需要提示的 CLI 参数，例如 "--runner"
        recommended: 作为默认值提供的名称（None 时取第一个候选）
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
    """解析 SKILL.md 文件，返回 (name, description, full_content)。

    使用 PyYAML 解析 frontmatter（与 quick_validate 一致），确保块标量
    （>、| 等）、带引号字符串、折叠语义在整个工具链中行为一致。
    utf-8-sig 读取会去除开头 BOM，与 quick_validate 保持一致。
    """
    content = (skill_path / "SKILL.md").read_text(encoding="utf-8-sig")
    lines = content.split("\n")

    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md 缺少 frontmatter（没有开头的 ---）")

    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise ValueError("SKILL.md 缺少 frontmatter（没有结尾的 ---）")

    frontmatter_text = "\n".join(lines[1:end_idx])
    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError as e:
        raise ValueError(f"frontmatter 中的 YAML 无效：{e}") from e
    if not isinstance(frontmatter, dict):
        raise ValueError("SKILL.md frontmatter 必须是 YAML 字典")

    name = frontmatter.get("name")
    if name is None:
        raise ValueError("SKILL.md frontmatter 缺少 'name'")
    if not isinstance(name, str):
        name = str(name)

    description = frontmatter.get("description")
    if description is None:
        description = ""
    elif not isinstance(description, str):
        description = str(description)

    return name.strip(), description.strip(), content
