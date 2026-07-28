# IMS Crew — 进销存管理系统生成器

> 基于 CrewAI 的多 Agent 软件团队，自动生成面向中小商户的进销存管理系统（IMS）完整代码。

---

## 快速开始

### 前置要求

- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) 或 pip
- 一个 LLM API Key（DeepSeek / OpenAI / Anthropic 等，详见 [LLM 模型配置](#llm-模型配置)）

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
# 完整团队模式（6 角色全流程，生成完整系统）
uv run ims-crew

# 仅后端模式（跳过前端/QA/DevOps，减少 Token 消耗）
uv run ims-crew --profile backend-only

# 快速原型模式（架构 + 后端 + 前端，最快出结果）
uv run ims-crew --profile prototype
```

> **预计运行时间**：5-15 分钟（取决于 LLM 响应速度）。

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

## 团队角色

| 角色 | 职责 | 提示词文件 |
|------|------|-----------|
| **产品经理** | 分析需求，编写 PRD 文档 | `prompts/agents/product_manager.md` |
| **系统架构师** | 技术选型，数据库 ER 设计，API 规划 | `prompts/agents/architect.md` |
| **后端工程师** | FastAPI 后端，数据库模型，业务逻辑 | `prompts/agents/backend_developer.md` |
| **前端工程师** | 管理后台界面（纯 HTML/CSS/JS） | `prompts/agents/frontend_developer.md` |
| **QA 工程师** | pytest 测试，代码审查，质量报告 | `prompts/agents/qa_engineer.md` |
| **DevOps 工程师** | Docker 化，部署配置，项目文档 | `prompts/agents/devops_engineer.md` |

执行流程：**PM → 架构师 → 后端 + 前端（并行）→ QA → DevOps**

---

## 命令行参考

```bash
# 完整用法
uv run ims-crew [--profile PROFILE] [--no-fix]

# 参数说明
  --profile PROFILE   团队组合配置
                      可选: full（默认）, backend-only, prototype
  --no-fix            跳过生成后的自动代码修复

# 训练模式（优化 Agent 表现）
uv run ims-train [iterations] [filename]

# 示例: 训练 10 轮
uv run ims-train 10 training_data.pkl
```

### Profile 说明

| Profile | 角色数 | 适用场景 |
|---------|--------|---------|
| `full` | 6 | 完整软件交付：需求→设计→后端→前端→测试→部署 |
| `backend-only` | 4 | 只需后端 API：PM→架构→后端→测试 |
| `prototype` | 3 | 快速原型：架构→后端→前端 |

---

## 项目结构

```
ims-crew/
├── prompts/                      # ⭐ 所有提示词独立存放
│   ├── agents/                   #   6 个 Agent 角色定义
│   ├── tasks/                    #   6 个 Task 任务描述
│   └── requirements/             #   产品需求规格文档
├── src/ims_crew/
│   ├── main.py                   # CLI 入口
│   ├── crew.py                   # Crew 装配（核心调度）
│   ├── prompt_loader.py          # .md → Python dict 加载器
│   ├── tools.py                  # 代码质量和 API 验证工具
│   ├── config/profiles.yaml      # 团队 Profile 配置
│   └── fixers/post_gen_fixes.py  # 自动修复管线
├── output/                       # 运行产出的文档
├── project/                      # 运行产出的应用代码
├── .env.example                  # 环境变量模板
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

可通过 `--no-fix` 参数跳过自动修复。

---

## FAQ

### 生成的代码质量如何？

每个 Agent 的提示词都经过精心设计，包含生产级别的编码规范和最佳实践。但 LLM 生成的代码仍需人工审查后再投入生产使用。

### 可以自定义 Agent 行为吗？

可以。直接编辑 `prompts/agents/` 下对应的 `.md` 文件即可。无需修改 Python 代码。

### 可以添加新的角色吗？

可以。在 `prompts/agents/` 下创建新的 `.md` 文件，然后在 `crew.py` 中注册即可。

### 如何切换团队组合？

使用 `--profile` 参数：`uv run ims-crew --profile prototype`。

也可以在 `src/ims_crew/config/profiles.yaml` 中自定义 Profile。

### 可以用其他 LLM 吗？

可以。通过 `.env` 文件配置即可，详见 [LLM 模型配置](#llm-模型配置) 章节。

支持 DeepSeek、OpenAI、Anthropic、Ollama（本地）、阿里通义千问等所有 LiteLLM 兼容的模型，也支持自定义 OpenAI 兼容端点。

可以为不同 Agent 角色分配不同模型：架构师用最强模型、开发用中等模型、QA 用轻量模型，从而优化 Token 消耗。

---

## 许可证

MIT

> ⚠️ **注意**：本工具生成的代码需要人工审查后再用于生产环境。LLM 生成的代码可能存在安全问题、性能问题或不完整的业务逻辑。
