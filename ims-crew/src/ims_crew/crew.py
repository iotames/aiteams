"""
Crew 装配 — 将 prompts/ 中的 Agent/Task 定义加载并组装成 Crew。

设计原则：
- 所有提示词内容从 prompts/*.md 加载，Python 代码中不含提示词文本
- 支持顺序执行（sequential）和团队 Profile 配置
- 通过 context 链传递前序任务产出
- 模型配置通过环境变量注入，不硬编码在代码中
"""

import os
from pathlib import Path
from typing import Any

import yaml

from crewai import Agent, Crew, Process, Task

from .prompt_loader import load_agent, load_task


# Agent 名称 → 环境变量中对应的模型配置键
_ROLE_LLM_ENV_MAP = {
    "product_manager": "PM_LLM",
    "architect": "ARCHITECT_LLM",
    "backend_developer": "BACKEND_LLM",
    "frontend_developer": "FRONTEND_LLM",
    "qa_engineer": "QA_LLM",
    "devops_engineer": "DEVOPS_LLM",
}


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


def _make_agent(name: str, allow_delegation: bool = False, llm: str | None = None) -> Agent:
    """从 prompts/agents/{name}.md 创建 Agent 实例。

    Agent 使用的模型按以下优先级决定：
    1. llm 参数（Python 调用方指定）
    2. 角色专用环境变量（如 ARCHITECT_LLM）
    3. 通用环境变量 MODEL_NAME
    4. LiteLLM 默认模型

    Args:
        name: Agent 标识名（也是 prompts/agents/ 目录下的文件名）
        allow_delegation: 是否允许委托
        llm: 可选，强制指定 LLM 模型（优先级最高）

    Returns:
        Agent 实例
    """
    effective_llm = llm or _resolve_llm(name)
    prompt = load_agent(name)
    return Agent(
        role=prompt.get("role", name),
        goal=prompt.get("goal", ""),
        backstory=prompt.get("backstory", ""),
        allow_delegation=allow_delegation,
        verbose=True,
        llm=effective_llm,
    )


def _make_task(
    name: str,
    agent: Agent,
    context_tasks: list[Task] | None = None,
    output_file: str | None = None,
    human_input: bool = False,
) -> Task:
    """从 prompts/tasks/{name}.md 创建 Task 实例。

    Args:
        name: Task 标识名
        agent: 负责执行的 Agent
        context_tasks: 前序任务列表（用于 context 传递）
        output_file: 输出文件路径
        human_input: 是否需要人工确认

    Returns:
        Task 实例
    """
    prompt = load_task(name)
    return Task(
        description=prompt.get("description", ""),
        expected_output=prompt.get("expected_output", ""),
        agent=agent,
        context=context_tasks,
        output_file=output_file,
        human_input=human_input,
    )


class IMSCrew:
    """进销存系统开发团队 — 多 Agent 协作生成完整系统。"""

    def agents(self) -> list[Agent]:
        """创建所有 Agent。可为不同角色指定不同 LLM 模型。"""
        return [
            _make_agent("product_manager"),
            _make_agent("architect"),
            _make_agent("backend_developer"),
            _make_agent("frontend_developer"),
            _make_agent("qa_engineer"),
            _make_agent("devops_engineer"),
        ]

    def tasks(self, agents: list[Agent]) -> list[Task]:
        """创建所有 Task，按顺序依赖链排列。

        依赖链:
            requirement_analysis → system_design
                ├→ backend_development
                ├→ frontend_development
                └→ testing (依赖 backend + frontend)
                    └→ deployment (依赖 testing)
        """
        pm, arch, backend, frontend, qa, devops = agents

        # 阶段 1: 需求
        t_requirement = _make_task(
            "requirement_analysis",
            agent=pm,
            output_file="output/PRD.md",
        )

        # 阶段 2: 设计
        t_design = _make_task(
            "system_design",
            agent=arch,
            context_tasks=[t_requirement],
            output_file="output/ARCHITECTURE.md",
        )

        # 阶段 3: 开发（并行的两端）
        t_backend = _make_task(
            "backend_development",
            agent=backend,
            context_tasks=[t_requirement, t_design],
        )

        t_frontend = _make_task(
            "frontend_development",
            agent=frontend,
            context_tasks=[t_requirement, t_design],
        )

        # 阶段 4: 测试
        t_testing = _make_task(
            "testing",
            agent=qa,
            context_tasks=[t_backend, t_frontend],
            output_file="output/QA_REPORT.md",
        )

        # 阶段 5: 部署
        t_deployment = _make_task(
            "deployment",
            agent=devops,
            context_tasks=[t_backend, t_frontend, t_testing],
        )

        return [
            t_requirement,
            t_design,
            t_backend,
            t_frontend,
            t_testing,
            t_deployment,
        ]

    def crew(self) -> Crew:
        """组装 Crew，配置顺序执行流程。"""
        agents = self.agents()
        tasks = self.tasks(agents)
        return Crew(
            agents=agents,
            tasks=tasks,
            process=Process.sequential,
            verbose=True,
            memory=False,
            max_execution_time=3600,
            respect_context_window=True,
        )

    @staticmethod
    def get_profile_names() -> list[str]:
        """返回可用的团队 Profile 列表。"""
        return ["full", "backend-only", "prototype"]

    def crew_with_profile(self, profile: str = "full") -> Crew:
        """根据 Profile 配置选择性组装 Crew。

        Profile 定义从 config/profiles.yaml 加载，确保单一数据源。

        Args:
            profile: 团队 Profile 名称

        Returns:
            按 Profile 裁剪后的 Crew
        """
        base_dir = Path(__file__).resolve().parent
        profiles_path = base_dir / "config" / "profiles.yaml"

        if not profiles_path.exists():
            raise FileNotFoundError(f"Profile 配置文件不存在: {profiles_path}")

        with open(profiles_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        all_profiles: dict = raw.get("profiles", {})
        if profile not in all_profiles:
            raise ValueError(
                f"未知的 Profile: {profile}，可选: {list(all_profiles.keys())}"
            )

        config = all_profiles[profile]
        agent_map = {name: _make_agent(name) for name in config["agents"]}

        # 任务 → Agent 映射
        task_agent_map = {
            "requirement_analysis": "product_manager",
            "system_design": "architect",
            "backend_development": "backend_developer",
            "frontend_development": "frontend_developer",
            "testing": "qa_engineer",
            "deployment": "devops_engineer",
        }

        # 构建任务依赖链
        task_map: dict[str, Task] = {}
        for task_name in config["tasks"]:
            agent_name = task_agent_map[task_name]
            agent = agent_map[agent_name]
            context = []
            if task_name == "system_design":
                context = [task_map["requirement_analysis"]]
            elif task_name == "backend_development":
                context = [task_map["requirement_analysis"], task_map["system_design"]]
            elif task_name == "frontend_development":
                context = [task_map["requirement_analysis"], task_map["system_design"]]
            elif task_name == "testing":
                ctx_names = [n for n in config["tasks"] if n in ("backend_development", "frontend_development")]
                context = [task_map[n] for n in ctx_names]
            elif task_name == "deployment":
                ctx_names = [n for n in config["tasks"] if n in ("backend_development", "frontend_development", "testing")]
                context = [task_map[n] for n in ctx_names]

            task_map[task_name] = _make_task(task_name, agent, context_tasks=context or None)

        return Crew(
            agents=list(agent_map.values()),
            tasks=list(task_map.values()),
            process=Process.sequential,
            verbose=True,
            memory=False,
            max_execution_time=3600,
            respect_context_window=True,
        )
