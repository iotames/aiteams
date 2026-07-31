#!/usr/bin/env python3
"""Run trigger evaluation for a skill description.

Tests whether a skill's description causes the target model backend to trigger
(read the skill / call the skill tool) for a set of queries. The backend is
pluggable via --runner (see scripts/runners/). Outputs results as JSON.
"""

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
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
    """Run the full eval set and return results."""
    results = []

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item in eval_set:
            for run_idx in range(runs_per_query):
                future = executor.submit(
                    runner.run_query,
                    item["query"],
                    skill_ctx,
                    model,
                    timeout,
                    str(project_root) if project_root else None,
                )
                future_to_info[future] = (item, run_idx)

        query_triggers: dict[str, list[bool]] = {}
        query_items: dict[str, dict] = {}
        for future in as_completed(future_to_info):
            item, _ = future_to_info[future]
            query = item["query"]
            query_items[query] = item
            if query not in query_triggers:
                query_triggers[query] = []
            try:
                result = future.result()
                query_triggers[query].append(result.triggered)
                if result.error:
                    print(
                        f"Warning: query failed ({result.error}): {query[:60]}",
                        file=sys.stderr,
                    )
            except Exception as e:
                print(f"Warning: query failed: {e}", file=sys.stderr)
                query_triggers[query].append(False)

    for query, triggers in query_triggers.items():
        item = query_items[query]
        trigger_rate = sum(triggers) / len(triggers)
        should_trigger = item["should_trigger"]
        if should_trigger:
            did_pass = trigger_rate >= trigger_threshold
        else:
            did_pass = trigger_rate < trigger_threshold
        results.append({
            "query": query,
            "should_trigger": should_trigger,
            "trigger_rate": trigger_rate,
            "triggers": sum(triggers),
            "runs": len(triggers),
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


def main():
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Run trigger evaluation for a skill description")
    parser.add_argument("--eval-set", required=True, help="Path to eval set JSON file")
    parser.add_argument("--skill-path", required=True, help="Path to skill directory")
    parser.add_argument("--description", default=None, help="Override description to test")
    parser.add_argument("--runner", default=None, help="Evaluation backend: claude-code / openai (未指定时交互询问); see scripts/runners/")
    parser.add_argument("--openai-base-url", default=None, help="Base URL for the openai runner (default: $OPENAI_BASE_URL or https://api.openai.com/v1)")
    parser.add_argument("--openai-api-key", default=None, help="API key for the openai runner (default: $OPENAI_API_KEY)")
    parser.add_argument("--num-workers", type=int, default=10, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per query in seconds")
    parser.add_argument("--runs-per-query", type=int, default=3, help="Number of runs per query")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="Trigger rate threshold")
    parser.add_argument("--model", default=None, help="Model to use (runner-specific; e.g. claude -p --model or OpenAI model id)")
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text(encoding="utf-8"))
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"Error: No SKILL.md found at {skill_path}", file=sys.stderr)
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

    if args.verbose:
        print(f"Runner: {runner.name}", file=sys.stderr)
        print(f"Evaluating: {description}", file=sys.stderr)

    output = run_eval(
        eval_set=eval_set,
        skill_ctx=SkillContext(skill_name=name, description=description),
        runner=runner,
        num_workers=args.num_workers,
        timeout=args.timeout,
        project_root=None,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        model=args.model,
    )

    if args.verbose:
        summary = output["summary"]
        print(f"Results: {summary['passed']}/{summary['total']} passed", file=sys.stderr)
        for r in output["results"]:
            status = "PASS" if r["pass"] else "FAIL"
            rate_str = f"{r['triggers']}/{r['runs']}"
            print(f"  [{status}] rate={rate_str} expected={r['should_trigger']}: {r['query'][:70]}", file=sys.stderr)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
