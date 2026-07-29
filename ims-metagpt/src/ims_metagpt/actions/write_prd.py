"""
写 PRD Action

由 IMSProductManager 使用，根据任务规划和用户需求输出 PRD。
支持 scope 参数控制 MVP / Full 范围。
提示词从 prompts/prd.md 动态加载。
"""

from metagpt.actions import Action

from ims_metagpt.prompts.prompt_loader import load_prompt


class WritePRD(Action):
    """撰写进销存产品需求文档"""

    name: str = "WritePRD"

    async def run(self, task_plan: str, requirement: str, scope: str = "mvp") -> str:
        """
        根据任务规划和用户需求生成 PRD。

        Args:
            task_plan: 任务规划文本。
            requirement: 用户的原始需求描述。
            scope: 生成范围，"mvp"（仅核心功能）或 "full"（全部功能）。

        Returns:
            完整的 PRD Markdown 文档。
        """
        prompt_template = load_prompt("prd")
        prompt = prompt_template.format(task_plan=task_plan, requirement=requirement, scope=scope)
        rsp = await self._aask(prompt)
        return rsp
