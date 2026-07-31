---
name: skill-creator
description: >-
  创建新技能、修改优化已有技能、运行评测、分析技能表现、优化技能描述。
  当用户想从零创建技能、编辑优化已有技能、运行测试评测、做基准对比（含方差分析）、
  或优化技能描述以提高触发准确率时使用。
  也适用于用户询问"怎么写 SKILL.md"、"技能应该包含什么内容"。
license: Apache-2.0
metadata:
  version: "2.1.0"
allowed-tools: Read Write Edit Bash Glob Grep Task Fleet ReadFile ReadSkill RunSkill WebFetch Research Review
---

# Skill Creator — 技能创建与优化

用于创建新技能并迭代优化已有技能。支持从需求调研、起草、测试、评估到交付的全流程。

> **高频路径 vs 低频参考**：本文件只包含核心流程。描述优化、打包分发、查看器界面细节、
> 盲比等**低频场景**已下沉到 `references/`，按需加载（见文末「参考文件」）。
> 创建简单零依赖技能且无需分发时，只需本文件的「创建技能」章节，其余都用不上。

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

### 语言约定

使用本工具创建或修改技能时，**默认语言为简体中文**，适用于：

- **SKILL.md 正文**：指令、说明、示例、注意事项
- **代码注释**：脚本、模板中的注释和文档字符串
- **用户交互文本**：CLI 输出、报错信息、界面文案、网页 UI
- **各类文档**：README、操作手册、参考文档、变更记录等

保留原文的例外：代码标识符（变量名、函数名、类名等）保持英文；技术术语（YAML、API、kebab-case 等）可保留原文；发给 LLM 的 prompt 文本不受此限，按需使用。

> 本工具链自身已遵循此约定：脚本注释、CLI 输出、评测报告、HTML 查看器均为简体中文。

> 依赖声明约定：新技能的依赖**不强制** requirements.txt —— 依赖什么语言就声明什么，写在 frontmatter 的 `compatibility` 字段（≤500 字符，如 `Requires Python 3.14+ and uv`）或 SKILL.md 正文「环境要求」节。requirements.txt 仅用于本技能（skill-creator）自身工具链的运行时依赖。

---

## 核心流程

1. **确定需求** — 明确技能用途、触发时机、输出格式
2. **起草技能** — 编写 SKILL.md 及配套资源
3. **创建测试用例** — 编写真实场景的测试 prompt
4. **运行评测** — 同时跑带技能/不带技能的对比测试
5. **评估结果** — 查看输出、分析定量指标、收集反馈
6. **迭代优化** — 根据反馈修改技能，重复 3-6
7. **交付** — 目录即技能，直接可用；需要单文件分发才打包（见 references/packaging.md）

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

- **name**：技能标识符，小写字母加连字符，**必须与技能目录名一致**（规范要求），最长 64 字符
- **description**：触发机制的核心。写清楚技能做什么以及具体的触发场景，最长 1024 字符。当前 AI 模型有"触发不足"的倾向——需要时却不使用技能。为此让描述稍微"强势"一点。例如不要写"如何构建简单仪表盘"，而是写"当用户提到仪表盘、数据可视化、内部指标时务必使用此技能，即使没有明确说'dashboard'一词"
- **allowed-tools**（可选）：空格分隔的预授权工具字符串，如 `allowed-tools: Read Write Bash(git:*)`。规范要求是字符串而非 YAML 列表
- **license**（可选）：开源许可证名或指向打包 LICENSE 文件的引用
- **compatibility**（可选）：环境要求，最长 500 字符（如 `Requires Python 3.14+ and uv`）
- 正文：按上述内容原则组织

**起草完成后，必须运行验证**：

```bash
python -m scripts.quick_validate <skill-path>
```

验证不通过（如 name 与目录名不符、description 为空或超长、frontmatter 含非法字段）则修正后重新验证，通过后才可进入测试用例环节。

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
2. **SKILL.md 正文** — 触发时加载（建议 <500 行 / <5000 tokens）
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

完整 schema 见 `references/schemas.md`（含 `expectations` 字段，下一步添加）。

**evals.json 受 `quick_validate` 强制校验**：`skill_name` 必须与 frontmatter `name` 一致，每条 eval 必须含 `id`/`prompt`/`expected_output`，`files`/`expectations` 必须为字符串列表；schema 之外的字段（如 `name`/`steps`）会产生警告。字段缺失或不一致时验证不通过，禁止进入评测。

---

## 二、运行评测

> 这是连续流程，不要中途停下。不要使用其他测试工具。

结果放在 `<skill-name>-workspace/` 目录（与技能目录同级）。按迭代组织（`iteration-1/`、`iteration-2/`...），每个测试用例一个子目录（`eval-0/`、`eval-1/`...）。运行时逐步创建。

目录结构约定（`aggregate_benchmark` 与查看器按此发现运行）：

```
<skill-name>-workspace/iteration-N/
└── eval-<ID>/
    ├── eval_metadata.json
    └── <config>/                # with_skill / without_skill（或 new_skill / old_skill）
        ├── grading.json         # 布局 A：单次运行直接放在 config 目录下
        ├── outputs/…            # 输出文件
        └── run-1/grading.json   # 布局 B：多次运行时用 run-N/ 子目录
```

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

每个测试用例写 `eval_metadata.json`（expectations 暂空），用描述性名称而非 `eval-0`：

```json
{
  "eval_id": 0,
  "eval_name": "描述性名称",
  "prompt": "测试 prompt",
  "expectations": []
}
```

### 第 2 步：测试运行时撰写断言

不等空等——这段时间撰写定量断言并向用户解释。已有断言则审查并说明。

好断言**客观可验证**且有**描述性名称**。主观类技能（写作风格、设计）适合定性评估，不强行写断言。

更新 `eval_metadata.json` 和 `evals/evals.json`。告知用户查看器中会看到什么（详见 `references/viewer.md`）。

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

1. **评分** — 逐条判断断言是否通过，保存到各运行目录的 `grading.json`（单次运行放 `config/` 下，多次运行放 `config/run-N/` 下，见上文目录结构）。`expectations` 数组必须使用 `text`、`passed`、`evidence` 字段（非 `name`/`met`/`details`）。可用脚本自动检查的优先写脚本。

2. **汇总 benchmark** —
   ```bash
   python -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>
   ```
   生成 `benchmark.json` 和 `benchmark.md`，包含通过率、耗时、token 的均值±标准差和差值。每个 with_skill 版本放在 baseline 之前。

3. **分析** — 阅读 benchmark 数据，找出汇总统计可能隐藏的模式：总是通过的断言（无区分度）、高方差评测（可能不稳定）、时间/token 权衡。详见 `references/advanced.md`。

4. **启动查看器**：
   ```bash
   python <skill-creator-path>/eval-viewer/generate_review.py \
     <workspace>/iteration-N \
     --skill-name "my-skill" \
     --benchmark <workspace>/iteration-N/benchmark.json
   ```
   迭代 2+ 时加 `--previous-workspace`。无图形界面用 `--static <output_path>` 生成静态 HTML 文件。界面各标签页的详细说明见 `references/viewer.md`。

5. **告知用户**："结果已打开。'Outputs' 标签页查看输出并留反馈，'Benchmark' 展示定量对比。"

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

空反馈表示没问题，专注于有具体意见的测试用例改进。完成后关闭查看器（服务器模式 Ctrl+C）。

---

## 三、优化技能

这是整个循环的核心：基于反馈让技能更好。

### 迭代循环

1. 应用改进
2. 重新运行所有测试到新目录，含基准。创建新技能时基准始终是 `without_skill`；优化已有技能时根据判断选择基准
3. 用 `--previous-workspace` 启动查看器
4. 等待用户审查
5. 读反馈，再改进，重复

持续直到用户满意、反馈全空、或无实质进展。

### 改进思路

1. **从反馈中泛化**。技能要能用于大量不同场景，而非仅适配几个测试用例。与其做琐碎的过拟合修改或严苛的"必须"，不如尝试不同思路或工作模式。
2. **保持精简**。去掉不发挥作用的内容。阅读完整执行记录——如果技能让模型浪费时间做低效的事，去掉导致这些行为的指令。
3. **解释原因**。解释每项指令背后的**为什么**。如果发现自己用全大写的 ALWAYS/NEVER 或极端僵化的结构，这是警告信号——重新组织语言，让模型理解要求的重要性。
4. **识别重复工作**。阅读测试记录，观察子任务是否都写了相似的辅助脚本。如果多个测试都写了 `create_docx.py` 或 `build_chart.py`，技能应该内置该脚本，放在 `scripts/` 中。

### 严格对比（可选）

需要更严格的版本对比（如"新版本真的更好吗？"）时，可用盲比系统——给独立 agent 两个输出，不告知版本信息，让其评判质量。详见 `references/advanced.md`。可选功能，需要子任务支持。

---

## 低频场景指引

以下场景按需读取对应参考文件，**不要主动加载**：

| 场景 | 参考文件 |
|---|---|
| 优化 description 触发准确率 | `references/description-optimization.md` |
| 打包为 `.skill` 单文件分发 | `references/packaging.md` |
| 查看器各标签页详细说明 | `references/viewer.md` |
| 盲比 / 分析 benchmark 模式 | `references/advanced.md` |
| 评测后端可插拔扩展（新 runner） | `references/runners.md` |

## 参考文件

按需读取：

- `references/schemas.md` — 各 JSON 结构定义（evals.json、grading.json、benchmark.json 等）
- `references/runners.md` — 评测后端可插拔架构与扩展指南
- `references/packaging.md` — 打包与脚本命令速查
- `references/description-optimization.md` — 描述优化完整流程
- `references/viewer.md` — 评测查看器界面说明
- `references/advanced.md` — 盲比与 benchmark 分析进阶
- `agents/grader.md` — 评分指令
- `agents/comparator.md` — 盲比 A/B 比较
- `agents/analyzer.md` — 分析 benchmark 结果
- `assets/eval_review.html` — 评测查询审查模板
- `eval-viewer/generate_review.py` — 评测查看器生成脚本

> 环境：依赖先 `pip install -r requirements.txt`（仅 PyYAML）。
> 测试：`python -m unittest discover -s tests`（无需额外安装）。
