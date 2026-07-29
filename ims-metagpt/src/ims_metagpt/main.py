"""
ims-metagpt CLI 入口 — 完整的软件生命周期管理

================================================================================
  ██ 使用场景概览
================================================================================

  场景 1：全新项目（MVP → 迭代 → 重构）
  ──────────────────────────────────────
  # Step 1: 先生成需求文档（PRD），人工审核修改确认
  ims-metagpt plan "生成一个进销存系统，先做商品管理和库存管理" -o ./my-ims

  #   → 人工编辑 ./my-ims/docs/prd.md，确认无误后

  # Step 2: 生成架构设计，人工审核修改确认
  ims-metagpt design -w ./my-ims

  #   → 人工编辑 ./my-ims/docs/design.md，确认无误后

  # Step 3: 生成 MVP 代码
  ims-metagpt code -w ./my-ims --scope mvp

  # Step 4: 迭代增加功能
  ims-metagpt iterate "增加采购管理模块" -w ./my-ims

  # Step 5: 重构优化
  ims-metagpt refactor "提取公共 CRUD 基类" -w ./my-ims


  场景 2：一键全流程（不拆分审核步骤，快速原型）
  ──────────────────────────────────────
  ims-metagpt plan "生成进销存系统" -o ./my-ims --auto


  场景 3：仅查看任务规划（确认需求理解是否正确）
  ──────────────────────────────────────
  ims-metagpt plan "生成进销存系统" -o ./my-ims --plan-only

================================================================================
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from metagpt.environment import Environment
from metagpt.logs import logger
from metagpt.team import Team

# ============================================================
# 导入自定义角色
# ============================================================
from ims_metagpt.roles.ims_architect import IMSArchitect
from ims_metagpt.roles.ims_engineer import IMSEngineer
from ims_metagpt.roles.ims_product_manager import IMSProductManager
from ims_metagpt.roles.ims_team_leader import IMSTeamLeader

# 加载 .env 文件（如果存在），读取 API Key 等环境变量
load_dotenv()

# ============================================================
# Typer CLI 应用
# ============================================================
# typer 是一个 CLI 框架，基于类型注解自动生成 --help 文档
# 源码参考: https://github.com/fastapi/typer
app = typer.Typer(
    name="ims-metagpt",
    help="基于 MetaGPT 的多 Agent 软件团队 — 完整的软件生命周期管理工具",
    add_completion=False,  # 不生成 shell 自动补全脚本（减少学习负担）
)


# ============================================================
# Team 构建函数（内部使用）
# ============================================================
def _build_team(roles: list) -> Team:
    """
    创建并返回一个 Team 实例。

    参数:
        roles: 角色列表，如 [IMSTeamLeader(), IMSProductManager()]

    返回:
        配置好的 Team，已连接 Environment

    架构说明:
    - 使用标准 Environment（非 MGXEnv），消息路由通过 _watch() 机制
    - 源码参考: metagpt/team.py, metagpt/environment/base_env.py
    """
    env = Environment(desc="IMS 软件生成团队工作环境")
    team = Team(investment=10.0, env=env, roles=roles)
    return team


def _ensure_workspace(workspace: str) -> Path:
    """
    确保工作区目录存在，不存在则创建。

    参数:
        workspace: 工作区路径（相对或绝对路径）

    返回:
        标准化后的 Path 对象
    """
    path = Path(workspace).absolute()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_file(filepath: Path) -> str:
    """读取文件内容，文件不存在时返回空字符串"""
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


# ============================================================
# 子命令 1：plan — 生成任务规划和 PRD
# ============================================================
@app.command("plan", help="[Step 1] 生成任务规划和产品需求文档（PRD），供人工审核")
def cmd_plan(
    idea: str = typer.Argument(
        ...,
        help="你的需求描述。例如：'生成一个进销存管理系统，支持商品管理、采购销售'",
        metavar="IDEA",
    ),
    output: str = typer.Option(
        "./ims-output",
        "--output", "-o",
        help="输出目录。所有生成的文件会保存到这个目录下。默认 ./ims-output",
        rich_help_panel="路径选项",
    ),
    scope: str = typer.Option(
        "mvp",
        "--scope", "-s",
        help="""生成范围。
          mvp  = 只规划核心功能（商品管理+库存管理），快速上线
          full = 规划全部功能（商品+采购+销售+库存+报表+系统管理）
        """,
        rich_help_panel="模式选项",
    ),
    plan_only: bool = typer.Option(
        False,
        "--plan-only",
        help="仅生成任务规划，不生成 PRD。用于快速确认需求理解是否正确",
        rich_help_panel="模式选项",
    ),
    auto_confirm: bool = typer.Option(
        False,
        "--auto",
        help="自动模式：跳过人工审核环节，生成后直接继续下一步（不常用，仅用于快速原型）",
        rich_help_panel="模式选项",
    ),
    n_round: int = typer.Option(
        default=10,
        help="最大运行轮次。一般保持默认即可。如果生成内容不完整可以适当增大",
        rich_help_panel="高级选项",
    ),
):
    """
    📋 使用场景：

    这是 MVP 流程的**第一步**。AI 会根据你的需求生成：
      - 任务规划（Task Plan）：需求被拆解成哪些任务
      - PRD（产品需求文档）：每个功能的详细描述

    ✅ 人工审核：
    生成后请打开 output/docs/prd.md，检查功能是否完整。
    修改确认后，再执行 `ims-metagpt design`。

    📝 示例：
      ims-metagpt plan "生成进销存系统" -o ./my-ims
      ims-metagpt plan "生成进销存系统" -o ./my-ims --scope mvp
      ims-metagpt plan "帮我分析需要哪些功能" -o ./preview --plan-only
      ims-metagpt plan "生成博客系统" -o ./blog --auto
    """
    # ---------- 打印参数说明（方便学习）----------
    logger.info("=" * 60)
    logger.info("📋 plan 命令参数")
    logger.info(f"   需求描述 (IDEA):  {idea}")
    logger.info(f"   输出目录 (-o):     {output}")
    logger.info(f"   范围 (--scope):   {scope}")
    logger.info(f"   仅规划 (--plan-only): {plan_only}")
    logger.info(f"   自动模式 (--auto): {auto_confirm}")
    logger.info("=" * 60)

    # ---------- 确保输出目录存在 ----------
    workspace = _ensure_workspace(output)
    docs_dir = workspace / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 组装团队 ----------
    if plan_only:
        # plan-only 模式：只需要 TeamLeader 做任务规划
        roles = [IMSTeamLeader()]
    else:
        # 完整规划模式：TeamLeader → ProductManager 生成 PRD
        roles = [IMSTeamLeader(), IMSProductManager(scope=scope)]

    team = _build_team(roles)
    team.invest(investment=10.0)

    # ---------- 执行 ----------
    try:
        asyncio.run(team.run(n_round=n_round, idea=idea))
    except Exception as e:
        logger.error(f"plan 执行失败: {e}")
        raise typer.Exit(code=1)

    # ---------- 保存产物 ----------
    history = team.env.history.get()
    saved_count = 0
    for msg in history:
        content = msg.content
        if not content or len(content) < 100:
            continue  # 跳过空消息或太短的消息
        # 根据消息特征保存到对应文件
        cause = str(msg.cause_by) if msg.cause_by else ""
        if "PlanTasks" in cause or "任务规划" in content[:100]:
            (docs_dir / "task-plan.md").write_text(content, encoding="utf-8")
            logger.info(f"✅ 已保存任务规划: {docs_dir / 'task-plan.md'}")
            saved_count += 1
        elif "WritePRD" in cause or "PRD" in content[:100] or "产品需求" in content[:100]:
            (docs_dir / "prd.md").write_text(content, encoding="utf-8")
            logger.info(f"✅ 已保存 PRD: {docs_dir / 'prd.md'}")
            saved_count += 1

    # ---------- 下一步指引 ----------
    logger.info("=" * 60)
    logger.info("📌 下一步操作：")
    if plan_only:
        logger.info(f"   ims-metagpt plan \"{idea}\" -o {output}")
        logger.info("   → 不加 --plan-only 生成完整 PRD")
    else:
        logger.info(f"   1. 编辑 {docs_dir / 'prd.md'}，确认或修改内容")
        logger.info(f"   2. 确认无误后执行：")
        logger.info(f"      ims-metagpt design -w {workspace}")
    logger.info("=" * 60)


# ============================================================
# 子命令 2：design — 生成架构设计
# ============================================================
@app.command("design", help="[Step 2] 基于已确认的 PRD，生成系统架构设计，供人工审核")
def cmd_design(
    workspace: str = typer.Option(
        ...,
        "--workspace", "-w",
        help="项目工作区路径（即 plan 命令的 -o 参数指定的目录）",
        rich_help_panel="路径选项",
    ),
    scope: str = typer.Option(
        "mvp",
        "--scope", "-s",
        help="""设计范围。
          mvp  = 只设计核心功能模块，架构简洁
          full = 设计完整功能架构
        """,
        rich_help_panel="模式选项",
    ),
    auto_confirm: bool = typer.Option(
        False,
        "--auto",
        help="自动模式：跳过人工审核（不常用）",
        rich_help_panel="模式选项",
    ),
    n_round: int = typer.Option(
        default=10,
        help="最大运行轮次，一般保持默认",
        rich_help_panel="高级选项",
    ),
):
    """
    🏗️ 使用场景：

    plan 阶段生成的 PRD 经人工审核确认后，用此命令生成**系统架构设计**，包含：
      - 技术栈选型
      - 数据库 ER 图
      - API 路由设计
      - 前端组件设计

    ✅ 前置条件：
      必须先执行 ims-metagpt plan，且 workspace/docs/prd.md 已存在。

    ✅ 人工审核：
      生成后请打开 workspace/docs/design.md 检查。
      确认无误后，再执行 `ims-metagpt code`。

    📝 示例：
      ims-metagpt design -w ./my-ims
      ims-metagpt design -w ./my-ims --scope mvp
      ims-metagpt design -w ./my-ims --auto
    """
    # ---------- 检查前置条件 ----------
    workspace_path = _ensure_workspace(workspace)
    docs_dir = workspace_path / "docs"
    prd_file = docs_dir / "prd.md"

    if not prd_file.exists():
        logger.error(f"❌ 未找到 PRD 文件: {prd_file}")
        logger.error("   请先执行 ims-metagpt plan 生成 PRD")
        logger.error("   示例: ims-metagpt plan \"生成进销存系统\" -o ./my-ims")
        raise typer.Exit(code=1)

    # ---------- 读取 PRD ----------
    prd_content = prd_file.read_text(encoding="utf-8")
    logger.info("=" * 60)
    logger.info(f"🏗️  基于 PRD 生成架构设计")
    logger.info(f"   PRD 来源: {prd_file}")
    logger.info(f"   范围 (--scope): {scope}")
    logger.info("=" * 60)

    # ---------- 组装团队 ----------
    # design 阶段只需要 Architect 角色
    # 通过人工将 PRD 保存到文件，再让 Architect 读取，实现解耦
    # 这样用户修改 PRD 后，Architect 读取的是最新版本
    roles = [IMSArchitect(scope=scope)]
    team = _build_team(roles)
    team.invest(investment=10.0)

    # ---------- 执行 ----------
    try:
        # 将 PRD 内容作为需求输入给 Architect
        asyncio.run(team.run(n_round=n_round, idea=f"请根据以下 PRD 设计系统架构：\n\n{prd_content}"))
    except Exception as e:
        logger.error(f"design 执行失败: {e}")
        raise typer.Exit(code=1)

    # ---------- 保存产物 ----------
    history = team.env.history.get()
    for msg in history:
        content = msg.content
        if len(content) > 200:
            (docs_dir / "design.md").write_text(content, encoding="utf-8")
            logger.info(f"✅ 已保存: {docs_dir / 'design.md'}")
            break

    # ---------- 下一步指引 ----------
    logger.info("=" * 60)
    logger.info("📌 下一步操作：")
    logger.info(f"   1. 编辑 {docs_dir / 'design.md'}，确认或修改内容")
    logger.info(f"   2. 确认无误后执行：")
    logger.info(f"      ims-metagpt code -w {workspace}")
    logger.info("=" * 60)


# ============================================================
# 子命令 3：code — 生成代码
# ============================================================
@app.command("code", help="[Step 3] 基于已确认的设计，生成 MVP 或全量代码")
def cmd_code(
    workspace: str = typer.Option(
        ...,
        "--workspace", "-w",
        help="项目工作区路径（即 plan 命令的 -o 参数指定的目录）",
        rich_help_panel="路径选项",
    ),
    scope: str = typer.Option(
        "mvp",
        "--scope", "-s",
        help="""生成范围。
          mvp  = 只生成核心功能代码（商品管理+库存管理），快速上线验证
          full = 生成全部功能代码（商品+采购+销售+库存+报表+系统管理）
        """,
        rich_help_panel="模式选项",
    ),
    mode: str = typer.Option(
        "full",
        "--mode", "-m",
        help="""生成模式。
          full         = 生成全栈代码（后端+前端+测试）
          backend-only = 只生成后端 API 代码
          frontend-only = 只生成前端页面代码
        """,
        rich_help_panel="模式选项",
    ),
    n_round: int = typer.Option(
        default=15,
        help="""最大运行轮次。MVP 模式建议 10-15，full 模式建议 20-30。
          如果生成的代码不完整，可以增大此值""",
        rich_help_panel="高级选项",
    ),
):
    """
    💻 使用场景：

    design 阶段生成的架构设计经人工审核确认后，用此命令生成**可运行的代码**。

    ✅ 前置条件：
      必须先执行 ims-metagpt design，且 workspace/docs/design.md 已存在。

    🔰 新手建议：
      首次使用建议 --scope mvp（只生成核心功能），减少 Token 消耗，
      验证流程走通后再用 iterate 命令增加功能。

    📝 示例：
      ims-metagpt code -w ./my-ims
      ims-metagpt code -w ./my-ims --scope mvp --mode backend-only
      ims-metagpt code -w ./my-ims --scope full --n-round 25
    """
    # ---------- 检查前置条件 ----------
    workspace_path = _ensure_workspace(workspace)
    docs_dir = workspace_path / "docs"
    design_file = docs_dir / "design.md"

    if not design_file.exists():
        logger.error(f"❌ 未找到 Design 文件: {design_file}")
        logger.error("   请先执行 ims-metagpt design 生成架构设计")
        logger.error("   示例: ims-metagpt design -w ./my-ims")
        raise typer.Exit(code=1)

    # ---------- 参数校验 ----------
    valid_scopes = ["mvp", "full"]
    valid_modes = ["full", "backend-only", "frontend-only"]
    if scope not in valid_scopes:
        logger.error(f"❌ scope 参数必须为 {valid_scopes} 之一，当前值: {scope}")
        raise typer.Exit(code=1)
    if mode not in valid_modes:
        logger.error(f"❌ mode 参数必须为 {valid_modes} 之一，当前值: {mode}")
        raise typer.Exit(code=1)

    # ---------- 读取设计文档 ----------
    design_content = design_file.read_text(encoding="utf-8")
    logger.info("=" * 60)
    logger.info(f"💻 基于架构设计生成代码")
    logger.info(f"   设计来源: {design_file}")
    logger.info(f"   生成范围 (--scope): {scope}")
    logger.info(f"   生成模式 (--mode):  {mode}")
    logger.info("=" * 60)

    # ---------- 构建工程师角色 ----------
    # 将 scope 和 mode 作为参数传给 Engineer
    engineer = IMSEngineer(code_scope=scope, code_mode=mode)
    roles = [engineer]
    team = _build_team(roles)
    team.invest(investment=10.0)

    # ---------- 执行 ----------
    try:
        asyncio.run(team.run(
            n_round=n_round,
            idea=f"请根据以下架构设计生成代码（范围: {scope}, 模式: {mode}）：\n\n{design_content}",
        ))
    except Exception as e:
        logger.error(f"code 执行失败: {e}")
        raise typer.Exit(code=1)

    # ---------- 保存产物 ----------
    history = team.env.history.get()
    output_dir = workspace_path
    for msg in history:
        content = msg.content
        if not content:
            continue
        # 解析代码文件输出（格式：文件路径: xxx  + 内容）
        # Engineer 的输出包含多个文件，按 "文件路径: xxx\n---\n内容" 格式解析
        sections = content.split("---")
        for section in sections:
            section = section.strip()
            if not section:
                continue
            lines = section.split("\n", 1)
            if len(lines) == 2 and ("backend/" in lines[0] or "frontend/" in lines[0] or "tests/" in lines[0]):
                filepath = lines[0].replace("文件路径:", "").strip()
                file_content = lines[1].strip()
                target = output_dir / filepath
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(file_content, encoding="utf-8")
                logger.info(f"✅ 已保存: {target}")

    # ---------- 下一步指引 ----------
    logger.info("=" * 60)
    logger.info("📌 下一步操作：")
    logger.info(f"   1. 查看生成的代码: {output_dir / 'backend'}/")
    logger.info(f"   2. 进入后端目录启动: cd {output_dir / 'backend'} && pip install -r requirements.txt && python run.py")
    logger.info(f"   3. 需要增加功能时执行:")
    logger.info(f"      ims-metagpt iterate \"增加采购管理\" -w {workspace}")
    logger.info("=" * 60)


# ============================================================
# 子命令 4：iterate — 迭代新增功能
# ============================================================
@app.command("iterate", help="[迭代] 在已有代码基础上，增量增加新功能")
def cmd_iterate(
    idea: str = typer.Argument(
        ...,
        help="新增功能描述。例如：'增加采购管理模块，含采购单创建和入库'",
        metavar="IDEA",
    ),
    workspace: str = typer.Option(
        ...,
        "--workspace", "-w",
        help="项目工作区路径（已有代码所在的目录）",
        rich_help_panel="路径选项",
    ),
    n_round: int = typer.Option(
        default=15,
        help="最大运行轮次",
        rich_help_panel="高级选项",
    ),
):
    """
    🔄 使用场景：

    MVP 版本上线后，需要**新增功能**时使用。AI 会：
      1. 读取已有代码，理解现有架构
      2. 规划增量变更
      3. 生成 git diff 格式的变更内容
      4. 输出到工作区

    ✅ 前置条件：
      workspace 中已有通过 code 命令生成的代码。

    📝 示例：
      ims-metagpt iterate "增加采购管理模块，含采购单创建和入库" -w ./my-ims
      ims-metagpt iterate "增加报表统计功能，含销售趋势图表" -w ./my-ims
    """
    workspace_path = _ensure_workspace(workspace)
    backend_dir = workspace_path / "backend"

    if not backend_dir.exists():
        logger.warning(f"⚠️ 未找到 backend 目录: {backend_dir}")
        logger.warning("   确认已在工作区中生成过代码？")

    logger.info("=" * 60)
    logger.info(f"🔄 增量迭代: {idea}")
    logger.info(f"   工作区: {workspace_path}")
    logger.info("=" * 60)

    # ---------- 读取已有代码作为上下文 ----------
    existing_code = ""
    if backend_dir.exists():
        for pyfile in sorted(backend_dir.rglob("*.py")):
            relative = pyfile.relative_to(workspace_path)
            existing_code += f"\n--- {relative} ---\n"
            existing_code += pyfile.read_text(encoding="utf-8")

    # ---------- 构建工程师角色（增量模式） ----------
    engineer = IMSEngineer(code_scope="iterate", code_mode="full", existing_code=existing_code)
    roles = [engineer]
    team = _build_team(roles)
    team.invest(investment=10.0)

    # ---------- 执行 ----------
    try:
        asyncio.run(team.run(n_round=n_round, idea=idea))
    except Exception as e:
        logger.error(f"iterate 执行失败: {e}")
        raise typer.Exit(code=1)

    # ---------- 保存产物 ----------
    history = team.env.history.get()
    for msg in history:
        content = msg.content
        if content and len(content) > 100:
            diff_file = workspace_path / f"changes_{len(list(workspace_path.glob('changes_*')))}.md"
            diff_file.write_text(content, encoding="utf-8")
            logger.info(f"✅ 变更已保存: {diff_file}")

    logger.info("=" * 60)
    logger.info("📌 下一步操作：")
    logger.info(f"   1. 审查变更文件，确认无误后应用到代码")
    logger.info(f"   2. 需要继续迭代执行:")
    logger.info(f"      ims-metagpt iterate \"下一个功能\" -w {workspace}")
    logger.info("=" * 60)


# ============================================================
# 子命令 5：refactor — 代码重构
# ============================================================
@app.command("refactor", help="[重构] 对已有代码进行重构优化")
def cmd_refactor(
    idea: str = typer.Argument(
        ...,
        help="重构目标描述。例如：'提取公共 CRUD 基类，统一错误处理'",
        metavar="IDEA",
    ),
    workspace: str = typer.Option(
        ...,
        "--workspace", "-w",
        help="项目工作区路径",
        rich_help_panel="路径选项",
    ),
    n_round: int = typer.Option(
        default=15,
        help="最大运行轮次",
        rich_help_panel="高级选项",
    ),
):
    """
    🔧 使用场景：

    代码累积了一定量的技术债务后，需要对**已有代码进行重构优化**。

    与 iterate 的区别：
      - iterate = 新增功能（加代码）
      - refactor = 优化已有代码（改代码，不改功能）

    📝 示例：
      ims-metagpt refactor "提取公共 CRUD 基类，减少重复代码" -w ./my-ims
      ims-metagpt refactor "统一错误处理中间件，添加请求日志" -w ./my-ims
    """
    workspace_path = _ensure_workspace(workspace)

    # ---------- 读取已有代码 ----------
    existing_code = ""
    for ext in ["*.py", "*.html", "*.js", "*.css"]:
        for f in sorted(workspace_path.rglob(ext)):
            if ".git" in str(f) or "__pycache__" in str(f):
                continue
            relative = f.relative_to(workspace_path)
            existing_code += f"\n--- {relative} ---\n"
            existing_code += f.read_text(encoding="utf-8")

    logger.info("=" * 60)
    logger.info(f"🔧 代码重构: {idea}")
    logger.info(f"   工作区: {workspace_path}")
    logger.info(f"   读取了 {len(existing_code)} 字符的现有代码")
    logger.info("=" * 60)

    # ---------- 构建工程师角色（重构模式） ----------
    engineer = IMSEngineer(code_scope="refactor", code_mode="full", existing_code=existing_code)
    roles = [engineer]
    team = _build_team(roles)
    team.invest(investment=10.0)

    # ---------- 执行 ----------
    try:
        asyncio.run(team.run(n_round=n_round, idea=idea))
    except Exception as e:
        logger.error(f"refactor 执行失败: {e}")
        raise typer.Exit(code=1)

    # ---------- 保存产物 ----------
    history = team.env.history.get()
    for msg in history:
        content = msg.content
        if content and len(content) > 100:
            diff_file = workspace_path / f"refactor_{len(list(workspace_path.glob('refactor_*')))}.md"
            diff_file.write_text(content, encoding="utf-8")
            logger.info(f"✅ 重构方案已保存: {diff_file}")

    logger.info("=" * 60)
    logger.info(f"📌 重构方案已生成，请审查 {workspace_path / 'refactor_*.md'} 后手动应用")
    logger.info("=" * 60)


# ============================================================
# 子命令 6：list-modes — 显示帮助
# ============================================================
@app.command("list-modes", help="显示所有命令和参数说明")
def cmd_list_modes():
    """列出所有可用命令及其用途"""
    typer.echo("")
    typer.echo("╔══════════════════════════════════════════════════════════╗")
    typer.echo("║            ims-metagpt 命令速查表                       ║")
    typer.echo("╚══════════════════════════════════════════════════════════╝")
    typer.echo("")
    typer.echo("📋  完整工程化流程（推荐）：")
    typer.echo("")
    typer.echo("  Step 1: 生成需求文档 → 人工审核")
    typer.echo("    ims-metagpt plan \"你的需求描述\" -o ./my-project")
    typer.echo("    └── 编辑 ./my-project/docs/prd.md，确认内容")
    typer.echo("")
    typer.echo("  Step 2: 生成架构设计 → 人工审核")
    typer.echo("    ims-metagpt design -w ./my-project")
    typer.echo("    └── 编辑 ./my-project/docs/design.md，确认内容")
    typer.echo("")
    typer.echo("  Step 3: 生成 MVP 代码")
    typer.echo("    ims-metagpt code -w ./my-project --scope mvp")
    typer.echo("")
    typer.echo("  Step 4: 迭代增加功能")
    typer.echo("    ims-metagpt iterate \"增加XX功能\" -w ./my-project")
    typer.echo("")
    typer.echo("  Step 5: 重构优化")
    typer.echo("    ims-metagpt refactor \"重构目标\" -w ./my-project")
    typer.echo("")
    typer.echo("🔧  所有命令：")
    typer.echo("  plan     生成任务规划和 PRD")
    typer.echo("  design   生成架构设计")
    typer.echo("  code     生成代码")
    typer.echo("  iterate  增量迭代（加功能）")
    typer.echo("  refactor 代码重构（改质量）")
    typer.echo("  list-modes  显示本帮助")
    typer.echo("  init-config 初始化 MetaGPT 配置")
    typer.echo("")
    typer.echo("💡  每个命令后加 --help 查看参数详情")
    typer.echo("   如: ims-metagpt code --help")
    typer.echo("")


# ============================================================
# 子命令 7：init-config — 初始化配置
# ============================================================
@app.command("init-config", help="初始化 MetaGPT 配置文件 (~/.metagpt/config2.yaml)")
def cmd_init_config():
    """将项目自带的 config2.yaml 复制到 ~/.metagpt/"""
    import shutil

    src = Path(__file__).parent.parent / "config" / "config2.yaml"
    target = Path.home() / ".metagpt" / "config2.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        backup = target.with_suffix(".bak")
        shutil.copy2(target, backup)
        typer.echo(f"原配置已备份至: {backup}")

    shutil.copy2(src, target)
    typer.echo(f"✅ 配置文件已初始化至: {target}")
    typer.echo("请编辑该文件，填入你的 API Key。")


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    app()
