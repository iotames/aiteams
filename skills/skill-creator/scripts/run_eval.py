#!/usr/bin/env python3
"""运行技能描述的触发评测。

测试技能的 description 是否让目标模型后端在一组 query 上触发
（读取技能 / 调用技能工具）。后端通过 --runner 可插拔
（见 scripts/runners/）。结果以 JSON 输出。

并发：使用 ThreadPoolExecutor。各 runner 的重活都是阻塞 I/O
（子进程 `claude -p` 或 HTTP 请求），会释放 GIL——线程即可获得
同样的并行度，且避免了跨进程 pickling runner 实例的脆弱性。
"""

import argparse
import json
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from scripts.runners import get_runner, detect_available_runners
from scripts.runners.base import SkillContext
from scripts.utils import ensure_utf8_stdio, parse_skill_md, prompt_choose_backend


def run_eval(
    eval_set: list[dict],
    skill_ctx: SkillContext,
    runner,
    num_workers: int,
    timeout: int,
    project_root: Path | None = None,
    runs_per_query: int = 1,
    trigger_threshold: float = 0.5,
    model: str | None = None,
) -> dict:
    """运行整个评测集并返回结果。"""
    results = []

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item_idx, item in enumerate(eval_set):
            for run_idx in range(runs_per_query):
                future = executor.submit(
                    runner.run_query,
                    item["query"],
                    skill_ctx,
                    model,
                    timeout,
                    str(project_root) if project_root else None,
                )
                # 用 eval 条目索引做 key：评测集中两条不同条目可能使用相同
                # query，按 query 字符串聚合会导致互相覆盖、统计错误。
                future_to_info[future] = (item_idx, run_idx)

        # 按 eval 条目索引聚合触发/错误（而不是按 query 字符串）
        item_triggers: dict[int, list[bool]] = {i: [] for i in range(len(eval_set))}
        item_errors: dict[int, list[str]] = {i: [] for i in range(len(eval_set))}
        for future in as_completed(future_to_info):
            item_idx, _ = future_to_info[future]
            try:
                result = future.result()
                item_triggers[item_idx].append(result.triggered)
                if result.error:
                    item_errors[item_idx].append(result.error)
                    print(
                        f"警告：query 失败（{result.error}）：{eval_set[item_idx]['query'][:60]}",
                        file=sys.stderr,
                    )
            except Exception as e:
                print(f"警告：query 失败：{e}", file=sys.stderr)
                item_triggers[item_idx].append(False)
                item_errors[item_idx].append(str(e))

    # 按 eval_set 原始顺序输出（与输入一致，便于 run_loop 按位置切分 train/test）
    for item_idx, item in enumerate(eval_set):
        triggers = item_triggers[item_idx]
        trigger_rate = sum(triggers) / len(triggers)
        should_trigger = item["should_trigger"]
        if should_trigger:
            did_pass = trigger_rate >= trigger_threshold
        else:
            did_pass = trigger_rate < trigger_threshold
        results.append({
            "query": item["query"],
            "should_trigger": should_trigger,
            "trigger_rate": trigger_rate,
            "triggers": sum(triggers),
            "runs": len(triggers),
            "errors": len(item_errors[item_idx]),
            "error_details": item_errors[item_idx][:3],
            "pass": did_pass,
        })

    passed = sum(1 for r in results if r["pass"])
    total = len(results)

    return {
        "skill_name": skill_ctx.skill_name,
        "description": skill_ctx.description,
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
        },
    }


def _make_project_root(arg: str | None) -> Path:
    """返回要交给 runner 的 project_root。

    显式 --project-root 优先；否则使用一次性临时目录，这样注入技能文件的
    runner（如 claude-code 在 .claude/commands/ 下写文件）绝不会污染用户的
    工作目录。
    """
    if arg:
        root = Path(arg).resolve()
        if not root.is_dir():
            raise ValueError(f"--project-root 不是目录：{root}")
        return root
    return Path(tempfile.mkdtemp(prefix="skill-eval-"))


def main():
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="运行技能描述的触发评测")
    parser.add_argument("--eval-set", required=True, help="评测集 JSON 文件路径")
    parser.add_argument("--skill-path", required=True, help="技能目录路径")
    parser.add_argument("--description", default=None, help="覆盖待测试的描述")
    parser.add_argument("--runner", default=None, help="评测后端：claude-code / openai（未指定时交互询问）；见 scripts/runners/")
    parser.add_argument("--openai-base-url", default=None, help="openai runner 的 Base URL（默认：$OPENAI_BASE_URL 或 https://api.openai.com/v1）")
    parser.add_argument("--openai-api-key", default=None, help="openai runner 的 API key（默认：$OPENAI_API_KEY）")
    parser.add_argument("--num-workers", type=int, default=10, help="并行 worker 数")
    parser.add_argument("--timeout", type=int, default=30, help="每条 query 的超时（秒）")
    parser.add_argument("--runs-per-query", type=int, default=3, help="每条 query 运行次数")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="触发率阈值")
    parser.add_argument("--model", default=None, help="要使用的模型（runner 相关；如 claude -p --model 或 OpenAI model id）")
    parser.add_argument("--project-root", default=None, help="runner 注入技能文件用的项目根（默认：一次性临时目录）")
    parser.add_argument("--verbose", action="store_true", help="向 stderr 打印进度")
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text(encoding="utf-8"))
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"错误：{skill_path} 下没有 SKILL.md", file=sys.stderr)
        sys.exit(1)

    name, original_description, content = parse_skill_md(skill_path)
    description = args.description or original_description

    runner_name = args.runner
    if not runner_name:
        runner_name = prompt_choose_backend(
            kind="评测后端 (runner)",
            candidates=detect_available_runners(),
            flag="--runner",
        )

    runner = get_runner(
        runner_name,
        base_url=args.openai_base_url,
        api_key=args.openai_api_key,
    )
    project_root = _make_project_root(args.project_root)

    if args.verbose:
        print(f"Runner：{runner.name}", file=sys.stderr)
        print(f"评测描述：{description}", file=sys.stderr)
        if not args.project_root:
            print(f"项目根：{project_root}（临时目录）", file=sys.stderr)

    output = run_eval(
        eval_set=eval_set,
        skill_ctx=SkillContext(skill_name=name, description=description),
        runner=runner,
        num_workers=args.num_workers,
        timeout=args.timeout,
        project_root=project_root,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
    )

    if args.verbose:
        summary = output["summary"]
        print(f"结果：{summary['passed']}/{summary['total']} 通过", file=sys.stderr)
        for r in output["results"]:
            status = "通过" if r["pass"] else "失败"
            rate_str = f"{r['triggers']}/{r['runs']}"
            err = f" errors={r['errors']}" if r["errors"] else ""
            print(f"  [{status}] rate={rate_str}{err} 期望触发={r['should_trigger']}：{r['query'][:70]}", file=sys.stderr)

    print(json.dumps(output, indent=2))

    # 清理一次性临时项目根（--project-root 显式指定时由调用方管理）
    if not args.project_root:
        shutil.rmtree(project_root, ignore_errors=True)


if __name__ == "__main__":
    main()
