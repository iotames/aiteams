# IMS Crew — 进销存管理系统生成器

> 基于 CrewAI 的多 Agent 软件团队，自动生成面向中小商户的进销存管理系统（IMS）完整代码。

---

## 快速开始

### 前置要求

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) 或 pip
- 一个 LLM API Key（DeepSeek / OpenAI / Anthropic 等，详见 [LLM 模型配置](#llm-模型配置)）

### 0. 编写你的需求

**这是人类参与的地方**。编辑以下文件，填写你的业务需求：

```bash
vim prompts/requirements/ims-requirements.md
```

该文件是 AI 团队的**唯一需求输入**，包含项目背景、目标用户、功能范围、技术约束。内容越详细，生成结果越精准。你也可以直接使用默认的进销存需求。

### 1. 配置环境变量

```bash
cd ims-crew
cp .env.example .env
```

编辑 `.env`，填入你的 API Key。例如使用 DeepSeek：

```bash
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
MODEL_NAME=deepseek/deepseek-v4-flash
```

也可以使用其他厂商，详见 [LLM 模型配置](#llm-模型配置)。

### 2. 安装依赖

```bash
uv sync
# 或: pip install -e .
```

### 3. 运行生成流水线

```bash
# 全流程（6 角色，生成完整系统）
uv run ims-crew

# 只跑指定角色，按角色短名逗号分隔
uv run ims-crew --only pm,arch,backend,qa       # 仅后端模式
uv run ims-crew --only arch,backend,frontend     # 快速原型

# 断点续跑：从指定角色开始（跳过前面的角色）
uv run ims-crew --from arch     # 跳过 PM，从架构师开始
uv run ims-crew --from backend  # 跳过 PM+架构师，从后端开始

# QA 反馈闭环轮数
uv run ims-crew --qa-rounds 3   # 3 轮修复-测试循环
uv run ims-crew --qa-rounds 0   # 跳过闭环，一次性测试
```

> **预计运行时间**：5-15 分钟（取决于 LLM 响应速度）。

角色短名对照：`pm`(产品经理)、`arch`(架构师)、`backend`(后端)、`frontend`(前端)、`qa`(测试)、`devops`(部署)。

### 4. 启动生成的系统

```bash
cd project

# 方式一：Docker Compose 一键启动
docker compose up

# 方式二：手动启动后端
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000

# 打开前端（新开终端）
python -m http.server 3000 -d frontend
```

浏览器访问：
- 管理后台：`http://localhost:3000`（如果使用 Python HTTP 服务器）
- API 文档：`http://localhost:8000/docs`（FastAPI 自动生成）

---

## LLM 模型配置

本工具通过 [LiteLLM](https://docs.litellm.ai/docs/) 接入各类大语言模型。
CrewAI 底层使用 LiteLLM，因此支持所有 [LiteLLM 兼容的提供商](https://docs.litellm.ai/docs/providers)。

### 配置方式

优先级从高到低：
1. **角色专用环境变量** — 为不同 Agent 指定不同模型（如 `ARCHITECT_LLM`）
2. **通用环境变量** `MODEL_NAME` — 所有 Agent 使用同一模型
3. **留空** — 使用对应 API Key 的默认模型

### 方案一：DeepSeek（国内直连，推荐）

[DeepSeek](https://platform.deepseek.com/) 提供高性价比的 API，国内可直接访问，延迟低。

**.env 配置：**
```bash
# 从 https://platform.deepseek.com/api_keys 获取
DEEPSEEK_API_KEY=sk-your-deepseek-api-key

# 使用 DeepSeek 最新模型（所有 Agent 共用）
MODEL_NAME=deepseek/deepseek-v4-flash
```

**按角色分配不同模型：**
```bash
DEEPSEEK_API_KEY=sk-your-deepseek-api-key

# 架构师和 PM 用最强模型
ARCHITECT_LLM=deepseek/deepseek-v4-pro
PM_LLM=deepseek/deepseek-v4-pro

# 开发工程师用性价比模型
BACKEND_LLM=deepseek/deepseek-v4-flash
FRONTEND_LLM=deepseek/deepseek-v4-flash

# QA 和 DevOps 用轻量模型
QA_LLM=deepseek/deepseek-v4-flash
DEVOPS_LLM=deepseek/deepseek-v4-flash
```

> **LiteLLM 模型命名规则**：`提供商/模型名`，DeepSeek 最新模型名为 `deepseek/deepseek-v4-flash`（快速模型）和 `deepseek/deepseek-v4-pro`（强力推理模型）。
> LiteLLM 的 `deepseek/` 前缀会将 base_url 设为 `https://api.deepseek.com` 并将模型名透传，因此直接使用 DeepSeek 官方模型名即可。
> 旧名 `deepseek/deepseek-chat`、`deepseek/deepseek-reasoner`、`deepseek/deepseek-coder` 已被官方废弃。

### 方案二：自定义 OpenAI 兼容 API（任意厂商）

许多模型服务商（如 vLLM、Ollama、LM Studio、国产模型代理等）提供 OpenAI 兼容接口。

**.env 配置：**
```bash
# 方式 A：通过环境变量覆盖 OpenAI 基础 URL
OPENAI_API_KEY=sk-your-custom-key
OPENAI_BASE_URL=https://your-custom-endpoint.com/v1
MODEL_NAME=openai/your-model-name

# 方式 B：使用自定义前缀（通过 OPENAI_API_BASE 环境变量）
# LiteLLM 自动读取 OPENAI_API_BASE 作为 openai/* 模型的 base_url
```

**实际示例——接入本地 Ollama（运行在 localhost:11434）：**

首先确保 Ollama 已运行并拉取了模型：
```bash
ollama pull qwen2.5-coder:7b
# 或 ollama pull llama3.1:8b
```

然后 `.env` 配置：
```bash
OPENAI_API_KEY=ollama  # Ollama 不需要真实 Key，但字段不能为空
OPENAI_BASE_URL=http://localhost:11434/v1
MODEL_NAME=openai/qwen2.5-coder:7b
```

> Ollama 从 v0.1.18 起提供 `/v1` 兼容端点，可直接作为 OpenAI 兼容 API 使用。

**实际示例——接入阿里云通义千问（DashScope）：**

```bash
DASHSCOPE_API_KEY=sk-your-dashscope-key
MODEL_NAME=qwen/qwen-max
# 或 openai/qwen-max — 通过 OPENAI_BASE_URL 自定义端点
```

### 方案三：OpenAI / Anthropic / OpenRouter

```bash
# ── OpenAI 直连 ──
OPENAI_API_KEY=sk-your-openai-key
MODEL_NAME=gpt-4o

# ── Anthropic Claude ──
ANTHROPIC_API_KEY=sk-ant-xxxx
MODEL_NAME=claude-sonnet-4-20250514

# ── OpenRouter（聚合多模型） ──
OPENROUTER_API_KEY=sk-or-xxxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=openrouter/anthropic/claude-sonnet-4
```

### 各角色模型分配建议

| 角色 | 推荐模型（强） | 推荐模型（经济） |
|------|---------------|-----------------|
| 产品经理 | 强推理模型 | 中等模型 |
| 系统架构师 | **最强模型** | 中等偏上 |
| 后端开发 | 强编码模型 | 中等模型 |
| 前端开发 | 中等模型 | 轻量模型 |
| QA 工程师 | 中等模型 | 轻量模型 |
| DevOps | 中等模型 | 轻量模型 |

合理分配可大幅降低 Token 消耗，同时保持关键产出的质量。

### 模型配置一览

| 环境变量 | 用途 | 示例值 |
|---------|------|--------|
| `MODEL_NAME` | 全局默认模型 | `gpt-4o`、`deepseek/deepseek-v4-flash` |
| `PM_LLM` | 产品经理专用模型 | `deepseek/deepseek-v4-flash` |
| `ARCHITECT_LLM` | 架构师专用模型 | `claude-sonnet-4-20250514` |
| `BACKEND_LLM` | 后端开发专用模型 | `openai/gpt-4o-mini` |
| `FRONTEND_LLM` | 前端开发专用模型 | `deepseek/deepseek-v4-flash` |
| `QA_LLM` | QA 专用模型 | `openai/gpt-4o-mini` |
| `DEVOPS_LLM` | DevOps 专用模型 | `openai/gpt-4o-mini` |
| `OPENAI_BASE_URL` | OpenAI 兼容 API 地址 | `http://localhost:11434/v1` |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | `sk-xxx` |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | `sk-ant-xxx` |
| `OPENROUTER_API_KEY` | OpenRouter API 密钥 | `sk-or-xxx` |

---

## 流水线时序与产物

### 角色执行时序

```
pm(产品经理) ──→ arch(架构师) ──→ backend(后端) ──→ qa(测试) ──→ devops(部署)
                                        └→ frontend(前端) ──↑
                                            （前后端并行）
```

每个角色按时序依次执行，后序角色自动获取前序角色的输出作为上下文。

### 各阶段输入与输出

| 步骤 | 角色 | 短名 | 读取（输入） | 写入（输出） | 产物类型 |
|------|------|------|-------------|-------------|---------|
| ① | **产品经理** | `pm` | `prompts/requirements/ims-requirements.md`（**人写**） | `output/PRD.md` | **提示词输出**（可编辑中间产物） |
| ② | **系统架构师** | `arch` | `output/PRD.md` | `output/ARCHITECTURE.md` + `output/openapi.yaml` + `output/models.py` | **提示词输出**（可编辑中间产物） |
| ③ | **后端工程师** | `backend` | `output/ARCHITECTURE.md` + `output/models.py` | `project/backend/**`（FastAPI 代码） | **最终代码产物** |
| ③' | **前端工程师** | `frontend` | `output/ARCHITECTURE.md` | `project/frontend/**`（HTML/CSS/JS） | **最终代码产物** |
| ④ | **QA 工程师** | `qa` | `project/backend/**` + `project/frontend/**` | `project/tests/**` + `output/QA_REPORT.md` | 混合（测试代码+报告） |
| ⑤ | **DevOps** | `devops` | 完整项目代码 | `project/Dockerfile`、`docker-compose.yml`、`README.md` | **最终代码产物** |

### QA 反馈闭环（可配置轮数）

```
QA 测试 ──→ 第1轮修复 ──→ 第1轮重测 ──→ 第2轮修复 ──→ 第2轮重测 ──→ ... ──→ 部署
                ↑_____________________________________________↓
                     （默认 5 轮，可通过 --qa-rounds 配置）
```

QA 阶段之后自动执行 N 轮 BUG 修复-测试循环（默认 5 轮）：
1. **bug_fixing** — 后端读取 QA 报告，修复 BUG
2. **bug_fixing_frontend** — 前端读取 QA 报告，修复 BUG
3. **qa_retest** — 重新运行测试，更新 QA 报告
4. 重复以上步骤 N 轮，每轮依赖上一轮的重测结果

每一轮 LLM 都会收到轮次标记（如"QA 轮次 3/5"），知道还有后续轮次，逐步收敛 BUG。

**智能修复分配**：系统自动解析 QA 报告，根据 `[BUG]` 标记中的 "后端"/"前端" 关键词，只对有 BUG 的角色执行修复。如果 QA 报告为空（无 BUG），修复步骤完全跳过。可通过 `--qa-rounds 0` 跳过整个闭环。

```bash
uv run ims-crew                    # 默认 5 轮
uv run ims-crew --qa-rounds 3      # 3 轮
uv run ims-crew --qa-rounds 0      # 跳过闭环，一次性测试
```

---

## 命令行参考

```bash
# 全流程（默认）
uv run ims-crew

# 从指定角色开始（断点续跑）
uv run ims-crew --from arch       # 从架构师开始（跳过 PM）
uv run ims-crew --from backend    # 从后端开始（跳过 PM+架构师）
uv run ims-crew --from qa         # 从测试开始（跳过开发阶段）

# 只跑指定角色子集
uv run ims-crew --only pm,arch,backend,qa      # 等价原 backend-only
uv run ims-crew --only arch,backend,frontend    # 等价原 prototype
uv run ims-crew --only backend,frontend,devops  # 自定义组合

# 组合使用
uv run ims-crew --from arch --only arch,backend,frontend

# 跳过自动修复
uv run ims-crew --skip-post-fix
# （旧参数 --no-fix 仍兼容）

# 使用环境变量控制
export CREW_LOG_LEVEL=DEBUG           # 调试日志
export CREW_MAX_EXECUTION_TIME=7200   # 任务超时 2 小时

# 训练模式
uv run ims-train [iterations] [filename]
uv run ims-train 10 training_data.pkl
```

### 角色短名速查

| 短名 | 完整角色名 | 对应 Task |
|------|-----------|----------|
| `pm` | product_manager | requirement_analysis |
| `arch` | architect | system_design |
| `backend` | backend_developer | backend_development |
| `frontend` | frontend_developer | frontend_development |
| `qa` | qa_engineer | testing → bug_fixing → qa_retest |
| `devops` | devops_engineer | deployment |

### 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--from` | 从哪个角色开始执行（跳过前面所有角色） | `--from arch` |
| `--only` | 只运行哪些角色（逗号分隔，按时序自动排序） | `--only pm,arch,backend` |
| `--qa-rounds` | QA 反馈闭环轮数（默认 5，最大 20，设为 0 跳过闭环） | `--qa-rounds 3` |
| `--skip-post-fix` | 跳过生成后自动修复（旧参数 `--no-fix` 仍兼容） | `--skip-post-fix` |
| `CREW_MAX_EXECUTION_TIME` | 环境变量，设置任务超时秒数（默认 3600） | `export CREW_MAX_EXECUTION_TIME=7200` |
| `CREW_LOG_LEVEL` | 环境变量，设置日志级别：DEBUG/INFO/WARNING（默认 INFO） | `export CREW_LOG_LEVEL=DEBUG` |

---

## 断点续跑与迭代

这是系统最重要的生产力特性。你可以在任意阶段**修改中间产物**后从对应角色**恢复执行**。

### 典型场景

**场景 1：修改 PRD 后重新生成**
```bash
# 1. 编辑需求文档
vim prompts/requirements/ims-requirements.md

# 2. 从架构师开始（保持之前 PM 的 PRD 理解，但直接加载你改后的需求）
#    注意：--from arch 会加载 output/PRD.md 而不是原始需求文件
#    所以需要先让 PM 重新生成 PRD，或直接编辑 output/PRD.md

# 方案 A：全流程重跑（保守）
uv run ims-crew

# 方案 B：编辑 output/PRD.md 后从架构师继续（快速）
#   vim output/PRD.md
#   uv run ims-crew --from arch
```

**场景 2：架构设计跑偏，修改后重跑**
```bash
# 编辑架构文档
vim output/ARCHITECTURE.md
vim output/models.py

# 从后端开始（架构阶段前序任务被跳过，文件内容自动注入上下文）
uv run ims-crew --from backend
```

**场景 3：后端代码生成后手动修改，只测+部署**
```bash
# 修改 project/backend/ 下的代码
# 从 QA 开始重新测试和部署
uv run ims-crew --from qa
```

### 文件加载机制

当使用 `--from` 跳过前序角色时，系统自动加载已存在的 output 文件，追加到首个运行任务的描述中。**即使在正常全流程中，每个任务的描述也会自动注入前序文件产出**（取代了旧的 `{variable}` 模板变量机制）：

| 从 `--from` | 被跳过角色 | 加载的文件 |
|------------|-----------|-----------|
| `arch` | PM | `output/PRD.md` |
| `backend` | PM + 架构师 | `output/PRD.md` + `output/ARCHITECTURE.md` + `output/models.py` |
| `frontend` | PM + 架构师 | `output/PRD.md` + `output/ARCHITECTURE.md` |
| `qa` | PM + 架构师 + 后端 + 前端 | 无 output 文件（依赖 project/ 下的实际代码） |

> 如果指定的 `--from` 角色的前序 output 文件不存在，系统会报错提示。请先运行全流程生成这些文件，或手动创建。

---

## 团队角色

| 角色 | 职责 | 提示词文件 |
|------|------|-----------|
| **产品经理** | 分析需求，编写 PRD 文档 | `prompts/agents/product_manager.md` |
| **系统架构师** | 技术选型，数据库 ER 设计，API 规划 | `prompts/agents/architect.md` |
| **后端工程师** | FastAPI 后端，数据库模型，业务逻辑 | `prompts/agents/backend_developer.md` |
| **前端工程师** | 管理后台界面（纯 HTML/CSS/JS） | `prompts/agents/frontend_developer.md` |
| **QA 工程师** | pytest 测试，代码审查，质量报告 | `prompts/agents/qa_engineer.md` |
| **DevOps 工程师** | Docker 化，部署配置，项目文档 | `prompts/agents/devops_engineer.md` |

角色间**不需要互相沟通**：架构师的设计文档（API 规范 + 数据库模型）是前后端的唯一契约，后端不读前端代码，前端不读后端代码。

---

## 项目结构

```
ims-crew/
├── prompts/                      # ⭐ 所有提示词独立存放
│   ├── agents/                   #   6 个 Agent 角色定义
│   ├── tasks/                    #   9 个 Task 任务描述
│   └── requirements/             #   产品需求规格文档
├── src/ims_crew/
│   ├── main.py                   # CLI 入口
│   ├── crew.py                   # Crew 装配（核心调度）
│   ├── prompt_loader.py          # .md → Python dict 加载器
│   ├── tools.py                  # 代码质量和 API 验证工具
│   └── fixers/post_gen_fixes.py  # 自动修复管线
├── output/                       # 运行产出的文档（可编辑中间产物）
├── project/                      # 运行产出的应用代码（最终产物）
├── .env.example                  # 环境变量模板
├── .gitignore                    # Git 忽略规则
└── pyproject.toml                # 项目配置
```

### 核心设计

**提示词与代码完全解耦**：所有 Agent 角色定义、Task 任务描述、产品需求规格都以 `.md` 文件存放在 `prompts/` 目录中。Python 代码通过 `prompt_loader.py` 动态加载。这意味着：

- ✅ 非技术人员可直接编辑 `.md` 文件调整 Agent 行为
- ✅ 提示词文件可在不同项目中复用
- ✅ 支持多语言（每种语言一套 `.md` 文件）
- ✅ 无需修改 Python 代码即可改变团队角色和任务

---

## 生成后的自动修复

生成完成后，系统自动执行以下修复：

| 修复项 | 解决什么问题 |
|--------|------------|
| `fix_requirements` | 修复缺失依赖、移除内置库 |
| `fix_pydantic_v2` | Pydantic v1→v2 语法迁移 |
| `fix_cors_middleware` | 确保 CORS 跨域配置 |
| `fix_database_url` | 数据库 URL 改为环境变量配置 |

可通过 `--skip-post-fix` 参数跳过自动修复（旧参数 `--no-fix` 仍兼容）。

---

## FAQ

### 生成的代码质量如何？

每个 Agent 的提示词都经过精心设计，包含生产级别的编码规范和最佳实践。但 LLM 生成的代码仍需人工审查后再投入生产使用。

### 可以自定义 Agent 行为吗？

可以。直接编辑 `prompts/agents/` 下对应的 `.md` 文件即可。无需修改 Python 代码。

### 可以添加新的角色吗？

可以。在 `prompts/agents/` 下创建新的 `.md` 文件，然后在 `crew.py` 中注册即可。

### 如何切换团队组合？

使用 `--only` 参数：`uv run ims-crew --only arch,backend,frontend`。详见[命令行参考](#命令行参考)。

### 可以用其他 LLM 吗？

可以。通过 `.env` 文件配置即可，详见 [LLM 模型配置](#llm-模型配置) 章节。

支持 DeepSeek、OpenAI、Anthropic、Ollama（本地）、阿里通义千问等所有 LiteLLM 兼容的模型，也支持自定义 OpenAI 兼容端点。

可以为不同 Agent 角色分配不同模型：架构师用最强模型、开发用中等模型、QA 用轻量模型，从而优化 Token 消耗。

---

## 许可证

MIT

> ⚠️ **注意**：本工具生成的代码需要人工审查后再用于生产环境。LLM 生成的代码可能存在安全问题、性能问题或不完整的业务逻辑。
