#!/usr/bin/env python3
"""
技能打包器 —— 把技能目录打包成可分发的 .skill 文件

用法：
    python -m scripts.package_skill <path/to/skill-folder> [--output output-dir]

示例：
    python -m scripts.package_skill skills/public/my-skill
    python -m scripts.package_skill skills/public/my-skill --output ./dist
"""

import fnmatch
import sys
import zipfile
from pathlib import Path

from scripts.quick_validate import validate_skill
from scripts.utils import ensure_utf8_stdio

# 打包时需要排除的模式
EXCLUDE_DIRS = {"__pycache__", "node_modules"}
EXCLUDE_GLOBS = {"*.pyc", "*.skill"}
EXCLUDE_FILES = {".DS_Store"}
# 只在技能根目录（不在更深层）排除的目录
ROOT_EXCLUDE_DIRS = {"evals"}


def should_exclude(rel_path: Path) -> bool:
    """检查一个路径是否应从打包中排除。"""
    parts = rel_path.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    # rel_path 相对于 skill_path.parent，所以 parts[0] 是技能
    # 目录名，parts[1]（如果存在）是第一个子目录。
    if len(parts) > 1 and parts[1] in ROOT_EXCLUDE_DIRS:
        return True
    name = rel_path.name
    if name in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_GLOBS)


def package_skill(skill_path, output_dir=None):
    """
    把技能目录打包成 .skill 文件。

    参数：
        skill_path: 技能目录的路径
        output_dir: .skill 文件的输出目录（可选，默认当前目录）

    返回：
        创建的 .skill 文件路径，出错时返回 None
    """
    skill_path = Path(skill_path).resolve()

    # 校验技能目录存在
    if not skill_path.exists():
        print(f"[错误] 技能目录不存在：{skill_path}")
        return None

    if not skill_path.is_dir():
        print(f"[错误] 路径不是目录：{skill_path}")
        return None

    # 校验 SKILL.md 存在
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        print(f"[错误] 在 {skill_path} 中未找到 SKILL.md")
        return None

    # 打包前先校验
    print("[信息] 正在校验技能……")
    valid, message = validate_skill(skill_path)
    if not valid:
        print(f"[错误] 校验失败：{message}")
        print("   请先修复校验错误再打包。")
        return None
    print(f"[成功] {message}\n")

    # 确定输出位置
    skill_name = skill_path.name
    if output_dir:
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = Path.cwd()

    skill_filename = output_path / f"{skill_name}.skill"

    # 创建 .skill 文件（zip 格式）
    try:
        with zipfile.ZipFile(skill_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 遍历技能目录，排除构建产物
            for file_path in skill_path.rglob('*'):
                if not file_path.is_file():
                    continue
                rel_path = file_path.relative_to(skill_path.parent)
                arcname = rel_path.as_posix()
                if should_exclude(rel_path):
                    print(f"  已跳过：{arcname}")
                    continue
                zipf.write(file_path, arcname)
                print(f"  已添加：{arcname}")

        print(f"\n[成功] 技能已打包到：{skill_filename}")
        return skill_filename

    except Exception as e:
        print(f"[错误] 创建 .skill 文件失败：{e}")
        return None


def main():
    ensure_utf8_stdio()
    import argparse
    parser = argparse.ArgumentParser(description="把技能目录打包成 .skill 文件")
    parser.add_argument("skill_path", help="技能目录的路径")
    parser.add_argument("--output", "-o", default=None, help=".skill 文件的输出目录（默认：当前目录）")
    args = parser.parse_args()

    skill_path = args.skill_path
    output_dir = args.output

    print(f"[信息] 正在打包技能：{skill_path}")
    if output_dir:
        print(f"   输出目录：{output_dir}")
    print()

    result = package_skill(skill_path, output_dir)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
