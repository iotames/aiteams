#!/usr/bin/env python3
"""
技能初始化脚手架 —— 从模板生成新技能目录与 SKILL.md

用法：
    python -m scripts.init_skill <skill-name> --path <输出目录> [--resources scripts,references,assets] [--examples] [--minimal]

示例：
    python -m scripts.init_skill flipbook-download --path ~/.agents/skills
    python -m scripts.init_skill my-api-helper --path ~/.agents/skills --resources scripts,references --examples
"""

import argparse
import re
import sys
from pathlib import Path

from scripts.utils import ensure_utf8_stdio

MAX_SKILL_NAME_LENGTH = 64
ALLOWED_RESOURCES = {"scripts", "references", "assets"}

SKILL_TEMPLATE = """---
name: {skill_name}
description: >-
  [TODO: 用 1-2 句话说明该技能让智能体做什么，并写清楚"何时使用"的触发
  场景（用户表达、文件类型、任务类型）。description 是触发机制的核心，
  写得稍微强势一点，覆盖正式/随意/隐晦的表述。]
---

# {skill_title}

## 概述

[TODO: 1-2 句话说明该技能实现什么]

## [TODO: 设计主章节，替换本行]

正文结构按任务自然形态**自由设计**，没有固定模板。只有对结构拿不准时才参考
创建工具（skill-creator）自带的 `references/structure-patterns.md` 常见模式；
模式只是起点，不要为了套模板而扭曲内容。

[TODO: 添加正文。要点：
- 使用祈使句，解释"为什么"而不是堆砌"必须"
- 包含具体示例（输入 → 输出）
- 输出格式用模板明确定义
- 「何时使用」只写进 description，不写进正文
- 技能内不放 README/CHANGELOG 等杂质文档
- 同一信息只存在一个地方（SKILL.md 或 references/）
- 需要复杂细节时用 references/ 按需加载，正文保持精简（<500 行）
- 确定性/重复性任务用 scripts/ 脚本
- 输出资源（模板、图标、字体）放 assets/]

## 资源（可选）

只创建本技能实际需要的资源目录；不需要就删除本段。

### scripts/

可执行代码（Python/Shell 等），用于确定性、可重复的任务。执行时无需加载进上下文。

### references/

按需加载的文档。API 参考、数据库 schema、领域知识、详细流程指南等太长或低频的内容放这里，由 SKILL.md 指引何时读取。

### assets/

不加载进上下文、而是用于输出的文件：模板、图标、字体、示例文档等。

---

**并非每个技能都需要三类资源。**
"""

MINIMAL_TEMPLATE = """---
name: {skill_name}
description: >-
  [TODO: 用 1-2 句话说明该技能让智能体做什么，并写清楚"何时使用"的触发
  场景（用户表达、文件类型、任务类型）。description 是触发机制的核心，
  写得稍微强势一点，覆盖正式/随意/隐晦的表述。]
---

# {skill_title}

[TODO: 正文。结构完全自由设计。]
"""

EXAMPLE_SCRIPT = '''#!/usr/bin/env python3
"""
{skill_name} 的示例辅助脚本 —— 占位实现，按需替换或删除。

例：数据处理、文件转换、API 调用等确定性任务都可以放进 scripts/。
"""


def main() -> None:
    print("这是 {skill_name} 的示例脚本")
    # TODO: 添加实际逻辑


if __name__ == "__main__":
    main()
'''

EXAMPLE_REFERENCE = """# {skill_title} 参考文档

[TODO: 替换为实际参考内容，或删除本文件]

适合放进 references/ 的内容：
- API 参考与端点示例
- 数据库 schema 与查询模式
- 详细的多步流程指南
- 正文放不下、只在特定场景才需要的信息

结构建议：概述 → 前置条件 → 分步说明 → 常见模式 → 故障排查。
"""

EXAMPLE_ASSET = """# 示例资源文件

[TODO: 替换为实际资源（模板、图标、字体等），或删除本文件]

assets/ 存放**不加载进上下文、直接用于输出**的文件：
- 模板：.pptx、.docx、样板目录
- 图片：.png、.jpg、.svg
- 字体：.ttf、.otf
- 数据：.csv、.json
"""


def normalize_skill_name(skill_name: str) -> str:
    """把用户输入规范化为 kebab-case 技能名。"""
    normalized = re.sub(r"[^a-z0-9]+", "-", skill_name.strip().lower())
    normalized = normalized.strip("-")
    return re.sub(r"-{2,}", "-", normalized)


def title_case_skill_name(skill_name: str) -> str:
    """把 kebab-case 技能名转成标题（英文技能名显示用）。"""
    return " ".join(word.capitalize() for word in skill_name.split("-"))


def parse_resources(raw_resources: str) -> list[str]:
    """解析 --resources 逗号列表，校验合法性并去重。"""
    if not raw_resources:
        return []
    resources = [item.strip() for item in raw_resources.split(",") if item.strip()]
    invalid = sorted({item for item in resources if item not in ALLOWED_RESOURCES})
    if invalid:
        allowed = ", ".join(sorted(ALLOWED_RESOURCES))
        print(f"[错误] 未知资源类型：{', '.join(invalid)}")
        print(f"   允许值：{allowed}")
        sys.exit(1)
    return list(dict.fromkeys(resources))


def create_resource_dirs(skill_dir: Path, skill_name: str, skill_title: str,
                         resources: list[str], include_examples: bool) -> None:
    """创建资源目录；--examples 时附带示例文件。"""
    for resource in resources:
        resource_dir = skill_dir / resource
        resource_dir.mkdir(exist_ok=True)
        if not include_examples:
            print(f"[OK] 已创建 {resource}/")
            continue
        if resource == "scripts":
            (resource_dir / "example.py").write_text(
                EXAMPLE_SCRIPT.format(skill_name=skill_name), encoding="utf-8")
            print("[OK] 已创建 scripts/example.py（按需替换或删除）")
        elif resource == "references":
            (resource_dir / "api_reference.md").write_text(
                EXAMPLE_REFERENCE.format(skill_title=skill_title), encoding="utf-8")
            print("[OK] 已创建 references/api_reference.md（按需替换或删除）")
        elif resource == "assets":
            (resource_dir / "example_asset.txt").write_text(
                EXAMPLE_ASSET, encoding="utf-8")
            print("[OK] 已创建 assets/example_asset.txt（按需替换或删除）")


def init_skill(skill_name: str, path: str, resources: list[str],
               include_examples: bool, minimal: bool = False) -> Path | None:
    """初始化技能目录：创建目录、生成 SKILL.md 模板、可选资源目录。

    返回技能目录路径，失败返回 None。
    """
    try:
        return _init_skill(skill_name, path, resources, include_examples, minimal)
    except OSError as e:
        # 权限不足、磁盘错误、目录被占用（含损坏符号链接）等统一友好报错
        print(f"[错误] 无法创建技能：{e}")
        return None


def _init_skill(skill_name: str, path: str, resources: list[str],
                include_examples: bool, minimal: bool = False) -> Path | None:
    """init_skill 的实际实现；I/O 错误由 init_skill 统一捕获。"""
    if len(skill_name) > MAX_SKILL_NAME_LENGTH:
        print(f"[错误] 技能名过长（{len(skill_name)} 字符），上限 {MAX_SKILL_NAME_LENGTH}。")
        return None

    skill_dir = Path(path).expanduser().resolve() / skill_name
    if skill_dir.exists():
        print(f"[错误] 技能目录已存在：{skill_dir}")
        return None

    skill_dir.mkdir(parents=True, exist_ok=False)
    print(f"[OK] 已创建技能目录：{skill_dir}")

    skill_title = title_case_skill_name(skill_name)
    template = MINIMAL_TEMPLATE if minimal else SKILL_TEMPLATE
    (skill_dir / "SKILL.md").write_text(
        template.format(skill_name=skill_name, skill_title=skill_title),
        encoding="utf-8")
    print(f"[OK] 已创建 SKILL.md{'（空画布）' if minimal else ' 模板'}")

    if resources:
        create_resource_dirs(skill_dir, skill_name, skill_title, resources, include_examples)

    print(f"\n[OK] 技能 '{skill_name}' 初始化完成")
    print("下一步：")
    print("1. 编辑 SKILL.md，完成 TODO 并更新 description")
    print("2. 按需替换或删除示例文件")
    print("3. 运行校验：python -m scripts.quick_validate <技能目录>")
    print("4. 复杂技能建议前向测试（见 SKILL.md「四、前向测试」）")
    return skill_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从模板生成新技能目录与 SKILL.md")
    parser.add_argument("skill_name", help="技能名（自动规范化为 kebab-case）")
    parser.add_argument("--path", required=True, help="技能目录的输出位置")
    parser.add_argument(
        "--resources", default="",
        help="逗号分隔的资源目录：scripts,references,assets")
    parser.add_argument(
        "--examples", action="store_true",
        help="在选中的资源目录里创建示例文件")
    parser.add_argument(
        "--minimal", action="store_true",
        help="生成空画布 SKILL.md（仅 frontmatter 与标题，结构完全自由）")
    args = parser.parse_args()

    skill_name = normalize_skill_name(args.skill_name)
    if not skill_name:
        print("[错误] 技能名必须包含至少一个字母或数字。")
        sys.exit(1)
    if len(skill_name) > MAX_SKILL_NAME_LENGTH:
        print(f"[错误] 技能名过长（{len(skill_name)} 字符），上限 {MAX_SKILL_NAME_LENGTH}。")
        sys.exit(1)
    if skill_name != args.skill_name:
        print(f"提示：技能名已从 '{args.skill_name}' 规范化为 '{skill_name}'。")

    resources = parse_resources(args.resources)
    if args.examples and not resources:
        print("[错误] --examples 需要同时设置 --resources。")
        sys.exit(1)

    result = init_skill(skill_name, args.path, resources, args.examples, args.minimal)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    ensure_utf8_stdio()
    main()
