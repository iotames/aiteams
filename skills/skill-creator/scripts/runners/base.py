"""技能触发评测的 Runner 抽象。

Runner 驱动一个模型后端（CLI、HTTP API……）来回答一个问题：
"给定技能的 name + description，这条 query 是否触发它？"

技能注入（后端如何获知技能）与触发检测（如何解读后端输出）都封装在
各 runner 内部，因此 run_eval.py / run_loop.py 保持后端无关。

要支持新的模型提供方，实现本协议并在 scripts/runners/__init__.py 注册。
详见 references/runners.md。
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SkillContext:
    """Runner 需要知道的关于被测技能的一切信息。"""

    skill_name: str
    description: str


@dataclass(frozen=True)
class TriggerResult:
    """一次 query 对一个后端运行的结果。"""

    triggered: bool
    evidence: str = ""   # 人类可读的判定依据
    error: str = ""      # 非空表示本次运行失败（按未触发处理）


class Runner(Protocol):
    """运行单条 query 并报告技能是否触发的后端。"""

    name: str

    def run_query(
        self,
        query: str,
        skill_ctx: SkillContext,
        model: str | None,
        timeout: int,
        project_root: str | None = None,
    ) -> TriggerResult:
        """用 skill_ctx 描述的技能运行 `query`。

        返回 TriggerResult；失败必须通过 `error` 报告而不是抛异常，
        以便调用方统一按未触发处理。
        """
        ...
