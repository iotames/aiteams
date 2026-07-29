"""
写后端代码 Action

由 IMSEngineer 使用，根据架构设计生成 FastAPI 后端代码。
提示词从 prompts/backend-code.md 动态加载。
"""

from metagpt.actions import Action

from ims_metagpt.prompts.prompt_loader import load_prompt


class WriteBackend(Action):
    """生成 FastAPI 后端代码"""

    name: str = "WriteBackend"

    async def run(self, design: str) -> str:
        """
        根据架构设计生成后端代码。

        Args:
            design: 系统架构设计文档内容。

        Returns:
            生成的后端代码文件列表（含路径和内容）。
        """
        prompt_template = load_prompt("backend-code")
        prompt = prompt_template.format(design=design)
        rsp = await self._aask(prompt)
        return rsp
