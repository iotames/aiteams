"""
ims-autogen CLI 入口 — 多 Agent 对话式软件团队。

一条命令启动完整的多角色对话：
  产品经理 <-> 用户（需求澄清）
  -> 架构师 <-> 产品经理（设计确认）
  -> 开发 <-> 架构师（技术答疑）
  -> 测试 <-> 开发（bug 修复循环）
  -> 产品经理（最终验收）
"""

import asyncio
import os
from pathlib import Path

import typer
from dotenv import load_dotenv

from autogen_agentchat.ui import Console

from .team import build_team

# 加载 .env 文件（必须在任何 get_config() 调用之前）
load_dotenv()

app = typer.Typer(
    name="ims-autogen",
    help="基于 AutoGen 的多 Agent 对话式软件团队 - 进销存管理系统生成器",
    add_completion=False,
)


def _build_resume_context(ws_path: Path) -> str | None:
    """扫描工作区已有产物，构建续传上下文。

    检查工作区中已有的文件，生成一个进度摘要，
    让团队知道哪些工作已完成，哪些还需要继续。
    """
    existing = sorted(ws_path.rglob("*"))
    files = [f for f in existing if f.is_file()]
    if not files:
        return None

    parts = [
        "【项目续传】以下文件已存在，请在此进度基础上继续完成剩余工作：\n"
    ]
    for f in files:
        rel = f.relative_to(ws_path)
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            # 取非空前 3 行作为摘要
            lines = [l.strip() for l in content.split("\n") if l.strip()][:3]
            summary = " | ".join(lines) if lines else "(空文件)"
            parts.append(f"- **{rel}**: {summary[:120]}")
        except Exception:
            parts.append(f"- **{rel}**: (无法读取)")

    parts.append(
        "\n请评估当前进度，继续完成未完成的工作（设计、编码、测试、验收）。"
    )
    return "\n".join(parts)


@app.command("run", help="启动多 Agent 对话，交互式完成需求-设计-开发-测试-验收全流程")
def cmd_run(
    idea: str = typer.Argument(
        ...,
        help='需求描述。例如：生成一个进销存管理系统，支持商品管理和库存管理',
        metavar="IDEA",
    ),
    workspace: str = typer.Option(
        "./ims-output",
        "--workspace", "-w",
        help="输出目录，所有生成的文件保存在这里",
        rich_help_panel="路径选项",
    ),
    resume: bool = typer.Option(
        False,
        "--resume", "-r",
        help="续传模式：基于已有产物继续，不从头开始",
        rich_help_panel="模式选项",
    ),
):
    """
    启动一次完整的多 Agent 对话开发流程。

    流程说明:
    1. Alice（产品经理）会先和你（human_user）沟通，确认需求细节
    2. Bob（架构师）设计系统架构
    3. Eve（全栈工程师）编码实现
    4. Charlie（测试工程师）测试并报告问题
    5. Alice 最终验收

    当 Alice 说 FINAL_ACCEPT 时流程结束。
    """
    # ---------- 设置工作区 ----------
    ws_path = Path(workspace).absolute()
    ws_path.mkdir(parents=True, exist_ok=True)
    os.environ["IMS_WORKSPACE"] = str(ws_path)

    # ---------- 构建初始任务消息 ----------
    task = idea
    if resume:
        ctx = _build_resume_context(ws_path)
        if ctx:
            task = f"{idea}\n\n{ctx}"
            typer.echo("📋 检测到已有产物，进入续传模式")
            typer.echo("    AI 团队会基于已有文件继续完成剩余工作\n")
        else:
            typer.echo("⚠️  工作区为空，忽略 --resume，从头开始\n")

    # ---------- 打印启动信息 ----------
    typer.echo("")
    typer.echo("+----------------------------------------------------------+")
    typer.echo("|  ims-autogen 多 Agent 对话式开发启动                       |")
    typer.echo("+----------------------------------------------------------+")
    typer.echo(f"|  需求: {idea[:60]}")
    typer.echo("|  模式: {}".format("续传" if resume else "全新"))
    typer.echo(f"|  输出: {ws_path}")
    typer.echo("+----------------------------------------------------------+")
    typer.echo("")
    typer.echo("对话即将开始！产品经理 Alice 会先和你沟通需求。")
    typer.echo("请关注终端提示，当 Alice 提问时输入你的回答。")
    typer.echo("")

    # ---------- 构建团队 ----------
    team, clients = build_team()

    # ---------- 运行 ----------
    try:
        asyncio.run(_run_team(team, task, clients))
    except KeyboardInterrupt:
        typer.echo("\n\n用户中断，流程结束。")
        raise typer.Exit(code=1)
    except asyncio.CancelledError:
        typer.echo("\n\n流程被取消，正在清理...")
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"\n运行出错: {e}")
        raise typer.Exit(code=1)

    # ---------- 完成 ----------
    typer.echo("")
    typer.echo("对话流程结束！")
    typer.echo(f"  生成的文件在: {ws_path}")
    typer.echo("")


async def _run_team(team, task: str, clients: list | None = None):
    """运行团队对话，流式输出到控制台，结束后清理资源。"""
    try:
        await Console(team.run_stream(task=task), output_stats=True)
    finally:
        # 关闭所有 model client，释放连接和线程资源
        if clients:
            for client in clients:
                try:
                    await client.close()
                except Exception:
                    pass  # 关闭失败不阻碍流程


@app.command("list-modes", help="显示所有命令说明")
def cmd_list_modes():
    """显示命令速查。"""
    typer.echo("")
    typer.echo("+----------------------------------------------------------+")
    typer.echo("|            ims-autogen 命令速查表                         |")
    typer.echo("+----------------------------------------------------------+")
    typer.echo("")
    typer.echo("启动完整对话流程：")
    typer.echo("")
    typer.echo('  ims-autogen run "生成进销存系统" -w ./my-ims')
    typer.echo("")
    typer.echo("  # 续传模式（断点续传）：")
    typer.echo('  ims-autogen run "继续完善项目" -w ./my-ims --resume')
    typer.echo("")
    typer.echo("所有命令：")
    typer.echo("  run          启动多 Agent 对话（交互式全流程）")
    typer.echo("  run --resume 续传：基于已有产物继续，不从头开始")
    typer.echo("  list-modes   显示本帮助")
    typer.echo("")
    typer.echo("配置说明：")
    typer.echo("  多层覆盖优先级：CLI 参数 > 环境变量 > .env 文件 > 默认值")
    typer.echo("  分角色模型：PM_MODEL_NAME / ARCHITECT_MODEL_NAME / DEVELOPER_MODEL_NAME / QA_MODEL_NAME")
    typer.echo("  选择器模型：SELECTOR_MODEL_NAME（未设置回退到全局 MODEL_NAME）")
    typer.echo("  最大轮数：  MAX_TURNS（默认 100）")
    typer.echo("")


@app.command("init-config", help="初始化 .env 配置文件")
def cmd_init_config():
    """将 .env.example 复制到工作目录。"""
    src = Path(__file__).parent.parent.parent / ".env.example"
    dst = Path.cwd() / ".env"
    if dst.exists():
        typer.echo(f".env 已存在，如需重新配置请先删除 {dst}")
        return
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    typer.echo(".env 已创建，请编辑填入你的 API Key")
    typer.echo(f"  配置文件: {dst}")


if __name__ == "__main__":
    app()
