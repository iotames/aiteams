"""
写设计文档 Action

由 IMSArchitect 使用，根据 PRD 输出系统架构设计。
支持 scope 参数控制 MVP / Full 范围。
提示词从 prompts/design.md 动态加载。
"""

from metagpt.actions import Action

from ims_metagpt.prompts.prompt_loader import load_prompt


class WriteDesign(Action):
    """撰写系统架构设计文档"""

    name: str = "WriteDesign"

    async def run(self, prd: str, scope: str = "mvp") -> str:
        """
        根据 PRD 生成系统架构设计。

        Args:
            prd: 产品需求文档内容。
            scope: 设计范围，"mvp"（仅核心功能）或 "full"（全部功能）。

        Returns:
            完整的系统架构设计 Markdown 文档。
        """
        prompt_template = load_prompt("design")
        prompt = prompt_template.format(prd=prd, scope=scope)
        rsp = await self._aask(prompt)
        return rsp
