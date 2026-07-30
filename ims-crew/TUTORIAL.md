# 使用 CrewAI 模拟软件团队构建进销存管理系统

> 实践指南：通过 CrewAI 多 Agent 协作，从零生成一个面向中小商户的进销存管理系统（Inventory Management System）的完整代码。
>
> **关键设计决策**：所有 Agent/Task 提示词以 `.md` 文件独立管理，与 Python 代码完全解耦，便于后期维护和复用。

---

## 目录

1. [整体架构](#1-整体架构)
2. [项目结构（实际实现）](#2-项目结构实际实现)
3. [安装与配置](#3-安装与配置)
4. [提示词体系（prompts/）](#4-提示词体系-prompts)
5. [Prompt Loader 层](#5-prompt-loader-层)
6. [Crew 装配（crew.py）](#6-crew-装配-crewpy)
7. [入口与运行](#7-入口与运行)
8. [团队 Profile 配置](#8-团队-profile-配置)
9. [后处理与自修复管线](#9-后处理与自修复管线)
10. [运行效果与产出](#10-运行效果与产出)
11. [进阶扩展](#11-进阶扩展)

---

## 1. 整体架构

### 团队角色设计

我们模拟一个 **6 人软件团队**，按顺序执行：

```
 Product Manager (需求分析)
        ↓
   Architect (系统设计)
        ↓
  ┌────┴────┐
Backend Dev  Frontend Dev  (并行执行，通过 context 共享架构产出)
  └────┬────┘
        ↓
  QA Engineer (测试验证)
        ↓
  DevOps Engineer (部署配置)
```

| 角色 | 职责 | 提示词文件 |
|------|------|-----------|
| **Product Manager** | 分析需求，编写 PRD，定义功能列表 | `prompts/agents/product_manager.md` |
| **Architect** | 技术选型，数据库设计，API 设计 | `prompts/agents/architect.md` |
| **Backend Developer** | 实现 FastAPI 后端，数据库模型，API 路由 | `prompts/agents/backend_developer.md` |
| **Frontend Developer** | 实现管理后台界面（纯 HTML/CSS/JS） | `prompts/agents/frontend_developer.md` |
| **QA Engineer** | 编写测试，代码审查，质量验证 | `prompts/agents/qa_engineer.md` |
| **DevOps Engineer** | Docker 化，部署脚本，CI 配置 | `prompts/agents/devops_engineer.md` |

### 核心设计原则

```
┌──────────────────────────────────────────────────┐
│                  prompts/                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ agents/  │  │  tasks/  │  │ requirements/│    │
│  │ *.md     │  │ *.md     │  │ *.md         │    │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘    │
│       │              │               │             │
└───────┼──────────────┼───────────────┼─────────────┘
        │              │               │
        ▼              ▼               ▼
┌──────────────────────────────────────────────┐
│              prompt_loader.py                  │
│          (Markdown → Python dict)              │
└───────────────────┬──────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────┐
│                crew.py                         │
│   (Agent/Task 装配 + Profile 选择 + Crew)     │
└──────────────────────────────────────────────┘
```

**关键优势**：
- 提示词与代码完全分离，非技术人员可直接修改 `.md` 文件调整 Agent 行为
- 相同的提示词文件可被不同项目复用
- 支持中英文等多语言提示词（每个 `.md` 文件独立）

---

## 2. 项目结构（实际实现）

```
ims-crew/
├── .env.example                  # 环境变量模板
├── pyproject.toml                # 项目依赖与入口配置
├── README.md                     # 端用户使用说明
├── crewai-ims-tutorial.md        # 本教程文档
│
├── prompts/                      # ⭐ 所有提示词独立存放（核心设计）
│   ├── agents/                   # Agent 角色定义
│   │   ├── product_manager.md
│   │   ├── architect.md
│   │   ├── backend_developer.md
│   │   ├── frontend_developer.md
│   │   ├── qa_engineer.md
│   │   └── devops_engineer.md
│   ├── tasks/                    # Task 任务描述
│   │   ├── requirement_analysis.md
│   │   ├── system_design.md
│   │   ├── backend_development.md
│   │   ├── frontend_development.md
│   │   ├── testing.md
│   │   └── deployment.md
│   └── requirements/             # 产品需求规格
│       └── ims-requirements.md
│
├── src/
│   └── ims_crew/
│       ├── __init__.py           # 包元信息
│       ├── main.py               # CLI 入口（argparse）
│       ├── crew.py               # Crew 装配（核心）
│       ├── prompt_loader.py      # Markdown → Python dict 加载器
│       ├── tools.py              # 代码质量/API 验证工具
│       ├── config/
│       │   └── profiles.yaml     # 团队 Profile 配置
│       └── fixers/
│           ├── __init__.py
│           └── post_gen_fixes.py # 生成后自动修复管线
│
├── output/                       # 运行产物（文档）
└── project/                      # 运行产物（生成的应用代码）
```

**和原始模板的主要区别**：
1. ✅ 新增 `prompts/` 目录 — 所有提示词独立为 `.md` 文件
2. ✅ 新增 `prompt_loader.py` — 负责将 Markdown 文件解析为结构化字典
3. ✅ 新增 `config/profiles.yaml` — 团队 Profile 支持（full / backend-only / prototype）
4. ✅ Python 代码中不含任何提示词文本字符串
5. ✅ YAML 配置仅用于 metadata 和工具配置，不含角色/任务内容

---

## 3. 安装与配置

### 3.1 初始化项目

```bash
cd ims-crew
# 使用 uv（推荐）或 pip
uv init
uv add crewai crewai-tools pyyaml
```

### 3.2 pyproject.toml

```toml
[project]
name = "ims-crew"
version = "0.2.0"
description = "CrewAI 多 Agent 软件团队 — 自动生成进销存管理系统"
requires-python = ">=3.11"
dependencies = [
    "crewai>=0.100.0",
    "crewai-tools>=0.0.10",
]

[project.scripts]
ims-crew = "ims_crew.main:run"
ims-train = "ims_crew.main:train"

[tool.setuptools.packages.find]
where = ["src"]
```

### 3.3 .env.example

```bash
OPENAI_API_KEY=your_openai_api_key_here
# 或者使用其他 LLM（通过 LiteLLM）
# ANTHROPIC_API_KEY=your_anthropic_api_key
# MODEL_NAME=gpt-4o
```

---

## 4. 提示词体系（prompts/）

### 4.1 文件格式约定

每个 `.md` 文件使用 Markdown 标题结构：

```markdown
# {文件名标题}

## {节名称}    ← 使用 ## 二级标题作为 Key
{节内容}
```

### 4.2 Agent 文件结构（示例）

**`prompts/agents/backend_developer.md`**:
```markdown
# Agent: 后端开发工程师 (Backend Developer)

## Role
后端开发工程师 (Backend Developer)

## Goal
根据架构设计文档和数据库模型，实现完整、可运行的后端 API 系统...

## Backstory
你是一位熟练的 Python 后端开发工程师，专注于 FastAPI 框架开发...
```

### 4.3 Task 文件结构（示例）

**`prompts/tasks/backend_development.md`**:
```markdown
# Task: 后端 API 开发

## Description
基于架构设计文档和数据库模型（见前序产出），实现完整的后端 API 代码...
### 需要创建的文件结构
...

## Expected Output
完整的后端 FastAPI 项目...

## 自检要求（输出前请确认）
1. 所有文件是否已创建并写入完整内容
...
```

### 4.4 设计原则

- **每个角色/任务一个独立文件** — 方便单独修改和复用
- **文件注入取代模板变量** — 前序任务产出文件通过代码自动读取并注入到 Task description（取代旧的 `{variable}` 模板变量机制）
- **每个 Task 含自检清单** — 输出前 LLM 自行验证文件完整性、语法正确性
- **纯文本无代码** — `.md` 文件中不含 Python 代码，非技术人员可直接编辑
- **目录即索引** — `prompts/agents/` 目录下的文件列表就是可用的 Agent 列表

---

## 5. Prompt Loader 层

**`prompt_loader.py`** 负责将 `.md` 文件解析为 Python 字典：

```python
# 使用示例
from ims_crew.prompt_loader import load_agent, load_task

agent_config = load_agent("backend_developer")
# 返回: {"role": "...", "goal": "...", "backstory": "..."}

task_config = load_task("backend_development")
# 返回: {"description": "...", "expected_output": "..."}
```

**解析规则**：
- `## 标题` → dict key（转为小写）
- 标题后的所有内容 → dict value
- 列表、代码块原样保留
- 连续空行压缩为单行

---

## 6. Crew 装配（crew.py）

**核心设计**：不使用 `@CrewBase` 装饰器（避免对 YAML 的依赖），而是手动构造 Agent/Task。

### 6.1 Agent 工厂函数

```python
def _make_agent(
    name: str, allow_delegation: bool = False,
    llm: str | None = None, tools: list | None = None,
) -> Agent:
    prompt = load_agent(name)
    role = prompt.get("role", name)
    goal = prompt.get("goal", "")
    backstory = prompt.get("backstory", "")
    return Agent(
        role=role, goal=goal, backstory=backstory,
        allow_delegation=allow_delegation,
        verbose=True, llm=llm,
        tools=tools or [],  # 绑定质量检查/测试工具
    )
```

不同角色绑定不同的工具：
- **后端工程师**：`CheckPythonSyntaxTool`, `CodeQualityCheckAllTool`, `ValidateAPIRoutesTool`
- **QA 工程师**：`RunPytestTool`, `CheckPythonSyntaxTool`, `CodeQualityCheckAllTool`

### 6.2 Task 工厂函数

```python
def _make_task(name, agent, context_tasks=None, output_file=None,
               human_input=False, description_append=None, inject_file_inputs=True):
    prompt = load_task(name)
    description = prompt.get("description", "")

    # 自动注入前序文件产出（替代 {variable} 模板变量）
    if inject_file_inputs:
        file_content = _load_task_file_inputs(name)
        if file_content:
            description += f"\n\n## 前序产出\n\n{file_content}"

    if description_append:
        description += f"\n\n{description_append}"

    return Task(
        description=description,
        expected_output=prompt.get("expected_output", ""),
        agent=agent,
        context=context_tasks,
        output_file=output_file,
        human_input=human_input,  # PRD 阶段启用人工审批
    )
```

### 6.3 依赖链设计

```
requirement_analysis (PM)
    ↓
system_design (Architect)    ← 依赖 PRD
    ↓
backend_development ← 依赖 PRD + Architecture
frontend_development ← 依赖 PRD + Architecture
    ↓
testing (QA)                ← 依赖 backend + frontend
    ↓
deployment (DevOps)         ← 依赖 backend + frontend + tests
```

### 6.4 多模型分配（可选）

```python
agents = [
    _make_agent("architect", llm="anthropic/claude-sonnet-4-20250514"),
    _make_agent("backend_developer", llm="openai/gpt-4o"),
    _make_agent("frontend_developer", llm="openai/gpt-4o-mini"),
    ...
]
```

---

## 7. 入口与运行

### 7.1 CLI 入口（main.py）

```python
# 支持 --from / --only / --skip-post-fix / --qa-rounds 等参数
def run():
    _check_env()  # 自动检查 .env 和 API Key
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="resume_from", ...)
    parser.add_argument("--only", ...)
    parser.add_argument("--skip-post-fix", action="store_true")
    parser.add_argument("--qa-rounds", type=int, default=5)
    ...
```

### 7.2 运行命令

```bash
# 设置 API Key
export OPENAI_API_KEY="sk-xxx"

# 完整团队（6 角色全流程）
cd ims-crew
uv run ims-crew

# 仅后端模式（减少 Token 消耗）
uv run ims-crew --only pm,arch,backend,qa

# 快速原型（跳过 QA 和 DevOps）
uv run ims-crew --only arch,backend,frontend

# 跳过自动修复
uv run ims-crew --skip-post-fix
# （旧参数 --no-fix 仍兼容）

# QA 反馈闭环轮数控制
uv run ims-crew --qa-rounds 3   # 3 轮修复-测试
uv run ims-crew --qa-rounds 0   # 跳过闭环

# 断点续跑
uv run ims-crew --from backend

# 训练模式（优化 Agent 表现）
uv run ims-train 5

# 环境变量控制
export CREW_LOG_LEVEL=DEBUG           # 调试日志
export CREW_MAX_EXECUTION_TIME=7200   # 任务超时
```

---

## 8. 角色裁剪与断点续跑

`--profile` 已被更灵活的 `--only`（精确角色选择）和 `--from`（断点续跑）取代。

### 8.1 角色裁剪（--only）

```bash
# 等价于原 full profile
uv run ims-crew

# 等价于原 backend-only profile
uv run ims-crew --only pm,arch,backend,qa

# 等价于原 prototype profile
uv run ims-crew --only arch,backend,frontend

# 任意自定义组合
uv run ims-crew --only backend,frontend,devops
```

### 8.2 断点续跑（--from）

```bash
# 从架构师开始（跳过 PM，自动注入已有的 PRD）
uv run ims-crew --from arch

# 从 QA 开始（跳过开发阶段，直接测试已有代码）
uv run ims-crew --from qa

# 与 --only 组合
uv run ims-crew --from arch --only arch,backend,frontend
```

---

## 9. 后处理与自修复管线

生成完成后自动执行 4 项修复（可通过 `--skip-post-fix` 或旧名 `--no-fix` 跳过）：

| 修复项 | 解决的问题 |
|--------|-----------|
| `fix_requirements()` | 修复 `requirements.txt` 缺失依赖、内置库混入 |
| `fix_pydantic_v2()` | 将 Pydantic v1 语法（`orm_mode`）转为 v2（`model_config`） |
| `fix_cors_middleware()` | 确保 `main.py` 中配置了 CORS 中间件 |
| `fix_database_url()` | 将硬编码的数据 URL 改为从环境变量读取 |

参考: SWE-Team post_generation_fixes.py

---

## 10. 运行效果与产出

### 预期目录结构

```
ims-crew/project/
├── backend/
│   ├── main.py              # FastAPI 应用入口
│   ├── database.py          # 数据库配置
│   ├── models.py            # SQLAlchemy 模型
│   ├── schemas.py           # Pydantic 模型
│   ├── routers/
│   │   ├── categories.py    # 分类管理 API
│   │   ├── products.py      # 商品管理 API
│   │   ├── purchases.py     # 采购管理 API
│   │   ├── sales.py         # 销售管理 API
│   │   └── reports.py       # 报表统计 API
│   └── requirements.txt
├── frontend/
│   ├── index.html           # 仪表盘
│   ├── categories.html      # 分类管理
│   ├── products.html        # 商品管理
│   ├── purchases.html       # 采购管理
│   ├── sales.html           # 销售管理
│   ├── inventory.html       # 库存管理
│   ├── reports.html         # 报表统计
│   └── shared/
│       ├── style.css
│       └── api.js
├── tests/
│   ├── conftest.py
│   ├── test_categories.py
│   ├── test_products.py
│   ├── test_purchases.py
│   └── test_sales.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── QA_REPORT.md
└── README.md
```

### 启动验证

```bash
cd project

# 方式一: Docker Compose 一键启动
docker compose up

# 方式二: 手动运行
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000

# 打开前端（用浏览器）
python -m http.server 3000 -d frontend
```

### 各角色产出质量预期

| 角色 | 预期产出 | 典型规模 |
|------|----------|---------|
| PM | 详细 PRD，含功能描述和数据字段 | 800-1500 字 |
| 架构师 | 完整的 ER 设计和 API 列表 | 10-15 个端点设计 |
| 后端 | 完整可编译的 FastAPI 项目 | 800-1500 行代码 |
| 前端 | 所有管理后台页面 HTML | 5-8 个 HTML 文件 |
| QA | 按模块组织的测试用例 | 5-10 个测试函数 |
| DevOps | 一键启动的 Docker 配置 | Dockerfile + compose + README |

---

## 11. 进阶扩展

### 11.1 从 Sequential 升级到 Flow（事件驱动）

需要更复杂的编排时升级到 CrewAI Flow：

```python
from crewai.flow import Flow, listen, start, router

class IMSFlow(Flow):
    @start()
    def kickoff(self):
        self.state["phase"] = "requirements"
        return IMSCrew().crew().kickoff()

    @listen(kickoff)
    def review_prd(self):
        """人工审查 PRD"""
        prd = self.state.get("prd", "")
        self.state["prd_approved"] = True
        return prd

    @router(review_prd)
    def decide_next(self):
        if self.state.get("prd_approved"):
            return "proceed_to_design"
        return "revise_requirements"
```

### 11.2 Human-in-the-Loop

系统已在 PRD 阶段默认启用人工确认（`human_input=True`）。在需求分析完成后，会暂停等待用户审查和编辑 PRD 后再继续后续流程：

```python
# PRD 阶段自动启用人工确认
human = task_name == "requirement_analysis"
t = _make_task(task_name, agent, ..., human_input=human)
```

### 11.3 复用提示词到其他项目

将 `prompts/` 目录复制到新项目，修改 `crew.py` 中的角色组合即可：

```python
# 复用到电商系统
from prompts_shared import load_agent, load_task
# 只需修改 prompts 目录下的 .md 文件内容
```

### 11.4 支持多语言提示词

```
prompts/
├── zh-CN/                    # 中文团队
│   ├── agents/
│   └── tasks/
└── en/                       # 英文团队
    ├── agents/
    └── tasks/
```

在 `crew.py` 中切换语言目录：

```python
PROMPTS_LANG = "en"  # 或 "zh-CN"
```

---

## 附录：参考项目

本教程的设计模式参考了以下开源项目：

| 项目 | ⭐ | 参考要点 |
|------|---|---------|
| [ai-team](https://github.com/RickZee/ai-team) | 13 | 9 角色分工、YAML 配置、失败分析、预算监控 |
| [CrewAI-Agentic-SWE-Team](https://github.com/praniketkw/CrewAI-Agentic-SWE-Team) | 3 | 6 角色编排、context 依赖链、后修复管线 |
| [crewAI-examples](https://github.com/crewAIInc/crewAI-examples) | 6.1k | @CrewBase 装饰器模式、YAML 声明式配置 |
| [Devyan](https://github.com/theyashwanthsai/Devyan) | 290 | 多 Agent 协作编程实验 |

---

> **许可证**: MIT
> **注意**: 生成的代码需要人工审查后再用于生产环境。LLM 生成的代码可能存在安全问题或不完整的业务逻辑。
