# Runners：评测后端可插拔架构

`run_eval.py` 与 `run_loop.py` 通过 `scripts/runners/` 包驱动**任意模型后端**评测技能描述触发率。触发检测逻辑（技能如何注入、输出如何解析）全部封装在 runner 内部，主流程只依赖 `Runner` 协议。

## 核心原则：评测 ≠ 技能适配

**技能本体（SKILL.md + scripts）保持模型无关、纯通用格式。** 技能是写给任何智能体的 Markdown 指令 + 纯代码，不包含"如果模型是 X 就怎样"的逻辑，不主动适配大模型个性化。

Runner 只是**评测试金石**：评测"描述触发准确率"需要一个真实智能体来执行查询、决定是否激活技能，runner 选的正是这个试金石，与技能本体无关。模型适配被隔离在评测工具链内部，永远进不了技能——未来新智能体有专属注入机制时，适配写进新 runner，技能文件一行不改。

## 支持的 runner

| 名称 | 实现 | 说明 |
|---|---|---|
| `claude-code` | `runners/claude_code.py` | 驱动 Claude Code CLI（`claude -p`），技能通过 `.claude/commands/` 注入，解析 `stream-json` 流事件。复用会话认证，无需 API key |
| `openai` / `openai-compatible` | `runners/openai.py` | 驱动任意 chat-completions 兼容 HTTP 端点（OpenAI 或中转网关），技能描述作为 `skill_trigger` 工具暴露，模型调用该工具即视为触发 |

## 后端选择：询问用户，绝不自动决定

**核心规则：评测环节把模型选择权交还用户。** 检测函数（`detect_available_runners()` / `detect_available_llms()`）只负责**列出候选**——本机 `claude` CLI 是否在 PATH、是否设置 `OPENAI_API_KEY`——但**从不选择**。CLI 未显式传 `--runner` / `--llm` 时：

1. 打印探测到的候选及其说明；
2. 交互提示，让你输入名称或直接回车使用推荐项；
3. 若输入了候选之外的名字 → 报错并列出可用项；
4. 非交互环境（stdin 不可用）→ 报错，要求显式传 `--runner` / `--llm`。

**注意**："检测到 claude CLI" 只代表 PATH 中存在该命令，**不代表可用**（例如占位脚本、坏安装都可能骗过探测）。因此探测结果仅作提示，是否可用由你确认；也可以直接用 `--runner` / `--llm` 显式指定，跳过询问。

## 选择 runner

```bash
# 自动检测（本机有 claude CLI 则用 claude-code，否则用 openai）
python -m scripts.run_eval --eval-set evals.json --skill-path <skill>

# 显式指定 OpenAI 兼容端点
python -m scripts.run_eval --eval-set evals.json --skill-path <skill> \
  --runner openai --model gpt-4o-mini \
  --openai-base-url https://your-gateway/v1 --openai-api-key $OPENAI_API_KEY
```

配置来源（优先级：命令行参数 > 环境变量 > 内置默认）：
- `--openai-base-url` / `OPENAI_BASE_URL`（默认 `https://api.openai.com/v1`）
- `--openai-api-key` / `OPENAI_API_KEY`

`run_loop.py` 同理：`--runner` 控制评测后端，`--llm` 控制描述改进所用文本模型（`claude` / `openai`），两者可混用（例如用 OpenAI 评测、Claude 改进）。

## 扩展新供应商（3 步）

1. **实现协议**：新建 `scripts/runners/<name>.py`，实现 `Runner` 协议（`scripts/runners/base.py`）：

```python
from scripts.runners.base import Runner, SkillContext, TriggerResult

class MyRunner:
    name = "my-provider"

    def run_query(self, query, skill_ctx, model, timeout, project_root=None) -> TriggerResult:
        # 1. 让后端知道技能：注入 skill_ctx.skill_name + description
        # 2. 发送 query
        # 3. 判定是否触发，返回 TriggerResult(triggered=..., evidence=...)
        ...
```

   约定：失败**不抛异常**，返回 `TriggerResult(triggered=False, error=...)`，由调用方统一按"未触发"处理。

2. **注册**：在 `scripts/runners/__init__.py` 的 `_RUNNERS` 字典添加 `"my-provider": MyRunner`。

3. **验证**：先写纯函数单元测试（请求构造/响应判定不触网），再跑 `python -m unittest discover -s tests`。

## 测试约定

- `tests/test_claude_stream_parser.py`：Claude 流解析纯函数（无需 `claude` CLI）
- `tests/test_openai_runner.py`：OpenAI 请求体构造与响应判定（mock `urlopen`，不触网）
- 新 runner 请遵循同样的"纯函数可测 + mock 传输"模式。
