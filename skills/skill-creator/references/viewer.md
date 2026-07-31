# 评测查看器说明

> 本文件为**低频参考**。仅在需要向用户展示评测结果、解读查看器界面时读取。
> 查看器的启动命令在 SKILL.md「运行评测」章节中。

`eval-viewer/generate_review.py` 生成评测查看页面，供用户审阅定性输出和定量指标。

## 启动方式

```bash
python <skill-creator-path>/eval-viewer/generate_review.py \
  <workspace>/iteration-N \
  --skill-name "my-skill" \
  --benchmark <workspace>/iteration-N/benchmark.json
```

- 迭代 2+ 时加 `--previous-workspace <workspace>/iteration-<N-1>`
- 无图形界面用 `--static <output_path>` 生成静态 HTML 文件（而非启动服务器）
- 反馈通过「提交全部审查」按钮保存：服务器模式写入 `feedback.json`，静态模式下载为 `feedback.json` 文件

## 「输出」标签页

一个测试用例一屏：

- **提示**：给定任务
- **输出**：技能输出（尽可能内联渲染）
- **上一轮输出**（迭代 2+）：上轮输出的折叠区域
- **正式评分**（有评分时）：断言通过/失败的折叠区域
- **你的反馈**：自动保存的文本框
- **上一轮反馈**（迭代 2+）：用户上次评论

## 「基准」标签页

- 通过率、耗时、token 按配置（with_skill / baseline）汇总
- 含每个 eval 的详细分析、均值 ± 标准差、差异值
- 每个 with_skill 版本排在 baseline 之前

## 导航与反馈

- 通过「上一个/下一个」按钮或方向键翻页
- 点击「提交全部审查」保存反馈到 `feedback.json`

## 查看 feedback.json

```json
{
  "reviews": [
    {"run_id": "eval-0-with_skill", "feedback": "图表缺少坐标轴标签", "timestamp": "..."},
    {"run_id": "eval-1-with_skill", "feedback": "", "timestamp": "..."}
  ],
  "status": "complete"
}
```

空反馈表示没问题，专注于有具体意见的测试用例改进。完成后关闭查看器（服务器模式 Ctrl+C）。

## 无图形/无浏览器环境

- 用 `--static` 生成独立 HTML 文件，将文件路径交给用户自行打开
- 用户完成后下载 `feedback.json`，将文件复制进 workspace 供下一轮使用
