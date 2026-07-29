# ims-autogen

> 基于 **AutoGen** 的多 Agent **对话式**软件团队 — 进销存管理系统（IMS）生成器。
> Agent 之间可以**双向对话**：开发向架构师提问、产品经理向用户确认需求、测试向开发报告 bug。

---

## 与 ims-metagpt / ims-crew 的区别

| 特性 | ims-metagpt | ims-crew | **ims-autogen 🆕** |
|---|---|---|---|
| 框架 | MetaGPT | CrewAI | **AutoGen v0.4+** |
| 对话方式 | 单向接力 | 串行流水线 | **🤝 双向对话（SelectorGroupChat）** |
| 开发问架构师 | ❌ | ❌ | **✅** |
| 产品问用户 | ❌ 只能审文件 | ❌ | **✅ 终端内实时问答** |
| 测试→开发→再测 | ❌ | ❌ | **✅ bug 修复循环** |
| 产品验收 | ❌ | ❌ | **✅ 验收通过才结束** |

---

## 快速开始

### 1. 安装

```bash
cd ims-autogen
pip install -e .
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key
```

**最少配置**（两行即可运行）：

```ini
API_KEY=sk-your-api-key
MODEL_NAME=deepseek-chat
```

> ⚠️ **重要**：`API_BASE` 必须以 `/v1` 结尾（OpenAI 兼容格式），默认已填好 DeepSeek 地址。

**主流模型供应商速查：**

| 供应商 | API_BASE | MODEL_NAME 示例 |
|--------|----------|-----------------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` / `deepseek-v4-flash` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` / `gpt-4o-mini` |
| 硅基流动 | `https://api.siliconflow.cn/v1` | `Qwen/Qwen3-235B-A22B` |
| 本地 Ollama | `http://localhost:11434/v1` | `llama3:8b` |

**非 OpenAI 模型自动适配**：`config.py` 会自动检测模型类型，为非 OpenAI 模型（DeepSeek、Claude、Qwen 等）注入必需的 `model_info`，你不需要手动配置任何额外参数。

### 3. 启动对话式开发

```bash
ims-autogen run "生成一个进销存管理系统" -w ./my-ims
```

启动后你会看到：

```
╔══════════════════════════════════════════════════════════╗
║      🤖 ims-autogen 多 Agent 对话式开发启动              ║
╠══════════════════════════════════════════════════════════╣
║  需求: 生成一个进销存管理系统                              ║
║  范围: MVP                                              ║
║  输出: D:\projects\my-ims                                ║
╚══════════════════════════════════════════════════════════╝

📢  对话即将开始！产品经理 Alice 会先和你沟通需求。
   请关注终端提示，当 Alice 提问时输入你的回答。
```

### 交互示例

```
---------- user ----------
生成一个进销存管理系统

---------- product_manager (Alice) ----------
好的！我先和你确认一下需求细节。
你好！我是产品经理 Alice。请问这个进销存系统主要用在什么场景？

---------- human_user (你) ----------
> 我们是一家小型便利店，需要管理商品信息、进货、销售和库存

---------- product_manager (Alice) ----------
明白了！有几个细节想确认：
1. 是否需要多门店管理？
2. 库存预警阈值设为多少合适？
...（对话继续，直到 Alice 确认清楚需求）
```

---

## 完整对话流程

```
Alice（产品经理）←→ human_user（你）  需求澄清
    │
Alice → Bob（架构师）                  PRD 输出
    │
Bob ←→ Alice                          设计确认
    │
Bob → Eve（开发）                      架构设计输出
    │
Eve ←→ Bob                            技术答疑
    │
Eve → 代码输出                         backend/ + frontend/
    │
Charlie（测试）→ 执行测试              发现 bug
    │
Charlie → Eve                          报告 bug
Eve 修复 → Charlie 回归测试
    │
Charlie → Alice                        测试报告
Alice 审查 → 验收通过 → FINAL_ACCEPT
```

---

## CLI 命令参考

### `ims-autogen run` — 启动对话式开发

这是核心命令，实现多 Agent 对话式软件开发全流程。

**用法：**
```bash
ims-autogen run <IDEA> [--workspace] [--resume]
```

**参数详解：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `IDEA` | 位置参数 | ✅ | — | 你的需求描述文本，用引号包裹。例：`"生成进销存系统"` |
| `-w` / `--workspace` | 选项 | ❌ | `./ims-output` | 输出目录路径。所有生成的文件（代码、文档）都保存在此目录下 |
| `-r` / `--resume` | 标志 | ❌ | `False` | **续传模式**。基于工作区已有产物继续，不从头开始 |

**续传模式说明：**
如果流程因报错或中断提前结束，但已有部分产出（如 `prd.md`），加上 `--resume` 续传：

```bash
# 续传：团队会读取已有文件，在此进度上继续
ims-autogen run "继续进销存系统" -w ./my-ims --resume

# 补充内容
ims-autogen run "项目已完成开发，但缺少 README.md，请补充" -w ./ims-output --resume

# 基于已有代码继续迭代
ims-autogen run "完善项目，补充采购管理和报表功能" -w ./ims-output --resume
```

续传时，系统会自动扫描工作区文件，将已有产物摘要注入到初始消息中，AI 团队会根据当前进度继续后续工作。

**示例：**
```bash
# 最简用法。默认在 ims-output 目录下生成代码
ims-autogen run "生成进销存系统"

# 指定输出目录
ims-autogen run "生成一个进销存管理系统，先做商品和库存" -w ./my-project
```

---

### `ims-autogen list-modes` — 显示帮助

无参数，打印命令速查表。

**用法：**
```bash
ims-autogen list-modes
```

---

### `ims-autogen init-config` — 初始化配置

无参数。将项目自带的 `.env.example` 复制到当前目录的 `.env`。

**用法：**
```bash
ims-autogen init-config
```

---

## 技术架构

```
ims-autogen/
├── src/
│   └── ims_autogen/
│       ├── main.py              # CLI 入口（typer）
│       ├── config.py             # 统一配置管理（多层覆盖）
│       ├── agents.py             # Agent 工厂（5 个角色）
│       ├── team.py               # Team 组装（SelectorGroupChat）
│       ├── tools.py              # 工具函数（文件读写、命令执行）
│       ├── prompt_loader.py      # 提示词加载器（动态加载 + 模板变量）
│       └── prompts/              # 系统提示词（每个角色独立 .md）
│           ├── product_manager.md
│           ├── architect.md
│           ├── developer.md
│           └── qa.md
├── .env.example
├── pyproject.toml
└── README.md
```

**核心对话机制：** SelectorGroupChat（模型选择下一个发言人）
- 5 个 Agent 共享同一对话上下文
- 选择器模型根据对话内容自动决定谁发言
- `TextMentionTermination("FINAL_ACCEPT")` 控制结束
- `UserProxyAgent(input_func=input)` 实现真人参与

---

## 提示词与代码解耦

提示词文件存放在 `prompts/` 目录中，Python 代码通过 `prompt_loader.py` 动态加载。

```
src/ims_autogen/prompts/        ← 默认语言（中文）
├── product_manager.md          # 产品经理角色定义
├── architect.md                # 架构师角色定义
├── developer.md                # 全栈工程师角色定义
└── qa.md                       # 测试工程师角色定义
prompts/en/                     ← 英文版（可选）
└── ...
```

### 这意味着什么

| 能力 | 说明 |
|---|---|
| **非技术人员可编辑** | 直接修改 `prompts/product_manager.md` 即可调整 Alice 的行为，无需碰 Python 代码 |
| **模板变量** | `.md` 文件中用 `{{scope}}`、`{{language}}` 等占位符，`load("product_manager", scope="MVP")` 注入 |
| **多语言** | 在 `prompts/en/` 下放英文版 `.md` 文件，调用 `load("product_manager", lang="en", scope="MVP")` |
| **自动校验** | 如果 `.md` 文件中有占位符忘了传值，`prompt_loader` 在加载时会抛出 `PromptValidationError`，不会悄悄留空 |
| **文件缓存** | 同一文件只读取一次磁盘，修改后调用 `clear_cache()` 使新内容生效 |

### 使用示例

```python
from ims_autogen.prompt_loader import load

# 加载中文版 MVP 范围的产品经理提示词
prompt = load("product_manager", scope="MVP")

# 加载英文版 Full 范围的开发者提示词
prompt = load("developer", lang="en", scope="Full")

# 列出可用提示词
from ims_autogen.prompt_loader import available
print(available())       # ['architect', 'developer', 'product_manager', 'qa']
print(available("en"))   # ['architect', 'developer', ...]
```

---

## 分角色模型配置

`.env` 支持为每个角色指定不同模型，配置由 `config.py` 统一管理，遵循**多层覆盖**原则：

**优先级：** CLI 参数 > 环境变量 > `.env` 文件 > 代码默认值

```ini
# 全局默认（所有角色共用）
API_KEY=sk-xxx
API_BASE=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat

# 分角色覆盖（可选，未设置回退到全局）
PM_MODEL_NAME=deepseek-v4-pro        # 产品经理用更强的推理模型
ARCHITECT_MODEL_NAME=deepseek-chat
DEVELOPER_MODEL_NAME=deepseek-chat
QA_MODEL_NAME=deepseek-chat
SELECTOR_MODEL_NAME=deepseek-chat    # 选择器建议用便宜快速的模型
```

`config.py` 中 `AppConfig.role_model("PM")` 自动处理回退逻辑：先读 `PM_MODEL_NAME`，未配置则用 `MODEL_NAME`。

---

## 常见问题

### 报错：`model_info is required when model name is not a valid OpenAI model`

这是因为 AutoGen 要求非 OpenAI 模型必须提供 `model_info`（模型能力描述）。**本项目的 `config.py` 已自动处理**，只要你的 `MODEL_NAME` 在已知模型列表中（DeepSeek、Claude、Qwen、GLM 等）。

如果你使用了全新的模型名，`config.py` 也会自动以安全默认值创建 `model_info`，通常不会报这个错。如果确实遇到了，请在 `.env` 中确认：

1. `API_BASE` 是否以 `/v1` 结尾（如 `https://api.deepseek.com/v1`，而不是 `https://api.deepseek.com`）
2. `MODEL_NAME` 是否拼写正确

### 报错：连接超时或 404

检查 `API_BASE` 是否可访问，尤其是：
- DeepSeek 地址必须是 `https://api.deepseek.com/v1`（注意有子路径 `/v1`）
- 如果用代理/VPN，确认 `API_BASE` 使用了正确的代理地址
