# aiteams — AI Agents 团队工场

> 面向生产环境的工程化多 Agent 团队集合。每个子目录都是一个独立的 AI 团队，服务于具体的业务场景。

## 团队目录

| 团队 | 技术栈 | 场景 | 特色 |
|------|--------|------|------|
| [ims-autogen](./ims-autogen/) | **AutoGen v0.4+** | 进销存管理系统（对话式） | 🤝 双向对话、人工在环、实时问答 |
| [ims-metagpt](./ims-metagpt/) | MetaGPT | 进销存管理系统（完整生命周期） | MVP → 迭代 → 重构三段式 |
| [ims-crew](./ims-crew/) | CrewAI | 进销存管理系统（串行流水线） | 角色流水线、MVP + 迭代 |
| [oh-my-openagent](./oh-my-openagent/) | — | Agent 角色 Prompt 参考库 | 11 个预定义角色的原始 system prompt |

## 设计原则

- **工程化优先** — 每个团队都具备完整的 CLI、配置、CI 就绪结构
- **解耦提示词** — Agent 角色和任务描述以 `.md` 文件管理，与代码完全分离
- **可复用** — 团队配置和提示词可在项目间移植
- **技术栈无关** — 不绑定单一框架，按场景选用最合适的 Agent 编排方案

## 项目结构

```
aiteams/
├── README.md              # 本文件
├── .gitignore             # 全局忽略规则
├── ims-autogen/           # 进销存系统开发团队（AutoGen）
│   ├── src/ims_autogen/   # 源代码
│   │   ├── main.py        # CLI 入口（typer）
│   │   ├── config.py      # 统一配置（多层覆盖）
│   │   ├── agents.py      # 5 角色 Agent 工厂
│   │   ├── team.py        # SelectorGroupChat 组装
│   │   ├── tools.py       # 工具函数
│   │   ├── prompt_loader.py  # 提示词动态加载
│   │   └── prompts/       # 角色提示词（.md）
│   ├── .env.example       # 环境配置模板
│   ├── README.md          # 使用说明
│   └── TUTORIAL.md        # 八章学习教程（新手必读）
├── ims-metagpt/           # 进销存系统开发团队（MetaGPT）
│   ├── prompts/           # 提示词文件（.md，可单独编辑）
│   ├── src/               # 源代码
│   ├── config/            # LLM 配置（多厂商示例）
│   ├── README.md          # 团队使用说明
│   └── TUTORIAL.md        # 学习教程
├── ims-crew/              # 进销存系统开发团队（CrewAI）
│   ├── prompts/           # 提示词文件（.md）
│   ├── src/               # 源代码
│   └── README.md          # 团队使用说明
└── oh-my-openagent/       # Agent 角色 Prompt 参考库
    └── README.md          # 提取说明
```

## 快速开始

每个团队独立运行，进入对应目录查看各自的 README：

```bash
# AutoGen 版本（双向对话 + 人工在环，推荐尝鲜）
cd ims-autogen
cat README.md
cat TUTORIAL.md   # 八章教程，从零开始

# MetaGPT 版本（完整软件生命周期）
cd ims-metagpt
cat README.md
cat TUTORIAL.md   # 六章教程

# CrewAI 版本（串行流水线）
cd ims-crew
cat README.md
```

## 三个 IMS 团队的区别

| 维度 | ims-autogen (AutoGen) | ims-metagpt (MetaGPT) | ims-crew (CrewAI) |
|------|----------------------|----------------------|-------------------|
| 对话方式 | **🤝 双向对话** | 单向接力 | 串行流水线 |
| 发言调度 | **SelectorGroupChat（模型决策）** | Environment 广播 | Sequential Process |
| 人工参与 | **✅ 终端内实时问答** | ❌ 事后审文件 | ❌ |
| 开发问架构师 | ✅ | ❌ | ❌ |
| 测试→修 bug 循环 | ✅ | ❌ | ❌ |
| 产品验收 | ✅ | ❌ | ❌ |
| CLI 方式 | 一条命令 `run` | 分步 `plan → design → code` | 一条命令 |
| 学习曲线 | 中等（附八章教程） | 中等（附六章教程） | 较低 |
| 适用场景 | 需求不明确、需频繁沟通 | 需求明确、完整交付 | 快速原型 |
