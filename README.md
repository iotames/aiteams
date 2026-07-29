# aiteams — AI Agents 团队工场

> 面向生产环境的工程化多 Agent 团队集合。每个子目录都是一个独立的 AI 团队，服务于具体的业务场景。

## 团队目录

| 团队 | 技术栈 | 场景 |
|------|--------|------|
| [ims-crew](./ims-crew/) | CrewAI | 进销存管理系统自动生成（MVP + 迭代） |
| [ims-metagpt](./ims-metagpt/) | MetaGPT | 进销存管理系统自动生成（完整软件生命周期：MVP → 迭代 → 重构） |

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
├── ims-crew/              # 进销存系统开发团队（CrewAI）
│   ├── prompts/           # 提示词文件（.md）
│   ├── src/               # 源代码
│   └── README.md          # 团队使用说明
├── ims-metagpt/           # 进销存系统开发团队（MetaGPT）
│   ├── prompts/           # 提示词文件（.md，可单独编辑）
│   ├── src/               # 源代码
│   ├── config/            # LLM 配置（多厂商示例）
│   ├── README.md          # 团队使用说明
│   └── TUTORIAL.md        # 学习教程（新手必读）
└── oh-my-openagent/       # 通用 Agent 角色定义文件集合
```

## 快速开始

每个团队独立运行，进入对应目录查看各自的 README：

```bash
# CrewAI 版本
cd ims-crew
cat README.md

# MetaGPT 版本（推荐新手从此开始）
cd ims-metagpt
cat README.md
cat TUTORIAL.md   # 六章学习教程，从零开始
```

## 两个 IMS 团队的区别

| 维度 | ims-crew (CrewAI) | ims-metagpt (MetaGPT) |
|------|-------------------|----------------------|
| 底层框架 | CrewAI | MetaGPT |
| 软件生命周期 | 单次生成 | MVP → 迭代 → 重构（完整周期） |
| 人工审核环节 | 无 | plan→design→code 三段式审核 |
| 提示词管理 | `.md` 文件 | `.md` 文件 + 动态加载器 |
| 学习曲线 | 较低 | 中等（附完整教程） |
