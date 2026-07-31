#!/usr/bin/env python3
"""
技能快速校验脚本 —— 最小版本
"""

import json
import re
import sys
from pathlib import Path

# 复用 utils 的 frontmatter 解析（避免行为漂移）；独立运行（python scripts/quick_validate.py）
# 时 scripts 包不可用，回退到同目录的 utils 模块。
try:
    from scripts.utils import ensure_utf8_stdio, extract_frontmatter
except ImportError:
    from utils import ensure_utf8_stdio, extract_frontmatter

EVALS_SCHEMA_FIELDS = ('id', 'prompt', 'expected_output', 'files', 'expectations')


def validate_evals_json(skill_path: Path, skill_name: str):
    """按 references/schemas.md 校验 evals/evals.json。

    返回 (ok, message)；message 在有警告时非空。
    """
    evals_file = skill_path / 'evals' / 'evals.json'
    if not evals_file.exists():
        return True, ""
    try:
        data = json.loads(evals_file.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return False, f"evals/evals.json 不是合法的 JSON：{e}"

    if not isinstance(data, dict) or 'skill_name' not in data:
        return False, "evals/evals.json 必须是包含 'skill_name' 字段的对象"
    if data['skill_name'] != skill_name:
        return False, (
            f"evals/evals.json 中的 'skill_name' ({data['skill_name']!r}) "
            f"与 frontmatter 中的 'name' ({skill_name!r}) 不一致"
        )

    evals = data.get('evals')
    if not isinstance(evals, list) or not evals:
        return False, "evals/evals.json 中的 'evals' 必须是非空列表"

    for i, item in enumerate(evals):
        if not isinstance(item, dict):
            return False, f"evals[{i}] 必须是对象"
        for field in ('id', 'prompt', 'expected_output'):
            if field not in item:
                return False, f"evals[{i}] 缺少必填字段 '{field}'"
        if not isinstance(item['id'], int):
            return False, f"evals[{i}].id 必须是整数"
        for field in ('prompt', 'expected_output'):
            if not isinstance(item[field], str) or not item[field].strip():
                return False, f"evals[{i}].{field} 必须是非空字符串"
        for field in ('files', 'expectations'):
            if field in item:
                if not isinstance(item[field], list) or not all(isinstance(x, str) for x in item[field]):
                    return False, f"evals[{i}].{field} 必须是字符串列表"
        unknown = set(item) - set(EVALS_SCHEMA_FIELDS)
        if unknown:
            return True, (
                f"evals[{i}] 包含 schema 之外的字段 {sorted(unknown)}；"
                f"允许的字段：{sorted(EVALS_SCHEMA_FIELDS)}（参见 references/schemas.md）"
            )
    return True, ""


def validate_skill(skill_path):
    """技能的基础校验"""
    skill_path = Path(skill_path).resolve()

    # 检查 SKILL.md 是否存在
    skill_md = skill_path / 'SKILL.md'
    if not skill_md.exists():
        return False, "SKILL.md 不存在"

    # 读取并校验 frontmatter
    try:
        content = skill_md.read_text(encoding="utf-8-sig")  # utf-8-sig 会去除开头 BOM
    except UnicodeDecodeError:
        return False, "SKILL.md 不是合法的 UTF-8 文本"
    if not content.startswith('---'):
        return False, "未找到 YAML frontmatter"

    # 解析 frontmatter（与 utils.parse_skill_md 共用同一套逻辑）
    try:
        frontmatter, frontmatter_text, _ = extract_frontmatter(content)
    except ValueError as e:
        return False, str(e)
    if frontmatter is None or not isinstance(frontmatter, dict):
        return False, "frontmatter 必须是 YAML 字典"

    warnings: list[str] = []

    # 定义允许的属性
    ALLOWED_PROPERTIES = {'name', 'description', 'license', 'allowed-tools', 'metadata', 'compatibility'}

    # 检查意外属性（不检查 metadata 下的嵌套键）
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_PROPERTIES
    if unexpected_keys:
        return False, (
            f"SKILL.md frontmatter 中有意外键：{', '.join(sorted(unexpected_keys))}。"
            f"允许的属性：{', '.join(sorted(ALLOWED_PROPERTIES))}"
        )

    # 检查必填字段
    if 'name' not in frontmatter:
        return False, "frontmatter 中缺少 'name'"
    if 'description' not in frontmatter:
        return False, "frontmatter 中缺少 'description'"

    # 提取 name 用于校验
    name = frontmatter.get('name', '')
    if not isinstance(name, str):
        return False, f"name 必须是字符串，实际为 {type(name).__name__}"
    name = name.strip()
    if not name:
        return False, "name 不能为空"

    # 检查命名规范（kebab-case：小写字母、数字、连字符）
    if not re.match(r'^[a-z0-9-]+$', name):
        return False, f"名称 '{name}' 应使用 kebab-case（仅小写字母、数字和连字符）"
    if name.startswith('-') or name.endswith('-') or '--' in name:
        return False, f"名称 '{name}' 不能以连字符开头/结尾，也不能包含连续连字符"
    # 检查名称长度（规范要求最大 64 字符）
    if len(name) > 64:
        return False, f"名称过长（{len(name)} 个字符），最大为 64 个字符"
    # 检查名称与父目录名一致（规范要求）
    if skill_path.name != name:
        return False, (
            f"名称 '{name}' 与父目录名称 '{skill_path.name}' 不匹配。"
            "规范要求 name 字段与技能目录名一致。"
        )

    # 提取并校验 description
    description = frontmatter.get('description', '')
    if not isinstance(description, str):
        return False, f"description 必须是字符串，实际为 {type(description).__name__}"
    description = description.strip()
    if not description:
        return False, "description 不能为空"
    # 检查尖括号
    if '<' in description or '>' in description:
        return False, "description 不能包含尖括号（< 或 >）"
    # 检查描述长度（规范要求最大 1024 字符）
    if len(description) > 1024:
        return False, f"description 过长（{len(description)} 个字符），最大为 1024 个字符"

    # 校验 compatibility 字段（可选）
    compatibility = frontmatter.get('compatibility', '')
    if compatibility:
        if not isinstance(compatibility, str):
            return False, f"compatibility 必须是字符串，实际为 {type(compatibility).__name__}"
        if len(compatibility) > 500:
            return False, f"compatibility 过长（{len(compatibility)} 个字符），最大为 500 个字符"

    # 校验 allowed-tools 格式（规范：空格分隔的字符串）
    allowed_tools = frontmatter.get('allowed-tools')
    if allowed_tools is not None:
        if isinstance(allowed_tools, list):
            return False, (
                "'allowed-tools' 必须是空格分隔的字符串，而不是 YAML 列表。"
                "示例：allowed-tools: Read Write Bash(git:*)"
            )
        if not isinstance(allowed_tools, str) or not allowed_tools.strip():
            return False, "'allowed-tools' 必须是非空且以空格分隔的字符串"
        if ',' in allowed_tools:
            return False, (
                "'allowed-tools' 必须以空格分隔，而不是逗号："
                f"{allowed_tools!r}"
            )

    # 校验 metadata 字段（规范：字符串到字符串的映射）
    metadata = frontmatter.get('metadata')
    if metadata is not None:
        if not isinstance(metadata, dict):
            return False, "'metadata' 必须是 YAML 映射（字符串到字符串）"
        for k, v in metadata.items():
            if not isinstance(k, str) or not isinstance(v, str):
                return False, (
                    "'metadata' 的键和值必须全部是字符串；"
                    f"键={k!r} 类型={type(v).__name__}"
                )

    # 按 references/schemas.md 校验 evals.json（如存在）
    eval_ok, eval_msg = validate_evals_json(skill_path, name)
    if not eval_ok:
        return False, eval_msg
    if eval_msg:
        warnings.append(eval_msg)

    # 存在 LICENSE 文件但未声明 license 字段时给出警告（不阻塞）
    license_field = frontmatter.get('license')
    has_license_file = (skill_path / 'LICENSE.txt').exists() or (skill_path / 'LICENSE').exists()
    if has_license_file and not license_field:
        warnings.append(
            "发现随附的许可文件，但 frontmatter 中缺少 'license' 字段。"
            "建议添加，例如 'license: Apache-2.0'。"
        )

    message = "技能校验通过！"
    if warnings:
        message += "\n" + "\n".join(f"警告：{w}" for w in warnings)
    return True, message

if __name__ == "__main__":
    # `python scripts/quick_validate.py <skill_directory>`（无需包上下文）。
    ensure_utf8_stdio()
    if len(sys.argv) != 2:
        print("用法：python -m scripts.quick_validate <skill_directory>")
        sys.exit(1)

    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
