# ims-metagpt

> 基于 MetaGPT 的多 Agent 软件团队 — **完整的软件生命周期管理工具**。
> 从 MVP 到迭代到重构，全流程 AI 辅助 + 人工审核。

---

## 快速开始

```bash
# 1. 安装依赖
pip install metagpt
pip install -e .

# 2. 配置 LLM
cp .env.example .env
# 编辑 .env，填入你的 API Key

# 3. 初始化 MetaGPT 配置
ims-metagpt init-config
```

---

## 完整工程化流程（推荐）

这是**标准的软件交付流程**，每个阶段都有人工审核环节，确保质量和可控性。

```
  ┌─────────────────────────────────────────────────────────┐
  │  ① plan: 生成需求文档 → 人工审核修改 → 确认              │
  │         ↓                                               │
  │  ② design: 生成架构设计 → 人工审核修改 → 确认            │
  │         ↓                                               │
  │  ③ code: 生成 MVP 代码 → 测试 → 部署上线                 │
  │         ↓                                               │
  │  ④ iterate: 迭代增加功能 → 审查 diff → 确认              │
  │         ↓                                               │
  │  ⑤ refactor: 重构优化代码 → 审查 diff → 确认             │
  └─────────────────────────────────────────────────────────┘
```

### Step 1：生成需求文档（PRD）→ 人工审核

```bash
ims-metagpt plan "生成一个进销存管理系统，先做商品管理和库存管理" -o ./my-ims
```

**AI 产出：**
- `./my-ims/docs/task-plan.md` — 任务规划（需求拆解)
- `./my-ims/docs/prd.md` — 产品需求文档

**你需要做的：**
1. 打开 `./my-ims/docs/prd.md`
2. 检查功能清单是否完整，修改遗漏或偏差
3. 确认无误后进入下一步

### Step 2：生成架构设计 → 人工审核

```bash
ims-metagpt design -w ./my-ims
```

**AI 产出：**
- `./my-ims/docs/design.md` — 系统架构设计（技术栈、ER 图、API 路由、前端组件)

**你需要做的：**
1. 打开 `./my-ims/docs/design.md`
2. 检查技术选型是否合理，数据模型是否完整
3. 确认无误后进入下一步

### Step 3：生成 MVP 代码

```bash
ims-metagpt code -w ./my-ims --scope mvp
```

**AI 产出：**
- `./my-ims/backend/` — 后端代码
- `./my-ims/frontend/` — 前端页面
- `./my-ims/tests/` — 测试用例

**启动验证：**
```bash
cd ./my-ims/backend
pip install -r requirements.txt
python run.py
```

### Step 4：迭代增加功能

MVP 上线后，需要增加新功能：

```bash
ims-metagpt iterate "增加采购管理模块，含采购单创建和入库审核" -w ./my-ims
```

**AI 产出：**
- `./my-ims/changes_0.md` — 增量变更 diff

**你需要做的：**
1. 审查变更文件，确认修改范围和影响
2. 将变更应用到代码

### Step 5：重构优化

代码累积了技术债务，需要重构：

```bash
ims-metagpt refactor "提取公共 CRUD 基类，统一错误处理" -w ./my-ims
```

---

## 命令详解

### `ims-metagpt plan <IDEA> [选项]`

**用途**：MVP 流程的第一步，生成需求文档供人工审核。

| 参数 | 简写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `IDEA` | — | ✅ | — | 你的需求描述。例如：`"生成一个进销存系统，支持商品管理"` |
| `--output` | `-o` | ❌ | `./ims-output` | 输出目录。所有生成的文件都保存到这里 |
| `--plan-only` | — | ❌ | `false` | 仅生成任务规划，不生成 PRD。用于快速确认需求理解是否正确 |
| `--auto` | — | ❌ | `false` | 自动模式：跳过人工审核提示，生成完即结束（快速原型用） |
| `--n-round` | — | ❌ | `10` | 最大运行轮次。生成内容不完整时可适当增大 |

**使用场景示例：**
```bash
# 标准用法
ims-metagpt plan "生成进销存系统，支持商品管理、采购销售、库存管理" -o ./my-ims

# 仅看任务规划（确认 AI 理解正确）
ims-metagpt plan "帮我分析进销存系统需要哪些功能" -o ./preview --plan-only

# 快速生成（跳过审核提醒）
ims-metagpt plan "生成博客系统" -o ./blog --auto
```

---

### `ims-metagpt design --workspace <路径> [选项]`

**用途**：基于已确认的 PRD，生成系统架构设计供人工审核。

| 参数 | 简写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--workspace` | `-w` | ✅ | — | 项目工作区路径（即 plan 命令的 `-o` 参数） |
| `--auto` | — | ❌ | `false` | 自动模式 |
| `--n-round` | — | ❌ | `10` | 最大运行轮次 |

**前置条件**：`workspace/docs/prd.md` 必须存在（由 `plan` 命令生成）。

**使用场景示例：**
```bash
# 标准用法（PRD 确认后）
ims-metagpt design -w ./my-ims

# 快速模式
ims-metagpt design -w ./my-ims --auto
```

---

### `ims-metagpt code --workspace <路径> [选项]`

**用途**：基于已确认的设计，生成可运行的代码。

| 参数 | 简写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--workspace` | `-w` | ✅ | — | 项目工作区路径 |
| `--scope` | `-s` | ❌ | `mvp` | 生成范围：`mvp`（仅核心功能）或 `full`（全部功能） |
| `--mode` | `-m` | ❌ | `full` | 生成模式：`full`（全栈）、`backend-only`（仅后端）、`frontend-only`（仅前端） |
| `--n-round` | — | ❌ | `15` | 最大运行轮次。full 模式建议 20-30 |

**前置条件**：`workspace/docs/design.md` 必须存在（由 `design` 命令生成）。

**使用场景示例：**
```bash
# 首次 MVP（推荐）
ims-metagpt code -w ./my-ims --scope mvp

# 仅生成后端代码（配合已有前端）
ims-metagpt code -w ./my-ims --scope full --mode backend-only

# 生成完整版
ims-metagpt code -w ./my-ims --scope full --n-round 25
```

---

### `ims-metagpt iterate <IDEA> --workspace <路径> [选项]`

**用途**：在已有代码基础上，增量增加新功能。

| 参数 | 简写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `IDEA` | — | ✅ | — | 新增功能描述。例如：`"增加采购管理模块"` |
| `--workspace` | `-w` | ✅ | — | 已有代码所在的项目路径 |
| `--n-round` | — | ❌ | `15` | 最大运行轮次 |

**使用场景示例：**
```bash
# MVP 上线后增加采购管理
ims-metagpt iterate "增加采购管理模块，含采购单创建和入库" -w ./my-ims

# 增加报表统计
ims-metagpt iterate "增加销售趋势图表和库存报表" -w ./my-ims
```

---

### `ims-metagpt refactor <IDEA> --workspace <路径> [选项]`

**用途**：对已有代码进行重构优化。

| 参数 | 简写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `IDEA` | — | ✅ | — | 重构目标描述。例如：`"提取公共 CRUD 基类"` |
| `--workspace` | `-w` | ✅ | — | 项目路径 |
| `--n-round` | — | ❌ | `15` | 最大运行轮次 |

**使用场景示例：**
```bash
# 减少重复代码
ims-metagpt refactor "提取公共 CRUD 基类，减少重复代码" -w ./my-ims

# 统一错误处理
ims-metagpt refactor "统一错误处理中间件，添加请求日志" -w ./my-ims
```

---

### `ims-metagpt list-modes`

显示所有命令的速查表。

### `ims-metagpt init-config`

初始化 MetaGPT 配置文件到 `~/.metagpt/config2.yaml`。

---

## 架构概览

### SOP 流程

```
用户需求
  │
  ▼ [plan]
TeamLeader (Mike) → 任务规划
  │
  ▼
ProductManager (Alice) → PRD  →  人工审核
  │
  ▼ [design]
Architect (Bob) → 架构设计  →  人工审核
  │
  ▼ [code]
Engineer (Eve) → 后端代码 → 前端代码 → 测试代码
  │
  ▼ [iterate] / [refactor]
Engineer (Eve) → 增量变更 diff
```

### 目录结构

```
ims-metagpt/
├── README.md
├── TUTORIAL.md                      # 学习教程（新手必读）
├── pyproject.toml
├── config/config2.yaml              # LLM 配置（多厂商示例）
├── src/ims_metagpt/
│   ├── main.py                      # CLI 入口（5 个子命令）
│   ├── roles/
│   │   ├── ims_team_leader.py       # 项目经理
│   │   ├── ims_product_manager.py   # 产品经理
│   │   ├── ims_architect.py         # 架构师
│   │   └── ims_engineer.py          # 全栈工程师
│   ├── actions/
│   │   ├── plan_tasks.py            # 任务分解
│   │   ├── write_prd.py             # 写 PRD
│   │   ├── write_design.py          # 写设计
│   │   ├── write_backend.py         # 写后端
│   │   ├── write_frontend.py        # 写前端
│   │   ├── write_tests.py           # 写测试
│   │   └── write_change_plan.py     # 增量变更规划
│   └── prompts/
│       ├── task_planning.py
│       ├── prd.py
│       ├── design.py
│       ├── backend_code.py
│       ├── frontend_code.py
│       └── test_code.py
└── tests/
```

---

## 学习资源

- **新手必读**：[TUTORIAL.md](TUTORIAL.md) — 六章教程，从 MetaGPT 概念到完整工程化流程
- **框架源码**：`MetaGPT/metagpt/` — 工作区中已有 MetaGPT 源码供参考
- **官方文档**：https://docs.deepwisdom.ai/
