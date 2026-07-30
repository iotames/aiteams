# aiteams — AI Agents 团队工场

> 面向生产环境的工程化多 Agent 团队集合。每个子目录都是一个独立的 AI 团队，服务于进销存管理系统（IMS）自动生成这一具体业务场景，分别使用不同的 Agent 编排框架实现。

## 目录说明

| 目录 | 技术 | 场景 | 特色 |
|------|------|------|------|
| [ims-autogen](./ims-autogen/) | AutoGen v0.4+ | 进销存管理系统（对话式） | 🤝 双向对话、人工在环、实时问答 |
| [ims-metagpt](./ims-metagpt/) | MetaGPT | 进销存管理系统（完整生命周期） | 分步接力：plan → design → code → iterate → refactor |
| [ims-crew](./ims-crew/) | CrewAI | 进销存管理系统（串行流水线） | 角色流水线、快速原型 |
| [oh-my-openagent](./oh-my-openagent/) | — | Agent 角色 Prompt 参考库 | 11 个预定义角色的原始/翻译 system prompt |
| [skills](./skills/) | — | 给AI智能体使用的技能包 | 项目复用的自动化工具包 |

## 设计原则

- **工程化优先** — 每个团队都具备完整的 CLI、配置管理、CI 就绪结构
- **解耦提示词** — Agent 角色和任务描述以 `.md` 文件管理，与代码完全分离
- **可复用** — 团队配置和提示词可在项目间移植
- **技术栈无关** — 不绑定单一框架，按场景选用最合适的 Agent 编排方案


## 系统要求

- **Python 3.10+**（建议 3.11+）
- 各子项目的依赖见各自 `pyproject.toml`，推荐在子目录内创建虚拟环境安装

## 快速开始

每个团队独立运行，进入对应目录按指引操作：

```bash
# 1. AutoGen 版本 —— 双向对话 + 人工在环（推荐尝鲜）
cd ims-autogen
pip install -e .
# 配置 API Key（编辑 .env 或复制 .env.example）
ims-autogen run "为一个超市开发进销存管理系统"

# 2. MetaGPT 版本 —— 完整软件生命周期
cd ims-metagpt
pip install -e .
# 配置 LLM（编辑 config/ 下的配置文件）
ims-metagpt plan "为一个超市开发进销存管理系统"
ims-metagpt design      # 接上一步，继续设计
ims-metagpt code        # 生成代码

# 3. CrewAI 版本 —— 串行流水线
cd ims-crew
pip install -e .
ims-crew --profile backend-only
```

> 💡 每个团队目录内都包含详细的 README 和教程（TUTORIAL.md），新手建议从 ims-autogen 开始。

## 三个 IMS 团队的区别

| 维度 | ims-autogen (AutoGen) | ims-metagpt (MetaGPT) | ims-crew (CrewAI) |
|------|----------------------|----------------------|-------------------|
| 对话方式 | **🤝 双向对话** | 单向接力 | 串行流水线 |
| 发言调度 | SelectorGroupChat（模型决策） | Environment 广播 | Sequential Process |
| 人工参与 | **✅** 终端内实时问答 | ❌ 事后审文件 | ❌ |
| 开发问架构师 | ✅ | ❌ | ❌ |
| 测试→修 bug 循环 | ✅ | ✅（iterate 子命令） | ❌ |
| 产品验收 | ✅ | ❌ | ❌ |
| CLI 方式 | 一条命令 `run` | 分步 `plan → design → code → iterate → refactor` | 一条命令 |
| 学习曲线 | 中等（附八章教程） | 中等（附六章教程） | 较低 |
| 适用场景 | 需求不明确、需频繁沟通 | 需求明确、完整交付 | 快速原型 |

## 其他目录

- **[oh-my-openagent](./oh-my-openagent/)** — 提取自上游开源项目的 Agent 角色 System Prompt 参考库，包含 11 个预定义角色的原始英文版和中文翻译版，可作为自定义 Agent 提示词的参考起点。
- **[skills/](./skills/)** — 技能扩展包，包含 Chrome DevTools Protocol 自动化（chromedp）和技能创建与评测框架（skill-creator），可在本仓库的 AI 协作开发中复用。
