#!/usr/bin/env python3
"""
进销存管理系统生成器 — 入口文件

通过 CrewAI 多 Agent 协作自动生成完整的进销存系统代码。
所有 Agent/Task 提示词从 prompts/ 目录加载，实现代码与提示词完全解耦。

Usage:
    uv run ims-crew            # 完整团队模式
    uv run ims-crew --profile backend-only  # 仅后端模式
    uv run ims-train           # 训练模式
"""

import sys
import argparse
from pathlib import Path

# ── 确保输出目录存在 ──────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "output"
PROJECT_DIR = BASE_DIR / "project"

for d in [OUTPUT_DIR, PROJECT_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def run():
    """执行 Crew，生成进销存系统"""
    parser = argparse.ArgumentParser(description="进销存管理系统生成器")
    parser.add_argument(
        "--profile",
        type=str,
        default="full",
        choices=["full", "backend-only", "prototype"],
        help="团队 Profile（默认 full: 所有角色完整流水线）",
    )
    parser.add_argument(
        "--no-fix",
        action="store_true",
        help="跳过生成后自动修复",
    )
    args = parser.parse_args()

    from .crew import IMSCrew

    print("=" * 60)
    print("  进销存管理系统生成器 — CrewAI 软件开发团队")
    print("=" * 60)
    print()
    print(f"  团队 Profile: {args.profile}")
    if args.profile == "full":
        print("  ├─ 产品经理    — 需求分析")
        print("  ├─ 系统架构师  — 系统设计")
        print("  ├─ 后端工程师  — API 开发")
        print("  ├─ 前端工程师  — 管理后台")
        print("  ├─ QA 工程师   — 测试验证")
        print("  └─ DevOps      — 部署配置")
    print()
    print("  预计运行时间: 5-15 分钟（取决于 LLM 响应速度）")
    print()

    # 执行 Crew
    crew_instance = IMSCrew().crew_with_profile(args.profile)
    result = crew_instance.kickoff()

    print()
    print("=" * 60)
    print("  ✅ 生成完成!")
    print(f"  输出目录: {PROJECT_DIR}")
    print(f"  文档目录: {OUTPUT_DIR}")
    print("=" * 60)

    # 执行生成后修复（默认启用）
    if not args.no_fix:
        print("\n🛠️  执行生成后自动修复...")
        from .fixers.post_gen_fixes import run_all_fixes
        fix_results = run_all_fixes(PROJECT_DIR)
        for category, fixes in fix_results.items():
            for f in fixes:
                print(f"  {f}")
        print()

    print("📋 快速启动:")
    print(f"  cd {PROJECT_DIR}")
    print("  # 方式一: Docker Compose 一键启动")
    print("  docker compose up")
    print()
    print("  # 方式二: 手动运行")
    print("  pip install -r backend/requirements.txt")
    print("  uvicorn backend.main:app --reload --port 8000")
    print()

    return result


def train():
    """使用训练数据优化 Agent 表现"""
    from .crew import IMSCrew

    parser = argparse.ArgumentParser(description="进销存管理系统训练模式")
    parser.add_argument("n_iterations", nargs="?", type=int, default=5,
                        help="训练迭代次数（默认 5）")
    parser.add_argument("filename", nargs="?", type=str, default="training_data.pkl",
                        help="训练数据保存文件（默认 training_data.pkl）")
    args = parser.parse_args(sys.argv[2:])  # 跳过 "train" 子命令

    print(f"🧠 开始训练 (迭代次数: {args.n_iterations})...")
    IMSCrew().crew().train(
        n_iterations=args.n_iterations,
        filename=args.filename,
        inputs={},
    )
    print(f"✅ 训练完成! 数据保存至: {args.filename}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "train":
        train()
    else:
        run()
