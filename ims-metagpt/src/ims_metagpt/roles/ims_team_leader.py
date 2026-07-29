"""
IMSTeamLeader — 团队领导角色

负责接收用户需求，进行任务规划分解。
使用 BY_ORDER 模式，按顺序执行 PlanTasks Action。
"""

from metagpt.actions import UserRequirement
from metagpt.logs import logger
from metagpt.roles import Role, RoleReactMode
from metagpt.schema import Message

from ims_metagpt.actions.plan_tasks import PlanTasks


class IMSTeamLeader(Role):
    """
    项目经理角色：接收用户需求 → 分解为结构化任务列表 → 传递给 ProductManager。

    继承关系: Role → IMSTeamLeader
    MetaGPT 源码参考: metagpt/roles/role.py（基类）
                      metagpt/roles/di/team_leader.py（官方 TeamLeader，更复杂的 PLAN_AND_ACT 模式）

    关键机制:
    - _watch([UserRequirement]): 订阅 UserRequirement 类型的消息（即用户输入），当收到此类消息时自动唤醒
    - BY_ORDER: 按 set_actions 的顺序依次执行 Action
    - _act(): 执行当前 todo Action，返回结果 Message
    """

    name: str = "Mike"
    profile: str = "TeamLeader"
    goal: str = "分析用户需求，制定合理的任务规划"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 设置 Action 列表
        self.set_actions([PlanTasks])
        # 使用 BY_ORDER 模式：按 Action 列表顺序依次执行
        self._set_react_mode(react_mode=RoleReactMode.BY_ORDER.value)
        # 订阅用户需求消息
        self._watch([UserRequirement])

    async def _act(self) -> Message:
        """执行当前 Action，返回结果消息"""
        logger.info(f"{self._setting}: 执行 {self.rc.todo.name}")

        todo = self.rc.todo
        # 获取最近一条消息内容作为用户需求
        msg = self.get_memories(k=1)[0]
        requirement = msg.content

        # 执行 Action
        task_plan = await todo.run(requirement=requirement)

        # 包装为 Message 返回，cause_by 标记为当前 Action 类型
        # 下游 Role 通过 _watch([PlanTasks]) 订阅此消息
        msg = Message(
            content=task_plan,
            role=self.profile,
            cause_by=type(todo),
        )
        return msg
