"""
增量变更规划 Action

用于 iterate（迭代）和 refactor（重构）模式。
基于已有代码，生成 git diff 格式的增量变更计划。
角色定义从 prompts/agents/fullstack-engineer.md 动态加载。
任务提示词从 prompts/change-plan.md 动态加载。
"""

from metagpt.actions import Action

from ims_metagpt.prompts.prompt_loader import load_prompt


class WriteChangePlan(Action):
    """基于已有代码和新需求，生成增量变更规划"""

    name: str = "WriteChangePlan"

    async def run(self, idea: str, existing_code: str = "", scope_type: str = "迭代") -> str:
        """
        分析现有代码和新需求，输出增量变更计划。

        Args:
            idea: 新需求或重构目标描述。
            existing_code: 已有的代码内容。
            scope_type: 变更类型，"迭代" 或 "重构"。

        Returns:
            增量变更计划（含变更分析和 git diff 格式的变更内容）。
        """
        role = load_prompt("agents/fullstack-engineer")
        task = load_prompt("change-plan")
        prompt = f"{role}\n\n{task}".format(
            scope_type=scope_type,
            idea=idea,
            existing_code=existing_code if existing_code else "(新项目，无现有代码)",
        )
        rsp = await self._aask(prompt)
        return rsp
