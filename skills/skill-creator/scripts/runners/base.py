"""Runner abstraction for skill-trigger evaluation.

A Runner drives one model backend (CLI, HTTP API, ...) to answer the
question: "given a skill's name + description, does this query trigger it?".

Skill injection (how the backend learns about the skill) and trigger
detection (how the backend's output is interpreted) are encapsulated inside
each runner, so run_eval.py / run_loop.py stay backend-agnostic.

To support a new model provider, implement this protocol and register it in
scripts/runners/__init__.py. See references/runners.md for details.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SkillContext:
    """Everything a runner needs to know about the skill under evaluation."""

    skill_name: str
    description: str


@dataclass(frozen=True)
class TriggerResult:
    """Outcome of running one query against one backend."""

    triggered: bool
    evidence: str = ""   # human-readable note on how the decision was reached
    error: str = ""      # non-empty when the run failed (treated as no trigger)


class Runner(Protocol):
    """Backend that runs a single query and reports whether the skill triggered."""

    name: str

    def run_query(
        self,
        query: str,
        skill_ctx: SkillContext,
        model: str | None,
        timeout: int,
        project_root: str | None = None,
    ) -> TriggerResult:
        """Run `query` against the skill described by `skill_ctx`.

        Returns TriggerResult; failures must be reported via `error` rather
        than raised, so the caller can treat them as non-triggers.
        """
        ...
