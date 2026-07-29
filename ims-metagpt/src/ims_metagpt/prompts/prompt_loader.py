"""
提示词加载器 — 从 .md 文件动态读取提示词模板。

设计目标：
1. 提示词与 Python 代码完全解耦，非技术人员可直接编辑 .md 文件
2. 支持运行时动态加载（改 .md 文件后重启即生效，无需改 Python）
3. 支持自定义覆盖（在工作区放同名 .md 文件可覆盖默认提示词）
4. 支持多语言（预留 lang 参数）

使用方式：
    from ims_metagpt.prompts.prompt_loader import load_prompt

    prompt = load_prompt("prd")
    prompt = load_prompt("design", lang="en")
    prompt = load_prompt("prd", custom_dir="./my-project/custom-prompts")

文件查找顺序：
    1. custom_dir（如果指定）
    2. PROMPTS_DIR 环境变量指向的目录（如果设置）
    3. 本文件所在目录下的 {lang}/ 子目录
    4. 本文件所在目录（默认）
"""

import os
from pathlib import Path

# 提示词文件所在目录（本文件所在目录）
_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str, lang: str = "zh", custom_dir: str = "") -> str:
    """
    加载指定名称的提示词文件。

    Args:
        name: 提示词名称（不含扩展名），如 "prd"、"design"
        lang: 语言代码，"zh"（中文默认）或 "en" 等
        custom_dir: 自定义提示词目录路径，用于按项目覆盖

    Returns:
        提示词文本内容

    Raises:
        FileNotFoundError: 未找到对应提示词文件

    文件命名规则：
        {name}.md                  — 默认中文提示词
        {lang}/{name}.md           — 特定语言版本
        例如: prompts/prd.md, prompts/en/prd.md
    """
    # 按优先级依次检查
    search_paths = []

    # 1. 自定义目录
    if custom_dir:
        search_paths.append(Path(custom_dir))

    # 2. 环境变量 PROMPTS_DIR
    env_dir = os.getenv("PROMPTS_DIR")
    if env_dir:
        search_paths.append(Path(env_dir))

    # 3. 语言子目录（非中文时检查）
    if lang != "zh":
        search_paths.append(_PROMPTS_DIR / lang)

    # 4. 默认目录
    search_paths.append(_PROMPTS_DIR)

    # 遍历查找
    for base in search_paths:
        path = base / f"{name}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")

    # 未找到
    searched = "\n  - ".join([str(p / f"{name}.md") for p in search_paths])
    raise FileNotFoundError(
        f"提示词文件未找到: {name}.md\n"
        f"已搜索路径:\n  - {searched}"
    )


def list_available(lang: str = "zh") -> list[str]:
    """列出所有可用的提示词文件名称"""
    pattern = "*.md"
    files = []
    for f in _PROMPTS_DIR.glob(pattern):
        if f.name == "README.md":
            continue
        files.append(f.stem)
    if lang != "zh":
        lang_dir = _PROMPTS_DIR / lang
        if lang_dir.exists():
            for f in lang_dir.glob(pattern):
                files.append(f.stem)
    return sorted(set(files))
