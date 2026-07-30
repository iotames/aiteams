"""
任务规划 Action

由 IMSTeamLeader 使用，将用户需求分解为结构化任务列表。
角色定义从 prompts/agents/project-manager.md 动态加载。
任务提示词从 prompts/task-planning.md 动态加载。
"""

from metagpt.actions import Action

from ims_metagpt.prompts.prompt_loader import load_prompt


class PlanTasks(Action):
    """将用户需求分解为可执行的任务规划"""

    name: str = "PlanTasks"

    async def run(self, requirement: str) -> str:
        """
        根据用户需求生成任务规划。

        Args:
            requirement: 用户的原始需求描述。

        Returns:
            结构化的任务规划 Markdown 文本。
        """
        role = load_prompt("agents/project-manager")
        task = load_prompt("task-planning")
        prompt = f"{role}\n\n{task}".format(requirement=requirement)
        rsp = await self._aask(prompt)
        return rsp
