"""
写前端代码 Action

由 IMSEngineer 使用，根据架构设计生成前端管理页面。
角色定义从 prompts/agents/frontend-developer.md 动态加载。
任务提示词从 prompts/frontend-code.md 动态加载。
"""

from metagpt.actions import Action

from ims_metagpt.prompts.prompt_loader import load_prompt


class WriteFrontend(Action):
    """生成前端管理页面代码"""

    name: str = "WriteFrontend"

    async def run(self, design: str) -> str:
        """
        根据架构设计生成前端代码。

        Args:
            design: 系统架构设计文档内容。

        Returns:
            生成的前端代码文件列表（含路径和内容）。
        """
        role = load_prompt("agents/frontend-developer")
        task = load_prompt("frontend-code")
        prompt = f"{role}\n\n{task}".format(design=design)
        rsp = await self._aask(prompt)
        return rsp
