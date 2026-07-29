"""
prompt_loader.py — 提示词加载器

设计目标：提示词与 Python 代码完全解耦。

职责：
1. 从 prompts/ 目录动态加载 .md 文件
2. 注入模板变量（{{variable}} 格式）
3. 支持多语言（自动检测目录）
4. 校验：加载时检查未替换的占位符，提前报错
5. 缓存：同一文件不重复读取磁盘

用法：
    from ims_autogen.prompt_loader import load

    # 加载产品经理提示词，注入变量
    prompt = load("product_manager", scope="MVP")

    # 加载英文版
    prompt = load("product_manager", lang="en", scope="Full")

非技术人员可直接编辑 prompts/ 下的 .md 文件来调整 Agent 行为，
无需修改任何 Python 代码。
"""

import os
import re
from pathlib import Path
from functools import lru_cache

# ── 目录结构 ──────────────────────────────────────────────
# prompts/              ← 默认语言（中文）
#   product_manager.md
#   architect.md
#   developer.md
#   qa.md
# prompts/en/           ← 英文版（可选）
#   product_manager.md
#   ...

_PROMPTS_DIR = Path(__file__).parent / "prompts"

# ── 占位符正则：匹配 {{var_name}} ──────────────────────────
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


class PromptNotFoundError(FileNotFoundError):
    """提示词文件未找到时抛出。"""
    pass


class PromptValidationError(ValueError):
    """提示词中有关键占位符未填充时抛出。"""
    pass


def _resolve_path(name: str, lang: str = "") -> Path:
    """
    解析提示词文件路径。

    查找顺序：
    1. prompts/{lang}/{name}.md  （指定语言）
    2. prompts/{name}.md          （默认语言）

    Args:
        name: 提示词名称（不含扩展名），如 "product_manager"
        lang: 语言代码，如 "zh"、"en"。空字符串表示默认语言

    Returns:
        文件的完整路径

    Raises:
        PromptNotFoundError: 两个位置都找不到文件
    """
    if lang:
        path = _PROMPTS_DIR / lang / f"{name}.md"
        if path.exists():
            return path

    path = _PROMPTS_DIR / f"{name}.md"
    if path.exists():
        return path

    searched = []
    if lang:
        searched.append(str(_PROMPTS_DIR / lang / f"{name}.md"))
    searched.append(str(_PROMPTS_DIR / f"{name}.md"))
    raise PromptNotFoundError(
        f"提示词文件未找到: {name}.md\n"
        f"  搜索路径: {', '.join(searched)}\n"
        f"  提示: 在 prompts/ 目录下创建该文件即可"
    )


@lru_cache(maxsize=32)
def _read_file(path: Path) -> str:
    """读取文件内容（带缓存，避免重复磁盘 IO）。"""
    return path.read_text(encoding="utf-8")


def load(name: str, lang: str = "", **variables) -> str:
    """
    加载并渲染提示词模板。

    Args:
        name: 提示词名称，如 "product_manager"
        lang: 语言代码，如 "zh"、"en"。留空使用默认语言
        **variables: 模板变量值。
              例如 load("product_manager", scope="MVP")
              会将 .md 文件中的 {{scope}} 替换为 "MVP"

    Returns:
        渲染后的提示词文本

    Raises:
        PromptNotFoundError: 文件不存在
        PromptValidationError: 文件中有未填充的占位符

    Examples:
        >>> load("product_manager", scope="MVP")
        >>> load("developer", lang="en", scope="Full")
    """
    # 1. 定位文件
    path = _resolve_path(name, lang)

    # 2. 读取内容
    text = _read_file(path)

    # 3. 变量注入
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", str(value))

    # 4. 校验：检查是否还有未填充的占位符
    unbound = _PLACEHOLDER_RE.findall(text)
    if unbound:
        raise PromptValidationError(
            f"提示词文件 {path.name} 中有未填充的占位符: "
            f"{', '.join(f'{{{{{v}}}}}' for v in unbound)}\n"
            f"  提示: 在调用 load() 时传入这些变量，"
            f"或者编辑 .md 文件移除不需要的占位符"
        )

    # 5. 返回渲染结果
    return text


def available(lang: str = "") -> list[str]:
    """
    列出可用的提示词名称。

    Args:
        lang: 语言代码。留空列出默认语言

    Returns:
        提示词名称列表（不含扩展名）
    """
    if lang:
        directory = _PROMPTS_DIR / lang
    else:
        directory = _PROMPTS_DIR
    if not directory.exists():
        return []
    return sorted(
        f.stem for f in directory.iterdir()
        if f.suffix == ".md" and not f.stem.startswith("_")
    )


def clear_cache() -> None:
    """清除文件读取缓存（修改 .md 文件后调用此函数使新内容生效）。"""
    _read_file.cache_clear()
