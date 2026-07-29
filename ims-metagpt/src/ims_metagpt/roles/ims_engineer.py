"""
IMSEngineer — 全栈工程师角色

支持多种工作模式：
  - MVP 模式：只生成核心功能代码（商品管理+库存）
  - Full 模式：生成全部功能代码
  - 迭代模式：在已有代码上增量增加功能
  - 重构模式：对已有代码进行重构优化
"""

from typing import Optional

from metagpt.actions import Action
from metagpt.logs import logger
from metagpt.roles import Role, RoleReactMode
from metagpt.schema import Message

from ims_metagpt.actions.write_backend import WriteBackend
from ims_metagpt.actions.write_change_plan import WriteChangePlan
from ims_metagpt.actions.write_design import WriteDesign
from ims_metagpt.actions.write_frontend import WriteFrontend
from ims_metagpt.actions.write_tests import WriteTests


class IMSEngineer(Role):
    """
    全栈工程师角色。

    继承关系: Role → IMSEngineer

    工作模式:
    - code_scope="mvp":   只生成核心功能（商品管理+库存），适合首次上线
    - code_scope="full":  生成全部功能，适合完整版
    - code_scope="iterate": 增量迭代模式，在已有代码上加新功能
    - code_scope="refactor": 重构模式，优化已有代码质量

    code_mode 控制生成的端:
    - "full":         后端 + 前端 + 测试
    - "backend-only": 仅后端
    - "frontend-only": 仅前端
    """

    name: str = "Eve"
    profile: str = "Engineer"
    goal: str = "生成高质量的全栈代码"

    # 扩展参数：控制代码生成范围
    code_scope: str = "mvp"          # mvp / full / iterate / refactor
    code_mode: str = "full"          # full / backend-only / frontend-only
    existing_code: str = ""          # 迭代/重构模式时传入的已有代码

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # 根据工作模式选择 Action 列表
        if self.code_scope in ("iterate", "refactor"):
            # 迭代/重构模式：使用增量变更规划
            self.set_actions([WriteChangePlan])
        else:
            # MVP/Full 模式：按顺序生成后端→前端→测试
            actions = []
            if self.code_mode in ("full", "backend-only"):
                actions.append(WriteBackend)
            if self.code_mode in ("full", "frontend-only"):
                actions.append(WriteFrontend)
            if self.code_mode == "full":
                actions.append(WriteTests)
            self.set_actions(actions)

        # 使用 BY_ORDER 模式：按 Action 列表顺序执行
        self._set_react_mode(react_mode=RoleReactMode.BY_ORDER.value)

        # 订阅架构设计消息（首次代码生成）
        self._watch([WriteDesign])

    async def _act(self) -> Message:
        logger.info(f"{self._setting}: 执行 {self.rc.todo.name} (scope={self.code_scope}, mode={self.code_mode})")

        todo = self.rc.todo
        memories = self.get_memories()

        # ============================================================
        # 迭代/重构模式：使用 WriteChangePlan
        # ============================================================
        if isinstance(todo, WriteChangePlan):
            # 从记忆中获取最新消息作为需求
            idea = memories[-1].content if memories else ""
            result = await todo.run(idea=idea, existing_code=self.existing_code)

        # ============================================================
        # MVP/Full 模式：WriteBackend / WriteFrontend / WriteTests
        # ============================================================
        elif isinstance(todo, WriteBackend):
            design = memories[-1].content if memories else ""
            # 在提示词中注入 scope 控制
            scope_hint = ""
            if self.code_scope == "mvp":
                scope_hint = (
                    "\n\n【范围限制】当前为 MVP 模式，请只生成以下核心功能：\n"
                    "1. 商品管理（分类、商品 CRUD、搜索）\n"
                    "2. 库存管理（入库、出库、库存查询、低库存预警）\n"
                    "不要生成采购管理、销售管理、报表等功能。"
                )
            result = await todo.run(design=design + scope_hint)

        elif isinstance(todo, WriteFrontend):
            design = memories[-1].content if memories else ""
            scope_hint = ""
            if self.code_scope == "mvp":
                scope_hint = (
                    "\n\n【范围限制】当前为 MVP 模式，请只生成以下核心页面：\n"
                    "1. 登录页面\n"
                    "2. 仪表盘（库存概况）\n"
                    "3. 商品管理页面\n"
                    "4. 入库/出库操作页面\n"
                    "不要生成采购管理、销售管理、报表等页面。"
                )
            result = await todo.run(design=design + scope_hint)

        elif isinstance(todo, WriteTests):
            code = ""
            for mem in reversed(memories):
                if "backend" in mem.content[:200].lower():
                    code = mem.content
                    break
            result = await todo.run(code=code or memories[-1].content if memories else "")

        else:
            result = await todo.run()

        # 包装为 Message 返回
        msg = Message(
            content=result,
            role=self.profile,
            cause_by=type(todo),
        )
        return msg
