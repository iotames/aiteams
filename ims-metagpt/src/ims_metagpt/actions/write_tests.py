"""
写测试代码 Action

由 IMSEngineer 使用，根据后端代码生成 pytest 测试用例。
角色定义从 prompts/agents/qa-engineer.md 动态加载。
任务提示词从 prompts/test-code.md 动态加载。
"""

from metagpt.actions import Action

from ims_metagpt.prompts.prompt_loader import load_prompt


class WriteTests(Action):
    """生成 pytest 测试代码"""

    name: str = "WriteTests"

    async def run(self, code: str) -> str:
        """
        根据后端代码生成测试用例。

        Args:
            code: 后端代码内容。

        Returns:
            生成的测试代码文件列表（含路径和内容）。
        """
        role = load_prompt("agents/qa-engineer")
        task = load_prompt("test-code")
        prompt = f"{role}\n\n{task}".format(code=code)
        rsp = await self._aask(prompt)
        return rsp
