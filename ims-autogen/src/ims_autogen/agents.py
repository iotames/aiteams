"""Agent 工厂 — 创建所有角色实例。

使用 prompt_loader 从 prompts/ 目录动态加载提示词。
编辑 prompts/ 下的 .md 文件即可调整 Agent 行为，无需修改 Python 代码。
"""

from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

from . import tools
from .config import get_config
from .prompt_loader import load as load_prompt


def _model_client(role_prefix: str = "") -> OpenAIChatCompletionClient:
    """创建模型客户端。

    配置来源：config.py 统一管理，多层覆盖。
    分角色配置: {ROLE}_MODEL_NAME / {ROLE}_API_KEY / {ROLE}_API_BASE
    回退到全局: MODEL_NAME / API_KEY / API_BASE
    """
    cfg = get_config()
    mc = cfg.role_model(role_prefix) if role_prefix else cfg.model
    return OpenAIChatCompletionClient(**mc.to_client_kwargs())


def create_product_manager(scope: str = "MVP") -> AssistantAgent:
    """创建产品经理 Alice。"""
    prompt = load_prompt("product_manager", scope=scope)
    return AssistantAgent(
        name="product_manager",
        description="产品经理 Alice — 负责需求澄清、撰写 PRD、验收产品",
        model_client=_model_client("PM"),
        system_message=prompt,
        tools=[tools.save_file, tools.read_file, tools.list_files],
        reflect_on_tool_use=True,
        model_client_stream=True,
    )


def create_architect(scope: str = "MVP") -> AssistantAgent:
    """创建架构师 Bob。"""
    prompt = load_prompt("architect", scope=scope)
    return AssistantAgent(
        name="architect",
        description="架构师 Bob — 负责系统架构设计和技术决策",
        model_client=_model_client("ARCHITECT"),
        system_message=prompt,
        tools=[tools.save_file, tools.read_file, tools.list_files],
        reflect_on_tool_use=True,
        model_client_stream=True,
    )


def create_developer(scope: str = "MVP") -> AssistantAgent:
    """创建全栈工程师 Eve。"""
    prompt = load_prompt("developer", scope=scope)
    return AssistantAgent(
        name="developer",
        description="全栈工程师 Eve — 负责后端和前端代码实现",
        model_client=_model_client("DEVELOPER"),
        system_message=prompt,
        tools=[tools.save_file, tools.read_file, tools.list_files, tools.run_command],
        reflect_on_tool_use=True,
        model_client_stream=True,
    )


def create_qa(scope: str = "MVP") -> AssistantAgent:
    """创建测试工程师 Charlie。"""
    prompt = load_prompt("qa", scope=scope)
    return AssistantAgent(
        name="qa",
        description="测试工程师 Charlie — 负责编写测试、执行测试、报告 bug",
        model_client=_model_client("QA"),
        system_message=prompt,
        tools=[tools.save_file, tools.read_file, tools.list_files, tools.run_command],
        reflect_on_tool_use=True,
        model_client_stream=True,
    )


def create_user_proxy() -> UserProxyAgent:
    """创建真人用户代理。"""
    return UserProxyAgent(
        name="human_user",
        description="真人用户 — 回答产品经理的提问、提供需求决策",
        input_func=input,
    )
