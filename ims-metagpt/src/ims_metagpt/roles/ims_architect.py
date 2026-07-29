"""
IMSArchitect — 架构师角色

负责接收 PRD，输出系统架构设计文档。
"""

from metagpt.logs import logger
from metagpt.roles import Role
from metagpt.schema import Message

from ims_metagpt.actions.write_design import WriteDesign
from ims_metagpt.actions.write_prd import WritePRD


class IMSArchitect(Role):
    """
    架构师角色：接收 PRD → 输出系统架构设计 → 传递给 Engineer。

    继承关系: Role → IMSArchitect
    MetaGPT 源码参考: metagpt/roles/architect.py（官方 Architect）

    关键机制:
    - _watch([WritePRD]): 订阅 WritePRD Action 的输出消息
    """

    name: str = "Bob"
    profile: str = "Architect"
    goal: str = "设计可扩展的全栈系统架构"
    scope: str = "mvp"  # mvp / full

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_actions([WriteDesign])
        self._watch([WritePRD])

    async def _act(self) -> Message:
        logger.info(f"{self._setting}: 执行 {self.rc.todo.name} (scope={self.scope})")

        todo = self.rc.todo
        # 获取最近一条消息作为 PRD 内容
        memories = self.get_memories(k=1)
        prd = memories[0].content if memories else ""

        # 执行 WriteDesign Action，传递 scope
        design = await todo.run(prd=prd, scope=self.scope)

        msg = Message(
            content=design,
            role=self.profile,
            cause_by=type(todo),
        )
        return msg
