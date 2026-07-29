"""Team 组装 — 使用 SelectorGroupChat 实现多 Agent 对话。"""

from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import SelectorGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

from .agents import (
    create_architect,
    create_developer,
    create_product_manager,
    create_qa,
    create_user_proxy,
)
from .config import get_config


def _selector_model_client() -> OpenAIChatCompletionClient:
    """创建选择器模型（决定下一个发言人），配置来自 config.py 统一管理。"""
    cfg = get_config()
    return OpenAIChatCompletionClient(**cfg.selector_model.to_client_kwargs())


SELECTOR_PROMPT = """你是一个多 Agent 软件开发团队的协调员。
你的工作是阅读对话历史，然后选择下一个应该发言的 Agent。

## 团队成员
- **product_manager** (Alice) — 产品经理：和用户沟通需求、写 PRD、验收产品
- **architect** (Bob) — 架构师：设计系统架构、回答技术问题
- **developer** (Eve) — 全栈工程师：编写后端和前端代码
- **qa** (Charlie) — 测试工程师：编写和执行测试、报告 bug
- **human_user** — 真人用户：回答产品经理的提问

## 发言选择原则
1. **最初** → product_manager 先和 human_user 沟通需求
2. **需求明确后** → product_manager 发言完毕 → architect 开始设计
3. **设计完成** → developer 开始编码
4. **代码产出后** → qa 开始测试
5. **QA 发现问题** → developer 修复
6. **修复完成** → qa 回归测试
7. **测试通过** → product_manager 做最终验收
8. **过程中如有提问** — 谁被问到的概率最大就选谁

请只返回 Agent 的名字（product_manager / architect / developer / qa / human_user），不要返回其他内容。
"""


def build_team(scope: str = "MVP") -> tuple[SelectorGroupChat, list]:
    """
    构建多 Agent 对话团队。

    Args:
        scope: 当前范围 "MVP" 或 "Full"

    Returns:
        (team, clients) — team 是配置好的 SelectorGroupChat，
        clients 是需要清理的 model_client 列表
    """
    cfg = get_config()

    # 创建所有 Agent
    pm = create_product_manager(scope)
    architect = create_architect(scope)
    dev = create_developer(scope)
    qa = create_qa(scope)
    user = create_user_proxy()

    participants = [pm, architect, dev, qa, user]

    # 收集所有需要清理的 model_client
    _clients: list = []
    for agent in participants:
        mc = getattr(agent, "model_client", None)
        if mc is not None:
            _clients.append(mc)

    # 终止条件：产品经理说 FINAL_ACCEPT
    termination = TextMentionTermination("FINAL_ACCEPT")

    # 选择器
    selector_client = _selector_model_client()
    _clients.append(selector_client)

    # SelectorGroupChat — 模型选择下一个发言人
    team = SelectorGroupChat(
        participants=participants,
        model_client=selector_client,
        termination_condition=termination,
        selector_prompt=SELECTOR_PROMPT,
        max_turns=cfg.max_turns,
    )
    return team, _clients
