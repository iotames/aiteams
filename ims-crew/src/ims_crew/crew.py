"""
Crew 装配 — 将 prompts/ 中的 Agent/Task 定义加载并组装成 Crew。

设计原则：
- 所有提示词内容从 prompts/*.md 加载，Python 代码中不含提示词文本
- 通过 context 链传递前序任务产出
- 支持断点续跑(--from)和角色裁剪(--only)
- 包含 QA 反馈闭环：测试 → BUG 修复 → 重新测试
- 模型配置通过环境变量注入，不硬编码在代码中
"""

import logging
import os
from pathlib import Path
from typing import Any

from crewai import Agent, Crew, Process, Task

from .prompt_loader import load_agent, load_task
from .tools import BACKEND_TOOLS, QA_TOOLS

logger = logging.getLogger(__name__)


# =============================================================
# 统一任务定义（单一数据源）
# =============================================================
# 每个任务定义包含：名称(name)、执行角色(role)、执行顺序(顺序决定)、
# 输出文件(output_file)、前序文件依赖(file_inputs)、context 依赖(deps)

TASK_DEFS: list[dict[str, Any]] = [
    {
        "name": "requirement_analysis",
        "role": "product_manager",
        "output_file": "output/PRD.md",
        "file_inputs": [],
        "deps": [],
    },
    {
        "name": "system_design",
        "role": "architect",
        "output_file": "output/ARCHITECTURE.md",
        "file_inputs": [("output/PRD.md", "PRD 文档")],
        "deps": ["requirement_analysis"],
    },
    {
        "name": "backend_development",
        "role": "backend_developer",
        "output_file": None,
        "file_inputs": [
            ("output/PRD.md", "PRD 文档"),
            ("output/ARCHITECTURE.md", "架构设计文档"),
            ("output/openapi.yaml", "OpenAPI 规范"),
            ("output/models.py", "数据库模型"),
        ],
        "deps": ["requirement_analysis", "system_design"],
    },
    {
        "name": "frontend_development",
        "role": "frontend_developer",
        "output_file": None,
        "file_inputs": [
            ("output/PRD.md", "PRD 文档"),
            ("output/ARCHITECTURE.md", "架构设计文档"),
            ("output/openapi.yaml", "OpenAPI 规范"),
        ],
        "deps": ["requirement_analysis", "system_design"],
    },
    {
        "name": "testing",
        "role": "qa_engineer",
        "output_file": "output/QA_REPORT.md",
        "file_inputs": [],  # 依赖 project/ 下代码，由代码扫描提供
        "deps": ["backend_development", "frontend_development"],
    },
    {
        "name": "bug_fixing",
        "role": "backend_developer",
        "output_file": None,
        "file_inputs": [("output/QA_REPORT.md", "QA 测试报告")],
        "deps": ["testing"],
    },
    {
        "name": "bug_fixing_frontend",
        "role": "frontend_developer",
        "output_file": None,
        "file_inputs": [("output/QA_REPORT.md", "QA 测试报告")],
        "deps": ["testing"],
    },
    {
        "name": "qa_retest",
        "role": "qa_engineer",
        "output_file": "output/QA_REPORT.md",  # 覆盖更新
        "file_inputs": [],
        "deps": ["bug_fixing", "bug_fixing_frontend"],
    },
    {
        "name": "deployment",
        "role": "devops_engineer",
        "output_file": None,
        "file_inputs": [],
        "deps": ["backend_development", "frontend_development"],
    },
]

# 从单一数据源派生的查找表
TASK_ORDER: list[str] = [t["name"] for t in TASK_DEFS]
TASK_ROLE_MAP: dict[str, str] = {t["name"]: t["role"] for t in TASK_DEFS}
ROLE_ORDER: list[str] = list(dict.fromkeys(t["role"] for t in TASK_DEFS))
TASK_OUTPUT_FILES: dict[str, str | None] = {t["name"]: t["output_file"] for t in TASK_DEFS}
TASK_FILE_INPUTS: dict[str, list[tuple[str, str]]] = {t["name"]: t["file_inputs"] for t in TASK_DEFS}
TASK_DEPS: dict[str, list[str]] = {t["name"]: t["deps"] for t in TASK_DEFS}

# CLI 短名 → 完整角色名
ROLE_ALIASES = {
    "pm": "product_manager",
    "arch": "architect",
    "backend": "backend_developer",
    "frontend": "frontend_developer",
    "qa": "qa_engineer",
    "devops": "devops_engineer",
}

# 角色显示名（用于打印）
ROLE_DISPLAY = {
    "product_manager": "产品经理",
    "architect": "系统架构师",
    "backend_developer": "后端工程师",
    "frontend_developer": "前端工程师",
    "qa_engineer": "QA 工程师",
    "devops_engineer": "DevOps",
}

# Agent 名称 → 环境变量中对应的模型配置键
_ROLE_LLM_ENV_MAP = {
    "product_manager": "PM_LLM",
    "architect": "ARCHITECT_LLM",
    "backend_developer": "BACKEND_LLM",
    "frontend_developer": "FRONTEND_LLM",
    "qa_engineer": "QA_LLM",
    "devops_engineer": "DEVOPS_LLM",
}

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "output"


def _resolve_llm(agent_name: str) -> str | None:
    """按优先级解析 Agent 使用的 LLM 模型。

    优先级（从高到低）：
    1. 角色专用环境变量，如 ARCHITECT_LLM=deepseek/deepseek-v4-flash
    2. 通用环境变量 MODEL_NAME=gpt-4o
    3. 返回 None，由 LiteLLM 使用默认模型
    """
    role_env = _ROLE_LLM_ENV_MAP.get(agent_name)
    if role_env:
        role_model = os.environ.get(role_env)
        if role_model:
            return role_model
    return os.environ.get("MODEL_NAME") or None


def _make_agent(
    name: str,
    allow_delegation: bool = False,
    llm: str | None = None,
    tools: list | None = None,
) -> Agent:
    """从 prompts/agents/{name}.md 创建 Agent 实例。

    Args:
        name: Agent 名称
        allow_delegation: 是否允许委托
        llm: 指定 LLM 模型
        tools: 绑定的工具列表
    """
    effective_llm = llm or _resolve_llm(name)
    prompt = load_agent(name)

    role = prompt.get("role", name)
    goal = prompt.get("goal", "")
    backstory = prompt.get("backstory", "")

    # 缺失字段告警
    if not goal:
        logger.warning("Agent %s 的 goal 为空，请检查 prompts/agents/%s.md", name, name)
    if not backstory:
        logger.warning("Agent %s 的 backstory 为空，请检查 prompts/agents/%s.md", name, name)

    return Agent(
        role=role,
        goal=goal,
        backstory=backstory,
        allow_delegation=allow_delegation,
        verbose=True,
        llm=effective_llm,
        tools=tools or [],
    )


def _load_file_content(rel_path: str, label: str) -> str | None:
    """读取 output 目录下的文件，如果存在则返回格式化内容。"""
    full_path = OUTPUT_DIR / rel_path
    if full_path.exists():
        content = full_path.read_text(encoding="utf-8")
        return f"=== {label} ({rel_path}) ===\n{content}"
    logger.debug("文件不存在，跳过注入: %s", full_path)
    return None


def _load_task_file_inputs(task_name: str) -> str:
    """加载任务依赖的产出文件，返回拼接文本。"""
    parts = []
    for rel_path, label in TASK_FILE_INPUTS.get(task_name, []):
        content = _load_file_content(rel_path, label)
        if content:
            parts.append(content)
    return "\n\n".join(parts)


def _make_task(
    name: str,
    agent: Agent,
    context_tasks: list[Task] | None = None,
    output_file: str | None = None,
    human_input: bool = False,
    description_append: str | None = None,
    inject_file_inputs: bool = True,
) -> Task:
    """从 prompts/tasks/{name}.md 创建 Task 实例。

    Args:
        name: Task 标识名
        agent: 负责执行的 Agent
        context_tasks: 前序任务列表（用于 context 传递）
        output_file: 输出文件路径
        human_input: 是否需要人工确认
        description_append: 追加到 description 后的文本
        inject_file_inputs: 是否自动注入文件依赖内容（默认 True）

    Returns:
        Task 实例
    """
    prompt = load_task(name)
    description = prompt.get("description", "")

    # 注入文件依赖内容（取代 {variable} 模板变量）
    if inject_file_inputs:
        file_content = _load_task_file_inputs(name)
        if file_content:
            description += f"\n\n## 前序产出\n\n{file_content}"

    if description_append:
        description += f"\n\n{description_append}"

    return Task(
        description=description,
        expected_output=prompt.get("expected_output", ""),
        agent=agent,
        context=context_tasks,
        output_file=output_file,
        human_input=human_input,
    )


def _load_skipped_outputs(skipped_task_names: list[str]) -> str:
    """加载被跳过任务的输出文件，返回拼接文本。"""
    parts = []
    for task_name in skipped_task_names:
        for rel_path, label in TASK_FILE_INPUTS.get(task_name, []):
            content = _load_file_content(rel_path, label)
            if content:
                parts.append(content)
    return "\n\n".join(parts)


class IMSCrew:
    """进销存系统开发团队 — 多 Agent 协作生成完整系统。"""

    def crew(self) -> Crew:
        """兼容旧接口，等价于全流程。"""
        return self.crew_with_options()

    @staticmethod
    def _parse_qa_report(output_dir: Path) -> set[str]:
        """解析 QA_REPORT.md 判断 BUG 归属，返回包含的角色名集合。

        根据标记 `[BUG]` 的内容匹配 "后端"/"backend" 或 "前端"/"frontend" 决定修复范围。
        文件不存在或无可解析 BUG 时返回空集合。
        """
        qa_file = output_dir / "QA_REPORT.md"
        if not qa_file.exists():
            return set()
        text = qa_file.read_text(encoding="utf-8")
        roles: set[str] = set()
        for line in text.splitlines():
            if "[BUG]" not in line:
                continue
            lower = line.lower()
            if "后端" in lower or "backend" in lower:
                roles.add("backend_developer")
            if "前端" in lower or "frontend" in lower:
                roles.add("frontend_developer")
        # 默认：如果无法识别归属，两端都修复
        if not roles:
            logger.info("QA 报告有 BUG 但无法识别归属，默认两端修复")
            roles = {"backend_developer", "frontend_developer"}
        return roles

    def crew_with_options(
        self,
        resume_from: str | None = None,
        only_roles: list[str] | None = None,
        qa_rounds: int = 5,
    ) -> Crew:
        """按参数装配 Crew，支持 N 轮 QA 循环。

        Args:
            resume_from: 从哪个角色开始执行。
            only_roles:  只包含哪些角色。
            qa_rounds:   QA 反馈闭环轮数（默认 5，设为 0 跳过闭环）。

        Returns:
            装配好的 Crew 实例
        """
        # ── 1. 确定要包含哪些角色 ──
        if only_roles:
            roles = sorted(only_roles, key=lambda r: ROLE_ORDER.index(r))
        else:
            roles = list(ROLE_ORDER)

        if resume_from:
            idx = ROLE_ORDER.index(resume_from)
            roles = [r for r in roles if ROLE_ORDER.index(r) >= idx]
            if not roles:
                raise ValueError(f"resume_from={resume_from} 不在 only_roles 中")

        # ── 2. 确定基础任务（不含 QA 循环和部署，这些后面动态生成） ──
        BASE_TASK_NAMES = [
            "requirement_analysis",
            "system_design",
            "backend_development",
            "frontend_development",
            "testing",
        ]
        qa_in_roles = "qa_engineer" in roles

        # 构建 Agent 映射（不同角色绑定对应工具）
        def _agent_tools(role_name: str) -> list:
            if role_name == "backend_developer":
                return BACKEND_TOOLS
            if role_name == "qa_engineer":
                return QA_TOOLS
            return []

        agent_map = {name: _make_agent(name, tools=_agent_tools(name)) for name in roles}

        # ── 3. 构建基础任务 ──
        task_map: dict[str, Task] = {}
        ordered_tasks: list[Task] = []

        active_task_names: list[str] = []
        for task_name in BASE_TASK_NAMES:
            agent_name = TASK_ROLE_MAP.get(task_name)
            if agent_name not in agent_map:
                continue
            agent = agent_map[agent_name]

            # 断点续跑：注入前序跳过任务的文件内容
            desc_append = None
            if resume_from:
                preceding_skipped = self._get_preceding_skipped(
                    task_name, active_task_names, BASE_TASK_NAMES
                )
                if preceding_skipped:
                    desc_append = _load_skipped_outputs(preceding_skipped)

            active_task_names.append(task_name)
            context = _build_context(task_name, task_map, active_task_names)
            output_f = TASK_OUTPUT_FILES.get(task_name)

            # 需求分析任务启用人工确认
            human = task_name == "requirement_analysis"

            t = _make_task(task_name, agent, context_tasks=context or None,
                           output_file=output_f, description_append=desc_append,
                           human_input=human)
            task_map[task_name] = t
            ordered_tasks.append(t)

        # ── 4. QA 反馈闭环（N 轮） ──
        if qa_rounds > 0 and qa_in_roles and "testing" in task_map:
            prev = task_map["testing"]
            for round_i in range(1, qa_rounds + 1):
                round_marker = f"\n\n【QA 轮次 {round_i}/{qa_rounds}】"

                # 解析 QA 报告，确定需要修复的角色
                fix_roles = self._parse_qa_report(OUTPUT_DIR)
                need_backend = "backend_developer" in fix_roles and "backend_developer" in agent_map
                need_frontend = "frontend_developer" in fix_roles and "frontend_developer" in agent_map

                # 如果 QA 报告为空（无 BUG），跳过本轮所有修复
                qa_empty = OUTPUT_DIR / "QA_REPORT.md"
                has_bugs = qa_empty.exists() and "[BUG]" in qa_empty.read_text(encoding="utf-8")

                fix_tasks: list[Task] = []

                if has_bugs and need_backend:
                    fix_b = _make_task("bug_fixing",
                                       agent_map["backend_developer"],
                                       context_tasks=[prev],
                                       description_append=round_marker)
                    task_map[f"bug_fixing_r{round_i}"] = fix_b
                    fix_tasks.append(fix_b)

                if has_bugs and need_frontend:
                    fix_f = _make_task("bug_fixing_frontend",
                                       agent_map["frontend_developer"],
                                       context_tasks=[prev],
                                       description_append=round_marker)
                    task_map[f"bug_fixing_frontend_r{round_i}"] = fix_f
                    fix_tasks.append(fix_f)

                # 无 BUG 或无需修复时仅创建 retest（用以确认无问题）
                if not fix_tasks:
                    logger.info("QA 第 %d 轮无 BUG 需修复，跳过修复步骤", round_i)

                # 最后一轮才写 QA_REPORT.md 覆盖
                out_file = "output/QA_REPORT.md" if round_i == qa_rounds else None
                retest = _make_task("qa_retest", agent_map["qa_engineer"],
                                    context_tasks=fix_tasks or [prev],
                                    output_file=out_file,
                                    description_append=(
                                        f"\n当前为第 {round_i}/{qa_rounds} 轮，共 {qa_rounds} 轮修复-测试循环。"
                                        + (" 本轮无需修复，直接验证。" if not fix_tasks else "")
                                    ))

                task_map[f"qa_retest_r{round_i}"] = retest
                ordered_tasks.extend([*fix_tasks, retest])
                prev = retest

            last_retest = task_map.get(f"qa_retest_r{qa_rounds}")
        elif "testing" in task_map:
            last_retest = task_map["testing"]
        else:
            last_retest = None

        # ── 5. 部署（依赖 backend + frontend 任务，不依赖 QA 闭环） ──
        if "devops_engineer" in agent_map:
            deploy_ctx = []
            for dep in ["backend_development", "frontend_development"]:
                if dep in task_map:
                    deploy_ctx.append(task_map[dep])
            t_deploy = _make_task("deployment", agent_map["devops_engineer"],
                                  context_tasks=deploy_ctx or None)
            task_map["deployment"] = t_deploy
            ordered_tasks.append(t_deploy)

        # max_execution_time 可配置
        max_time = int(os.environ.get("CREW_MAX_EXECUTION_TIME", "3600"))

        return Crew(
            agents=list(agent_map.values()),
            tasks=ordered_tasks,
            process=Process.sequential,
            verbose=True,
            memory=False,
            max_execution_time=max_time,
            respect_context_window=True,
        )

    @staticmethod
    def _get_preceding_skipped(
        task_name: str,
        active_task_names: list[str],
        all_base_tasks: list[str],
    ) -> list[str]:
        """断点续跑时，找出在当前任务之前被跳过的任务。"""
        skipped = []
        in_base = set(all_base_tasks)
        active_set = set(active_task_names)
        for t in TASK_ORDER:
            if t == task_name:
                break
            if t in in_base and t not in active_set and t in TASK_FILE_INPUTS:
                skipped.append(t)
        return skipped


def _build_context(
    task_name: str,
    task_map: dict[str, Task],
    active_task_names: list[str],
) -> list[Task]:
    """构建任务的 context 依赖。

    根据当前活跃的任务列表，只引用存在的任务。
    依赖关系由 TASK_DEPS（单一数据源）定义。
    """
    context = []
    active_set = set(active_task_names)

    for dep_name in TASK_DEPS.get(task_name, []):
        if dep_name in active_set and dep_name in task_map:
            context.append(task_map[dep_name])
    return context
