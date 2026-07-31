#!/usr/bin/env python3
"""
把各次运行结果聚合成基准摘要统计。

读取运行目录中的 grading.json，生成：
- 每个指标的 run_summary（mean、stddev、min、max）
- with_skill 与 without_skill 两种配置之间的差值（delta）

用法：
    python -m scripts.aggregate_benchmark <benchmark_dir>

示例：
    python -m scripts.aggregate_benchmark benchmarks/2026-01-15T10-30-00/

脚本支持两种目录布局：

    Workspace 布局（来自 skill-creator 迭代）：
    <benchmark_dir>/
    └── eval-N/
        ├── with_skill/
        │   ├── run-1/grading.json
        │   └── run-2/grading.json
        └── without_skill/
            ├── run-1/grading.json
            └── run-2/grading.json

    兼容布局（config 目录下直接放 grading.json，单次运行）：
    <benchmark_dir>/
    └── eval-N/
        ├── with_skill/
        │   └── grading.json
        └── without_skill/
            └── grading.json

    旧版布局（runs/ 子目录）：
    <benchmark_dir>/
    └── runs/
        └── eval-N/
            ├── with_skill/
            │   └── run-1/grading.json
            └── without_skill/
                └── run-1/grading.json
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.utils import ensure_utf8_stdio


def calculate_stats(values: list[float]) -> dict:
    """计算一组数值的 mean、stddev、min、max。"""
    if not values:
        return {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}

    n = len(values)
    mean = sum(values) / n

    if n > 1:
        variance = sum((x - mean) ** 2 for x in values) / (n - 1)
        stddev = math.sqrt(variance)
    else:
        stddev = 0.0

    return {
        "mean": round(mean, 4),
        "stddev": round(stddev, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4)
    }


# 配置目录名 → 展示标签（generate_markdown 使用）
CONFIG_LABELS = {
    "with_skill": "带技能",
    "without_skill": "不带技能",
    "new_skill": "新技能",
    "old_skill": "旧技能",
}


def _config_label(config: str) -> str:
    return CONFIG_LABELS.get(config, config.replace("_", " ").title())


def _load_run(grading_file: Path, eval_id: int, run_number: int) -> dict | None:
    """把单次运行的 grading.json 解析为聚合结果字典。"""
    try:
        with open(grading_file, encoding="utf-8") as f:
            grading = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"警告：{grading_file} 中的 JSON 无效：{e}")
        return None

    # 提取指标
    result = {
        "eval_id": eval_id,
        "run_number": run_number,
        "pass_rate": grading.get("summary", {}).get("pass_rate", 0.0),
        "passed": grading.get("summary", {}).get("passed", 0),
        "failed": grading.get("summary", {}).get("failed", 0),
        "total": grading.get("summary", {}).get("total", 0),
    }

    # 提取计时——先看 grading.json，再看同级的 timing.json
    timing = grading.get("timing", {})
    result["time_seconds"] = timing.get("total_duration_seconds", 0.0)
    timing_file = grading_file.parent / "timing.json"
    if result["time_seconds"] == 0.0 and timing_file.exists():
        try:
            with open(timing_file, encoding="utf-8") as tf:
                timing_data = json.load(tf)
            result["time_seconds"] = timing_data.get("total_duration_seconds", 0.0)
            result["tokens"] = timing_data.get("total_tokens", 0)
        except json.JSONDecodeError:
            pass

    # 提取执行指标
    metrics = grading.get("execution_metrics", {})
    result["tool_calls"] = metrics.get("total_tool_calls", 0)
    if not result.get("tokens"):
        result["tokens"] = metrics.get("output_chars", 0)
    result["errors"] = metrics.get("errors_encountered", 0)

    # 提取期望——查看器要求字段：text、passed、evidence
    raw_expectations = grading.get("expectations", [])
    for exp in raw_expectations:
        if "text" not in exp or "passed" not in exp:
            print(f"警告：{grading_file} 中的 expectation 缺少必填字段（text、passed、evidence）：{exp}")
    result["expectations"] = raw_expectations

    # 从 user_notes_summary 提取备注
    notes_summary = grading.get("user_notes_summary", {})
    notes = []
    notes.extend(notes_summary.get("uncertainties", []))
    notes.extend(notes_summary.get("needs_review", []))
    notes.extend(notes_summary.get("workarounds", []))
    result["notes"] = notes

    return result


def load_run_results(benchmark_dir: Path) -> dict:
    """
    从基准目录加载所有运行结果。

    返回以配置名（如 "with_skill"/"without_skill" 或 "new_skill"/"old_skill"）
    为键的字典，每个配置对应一个运行结果列表。

    config 目录内支持的布局：
    - `run-1/grading.json`、`run-2/grading.json`、...（多次运行）
    - 直接放 `grading.json`（单次运行，无 run-* 层）
    """
    # 同时支持两种布局：eval 目录直接在 benchmark_dir 下，或在 runs/ 下
    runs_dir = benchmark_dir / "runs"
    if runs_dir.exists():
        search_dir = runs_dir
    elif list(benchmark_dir.glob("eval-*")):
        search_dir = benchmark_dir
    else:
        print(f"在 {benchmark_dir} 或 {benchmark_dir / 'runs'} 下未找到 eval 目录")
        return {}

    results: dict[str, list] = {}

    for eval_idx, eval_dir in enumerate(sorted(search_dir.glob("eval-*"))):
        metadata_path = eval_dir / "eval_metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, encoding="utf-8") as mf:
                    eval_id = json.load(mf).get("eval_id", eval_idx)
            except (json.JSONDecodeError, OSError):
                eval_id = eval_idx
        else:
            try:
                eval_id = int(eval_dir.name.split("-")[1])
            except ValueError:
                eval_id = eval_idx

        # 动态发现配置目录，而不是硬编码名称
        for config_dir in sorted(eval_dir.iterdir()):
            if not config_dir.is_dir():
                continue
            config = config_dir.name

            # 布局 1：run-N/ 子目录（每个配置多次运行）
            run_dirs = sorted(config_dir.glob("run-*"))
            if run_dirs:
                if config not in results:
                    results[config] = []
                for run_dir in run_dirs:
                    try:
                        run_number = int(run_dir.name.split("-")[1])
                    except (IndexError, ValueError):
                        continue
                    grading_file = run_dir / "grading.json"
                    if not grading_file.exists():
                        print(f"警告：{run_dir} 中未找到 grading.json")
                        continue
                    item = _load_run(grading_file, eval_id, run_number)
                    if item is not None:
                        results[config].append(item)
                continue

            # 布局 2：config 目录下直接放 grading.json
            grading_file = config_dir / "grading.json"
            if grading_file.exists():
                if config not in results:
                    results[config] = []
                item = _load_run(grading_file, eval_id, run_number=1)
                if item is not None:
                    results[config].append(item)

    return results


def aggregate_results(results: dict) -> dict:
    """
    把运行结果聚合成摘要统计。

    返回包含各配置统计值和差值的 run_summary。
    """
    run_summary = {}
    configs = list(results.keys())

    for config in configs:
        runs = results.get(config, [])

        if not runs:
            run_summary[config] = {
                "pass_rate": {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0},
                "time_seconds": {"mean": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0},
                "tokens": {"mean": 0, "stddev": 0, "min": 0, "max": 0}
            }
            continue

        pass_rates = [r["pass_rate"] for r in runs]
        times = [r["time_seconds"] for r in runs]
        tokens = [r.get("tokens", 0) for r in runs]

        run_summary[config] = {
            "pass_rate": calculate_stats(pass_rates),
            "time_seconds": calculate_stats(times),
            "tokens": calculate_stats(tokens)
        }

    # 计算前两个配置之间的差值（如果存在两个）
    if len(configs) >= 2:
        primary = run_summary.get(configs[0], {})
        baseline = run_summary.get(configs[1], {})
    else:
        primary = run_summary.get(configs[0], {}) if configs else {}
        baseline = {}

    delta_pass_rate = primary.get("pass_rate", {}).get("mean", 0) - baseline.get("pass_rate", {}).get("mean", 0)
    delta_time = primary.get("time_seconds", {}).get("mean", 0) - baseline.get("time_seconds", {}).get("mean", 0)
    delta_tokens = primary.get("tokens", {}).get("mean", 0) - baseline.get("tokens", {}).get("mean", 0)

    run_summary["delta"] = {
        "pass_rate": f"{delta_pass_rate:+.2f}",
        "time_seconds": f"{delta_time:+.1f}",
        "tokens": f"{delta_tokens:+.0f}"
    }

    return run_summary


def generate_benchmark(benchmark_dir: Path, skill_name: str = "", skill_path: str = "") -> dict:
    """
    根据运行结果生成完整的 benchmark.json。
    """
    results = load_run_results(benchmark_dir)
    run_summary = aggregate_results(results)

    # 构造 benchmark.json 的 runs 数组
    runs = []
    for config in results:
        for result in results[config]:
            runs.append({
                "eval_id": result["eval_id"],
                "configuration": config,
                "run_number": result["run_number"],
                "result": {
                    "pass_rate": result["pass_rate"],
                    "passed": result["passed"],
                    "failed": result["failed"],
                    "total": result["total"],
                    "time_seconds": result["time_seconds"],
                    "tokens": result.get("tokens", 0),
                    "tool_calls": result.get("tool_calls", 0),
                    "errors": result.get("errors", 0)
                },
                "expectations": result["expectations"],
                "notes": result["notes"]
            })

    # 从结果确定 eval ID 列表
    eval_ids = sorted(set(
        r["eval_id"]
        for config in results.values()
        for r in config
    ))

    # 每种配置的运行次数（基准约定各配置次数统一，取第一个配置为准）
    configs = list(results.keys())
    runs_per_configuration = len(results[configs[0]]) if configs else 0

    benchmark = {
        "metadata": {
            "skill_name": skill_name or "<skill-name>",
            "skill_path": skill_path or "<path/to/skill>",
            "executor_model": "<model-name>",
            "analyzer_model": "<model-name>",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "evals_run": eval_ids,
            "runs_per_configuration": runs_per_configuration
        },
        "runs": runs,
        "run_summary": run_summary,
        "notes": []  # 由分析器填充
    }

    return benchmark


def generate_markdown(benchmark: dict) -> str:
    """从基准数据生成人类可读的 benchmark.md。"""
    metadata = benchmark["metadata"]
    run_summary = benchmark["run_summary"]

    # 确定配置名（排除 "delta"）
    configs = [k for k in run_summary if k != "delta"]
    config_a = configs[0] if len(configs) >= 1 else "config_a"
    config_b = configs[1] if len(configs) >= 2 else "config_b"
    label_a = _config_label(config_a)
    label_b = _config_label(config_b)

    lines = [
        f"# 技能基准：{metadata['skill_name']}",
        "",
        f"**模型**：{metadata['executor_model']}",
        f"**日期**：{metadata['timestamp']}",
        f"**评测**：{', '.join(map(str, metadata['evals_run']))}（每种配置各运行 {metadata['runs_per_configuration']} 次）",
        "",
        "## 汇总",
        "",
        f"| 指标 | {label_a} | {label_b} | 差值 |",
        "|--------|------------|---------------|-------|",
    ]

    a_summary = run_summary.get(config_a, {})
    b_summary = run_summary.get(config_b, {})
    delta = run_summary.get("delta", {})

    # 通过率
    a_pr = a_summary.get("pass_rate", {})
    b_pr = b_summary.get("pass_rate", {})
    lines.append(f"| 通过率 | {a_pr.get('mean', 0)*100:.0f}% ± {a_pr.get('stddev', 0)*100:.0f}% | {b_pr.get('mean', 0)*100:.0f}% ± {b_pr.get('stddev', 0)*100:.0f}% | {delta.get('pass_rate', '—')} |")

    # 耗时
    a_time = a_summary.get("time_seconds", {})
    b_time = b_summary.get("time_seconds", {})
    lines.append(f"| 耗时 | {a_time.get('mean', 0):.1f}s ± {a_time.get('stddev', 0):.1f}s | {b_time.get('mean', 0):.1f}s ± {b_time.get('stddev', 0):.1f}s | {delta.get('time_seconds', '—')}s |")

    # Token 数量
    a_tokens = a_summary.get("tokens", {})
    b_tokens = b_summary.get("tokens", {})
    lines.append(f"| Token | {a_tokens.get('mean', 0):.0f} ± {a_tokens.get('stddev', 0):.0f} | {b_tokens.get('mean', 0):.0f} ± {b_tokens.get('stddev', 0):.0f} | {delta.get('tokens', '—')} |")

    # 备注
    if benchmark.get("notes"):
        lines.extend([
            "",
            "## 备注",
            ""
        ])
        for note in benchmark["notes"]:
            lines.append(f"- {note}")

    return "\n".join(lines)


def main():
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="把基准运行结果聚合成摘要统计"
    )
    parser.add_argument(
        "benchmark_dir",
        type=Path,
        help="基准目录路径"
    )
    parser.add_argument(
        "--skill-name",
        default="",
        help="被测技能的名称"
    )
    parser.add_argument(
        "--skill-path",
        default="",
        help="被测技能的路径"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="benchmark.json 的输出路径（默认：<benchmark_dir>/benchmark.json）"
    )

    args = parser.parse_args()

    if not args.benchmark_dir.exists():
        print(f"目录不存在：{args.benchmark_dir}")
        sys.exit(1)

    # 生成 benchmark
    benchmark = generate_benchmark(args.benchmark_dir, args.skill_name, args.skill_path)

    # 确定输出路径
    output_json = args.output or (args.benchmark_dir / "benchmark.json")
    output_md = output_json.with_suffix(".md")

    # 写 benchmark.json
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(benchmark, f, indent=2)
    print(f"已生成：{output_json}")

    # 写 benchmark.md
    markdown = generate_markdown(benchmark)
    with open(output_md, "w", encoding="utf-8") as f:
        f.write(markdown)
    print(f"已生成：{output_md}")

    # 打印摘要
    run_summary = benchmark["run_summary"]
    configs = [k for k in run_summary if k != "delta"]
    delta = run_summary.get("delta", {})

    print(f"\n摘要：")
    for config in configs:
        pr = run_summary[config]["pass_rate"]["mean"]
        label = _config_label(config)
        print(f"  {label}：{pr*100:.1f}% 通过率")
    print(f"  差值：         {delta.get('pass_rate', '—')}")


if __name__ == "__main__":
    main()
