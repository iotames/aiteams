"""
IMSProductManager — 产品经理角色

负责接收任务规划，撰写进销存 PRD。
"""

from metagpt.logs import logger
from metagpt.roles import Role
from metagpt.schema import Message

from ims_metagpt.actions.plan_tasks import PlanTasks
from ims_metagpt.actions.write_prd import WritePRD


class IMSProductManager(Role):
    """
    产品经理角色：接收任务规划 → 撰写 PRD 文档 → 传递给 Architect。

    继承关系: Role → IMSProductManager
    MetaGPT 源码参考: metagpt/roles/product_manager.py（官方 ProductManager）

    关键机制:
    - _watch([PlanTasks]): 订阅 PlanTasks Action 的输出消息
    - get_memories(): 获取历史消息作为上下文
    - _act(): 重写 _act 以传递多个参数给 Action.run()
    """

    name: str = "Alice"
    profile: str = "ProductManager"
    goal: str = "撰写高质量的进销存产品需求文档"
    scope: str = "mvp"  # mvp / full

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_actions([WritePRD])
        self._watch([PlanTasks])

    async def _act(self) -> Message:
        logger.info(f"{self._setting}: 执行 {self.rc.todo.name} (scope={self.scope})")

        todo = self.rc.todo
        # 获取所有历史记忆作为上下文
        memories = self.get_memories()
        # 第一条消息是用户原始需求
        requirement = memories[0].content if memories else ""
        # 最近一条消息是任务规划（由 PlanTasks Action 产生）
        task_plan = memories[-1].content if memories else ""

        # 执行 WritePRD Action，传递 scope 参数
        prd = await todo.run(task_plan=task_plan, requirement=requirement, scope=self.scope)

        msg = Message(
            content=prd,
            role=self.profile,
            cause_by=type(todo),
        )
        return msg
