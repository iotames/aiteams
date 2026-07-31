#!/usr/bin/env python3
"""根据 run_loop.py 的输出生成 HTML 报告。

读取 run_loop.py 的 JSON 输出，生成可视化 HTML 报告，
展示每个描述尝试在每条测试用例上的通过/失败情况，
并区分训练查询与测试查询。
"""

import argparse
import html
import json
import sys
from pathlib import Path

from scripts.utils import ensure_utf8_stdio


def aggregate_runs(results: list[dict]) -> tuple[int, int]:
    """计算所有重试次数的合计正确/总数。"""
    correct = 0
    total = 0
    for r in results:
        runs = r.get("runs", 0)
        triggers = r.get("triggers", 0)
        total += runs
        if r.get("should_trigger", True):
            correct += triggers
        else:
            correct += runs - triggers
    return correct, total


def score_class(correct: int, total: int) -> str:
    """根据正确率返回 CSS 类名（good / ok / bad）。"""
    if total > 0:
        ratio = correct / total
        if ratio >= 0.8:
            return "score-good"
        elif ratio >= 0.5:
            return "score-ok"
    return "score-bad"


def generate_html(data: dict, auto_refresh: bool = False, skill_name: str = "") -> str:
    """根据循环输出数据生成 HTML 报告。auto_refresh 为 True 时添加 meta refresh 标签。"""
    history = data.get("history", [])
    holdout = data.get("holdout", 0)
    title_prefix = html.escape(skill_name + " \u2014 ") if skill_name else ""

    # 收集训练集和测试集的所有唯一查询，附带 should_trigger 信息
    train_queries: list[dict] = []
    test_queries: list[dict] = []
    if history:
        for r in history[0].get("train_results", history[0].get("results", [])):
            train_queries.append({"query": r["query"], "should_trigger": r.get("should_trigger", True)})
        if history[0].get("test_results"):
            for r in history[0].get("test_results", []):
                test_queries.append({"query": r["query"], "should_trigger": r.get("should_trigger", True)})

    refresh_tag = '    <meta http-equiv="refresh" content="5">\n' if auto_refresh else ""

    html_parts = ["""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
""" + refresh_tag + """    <title>""" + title_prefix + """技能描述优化</title>
    <style>
        body {
            font-family: Georgia, 'Noto Serif SC', 'Songti SC', serif;
            max-width: 100%;
            margin: 0 auto;
            padding: 20px;
            background: #faf9f5;
            color: #141413;
        }
        h1 { font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; color: #141413; }
        .explainer {
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            border: 1px solid #e8e6dc;
            color: #b0aea5;
            font-size: 0.875rem;
            line-height: 1.6;
        }
        .summary {
            background: white;
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            border: 1px solid #e8e6dc;
        }
        .summary p { margin: 5px 0; }
        .best { color: #788c5d; font-weight: bold; }
        .table-container {
            overflow-x: auto;
            width: 100%;
        }
        table {
            border-collapse: collapse;
            background: white;
            border: 1px solid #e8e6dc;
            border-radius: 6px;
            font-size: 12px;
            min-width: 100%;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border: 1px solid #e8e6dc;
            white-space: normal;
            word-wrap: break-word;
        }
        th {
            font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
            background: #141413;
            color: #faf9f5;
            font-weight: 500;
        }
        th.test-col {
            background: #6a9bcc;
        }
        th.query-col { min-width: 200px; }
        td.description {
            font-family: monospace;
            font-size: 11px;
            word-wrap: break-word;
            max-width: 400px;
        }
        td.result {
            text-align: center;
            font-size: 16px;
            min-width: 40px;
        }
        td.test-result {
            background: #f0f6fc;
        }
        .pass { color: #788c5d; }
        .fail { color: #c44; }
        .rate {
            font-size: 9px;
            color: #b0aea5;
            display: block;
        }
        tr:hover { background: #faf9f5; }
        .score {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 11px;
        }
        .score-good { background: #eef2e8; color: #788c5d; }
        .score-ok { background: #fef3c7; color: #d97706; }
        .score-bad { background: #fceaea; color: #c44; }
        .train-label { color: #b0aea5; font-size: 10px; }
        .test-label { color: #6a9bcc; font-size: 10px; font-weight: bold; }
        .best-row { background: #f5f8f2; }
        th.positive-col { border-bottom: 3px solid #788c5d; }
        th.negative-col { border-bottom: 3px solid #c44; }
        th.test-col.positive-col { border-bottom: 3px solid #788c5d; }
        th.test-col.negative-col { border-bottom: 3px solid #c44; }
        .legend { font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; display: flex; gap: 20px; margin-bottom: 10px; font-size: 13px; align-items: center; }
        .legend-item { display: flex; align-items: center; gap: 6px; }
        .legend-swatch { width: 16px; height: 16px; border-radius: 3px; display: inline-block; }
        .swatch-positive { background: #141413; border-bottom: 3px solid #788c5d; }
        .swatch-negative { background: #141413; border-bottom: 3px solid #c44; }
        .swatch-test { background: #6a9bcc; }
        .swatch-train { background: #141413; }
    </style>
</head>
<body>
    <h1>""" + title_prefix + """技能描述优化</h1>
    <div class="explainer">
        <strong>正在优化技能描述。</strong> 此页面会随模型测试技能描述的不同版本自动更新。每一行是一次迭代 —— 一个新的描述尝试。列对应测试查询：绿色对勾表示技能正确触发（或正确地没有触发），红色叉号表示判断错误。“训练”分数表示在用于改进描述的查询上的表现；“测试”分数表示在优化器从未见过的留出查询上的表现。完成后，表现最佳的描述会被应用到你的技能上。
    </div>
"""]

    # 汇总区块
    best_test_score = data.get('best_test_score')
    best_train_score = data.get('best_train_score')
    html_parts.append(f"""
    <div class="summary">
        <p><strong>原始描述：</strong> {html.escape(data.get('original_description', 'N/A'))}</p>
        <p class="best"><strong>最佳描述：</strong> {html.escape(data.get('best_description', 'N/A'))}</p>
        <p><strong>最佳分数：</strong> {data.get('best_score', 'N/A')} {'（测试）' if best_test_score else '（训练）'}</p>
        <p><strong>迭代次数：</strong> {data.get('iterations_run', 0)} | <strong>训练集：</strong> {data.get('train_size', '?')} | <strong>测试集：</strong> {data.get('test_size', '?')}</p>
    </div>
""")

    # 图例
    html_parts.append("""
    <div class="legend">
        <span style="font-weight:600">查询列：</span>
        <span class="legend-item"><span class="legend-swatch swatch-positive"></span> 应触发</span>
        <span class="legend-item"><span class="legend-swatch swatch-negative"></span> 不应触发</span>
        <span class="legend-item"><span class="legend-swatch swatch-train"></span> 训练</span>
        <span class="legend-item"><span class="legend-swatch swatch-test"></span> 测试</span>
    </div>
""")

    # 表头
    html_parts.append("""
    <div class="table-container">
    <table>
        <thead>
            <tr>
                <th>迭代</th>
                <th>训练</th>
                <th>测试</th>
                <th class="query-col">描述</th>
""")

    # 为每个训练查询添加列头
    for qinfo in train_queries:
        polarity = "positive-col" if qinfo["should_trigger"] else "negative-col"
        html_parts.append(f'                <th class="{polarity}">{html.escape(qinfo["query"])}</th>\n')

    # 为每个测试查询添加列头（不同颜色）
    for qinfo in test_queries:
        polarity = "positive-col" if qinfo["should_trigger"] else "negative-col"
        html_parts.append(f'                <th class="test-col {polarity}">{html.escape(qinfo["query"])}</th>\n')

    html_parts.append("""            </tr>
        </thead>
        <tbody>
""")

    # 找出最佳迭代用于高亮
    if history:
        if test_queries:
            best_iter = max(history, key=lambda h: h.get("test_passed") or 0).get("iteration")
        else:
            best_iter = max(history, key=lambda h: h.get("train_passed", h.get("passed", 0))).get("iteration")
    else:
        best_iter = None

    # 为每次迭代添加行
    for h in history:
        iteration = h.get("iteration", "?")
        train_passed = h.get("train_passed", h.get("passed", 0))
        train_total = h.get("train_total", h.get("total", 0))
        test_passed = h.get("test_passed")
        test_total = h.get("test_total")
        description = h.get("description", "")
        train_results = h.get("train_results", h.get("results", [])) or []
        test_results = h.get("test_results") or []

        # 为查询结果建立查找表
        train_by_query = {r["query"]: r for r in train_results}
        test_by_query = {r["query"]: r for r in test_results} if test_results else {}

        train_correct, train_runs = aggregate_runs(train_results)
        test_correct, test_runs = aggregate_runs(test_results)

        train_class = score_class(train_correct, train_runs)
        test_class = score_class(test_correct, test_runs)

        row_class = "best-row" if iteration == best_iter else ""

        html_parts.append(f"""            <tr class="{row_class}">
                <td>{iteration}</td>
                <td><span class="score {train_class}">{train_correct}/{train_runs}</span></td>
                <td><span class="score {test_class}">{test_correct}/{test_runs}</span></td>
                <td class="description">{html.escape(description)}</td>
""")

        # 为每个训练查询添加结果
        for qinfo in train_queries:
            r = train_by_query.get(qinfo["query"], {})
            did_pass = r.get("pass", False)
            triggers = r.get("triggers", 0)
            runs = r.get("runs", 0)

            icon = "✓" if did_pass else "✗"
            css_class = "pass" if did_pass else "fail"

            html_parts.append(f'                <td class="result {css_class}">{icon}<span class="rate">{triggers}/{runs}</span></td>\n')

        # 为每个测试查询添加结果（不同背景色）
        for qinfo in test_queries:
            r = test_by_query.get(qinfo["query"], {})
            did_pass = r.get("pass", False)
            triggers = r.get("triggers", 0)
            runs = r.get("runs", 0)

            icon = "✓" if did_pass else "✗"
            css_class = "pass" if did_pass else "fail"

            html_parts.append(f'                <td class="result test-result {css_class}">{icon}<span class="rate">{triggers}/{runs}</span></td>\n')

        html_parts.append("            </tr>\n")

    html_parts.append("""        </tbody>
    </table>
    </div>
""")

    html_parts.append("""
</body>
</html>
""")

    return "".join(html_parts)


def main():
    parser = argparse.ArgumentParser(description="根据 run_loop 输出生成 HTML 报告")
    parser.add_argument("input", help="run_loop.py 的 JSON 输出路径（或 - 表示标准输入）")
    parser.add_argument("-o", "--output", default=None, help="输出的 HTML 文件（默认：标准输出）")
    parser.add_argument("--skill-name", default="", help="要显示在报告标题中的技能名称")
    args = parser.parse_args()

    ensure_utf8_stdio()

    if args.input == "-":
        data = json.load(sys.stdin)
    else:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))

    html_output = generate_html(data, skill_name=args.skill_name)

    if args.output:
        Path(args.output).write_text(html_output, encoding="utf-8")
        print(f"报告已写入：{args.output}", file=sys.stderr)
    else:
        print(html_output)


if __name__ == "__main__":
    main()
