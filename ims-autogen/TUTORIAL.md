# ims-autogen 学习教程

> 基于 AutoGen v0.4+ 的多 Agent 对话式软件团队实战教程。
> 适合人群：有 Python 基础，想学习 AutoGen 多 Agent 框架的开发者。
>
> **本教程的代码示例全部来自 ims-autogen 项目的实际代码**，不是空中楼阁的 Demo。
> 每一段代码你都能在 `src/ims_autogen/` 下找到对应实现。

---

## 目录

- [第一章：AutoGen 核心概念](#第一章autogen-核心概念)
- [第二章：第一个 Agent](#第二章第一个-agent)
- [第三章：多个 Agent 对话](#第三章多个-agent-对话)
- [第四章：人工在环](#第四章人工在环)
- [第五章：SelectorGroupChat — 本项目使用的方式](#第五章selectorgroupchat--本项目使用的方式)
- [第六章：ims-autogen 项目代码逐模块解读](#第六章ims-autogen-项目代码逐模块解读)
  - [6.1 入口：main.py](#61-入口mainpy)
  - [6.2 配置：config.py](#62-配置configpy)
  - [6.3 Agent 工厂：agents.py](#63-agent-工厂agentspy)
  - [6.4 团队组装：team.py](#64-团队组装teampy)
  - [6.5 提示词加载器：prompt_loader.py](#65-提示词加载器prompt_loaderpy)
  - [6.6 工具：tools.py](#66-工具toolspy)
  - [6.7 数据流全景](#67-数据流全景)
- [第七章：自定义扩展](#第七章自定义扩展)
- [第八章：实战 — 从零构建一个客服团队](#第八章实战--从零构建一个客服团队)

---

## 第一章：AutoGen 核心概念

### 1.1 什么是 AutoGen？

AutoGen 是微软开源的**多 Agent 对话框架**。与 MetaGPT 的"角色接力"模式不同，AutoGen 的 Agent 之间是**双向对话**的——Agent A 问问题，Agent B 回答，A 再追问，像真人聊天。

### 1.2 本项目使用的五个核心概念

| 概念 | 项目中的对应代码 | 一句话 |
|------|-----------------|--------|
| **Model**（模型） | `agents.py` 中的 `_model_client()` | Agent 的脑子，接 DeepSeek、GPT-4o 等 |
| **Message**（消息） | Agent 之间自动传递，代码中几乎不直接操作 | 说的话 |
| **Agent**（智能体） | `agents.py` 中的 5 个工厂函数 | 一个 AI 角色，有名字、个性、工具 |
| **Team**（团队） | `team.py` 中的 `SelectorGroupChat` | 会议室，让 Agent 们轮流说话 |
| **Termination**（终止条件） | `team.py` 中的 `TextMentionTermination("FINAL_ACCEPT")` | 会议结束铃 |

### 1.3 和 MetaGPT 的关键区别

| 维度 | MetaGPT（ims-metagpt） | AutoGen（ims-autogen） |
|------|----------------------|----------------------|
| 通信 | 单向 `_watch` 订阅 | **双向对话**，互发消息 |
| 路由 | Environment 广播过滤 | **Team 调度**，决定谁发言 |
| 角色 | 继承 `Role` 类 | **`AssistantAgent`** + 提示词即可 |
| 人工 | 只能事后审文件 | **`UserProxyAgent`** 实时参与 |
| 本项目 CLI | 分步命令 `plan → design → code` | **一条命令** `ims-autogen run` |

---

## 第二章：第一个 Agent

### 2.1 安装

先装本项目，它会自动安装 AutoGen：

```bash
cd ims-autogen
pip install -e .
```

### 2.2 配置 API Key

本项目全部通过 `.env` 加载配置，绝不硬编码 API Key：

```bash
cp .env.example .env
# 编辑 .env，至少填 API_KEY
```

`.env` 的格式（由 `config.py` 中的 `AppConfig.from_env()` 统一读取，遵循多层覆盖）：

```ini
# 全局配置
API_KEY=sk-your-key
API_BASE=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat
```

> **多层覆盖优先级：** CLI 参数 > 环境变量 > `.env` 文件 > `config.py` 中 `ModelConfig` 的默认值。详见[第七章 7.3 节](#73-更换-llm-模型)。

### 2.3 手动创建和使用一个 Agent

这是本项目 `agents.py` 中 Agent 创建方式的简化版。以下代码可以独立运行，不需要启动整个项目：

```python
import asyncio
import os
from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

# 加载 .env（和项目 main.py 一样）
load_dotenv()

# 创建模型客户端 —— 对应 agents.py 的 _model_client() 函数
model_client = OpenAIChatCompletionClient(
    model=os.getenv("MODEL_NAME", "deepseek-chat"),
    api_key=os.getenv("API_KEY", ""),
    base_url=os.getenv("API_BASE", "https://api.deepseek.com/v1"),
)

# 创建 Agent —— 对应 agents.py 的 create_product_manager()
agent = AssistantAgent(
    name="assistant",
    model_client=model_client,
    system_message="你是一个助手。回答问题要简洁。",
)

async def main():
    # agent.run() 返回 TaskResult，包含所有消息
    result = await agent.run(task="用一句话解释什么是数据库索引")
    for msg in result.messages:
        print(f"[{msg.source}] {msg.content}")

    # 必须主动关闭（AutoGen 官方最佳实践）
    await model_client.close()

asyncio.run(main())
```

### 2.4 Message 的结构

当你运行上面的代码，`result.messages` 里会有两条消息：

```python
TextMessage(source='user', content='用一句话解释什么是数据库索引')
TextMessage(source='assistant', content='数据库索引是一种数据结构，用于加快数据查询速度。')
```

每条消息都有 `source`（谁说的）和 `content`（内容）。这是 AutoGen 中最常用的消息类型——`TextMessage`。

> 更多消息类型见[官方 Messages 文档](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/messages.html)

---

## 第三章：多个 Agent 对话

### 3.1 RoundRobinGroupChat — 轮流发言

让两个 Agent 轮流对话，这是理解 Team 机制的最简方式。

这个模式虽然本项目没有直接使用（我们用的是 SelectorGroupChat），但理解它能帮你明白 Team 的工作原理。

```python
import asyncio
import os
from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient

load_dotenv()

model_client = OpenAIChatCompletionClient(
    model=os.getenv("MODEL_NAME", "deepseek-chat"),
    api_key=os.getenv("API_KEY", ""),
    base_url=os.getenv("API_BASE", "https://api.deepseek.com/v1"),
)

# 创建两个 Agent（和本项目 agents.py 的工厂函数模式一致）
writer = AssistantAgent(
    name="writer",
    model_client=model_client,
    system_message="你是一个诗人，写短诗。",
)
critic = AssistantAgent(
    name="critic",
    model_client=model_client,
    system_message="你是一个评论家。满意就说 APPROVE。",
)

# 终止条件（和项目 team.py 中 build_team() 一样的用法）
termination = TextMentionTermination("APPROVE")

# 组装团队
team = RoundRobinGroupChat(
    [writer, critic],
    termination_condition=termination,
)

async def main():
    # 用 Console 流式输出（和项目 main.py 中 _run_team() 一样的用法）
    await Console(team.run_stream(task="写一首关于夏天的诗"))
    await model_client.close()

asyncio.run(main())
```

**执行流程：**
```
user → writer(写诗) → critic(评论) → writer(修改) → critic(APPROVE) → 结束
```

### 3.2 终止条件详解

`TextMentionTermination` 是项目 `team.py` 中 `build_team()` 实际使用的终止条件。它的行为是：**任意 Agent 的发言内容包含指定文字时，结束对话**。

```python
from autogen_agentchat.conditions import TextMentionTermination

# 当任何 Agent 说出 "FINAL_ACCEPT" 时结束（项目实际使用的）
termination = TextMentionTermination("FINAL_ACCEPT")
```

> 更多终止条件见[官方 Termination 文档](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/termination.html)

---

## 第四章：人工在环

### 4.1 UserProxyAgent

本项目实现了"产品经理可以向真人用户提问"的功能，靠的就是 `UserProxyAgent`。

对应项目代码 `agents.py` 中的 `create_user_proxy()` 函数：

```python
from autogen_agentchat.agents import UserProxyAgent

user_proxy = UserProxyAgent(
    name="human_user",
    description="真人用户 — 回答产品经理的提问",  # 帮助选择器决定何时选它
    input_func=input,   # input_func=input 表示从终端读入
)
```

### 4.2 运行效果

当 Team 的选择器决定让 `human_user` 发言时，终端会停下来等待你输入：

```
---------- architect ----------
PRD 中数据库类型没有明确，请问用 MySQL 还是 PostgreSQL？
---------- human_user ----------
> （终端在这里等待，你打字后回车）
用 PostgreSQL，因为需要处理复杂库存查询
---------- architect ----------
好的，我按 PostgreSQL 来设计。
```

> 更详细的人工在环模式见[官方 Human-in-the-Loop 文档](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/human-in-the-loop.html)

---

## 第五章：SelectorGroupChat — 本项目使用的方式

### 5.1 为什么不用 RoundRobin？

如果团队有 5 个人，轮流发言每轮需要 5 次，而且流程是死的。但软件开发团队的对话流向是**不确定的**：

- 开发遇到问题时应该问架构师，而不是等轮到测试
- 测试发现 bug 应该立即通知开发，而不是等下一轮

**SelectorGroupChat** 用一个 LLM 模型做"选择器"，阅读当前对话历史，动态决定下一个谁发言。

### 5.2 项目中的实际代码

对应 `team.py` 中的 `build_team()` 函数和 `SELECTOR_PROMPT` 常量：

```python
from autogen_agentchat.teams import SelectorGroupChat

# 选择器的指导语，告诉它什么时候选谁
SELECTOR_PROMPT = """根据对话历史选择下一个发言者：
- product_manager: 产品经理，先和用户沟通需求，最后做验收
- architect: 架构师，设计架构，回答技术问题
- developer: 开发，编码实现，修复 bug
- qa: 测试，写测试、报告 bug
- human_user: 真人用户，回答产品经理的提问
只返回名字。"""

team = SelectorGroupChat(
    participants=[pm, architect, dev, qa, user],   # 5 个 Agent
    model_client=_selector_model_client(),          # 选择器用的模型
    termination_condition=termination,              # FINAL_ACCEPT
    selector_prompt=SELECTOR_PROMPT,                # 上面那段话
    max_turns=100,                                  # 安全上限
)
```

### 5.3 选择器的工作方式

```
当前对话：
[user] 生成一个进销存系统
[product_manager] 主要用在什么场景？
                           ↓
   选择器模型（另一个 LLM）阅读以上对话
                           ↓
   判断：PM 刚提问，应该等人回答 → 选 human_user
                           ↓
[human_user] 我们是一家便利店...
```

> 更详细见[官方 Selector Group Chat 文档](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/selector-group-chat.html)

---

## 第六章：ims-autogen 项目代码逐模块解读

### 6.1 入口：main.py

`main.py` 是整个项目的 CLI 入口，使用 [typer](https://typer.tiangolo.com/) 框架。核心是 `cmd_run()` 函数：

```python
@app.command("run", help="启动多 Agent 对话...")
def cmd_run(
    idea: str = typer.Argument(..., help="需求描述"),
    workspace: str = typer.Option("./ims-output", "--workspace", "-w"),
    scope: str = typer.Option("MVP", "--scope", "-s"),
):
```

执行流程：
1. 创建工作区目录，设置环境变量 `IMS_WORKSPACE`
2. 调用 `build_team(scope=scope)` 组装团队，解包返回 `(team, clients)`
3. `asyncio.run(_run_team(team, idea, clients))` 启动对话
4. `_run_team()` 内部调用 `Console(team.run_stream(task=task), output_stats=True)` 流式输出
5. **finally 块关闭所有 model_client**，确保连接和线程资源得到释放

此外还有两个辅助命令：
- `cmd_list_modes()` — 打印命令速查表 + 配置说明
- `cmd_init_config()` — 将 `.env.example` 复制到当前目录

### 6.2 配置：config.py

`config.py` 是统一配置管理模块，实现了**四层覆盖**：

```
CLI 参数（运行时传入）  ← 最高优先级
    ↓ 覆盖
环境变量（os.environ）
    ↓ 覆盖
.env 文件（load_dotenv 加载）
    ↓ 覆盖
代码默认值（ModelConfig 字段默认值）  ← 最低优先级
```

核心类：

```python
@dataclass
class ModelConfig:
    api_key: str = ""
    api_base: str = "https://api.deepseek.com/v1"
    model_name: str = "deepseek-chat"

    def to_client_kwargs(self) -> dict:
        """转为 OpenAIChatCompletionClient 构造参数"""

@dataclass
class AppConfig:
    model: ModelConfig          # 全局模型
    selector_model: ModelConfig  # 选择器模型
    workspace: str              # 工作区路径
    max_turns: int              # 最大发言轮数

    @classmethod
    def from_env(cls) -> "AppConfig": ...
    def role_model(self, role: str) -> ModelConfig: ...
```

- `get_config()` — 全局单例，懒加载（首次调用时从环境变量加载）
- `reload_config()` — 修改 `.env` 后重新加载
- `AppConfig.role_model("PM")` — 分角色模型配置，自动处理 `{ROLE}_MODEL_NAME → MODEL_NAME → 默认值` 的回退链

### 6.3 Agent 工厂：agents.py

`agents.py` 提供 5 个工厂函数，每个函数做三件事（以 `create_product_manager` 为例）：

```python
def create_product_manager(scope: str = "MVP") -> AssistantAgent:
    # 1. 从 prompts/ 目录动态加载提示词（不是硬编码）
    prompt = load_prompt("product_manager", scope=scope)
    return AssistantAgent(
        name="product_manager",            # 团队内唯一标识
        description="产品经理 Alice...",     # 帮助选择器理解角色
        model_client=_model_client("PM"),  # 支持分角色配置模型
        system_message=prompt,             # 提示词从 .md 加载
        tools=[tools.save_file, ...],      # Agent 可用的工具
        reflect_on_tool_use=True,          # 用工具后自动总结
        model_client_stream=True,          # 启用流式输出
    )
```

`_model_client()` 函数支持分角色模型配置：

```python
def _model_client(role_prefix: str = "") -> OpenAIChatCompletionClient:
    # 优先读 PM_MODEL_NAME → 回退到 MODEL_NAME
    model = os.getenv(f"{role_prefix}_MODEL_NAME") or os.getenv("MODEL_NAME")
    # API_KEY 和 API_BASE 同理
```

**5 个角色的工具分配：**

| 角色 | 工厂函数 | 可用工具 |
|------|---------|---------|
| 产品经理 Alice | `create_product_manager()` | `save_file`, `read_file`, `list_files` |
| 架构师 Bob | `create_architect()` | `save_file`, `read_file`, `list_files` |
| 全栈工程师 Eve | `create_developer()` | `save_file`, `read_file`, `list_files`, `run_command` |
| 测试 Charlie | `create_qa()` | `save_file`, `read_file`, `list_files`, `run_command` |
| 真人用户 | `create_user_proxy()` | 无（通过 `input_func=input` 从终端读入） |

### 6.4 团队组装：team.py

`build_team()` 函数组装整个团队，返回 `(team, clients)` 元组：

```python
def build_team(scope: str = "MVP") -> tuple[SelectorGroupChat, list]:
    cfg = get_config()
    # 创建全部 5 个 Agent
    pm = create_product_manager(scope)
    architect = create_architect(scope)
    dev = create_developer(scope)
    qa = create_qa(scope)
    user = create_user_proxy()

    participants = [pm, architect, dev, qa, user]
    # 收集所有 model_client 用于清理
    _clients = [a.model_client for a in participants if hasattr(a, "model_client")]

    termination = TextMentionTermination("FINAL_ACCEPT")
    selector_client = _selector_model_client()
    _clients.append(selector_client)

    team = SelectorGroupChat(
        participants=participants,
        model_client=selector_client,
        termination_condition=termination,
        selector_prompt=SELECTOR_PROMPT,
        max_turns=cfg.max_turns,  # 从配置读取，可环境变量 MAX_TURNS 覆盖
    )
    return team, _clients
```

选择器有独立的模型配置函数 `_selector_model_client()`，支持通过 `SELECTOR_MODEL_NAME`、`SELECTOR_API_KEY`、`SELECTOR_API_BASE` 环境变量单独配置，未设置时回退到全局配置。

### 6.5 提示词加载器：prompt_loader.py

`load()` 函数做 4 件事：

```python
def load(name: str, lang: str = "", **variables) -> str:
    path = _resolve_path(name, lang)           # 1. 定位文件（支持多语言目录）
    text = _read_file(path)                     # 2. 读取（带 LRU 缓存）
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", str(value))  # 3. 变量注入
    unbound = _PLACEHOLDER_RE.findall(text)     # 4. 校验：漏填占位符会报错
    if unbound:
        raise PromptValidationError(...)
    return text
```

关键设计：
- **双异常类型**：文件找不到抛 `PromptNotFoundError`，占位符未填充抛 `PromptValidationError`——不同的错误原因对应不同的异常
- **LRU 缓存**：`_read_file()` 用 `@lru_cache` 装饰，同一文件不重复读磁盘，修改后调用 `clear_cache()` 刷新
- **多语言**：`_resolve_path()` 先查 `prompts/{lang}/{name}.md`，找不到回退到 `prompts/{name}.md`
- **辅助函数**：`available(lang)` 列出可用提示词名称，`clear_cache()` 清除缓存

### 6.6 工具：tools.py

4 个工具函数，都是 async，操作限制在工作区目录内：

```python
save_file(path, content)   # 保存代码/文档到工作区，自动创建父目录
read_file(path)            # 读取已有文件，不存在返回错误信息
list_files(pattern)        # 列出工作区文件，支持 glob 通配符
run_command(command)       # 执行 shell 命令（用于运行测试），带超时保护
```

工作区路径由环境变量 `IMS_WORKSPACE` 控制（`main.py` 中 `cmd_run()` 设置），确保 Agent 的文件操作不会超出项目范围。

### 6.7 数据流全景

```
你的终端输入: ims-autogen run "生成进销存" -w ./output
          │
    main.py: build_team("MVP") → (team, clients)
          │
    config.py: get_config() → AppConfig（多层覆盖）
          │
    team.py: SelectorGroupChat(5个Agent)
          │
    main.py: asyncio.run(team.run_stream(task="生成进销存"))
          │
          ▼
    ┌── SelectorGroupChat 内部循环 ──────────────────────┐
    │  ① 选择器 LLM 读对话 → 决定下一个谁发言              │
    │  ② 被选中的 Agent 调用 LLM + 工具 → 回复            │
    │  ③ 检查是否有人说了 FINAL_ACCEPT                    │
    │  ④ 没结束 → 回到 ①                                 │
    └────────────────────────────────────────────────────┘
          │
          ▼
    _run_team() finally: 关闭所有 model_client
          │
          结束，代码保存在 ./output/
```

---

## 第七章：自定义扩展

### 7.1 修改现有角色行为

无需改 Python 代码，编辑 `prompts/product_manager.md` 即可。

例如想让 Alice 在验收时更严格，在文件末尾加一段：

```markdown
## 验收标准
- 所有 API 必须有输入校验
- 测试覆盖率不低于 80%
- 代码中不能有硬编码的数据库连接字符串
```

保存后重新运行 `ims-autogen run`，新规则自动生效。

> 为什么不需要改代码？因为 `agents.py` 中 `create_product_manager()` 通过 `load_prompt("product_manager", scope=scope)` 动态加载文件内容。

### 7.2 新增一个角色：运维工程师

**第一步**：创建提示词文件 `prompts/devops.md`

```markdown
# 角色系统提示词：运维工程师 (David)

你是 David，负责部署和运维。
- 阅读架构设计，编写 Docker 部署方案
- 使用 save_file 保存 deploy/docker-compose.yml
- 回答团队关于部署环境的问题

当前范围：{{scope}}
```

**第二步**：在 `agents.py` 中添加工厂函数（参照 `create_product_manager()` 的模式）

```python
def create_devops(scope: str = "MVP") -> AssistantAgent:
    prompt = load_prompt("devops", scope=scope)
    return AssistantAgent(
        name="devops",
        description="运维工程师 David — 负责部署和环境配置",
        model_client=_model_client("DEVOPS"),
        system_message=prompt,
        tools=[tools.save_file, tools.read_file, tools.run_command],
        reflect_on_tool_use=True,
        model_client_stream=True,
    )
```

**第三步**：在 `team.py` 中 `build_team()` 的 `participants` 列表中加入 `devops`，并在 `SELECTOR_PROMPT` 中添加相应说明：

```python
participants=[pm, architect, dev, qa, devops, user],
```

**第四步**：在 `.env` 中为运维配不同模型（可选）：

```ini
DEVOPS_MODEL_NAME=gpt-4o-mini
```

### 7.3 更换 LLM 模型

编辑 `.env`，支持分角色配置。配置由 `config.py` 统一管理，遵循四层覆盖：

```ini
# 全局默认（所有角色共用）
API_KEY=sk-deepseek-key
API_BASE=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat

# 分角色覆盖（可选，未设置回退到全局）
PM_API_KEY=sk-openai-key
PM_API_BASE=https://api.openai.com/v1
PM_MODEL_NAME=gpt-4o

# 选择器用又快又便宜的（可选）
SELECTOR_MODEL_NAME=gpt-4o-mini

# 运行参数（可选）
MAX_TURNS=200
```

**多层覆盖优先级：** CLI 参数 > 环境变量 > `.env` 文件 > `config.py` 中 `ModelConfig` 默认值。

回退逻辑在 `config.py` 的 `AppConfig.role_model(role)` 中统一处理：先读 `{ROLE}_MODEL_NAME`，未配置则回退到全局 `MODEL_NAME`。

### 7.4 添加多语言支持

在 `prompts/en/` 下创建英文版提示词文件：

```
prompts/en/
├── product_manager.md
├── architect.md
├── developer.md
└── qa.md
```

然后调用 `load_prompt("product_manager", lang="en", scope="Full")`，`prompt_loader.py` 的 `_resolve_path()` 会优先查找 `prompts/en/product_manager.md`。

---

## 第八章：实战 — 从零构建一个客服团队

现在用与本项目**完全相同的架构模式**，从零搭建一个客户支持系统。这段代码可以作为独立项目运行。

### 8.1 目录结构

```
support-bot/
├── .env                      # API Key 配置
├── main.py                   # 入口
└── prompts/                  # 提示词（与代码解耦）
    ├── front_desk.md
    └── tech_support.md
```

### 8.2 提示词文件

`prompts/front_desk.md`：

```markdown
你是一个友好的前台客服。
- 问候客户，了解问题
- 如果是简单问题（密码重置、订单查询），直接回答
- 如果是技术问题（报错、系统故障），说 TRANSFER_TO_TECH
- 问题解决后说 CASE_CLOSED
```

`prompts/tech_support.md`：

```markdown
你是一个技术支持工程师。
- 解决技术问题
- 每一步让客户确认后再继续
- 问题解决后说 CASE_CLOSED
- 超出能力范围时说 TRANSFER_TO_HUMAN
```

### 8.3 main.py（完整可运行）

```python
"""
支持工单系统 — 多 Agent 客服团队。
与 ims-autogen 同样的架构模式：prompt_loader + agents + team。
"""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient


# ── 1. 提示词加载器（复用项目的设计模式）────────────
def load_prompt(name: str) -> str:
    path = Path(__file__).parent / "prompts" / f"{name}.md"
    return path.read_text(encoding="utf-8")


# ── 2. 模型客户端（和 agents.py 中 _model_client() 一样）─
def model_client():
    return OpenAIChatCompletionClient(
        model=os.getenv("MODEL_NAME", "deepseek-chat"),
        api_key=os.getenv("API_KEY", ""),
        base_url=os.getenv("API_BASE", "https://api.deepseek.com/v1"),
    )


# ── 3. 创建 Agent ─────────────────────────────────
def create_agents():
    mc = model_client()
    return [
        AssistantAgent(
            name="front_desk",
            description="前台客服：接待客户，处理简单问题",
            model_client=mc,
            system_message=load_prompt("front_desk"),
        ),
        AssistantAgent(
            name="tech_support",
            description="技术支持：解决技术问题",
            model_client=mc,
            system_message=load_prompt("tech_support"),
        ),
        UserProxyAgent(
            name="human_agent",
            description="人工客服：处理复杂投诉",
            input_func=input,
        ),
    ]


# ── 4. 主流程 ────────────────────────────────────
async def main():
    load_dotenv()
    agents = create_agents()

    team = SelectorGroupChat(
        participants=agents,
        model_client=model_client(),
        termination_condition=TextMentionTermination("CASE_CLOSED"),
        selector_prompt=(
            "根据对话历史选择下一个发言者：\n"
            "- front_desk: 前台客服，处理简单问题\n"
            "- tech_support: 技术支持\n"
            "- human_agent: 人工客服\n"
            "只返回名字。"
        ),
        max_turns=50,
    )

    await Console(
        team.run_stream(task="我的系统登录时报错 Error 500")
    )

    # 清理资源
    for agent in agents:
        if hasattr(agent, "model_client") and agent.model_client:
            await agent.model_client.close()

asyncio.run(main())
```

### 8.4 运行

```bash
cd support-bot
pip install -U "autogen-agentchat" "autogen-ext[openai]" "python-dotenv"
# 创建 .env：API_KEY=xxx
python main.py
```

### 8.5 和 ims-autogen 的架构对比

```
support-bot/                    ims-autogen/
  main.py                          main.py + team.py + agents.py
  prompts/                          prompts/ + prompt_loader.py
  3 个 Agent                        5 个 Agent
  SelectorGroupChat                 SelectorGroupChat
  CASE_CLOSED                        FINAL_ACCEPT
```

模式完全一致。你学会了这个模式，就能看懂并修改 `ims-autogen` 的全部代码。

---

## 总结

| 章节 | 核心内容 | 对应项目代码 |
|------|---------|-------------|
| 第一章 | AutoGen 五大概念 | 全局理解 |
| 第二章 | 单 Agent 创建 + Message | `agents.py` + `prompt_loader.py` |
| 第三章 | RoundRobinGroupChat + 终止条件 | `team.py` 中的 `TextMentionTermination` |
| 第四章 | UserProxyAgent 人工在环 | `agents.py` 中的 `create_user_proxy()` |
| 第五章 | SelectorGroupChat 选择器机制 | `team.py` 中的 `build_team()` |
| 第六章 | 项目代码逐模块解读（含配置管理） | 全部源文件（`main.py` → `config.py` → `agents.py` → ...） |
| 第七章 | 改提示词、加角色、换模型、多语言 | 扩展实战 |
| 第八章 | 从零搭建一个相同架构的客服系统 | 独立项目 |

**下一步行动：**
```bash
# 1. 跑一遍完整流程
cd ims-autogen
ims-autogen run "生成进销存系统" -w ./my-first-run

# 2. 改一个提示词试试
echo -e "\n## 额外要求\n- 所有页面都要有深色模式" >> prompts/product_manager.md

# 3. 再次运行，看行为变化
ims-autogen run "生成进销存系统" -w ./my-second-run
```
