#!/usr/bin/env python3
"""根据评测结果改进技能描述。

接收 run_eval.py 的评测结果，调用 LLM 客户端（见 scripts/llm.py）生成改进
后的描述。默认使用 Claude Code CLI（`claude -p`），复用会话认证——无需单独
的 ANTHROPIC_API_KEY。使用 --llm openai 可走任意 chat-completions 端点。
"""

import argparse
import json
import re
import sys
from pathlib import Path

from scripts.llm import detect_available_llms, get_llm_client
from scripts.utils import ensure_utf8_stdio, parse_skill_md, prompt_choose_backend


def improve_description(
    skill_name: str,
    skill_content: str,
    current_description: str,
    eval_results: dict,
    history: list[dict],
    model: str,
    test_results: dict | None = None,
    log_dir: Path | None = None,
    iteration: int | None = None,
    llm_client=None,
) -> str:
    """根据评测结果请 LLM 改进描述。"""
    failed_triggers = [
        r for r in eval_results["results"]
        if r["should_trigger"] and not r["pass"]
    ]
    false_triggers = [
        r for r in eval_results["results"]
        if not r["should_trigger"] and not r["pass"]
    ]

    # 构建分数摘要
    train_score = f"{eval_results['summary']['passed']}/{eval_results['summary']['total']}"
    if test_results:
        test_score = f"{test_results['summary']['passed']}/{test_results['summary']['total']}"
        scores_summary = f"Train: {train_score}, Test: {test_score}"
    else:
        scores_summary = f"Train: {train_score}"

    prompt = f"""You are optimizing the description of a skill called "{skill_name}" for a coding agent (such as Claude Code, Codex, or another agent harness). A "skill" is sort of like a prompt, but with progressive disclosure -- there's a title and description that the agent sees when deciding whether to use the skill, and then if it does use the skill, it reads the .md file which has lots more details and potentially links to other resources in the skill folder like helper files and scripts and additional documentation or examples.

The description appears in the agent's "available_skills" list. When a user sends a query, the agent decides whether to invoke the skill based solely on the title and on this description. Your goal is to write a description that triggers for relevant queries, and doesn't trigger for irrelevant ones.

Here's the current description:
<current_description>
"{current_description}"
</current_description>

Current scores ({scores_summary}):
<scores_summary>
"""
    if failed_triggers:
        prompt += "FAILED TO TRIGGER (should have triggered but didn't):\n"
        for r in failed_triggers:
            prompt += f'  - "{r["query"]}" (triggered {r["triggers"]}/{r["runs"]} times)\n'
        prompt += "\n"

    if false_triggers:
        prompt += "FALSE TRIGGERS (triggered but shouldn't have):\n"
        for r in false_triggers:
            prompt += f'  - "{r["query"]}" (triggered {r["triggers"]}/{r["runs"]} times)\n'
        prompt += "\n"

    if history:
        prompt += "PREVIOUS ATTEMPTS (do NOT repeat these — try something structurally different):\n\n"
        for h in history:
            train_s = f"{h.get('train_passed', h.get('passed', 0))}/{h.get('train_total', h.get('total', 0))}"
            test_s = f"{h.get('test_passed', '?')}/{h.get('test_total', '?')}" if h.get('test_passed') is not None else None
            score_str = f"train={train_s}" + (f", test={test_s}" if test_s else "")
            prompt += f'<attempt {score_str}>\n'
            prompt += f'Description: "{h["description"]}"\n'
            if "results" in h:
                prompt += "Train results:\n"
                for r in h["results"]:
                    status = "PASS" if r["pass"] else "FAIL"
                    prompt += f'  [{status}] "{r["query"][:80]}" (triggered {r["triggers"]}/{r["runs"]})\n'
            if h.get("note"):
                prompt += f'Note: {h["note"]}\n'
            prompt += "</attempt>\n\n"

    prompt += f"""</scores_summary>

Skill content (for context on what the skill does):
<skill_content>
{skill_content}
</skill_content>

Based on the failures, write a new and improved description that is more likely to trigger correctly. When I say "based on the failures", it's a bit of a tricky line to walk because we don't want to overfit to the specific cases you're seeing. So what I DON'T want you to do is produce an ever-expanding list of specific queries that this skill should or shouldn't trigger for. Instead, try to generalize from the failures to broader categories of user intent and situations where this skill would be useful or not useful. The reason for this is twofold:

1. Avoid overfitting
2. The list might get loooong and it's injected into ALL queries and there might be a lot of skills, so we don't want to blow too much space on any given description.

Concretely, your description should not be more than about 100-200 words, even if that comes at the cost of accuracy. There is a hard limit of 1024 characters — descriptions over that will be truncated, so stay comfortably under it.

Here are some tips that we've found to work well in writing these descriptions:
- The skill should be phrased in the imperative -- "Use this skill for" rather than "this skill does"
- The skill description should focus on the user's intent, what they are trying to achieve, vs. the implementation details of how the skill works.
- The description competes with other skills for the agent's attention — make it distinctive and immediately recognizable.
- If you're getting lots of failures after repeated attempts, change things up. Try different sentence structures or wordings.

I'd encourage you to be creative and mix up the style in different iterations since you'll have multiple opportunities to try different approaches and we'll just grab the highest-scoring one at the end.

Please respond with only the new description text in <new_description> tags, nothing else."""

    client = llm_client
    if client is None:
        raise ValueError(
            "improve_description() 需要 llm_client —— 请显式传入"
            "（CLI 会询问用户使用哪个后端）。"
        )
    text = client.complete(prompt, model=model)

    match = re.search(r"<new_description>(.*?)</new_description>", text, re.DOTALL)
    description = match.group(1).strip().strip('"') if match else text.strip().strip('"')

    transcript: dict = {
        "iteration": iteration,
        "prompt": prompt,
        "response": text,
        "parsed_description": description,
        "char_count": len(description),
        "over_limit": len(description) > 1024,
    }

    # 安全网：prompt 里已经声明了 1024 字符的硬限制，但如果模型
    # 还是超了，就再发起一次全新的一次性调用，把过长版本引用进去
    # 并要求缩短重写。（旧的 SDK 路径是真正的多轮对话；`claude -p`
    # 是单轮的，所以我们把前一次输出内联到新 prompt 里。）
    if len(description) > 1024:
        shorten_prompt = (
            f"{prompt}\n\n"
            f"---\n\n"
            f"A previous attempt produced this description, which at "
            f"{len(description)} characters is over the 1024-character hard limit:\n\n"
            f'"{description}"\n\n'
            f"Rewrite it to be under 1024 characters while keeping the most "
            f"important trigger words and intent coverage. Respond with only "
            f"the new description in <new_description> tags."
        )
        shorten_text = client.complete(shorten_prompt, model=model)
        match = re.search(r"<new_description>(.*?)</new_description>", shorten_text, re.DOTALL)
        shortened = match.group(1).strip().strip('"') if match else shorten_text.strip().strip('"')

        transcript["rewrite_prompt"] = shorten_prompt
        transcript["rewrite_response"] = shorten_text
        transcript["rewrite_description"] = shortened
        transcript["rewrite_char_count"] = len(shortened)
        description = shortened

    transcript["final_description"] = description

    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"improve_iter_{iteration or 'unknown'}.json"
        log_file.write_text(json.dumps(transcript, indent=2), encoding="utf-8")

    return description


def main():
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="根据评测结果改进技能描述")
    parser.add_argument("--eval-results", required=True, help="评测结果 JSON 路径（来自 run_eval.py）")
    parser.add_argument("--skill-path", required=True, help="技能目录路径")
    parser.add_argument("--history", default=None, help="历史 JSON 路径（之前的尝试）")
    parser.add_argument("--model", required=True, help="改进所用的模型")
    parser.add_argument("--llm", default=None, help="LLM 后端：claude / openai（未指定时交互询问）；见 scripts/llm.py")
    parser.add_argument("--openai-base-url", default=None, help="openai LLM 客户端的 Base URL（默认：$OPENAI_BASE_URL 或 https://api.openai.com/v1）")
    parser.add_argument("--openai-api-key", default=None, help="openai LLM 客户端的 API key（默认：$OPENAI_API_KEY）")
    parser.add_argument("--verbose", action="store_true", help="向 stderr 打印思考过程")
    args = parser.parse_args()

    skill_path = Path(args.skill_path)
    if not (skill_path / "SKILL.md").exists():
        print(f"错误：{skill_path} 下没有 SKILL.md", file=sys.stderr)
        sys.exit(1)

    eval_results = json.loads(Path(args.eval_results).read_text(encoding="utf-8"))
    history = []
    if args.history:
        history = json.loads(Path(args.history).read_text(encoding="utf-8"))

    name, _, content = parse_skill_md(skill_path)
    current_description = eval_results["description"]

    if args.verbose:
        print(f"当前：{current_description}", file=sys.stderr)
        print(f"分数：{eval_results['summary']['passed']}/{eval_results['summary']['total']}", file=sys.stderr)

    llm_name = args.llm
    if not llm_name:
        llm_name = prompt_choose_backend(
            kind="描述改进模型 (llm)",
            candidates=detect_available_llms(),
            flag="--llm",
        )

    new_description = improve_description(
        skill_name=name,
        skill_content=content,
        current_description=current_description,
        eval_results=eval_results,
        history=history,
        model=args.model,
        llm_client=get_llm_client(
            llm_name,
            base_url=args.openai_base_url,
            api_key=args.openai_api_key,
        ),
    )

    if args.verbose:
        print(f"改进后：{new_description}", file=sys.stderr)

    # 输出为 JSON：包含新描述和更新后的历史
    output = {
        "description": new_description,
        "history": history + [{
            "description": current_description,
            "passed": eval_results["summary"]["passed"],
            "failed": eval_results["summary"]["failed"],
            "total": eval_results["summary"]["total"],
            "results": eval_results["results"],
        }],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
