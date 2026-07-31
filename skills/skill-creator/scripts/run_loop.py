#!/usr/bin/env python3
"""运行「评测 + 改进」循环，直到全部通过或达到最大迭代次数。

把 run_eval.py 和 improve_description.py 组合成一个循环，跟踪历史并返回
找到的最佳描述。支持 train/test 分割以防止过拟合。
"""

import argparse
import json
import random
import sys
import tempfile
import time
import webbrowser
from pathlib import Path

from scripts.generate_report import generate_html
from scripts.improve_description import improve_description
from scripts.llm import get_llm_client, detect_available_llms
from scripts.runners import get_runner, detect_available_runners
from scripts.runners.base import SkillContext
from scripts.run_eval import run_eval, _make_project_root
from scripts.utils import ensure_utf8_stdio, parse_skill_md, prompt_choose_backend


def split_eval_set(eval_set: list[dict], holdout: float, seed: int = 42) -> tuple[list[dict], list[dict]]:
    """把评测集按 should_trigger 分层拆分为 train 和 test。"""
    random.seed(seed)

    # 按 should_trigger 分组
    trigger = [e for e in eval_set if e["should_trigger"]]
    no_trigger = [e for e in eval_set if not e["should_trigger"]]

    # 各自洗牌
    random.shuffle(trigger)
    random.shuffle(no_trigger)

    # 计算分割点
    n_trigger_test = max(1, int(len(trigger) * holdout))
    n_no_trigger_test = max(1, int(len(no_trigger) * holdout))

    # 分割
    test_set = trigger[:n_trigger_test] + no_trigger[:n_no_trigger_test]
    train_set = trigger[n_trigger_test:] + no_trigger[n_no_trigger_test:]

    return train_set, test_set


def run_loop(
    eval_set: list[dict],
    skill_path: Path,
    description_override: str | None,
    num_workers: int,
    timeout: int,
    max_iterations: int,
    runs_per_query: int,
    trigger_threshold: float,
    holdout: float,
    model: str,
    verbose: bool,
    live_report_path: Path | None = None,
    log_dir: Path | None = None,
    runner=None,
    llm_client=None,
    project_root_arg: str | None = None,
) -> dict:
    """运行「评测 + 改进」循环。"""
    name, original_description, content = parse_skill_md(skill_path)
    current_description = description_override or original_description

    # 如果 holdout > 0 则拆分为 train/test
    if holdout > 0:
        train_set, test_set = split_eval_set(eval_set, holdout)
        if not train_set:
            raise ValueError(
                "holdout 分割导致 train 集为空——请降低 --holdout 或增加评测查询"
            )
        if verbose:
            print(f"分割：{len(train_set)} train, {len(test_set)} test (holdout={holdout})", file=sys.stderr)
    else:
        train_set = eval_set
        test_set = []

    history = []
    exit_reason = "unknown"

    # 需要注入技能文件的 runner 需要一个项目根；默认用一次性临时目录
    # （--project-root 可覆盖）。
    project_root = _make_project_root(project_root_arg)

    for iteration in range(1, max_iterations + 1):
        if verbose:
            print(f"\n{'='*60}", file=sys.stderr)
            print(f"第 {iteration}/{max_iterations} 轮", file=sys.stderr)
            print(f"描述：{current_description}", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)

        # 一次性并行评测 train + test
        all_queries = train_set + test_set
        t0 = time.time()
        all_results = run_eval(
            eval_set=all_queries,
            skill_ctx=SkillContext(skill_name=name, description=current_description),
            runner=runner,
            num_workers=num_workers,
            timeout=timeout,
            project_root=project_root,
            runs_per_query=runs_per_query,
            trigger_threshold=trigger_threshold,
            model=model,
        )
        eval_elapsed = time.time() - t0

        # 按 query 把结果拆回 train/test
        train_queries_set = {q["query"] for q in train_set}
        train_result_list = [r for r in all_results["results"] if r["query"] in train_queries_set]
        test_result_list = [r for r in all_results["results"] if r["query"] not in train_queries_set]

        train_passed = sum(1 for r in train_result_list if r["pass"])
        train_total = len(train_result_list)
        train_summary = {"passed": train_passed, "failed": train_total - train_passed, "total": train_total}
        train_results = {"results": train_result_list, "summary": train_summary}

        if test_set:
            test_passed = sum(1 for r in test_result_list if r["pass"])
            test_total = len(test_result_list)
            test_summary = {"passed": test_passed, "failed": test_total - test_passed, "total": test_total}
            test_results = {"results": test_result_list, "summary": test_summary}
        else:
            test_results = None
            test_summary = None

        history.append({
            "iteration": iteration,
            "description": current_description,
            "train_passed": train_summary["passed"],
            "train_failed": train_summary["failed"],
            "train_total": train_summary["total"],
            "train_results": train_results["results"],
            "test_passed": test_summary["passed"] if test_summary else None,
            "test_failed": test_summary["failed"] if test_summary else None,
            "test_total": test_summary["total"] if test_summary else None,
            "test_results": test_results["results"] if test_results else None,
            # 兼容 report generator 的字段名
            "passed": train_summary["passed"],
            "failed": train_summary["failed"],
            "total": train_summary["total"],
            "results": train_results["results"],
        })

        # 如提供了路径则写实时报告
        if live_report_path:
            partial_output = {
                "original_description": original_description,
                "best_description": current_description,
                "best_score": "in progress",
                "iterations_run": len(history),
                "holdout": holdout,
                "train_size": len(train_set),
                "test_size": len(test_set),
                "history": history,
            }
            live_report_path.write_text(generate_html(partial_output, auto_refresh=True, skill_name=name), encoding="utf-8")

        if verbose:
            def print_eval_stats(label, results, elapsed):
                pos = [r for r in results if r["should_trigger"]]
                neg = [r for r in results if not r["should_trigger"]]
                tp = sum(r["triggers"] for r in pos)
                pos_runs = sum(r["runs"] for r in pos)
                fn = pos_runs - tp
                fp = sum(r["triggers"] for r in neg)
                neg_runs = sum(r["runs"] for r in neg)
                tn = neg_runs - fp
                total = tp + tn + fp + fn
                precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
                recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
                accuracy = (tp + tn) / total if total > 0 else 0.0
                print(f"{label}: {tp+tn}/{total} 正确，精确率={precision:.0%} 召回率={recall:.0%} 准确率={accuracy:.0%}（{elapsed:.1f}s）", file=sys.stderr)
                for r in results:
                    status = "通过" if r["pass"] else "失败"
                    rate_str = f"{r['triggers']}/{r['runs']}"
                    print(f"  [{status}] rate={rate_str} 期望触发={r['should_trigger']}：{r['query'][:60]}", file=sys.stderr)

            print_eval_stats("Train", train_results["results"], eval_elapsed)
            if test_summary:
                print_eval_stats("Test ", test_results["results"], 0)

        # 0/0 必须视为"未完成"而非"全部通过"，否则退化分割（train 为空）
        # 会被误判为成功并立即退出。
        if train_summary["total"] > 0 and train_summary["failed"] == 0:
            exit_reason = f"all_passed (iteration {iteration})"
            if verbose:
                print(f"\n第 {iteration} 轮所有 train 查询都通过了！", file=sys.stderr)
            break

        if iteration == max_iterations:
            exit_reason = f"max_iterations ({max_iterations})"
            if verbose:
                print(f"\n达到最大迭代次数（{max_iterations}）。", file=sys.stderr)
            break

        # 根据 train 结果改进描述
        if verbose:
            print(f"\n正在改进描述...", file=sys.stderr)

        t0 = time.time()
        # 从历史中剔除 test 分数，避免改进模型看到它们
        blinded_history = [
            {k: v for k, v in h.items() if not k.startswith("test_")}
            for h in history
        ]
        new_description = improve_description(
            skill_name=name,
            skill_content=content,
            current_description=current_description,
            eval_results=train_results,
            history=blinded_history,
            model=model,
            log_dir=log_dir,
            iteration=iteration,
            llm_client=llm_client,
        )
        improve_elapsed = time.time() - t0

        if verbose:
            print(f"建议（{improve_elapsed:.1f}s）：{new_description}", file=sys.stderr)

        current_description = new_description

    # 按 TEST 分数找最佳迭代（没有 test 集则用 train）
    if test_set:
        best = max(history, key=lambda h: h["test_passed"] or 0)
        best_score = f"{best['test_passed']}/{best['test_total']}"
    else:
        best = max(history, key=lambda h: h["train_passed"])
        best_score = f"{best['train_passed']}/{best['train_total']}"

    if verbose:
        print(f"\n退出原因：{exit_reason}", file=sys.stderr)
        print(f"最佳分数：{best_score}（第 {best['iteration']} 轮）", file=sys.stderr)

    return {
        "exit_reason": exit_reason,
        "original_description": original_description,
        "best_description": best["description"],
        "best_score": best_score,
        "best_train_score": f"{best['train_passed']}/{best['train_total']}",
        "best_test_score": f"{best['test_passed']}/{best['test_total']}" if test_set else None,
        "final_description": current_description,
        "iterations_run": len(history),
        "holdout": holdout,
        "train_size": len(train_set),
        "test_size": len(test_set),
        "history": history,
    }


def main():
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="运行「评测 + 改进」循环")
    parser.add_argument("--eval-set", required=True, help="评测集 JSON 文件路径")
    parser.add_argument("--skill-path", required=True, help="技能目录路径")
    parser.add_argument("--description", default=None, help="覆盖起始描述")
    parser.add_argument("--num-workers", type=int, default=10, help="并行 worker 数")
    parser.add_argument("--timeout", type=int, default=30, help="每条 query 的超时（秒）")
    parser.add_argument("--max-iterations", type=int, default=5, help="最大改进迭代次数")
    parser.add_argument("--runs-per-query", type=int, default=3, help="每条 query 运行次数")
    parser.add_argument("--trigger-threshold", type=float, default=0.5, help="触发率阈值")
    parser.add_argument("--holdout", type=float, default=0.4, help="留作测试的评测集比例（0 表示禁用）")
    parser.add_argument("--model", required=True, help="改进所用的模型")
    parser.add_argument("--runner", default=None, help="评测后端：claude-code / openai（未指定时交互询问）；见 scripts/runners/")
    parser.add_argument("--llm", default=None, help="描述改进的 LLM 后端：claude / openai（未指定时交互询问）；见 scripts/llm.py")
    parser.add_argument("--openai-base-url", default=None, help="openai runner/LLM 客户端的 Base URL（默认：$OPENAI_BASE_URL）")
    parser.add_argument("--openai-api-key", default=None, help="openai runner/LLM 客户端的 API key（默认：$OPENAI_API_KEY）")
    parser.add_argument("--project-root", default=None, help="runner 注入技能文件用的项目根（默认：一次性临时目录）")
    parser.add_argument("--verbose", action="store_true", help="向 stderr 打印进度")
    parser.add_argument("--report", default="auto", help="在此路径生成 HTML 报告（默认 'auto' 为临时文件，'none' 禁用）")
    parser.add_argument("--results-dir", default=None, help="把全部输出（results.json、report.html、log.txt）保存到此处的时间戳子目录")
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_set).read_text(encoding="utf-8"))
    skill_path = Path(args.skill_path)

    if not (skill_path / "SKILL.md").exists():
        print(f"错误：{skill_path} 下没有 SKILL.md", file=sys.stderr)
        sys.exit(1)

    name, _, _ = parse_skill_md(skill_path)

    # 设置实时报告路径
    if args.report != "none":
        if args.report == "auto":
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            live_report_path = Path(tempfile.gettempdir()) / f"skill_description_report_{skill_path.name}_{timestamp}.html"
        else:
            live_report_path = Path(args.report)
        # 立即打开报告，让用户可以实时观看
        live_report_path.write_text("<html><body><h1>正在启动优化循环...</h1><meta http-equiv='refresh' content='5'></body></html>", encoding="utf-8")
        webbrowser.open(str(live_report_path))
    else:
        live_report_path = None

    # 确定输出目录（在 run_loop 之前创建，以便写入日志）
    if args.results_dir:
        timestamp = time.strftime("%Y-%m-%d_%H%M%S")
        results_dir = Path(args.results_dir) / timestamp
        results_dir.mkdir(parents=True, exist_ok=True)
    else:
        results_dir = None

    log_dir = results_dir / "logs" if results_dir else None

    runner_name = args.runner
    if not runner_name:
        runner_name = prompt_choose_backend(
            kind="评测后端 (runner)",
            candidates=detect_available_runners(),
            flag="--runner",
        )
    llm_name = args.llm
    if not llm_name:
        llm_name = prompt_choose_backend(
            kind="描述改进模型 (llm)",
            candidates=detect_available_llms(),
            flag="--llm",
        )

    output = run_loop(
        eval_set=eval_set,
        skill_path=skill_path,
        description_override=args.description,
        num_workers=args.num_workers,
        timeout=args.timeout,
        max_iterations=args.max_iterations,
        runs_per_query=args.runs_per_query,
        trigger_threshold=args.trigger_threshold,
        holdout=args.holdout,
        model=args.model,
        verbose=args.verbose,
        live_report_path=live_report_path,
        log_dir=log_dir,
        runner=get_runner(
            runner_name,
            base_url=args.openai_base_url,
            api_key=args.openai_api_key,
        ),
        llm_client=get_llm_client(
            llm_name,
            base_url=args.openai_base_url,
            api_key=args.openai_api_key,
        ),
        project_root_arg=args.project_root,
    )

    # 写 JSON 输出
    json_output = json.dumps(output, indent=2)
    print(json_output)
    if results_dir:
        (results_dir / "results.json").write_text(json_output, encoding="utf-8")

    # 写最终 HTML 报告（关闭自动刷新）
    if live_report_path:
        live_report_path.write_text(generate_html(output, auto_refresh=False, skill_name=name), encoding="utf-8")
        print(f"\n报告：{live_report_path}", file=sys.stderr)

    if results_dir and live_report_path:
        (results_dir / "report.html").write_text(generate_html(output, auto_refresh=False, skill_name=name), encoding="utf-8")

    if results_dir:
        print(f"结果已保存到：{results_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
