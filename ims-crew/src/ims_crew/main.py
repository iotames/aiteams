#!/usr/bin/env python3
"""
进销存管理系统生成器 — 入口文件

通过 CrewAI 多 Agent 协作自动生成完整的进销存系统代码。
所有 Agent/Task 提示词从 prompts/ 目录加载，实现代码与提示词完全解耦。

用法:
    uv run ims-crew                          # 全流程 6 角色
    uv run ims-crew --from backend           # 从后端开发开始(断点续跑)
    uv run ims-crew --only pm,arch,backend,qa  # 只跑指定角色
    uv run ims-train                         # 训练模式
"""

import logging
import os
import sys
import argparse
from pathlib import Path

# ── 日志配置 ──────────────────────────────────────────────
LOG_LEVEL = os.environ.get("CREW_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ims-crew")

# ── 确保输出目录存在 ──────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "output"
PROJECT_DIR = BASE_DIR / "project"

for d in [OUTPUT_DIR, PROJECT_DIR]:
    d.mkdir(parents=True, exist_ok=True)


ROLE_SHORT_NAMES = ["pm", "arch", "backend", "frontend", "qa", "devops"]


def _check_env() -> None:
    """检查运行环境：.env 文件和必要的 API Key。"""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        logger.warning(
            ".env 文件不存在，请从 .env.example 复制并配置 API Key:\n"
            "  cp .env.example .env\n"
            "  然后编辑 .env 填入 LLM API Key"
        )

    # 检查是否有任何 LLM API Key 配置
    key_envs = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY"]
    has_key = any(os.environ.get(k) or (env_file.exists() and k in env_file.read_text(encoding="utf-8")) for k in key_envs)
    if not has_key:
        logger.warning(
            "未检测到任何 LLM API Key。请配置至少一个:\n"
            "  OPENAI_API_KEY / ANTHROPIC_API_KEY / DEEPSEEK_API_KEY / OPENROUTER_API_KEY"
        )


def _parse_role_list(value: str) -> list[str]:
    """解析逗号分隔的角色短名列表，返回完整角色名。"""
    from .crew import ROLE_ALIASES

    raw = [s.strip() for s in value.split(",")]
    for s in raw:
        if s not in ROLE_ALIASES:
            print(f"  ❌ 未知角色: {s}，可选: {', '.join(ROLE_ALIASES.keys())}")
            sys.exit(1)
    return [ROLE_ALIASES[s] for s in raw]


def run():
    """执行 Crew，生成进销存系统"""
    _check_env()

    parser = argparse.ArgumentParser(description="进销存管理系统生成器")
    parser.add_argument(
        "--from", dest="resume_from",
        type=str, default="",
        choices=ROLE_SHORT_NAMES + [""],
        help="从指定角色开始（跳过前面的角色）: pm / arch / backend / frontend / qa / devops",
    )
    parser.add_argument(
        "--only",
        type=str, default="",
        help="只运行指定角色(逗号分隔): pm,arch,backend,qa",
    )
    parser.add_argument(
        "--skip-post-fix",
        action="store_true",
        help="跳过生成后自动修复（原名 --no-fix，仍兼容）",
    )
    parser.add_argument(
        "--no-fix",  # 兼容旧参数名
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--qa-rounds",
        type=int,
        default=5,
        help="QA 反馈闭环轮数（默认 5，最大 20，设为 0 跳过闭环）",
    )
    args = parser.parse_args()

    # ── 参数验证 ──
    if args.qa_rounds < 0:
        print("  ❌ --qa-rounds 不能为负数")
        sys.exit(1)
    if args.qa_rounds > 20:
        print("  ⚠️  --qa-rounds 最大值为 20，已自动限制为 20")
        args.qa_rounds = 20

    from .crew import IMSCrew, ROLE_ALIASES, ROLE_ORDER, ROLE_DISPLAY

    # 解析参数
    only_roles = _parse_role_list(args.only) if args.only else None
    resume_from = ROLE_ALIASES.get(args.resume_from) if args.resume_from else None

    # 兼容 --no-fix（旧参数名）
    skip_post_fix = args.skip_post_fix or args.no_fix

    # 打印流水线概要
    print("=" * 60)
    print("  进销存管理系统生成器 — CrewAI 软件开发团队")
    print("=" * 60)
    print()

    if resume_from:
        idx = ROLE_ORDER.index(resume_from)
        print(f"  断点续跑: 从 {ROLE_DISPLAY[resume_from]} 开始")
        print(f"  ── 跳过: {' → '.join(ROLE_DISPLAY[r] for r in ROLE_ORDER[:idx])}")
        print(f"  ── 执行: {' → '.join(ROLE_DISPLAY[r] for r in ROLE_ORDER[idx:])}")
    elif only_roles:
        print(f"  仅运行: {' → '.join(ROLE_DISPLAY[r] for r in only_roles)}")
    else:
        print("  全流程 6 角色:")
        print("  ├─ 产品经理    → 需求分析    (output/PRD.md)")
        print("  ├─ 系统架构师  → 系统设计    (output/ARCHITECTURE.md + openapi.yaml)")
        print("  ├─ 后端工程师  → API 开发    (project/backend/)")
        print("  ├─ 前端工程师  → 管理后台    (project/frontend/)")
        print("  ├─ QA 工程师   → 测试验证    (project/tests/ + QA_REPORT.md)")
        print("  └─ DevOps      → 部署配置    (project/Dockerfile + docker-compose)")
    if args.qa_rounds > 0 and (resume_from or not only_roles or "qa" in (args.only or "").split(",")):
        print(f"  QA 反馈闭环: {args.qa_rounds} 轮 修复→测试循环")
    else:
        print("  QA 反馈闭环: 关闭")
    if skip_post_fix:
        print("  生成后自动修复: 跳过")
    else:
        print("  生成后自动修复: 启用")
    print()
    print("  预计运行时间: 5-15 分钟（取决于 LLM 响应速度）")
    print()

    # 执行 Crew
    crew_instance = IMSCrew()
    assembled = crew_instance.crew_with_options(
        resume_from=resume_from,
        only_roles=only_roles,
        qa_rounds=args.qa_rounds,
    )
    result = assembled.kickoff()

    print()
    print("=" * 60)
    print("  ✅ 生成完成!")
    print(f"  文档目录: {OUTPUT_DIR}")
    print(f"  代码目录: {PROJECT_DIR}")
    print("=" * 60)

    # 执行生成后修复（默认启用）
    if not skip_post_fix:
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

    logger.info("生成完成，结果见 %s 和 %s", OUTPUT_DIR, PROJECT_DIR)
    return result


def train():
    """使用训练数据优化 Agent 表现"""
    from .crew import IMSCrew

    parser = argparse.ArgumentParser(description="进销存管理系统训练模式")
    parser.add_argument("n_iterations", nargs="?", type=int, default=5,
                        help="训练迭代次数（默认 5）")
    parser.add_argument("filename", nargs="?", type=str, default="training_data.pkl",
                        help="训练数据保存文件（默认 training_data.pkl）")
    # 使用 parse_known_args 避免与父命令的 argparse 冲突
    args, _ = parser.parse_known_args()

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
