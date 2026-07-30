---
name: skill-creator
description: >-
  创建新技能、修改优化已有技能、运行评测、分析技能表现、优化技能描述。
  当用户想从零创建技能、编辑优化已有技能、运行测试评测、做基准对比（含方差分析）、
  或优化技能描述以提高触发准确率时使用。
  也适用于用户询问"怎么写 SKILL.md"、"技能应该包含什么内容"。
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Task
  - Fleet
  - ReadFile
  - ReadSkill
  - RunSkill
  - WebFetch
  - Research
  - Review
---

# Skill Creator — 技能创建与优化

用于创建新技能并迭代优化已有技能。支持从需求调研、起草、测试、评估到打包的全流程。

---

## SKILL.md 内容原则

SKILL.md 是写给 AI 模型看的**使用说明书**，不是技术实现文档。

| 内容 | 说明 |
|---|---|
| 用途 | 这个技能能做什么、什么时候触发 |
| 环境要求 | 依赖的工具、库、系统环境 |
| API 签名 | 函数参数、返回值、参数说明 |
| 使用示例 | 典型调用方式，带代码或步骤 |
| 注意事项 | 使用层面的陷阱、边界情况 |
| 实现细节 | 代码内部逻辑、搜索路径、兜底机制等放在代码注释中 |

**关键原则：** 告诉模型「怎么用」，或者「调用的示例代码」，而不是告诉模型「技能代码和原理」。

---

## 核心流程

1. **确定需求** — 明确技能用途、触发时机、输出格式
2. **起草技能** — 编写 SKILL.md 及配套资源
3. **创建测试用例** — 编写真实场景的测试 prompt
4. **运行评测** — 同时跑带技能/不带技能的对比测试
5. **评估结果** — 查看输出、分析定量指标、收集反馈
6. **迭代优化** — 根据反馈修改技能，重复 3-6
7. **打包发布** — 优化描述后打包为 `.skill` 文件

---

## 一、创建技能

### 1. 确定需求

先理解用户意图。如果对话中已包含用户想捕捉的工作流（如"把这个做成技能"），从对话历史中提取：使用的工具、步骤顺序、用户的修正、输入/输出格式。用户可能需要补充遗漏信息，确认后再进入下一步。

- 这个技能让 AI 做什么？
- 什么情况下触发？（用户的哪些表达/上下文）
- 预期的输出格式是什么？
- 需要测试用例吗？客观可验证的输出（文件转换、数据提取、代码生成）适合测试用例；主观输出（写作风格、艺术创作）通常不需要。根据技能类型给建议，让用户决定。

### 2. 调研

主动询问边界情况、输入输出格式、示例文件、成功标准、依赖项。确认后再写测试 prompt。

如果有可用 MCP，并行搜索文档或类似技能作为参考。带着上下文来，减少用户负担。

### 3. 起草 SKILL.md

根据用户调研，填充以下内容：

- **name**：技能标识符，小写字母加连字符
- **description**：触发机制的核心。写清楚技能做什么以及具体的触发场景。当前 AI 模型有"触发不足"的倾向——需要时却不使用技能。为此让描述稍微"强势"一点。例如不要写"如何构建简单仪表盘"，而是写"当用户提到仪表盘、数据可视化、内部指标时务必使用此技能，即使没有明确说'dashboard'一词"
- 正文：按上述内容原则组织

#### 技能目录结构

```
skill-name/
├── SKILL.md（必需）
│   ├── YAML frontmatter（name、description 必需）
│   └── Markdown 指令
├── scripts/     - 可执行脚本（确定性/重复性任务）
├── references/  - 按需加载的文档
└── assets/      - 输出用资源（模板、图标、字体等）
```

#### 渐进式加载

技能使用三层加载机制：
1. **元数据**（name + description）— 始终在上下文中
2. **SKILL.md 正文** — 触发时加载（建议 <500 行）
3. **附带资源** — 按需加载（无限制）

正文接近 500 行时，拆分到 `references/` 并添加目录索引。大文件（>300 行）也要提供目录索引。多领域技能按变体组织：

```
cloud-deploy/
├── SKILL.md（工作流 + 选择逻辑）
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```

#### 编写要点

- 使用**祈使句**
- 解释"为什么"重要，而不是生硬地堆砌"必须"
- 包含具体**示例**（输入 → 输出）
- 输出格式用**模板**明确定义
- 先写草稿，再以全新视角审视改进
- 代码、命令、文件路径保持原文

#### 不意外原则

技能不得包含恶意代码或危害安全的内容。不要参与创建误导性或用于未授权访问的技能。

### 4. 测试用例

写完初稿后，编写 2-3 个真实场景的测试 prompt。与用户确认后再运行。

保存到 `evals/evals.json`，暂不写断言：

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "用户的测试任务",
      "expected_output": "预期结果描述",
      "files": []
    }
  ]
}
```

完整 schema 见 `references/schemas.md`（含 `assertions` 字段，下一步添加）。

---

## 二、运行评测

> 这是连续流程，不要中途停下。不要使用其他测试工具。

结果放在 `<skill-name>-workspace/` 目录（与技能目录同级）。按迭代组织（`iteration-1/`、`iteration-2/`...），每个测试用例一个子目录（`eval-0/`、`eval-1/`...）。运行时逐步创建。

### 第 1 步：同轮次并行启动所有运行

每个测试用例同时启动两个子任务——**带技能**和**基准**。不要先跑带技能的再补基准，一次全部启动。

**带技能运行：**
```
执行任务：
- 技能路径：<path-to-skill>
- 任务：<eval prompt>
- 输入文件：<eval files if any, or "none">
- 输出保存到：<workspace>/iteration-<N>/eval-<ID>/with_skill/outputs/
- 保存内容：<用户关心的输出>
```

**基准运行：**
- **创建新技能**：不带任何技能，保存到 `without_skill/outputs/`
- **优化已有技能**：编辑前快照（`cp -r <skill-path> <workspace>/skill-snapshot/`），基准指向快照，保存到 `old_skill/outputs/`

每个测试用例写 `eval_metadata.json`（断言暂空），用描述性名称而非 `eval-0`：

```json
{
  "eval_id": 0,
  "eval_name": "描述性名称",
  "prompt": "测试 prompt",
  "assertions": []
}
```

### 第 2 步：测试运行时撰写断言

不等空等——这段时间撰写定量断言并向用户解释。已有断言则审查并说明。

好断言**客观可验证**且有**描述性名称**。主观类技能（写作风格、设计）适合定性评估，不强行写断言。

更新 `eval_metadata.json` 和 `evals/evals.json`。告知用户 viewer 中会看到什么。

### 第 3 步：测试完成时保存计时数据

子任务完成时，立即保存 `total_tokens` 和 `duration_ms` 到 `timing.json`：

```json
{
  "total_tokens": 84852,
  "duration_ms": 23332,
  "total_duration_seconds": 23.3
}
```

这是唯一保存机会——通知不持久化。每个通知到达立即处理。

### 第 4 步：评分、汇总、启动查看器

1. **评分** — 逐条判断断言是否通过，保存到各运行目录的 `grading.json`。`expectations` 数组必须使用 `text`、`passed`、`evidence` 字段（非 `name`/`met`/`details`）。可用脚本自动检查的优先写脚本。

2. **汇总 benchmark** —
   ```bash
   python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
   ```
   生成 `benchmark.json` 和 `benchmark.md`，包含通过率、耗时、token 的均值±标准差和差值。每个 with_skill 版本放在 baseline 之前。

3. **分析** — 阅读 benchmark 数据，找出汇总统计可能隐藏的模式：总是通过的断言（无区分度）、高方差评测（可能不稳定）、时间/token 权衡。

4. **启动查看器**：
   ```bash
   nohup python <skill-creator-path>/eval-viewer/generate_review.py \
     <workspace>/iteration-N \
     --skill-name "my-skill" \
     --benchmark <workspace>/iteration-N/benchmark.json \
     > /dev/null 2>&1 &
   VIEWER_PID=$!
   ```
   迭代 2+ 时加 `--previous-workspace`。无图形界面用 `--static <output_path>` 生成 HTML 文件。

5. **告知用户**："结果已打开。'Outputs' 标签页查看输出并留反馈，'Benchmark' 展示定量对比。"

#### 查看器说明

**Outputs 标签页：**
- **Prompt**：给定任务
- **Output**：技能输出（尽可能内联渲染）
- **Previous Output**（迭代 2+）：上轮输出的折叠区域
- **Formal Grades**（有评分时）：断言通过/失败的折叠区域
- **Feedback**：自动保存的文本框
- **Previous Feedback**（迭代 2+）：用户上次评论

**Benchmark 标签页：** 通过率、耗时、token 按配置汇总，含每个 eval 的详细分析。

通过方向键或按钮翻页。点击 "Submit All Reviews" 保存反馈到 `feedback.json`。

### 第 5 步：阅读反馈

```json
{
  "reviews": [
    {"run_id": "eval-0-with_skill", "feedback": "图表缺少坐标轴标签", "timestamp": "..."},
    {"run_id": "eval-1-with_skill", "feedback": "", "timestamp": "..."}
  ],
  "status": "complete"
}
```

空反馈表示没问题，专注于有具体意见的测试用例改进。完成后关闭查看器：`kill $VIEWER_PID 2>/dev/null`。

---

## 三、优化技能

### 改进思路

1. **从反馈中泛化**。技能要能用于大量不同场景，而非仅适配几个测试用例。与其做琐碎的过拟合修改或严苛的"必须"，不如尝试不同思路或工作模式。

2. **保持精简**。去掉不发挥作用的内容。阅读完整执行记录——如果技能让模型浪费时间做低效的事，去掉导致这些行为的指令。

3. **解释原因**。解释每项指令背后的**为什么**。如果发现自己用全大写的 ALWAYS/NEVER 或极端僵化的结构，这是警告信号——重新组织语言，让模型理解要求的重要性。

4. **识别重复工作**。阅读测试记录，观察子任务是否都写了相似的辅助脚本。如果多个测试都写了 `create_docx.py` 或 `build_chart.py`，技能应该内置该脚本，放在 `scripts/` 中。

### 迭代循环

1. 应用改进
2. 重新运行所有测试到新目录，含基准。创建新技能时基准始终是 `without_skill`；优化已有技能时根据判断选择基准
3. 用 `--previous-workspace` 启动查看器
4. 等待用户审查
5. 读反馈，再改进，重复

持续直到用户满意、反馈全空、或无实质进展。

### 进阶：盲比

需要更严格的版本对比时，可用盲比系统（详见 `agents/comparator.md` 和 `agents/analyzer.md`）。给独立 agent 两个输出，不告知版本信息，让其评判质量。

可选功能，需要子任务支持。

---

## 四、描述优化

description 字段是触发机制的核心。技能内容完善后，可优化描述提高触发准确率。

### 第 1 步：生成触发评测查询

创建 20 条混合应触发/不应触发的查询：

```json
[
  {"query": "用户 prompt", "should_trigger": true},
  {"query": "另一个 prompt", "should_trigger": false}
]
```

查询必须**真实**——包含文件路径、用户背景、列名、公司名、URL 等细节。混合不同长度、大小写、口语化表达。关注边界情况。

不好的例子：`"格式化数据"`、`"从 PDF 提取文本"`
好的例子：`"老板发了个 xlsx 文件想加一列利润率百分比"`

**应触发**（8-10 条）：覆盖不同表述方式——正式的、随意的，包含不直接提技能名但明显需要的场景。
**不应触发**（8-10 条）：最有价值的是"接近但不同"的场景——共享关键词但实际需求不同。

### 第 2 步：用户确认

使用 `assets/eval_review.html` 模板展示给用户确认。替换 `__EVAL_DATA_PLACEHOLDER__`、`__SKILL_NAME_PLACEHOLDER__`、`__SKILL_DESCRIPTION_PLACEHOLDER__`。用户可编辑查询、切换应触发/不应触发、增删条目，然后导出。

### 第 3 步：运行优化循环

```bash
python -m scripts.run_loop \
  --eval-set <path-to-trigger-eval.json> \
  --skill-path <path-to-skill> \
  --model <当前模型 ID> \
  --max-iterations 5 \
  --verbose
```

将评测集分为 60% 训练 / 40% 测试，评估当前描述（每条 3 次取可靠触发率），基于失败案例提出改进，在训练和测试集上重新评估，最多 5 轮。用测试分数选择最佳描述以避免过拟合。

### 第 4 步：应用结果

取 `best_description` 更新 frontmatter，展示前后对比和分数。

---

## 五、打包

```bash
python -m scripts.package_skill <path/to/skill-folder>
```

打包后交付 `.skill` 文件供安装。保留原名（如原技能是 `research-helper`，输出 `research-helper.skill`）。先复制到可写位置再编辑。

---

## 参考文件

按需读取：

- `agents/grader.md` — 评分指令
- `agents/comparator.md` — 盲比 A/B 比较
- `agents/analyzer.md` — 分析 benchmark 结果
- `references/schemas.md` — 各 JSON 结构定义
- `assets/eval_review.html` — 评测查询审查模板
- `eval-viewer/generate_review.py` — 评测查看器生成脚本

## 脚本

```bash
# 汇总 benchmark
python scripts/aggregate_benchmark.py <workspace>/iteration-N --skill-name <name>

# 生成评测报告
python scripts/generate_report.py

# 优化技能描述
python scripts/improve_description.py <skill-path>/SKILL.md

# 打包技能
python scripts/package_skill.py <skill-path> --output <output-dir>

# 快速验证
python scripts/quick_validate.py

# 运行单次评测
python scripts/run_eval.py

# 运行优化循环
python scripts/run_loop.py
```
